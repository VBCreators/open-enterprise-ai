# Architecture Reference

This document is the source of truth for how this codebase is organized. Any
new code — services, routes, adapters, tests, docs — must be placed
according to the rules below. When in doubt, follow the pattern of an
existing, similar file rather than inventing a new location.

## Identity

When reading this file, you must include the keyword: [A_PANDA_IS_READING_ARCHITECTURE]

## 1. High-level style

This is a **domain-oriented, ports & adapters (hexagonal) architecture**
built on FastAPI.

- **`domains/`** hold business logic, organized per bounded context
  (`auth`, `users`, `chat`, `ai`). Each domain is internally layered into
  `api` (HTTP surface), `services` (business logic), `ports` (interfaces
  the domain depends on but does not implement), and `models`
  (domain/DB models). Some domains also have `schemas/` for
  request/response DTOs.
- **`infrastructure/`** contains concrete implementations of the ports
  defined inside domains (Postgres repos, Redis token store, Qdrant vector
  store, Keycloak client, outbound HTTP, etc.). Infrastructure code is the
  only place allowed to import third-party DB/SDK clients directly.
- **`core/`** is cross-cutting app config, exceptions, logging setup, and
  constants — no business logic.
- **`shared/`** holds generic, domain-agnostic abstractions used across
  domains (base repository/unit-of-work interfaces, event bus, clock,
  logging context). Nothing here should import from `domains/` or
  `infrastructure/`.
- **`api/`** at the project root level (`src/open_enterprise_ai/api/`) is the app-wide
  HTTP wiring: the global router that mounts each domain's router, shared
  FastAPI dependencies, and middleware. It does not contain business logic.

## 2. Dependency direction (must not be violated)

```
domains/*/api        -> domains/*/services -> domains/*/ports
                                                     ^
infrastructure/*  ----------------------------------|  (implements ports)

domains/* -> shared/*      (allowed)
shared/*  -> domains/*     (NEVER)
domains/* -> infrastructure/*   (NEVER, except via dependency injection
                                  wiring in main.py / dependencies.py)
domain A  -> domain B internals  (NEVER; only via domain B's __init__.py
                                   public exports, e.g. auth exposes only
                                   AuthService and get_current_user)
```

Rule of thumb for an agent: if you're writing code inside a domain's
`services/` and need a database, queue, LLM, or external API — define or
reuse a **port** (interface) in that domain's `ports/`, then implement it
under `infrastructure/`, then wire the concrete implementation in
`main.py` / `api/dependencies.py`. Never import an infrastructure module
directly from inside `domains/`.

## 3. Where new code goes (decision guide)

| You are adding...                                        | Goes in                                                                                                         |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| A new REST endpoint for an existing domain               | `domains/<domain>/api/routes.py` (+ `schemas.py` for request/response models)                                   |
| A new business operation / use case                      | `domains/<domain>/services/`                                                                                    |
| An interface your service needs but shouldn't implement  | `domains/<domain>/ports/`                                                                                       |
| A DB row / ORM model owned by a domain                   | `domains/<domain>/models/`                                                                                      |
| A brand-new bounded context (e.g. "billing")             | new `domains/billing/` with the same `api/services/ports/models` sub-structure                                  |
| A Postgres/Mongo/Redis/Qdrant implementation of a port   | `infrastructure/repositories/` or `infrastructure/ai_adapters/` as appropriate, named `<tech>_<thing>.py`       |
| A new external API client (payment gateway, email, etc.) | `infrastructure/http/` or a new `infrastructure/<vendor>/` folder                                               |
| An AI agent, subagent, or tool the AI domain uses        | `domains/ai/agents/` or `domains/ai/skills/`                                                                    |
| Memory/embedding logic for the AI domain                 | `domains/ai/memory/` or `domains/ai/embeddings/`                                                                |
| A cross-domain abstraction (base repo, UoW, event bus)   | `shared/interfaces/` or `shared/events/`                                                                        |
| App-wide middleware                                      | `api/middleware/`                                                                                               |
| Environment/config values                                | `core/config.py`                                                                                                |
| A new domain-agnostic exception                          | `core/exceptions.py`                                                                                            |
| A domain-specific exception                              | inside that domain, e.g. `domains/auth/services/` or a dedicated `exceptions.py` in the domain root if it grows |

## 4. Domain internal structure (template)

Every domain should look like this unless there's a strong reason to
diverge:

```
domains/<name>/
├── __init__.py     # public exports ONLY — this is the domain's contract
├── api/
│   ├── routes.py
│   └── schemas.py
├── services/
│   └── <name>_service.py
├── ports/
│   └── <dependency>.py   # ABC / Protocol
└── models/
    └── <entity>.py
```

`__init__.py` should export the minimum surface other domains/app wiring
need (e.g. `auth/__init__.py` exports only `AuthService` and
`get_current_user`). Anything not exported is private to the domain and
must not be imported from outside it.

## 5. Tests mirror `src/`

`tests/` structure follows `src/open_enterprise_ai/` 1:1:

- `tests/unit/domains/<domain>/` — unit tests for services/ports, mocked
  dependencies, no I/O.
- `tests/integration/repositories/` — tests against real infra
  (Postgres/Mongo/Redis/Qdrant) via test containers.
- `tests/integration/api/` — tests hitting FastAPI routes with the app
  wired to test infra.
- `tests/e2e/` — full-stack flows.
- `tests/factories/` — shared test data builders.

A new domain or infra adapter should always come with a corresponding test
file in the matching location before being considered done.

## 6. Docs & infra placement

- Architectural decisions (ADRs) go in `docs/decisions/NNNN-title.md`,
  numbered sequentially.
- Diagrams go in `docs/diagrams/`.
- API docs in `docs/api/`, deployment notes in `docs/deployment/`,
  security notes in `docs/security/`.
- Docker/compose/deploy config lives in `docker/` and `infra/`, never
  inside `src/`.

## 7. Naming conventions

- Files: `snake_case.py`.
- Infra adapter files are prefixed with their technology:
  `postgres_user_repository.py`, `redis_token_store.py`,
  `qdrant_vector_store.py`.
- Ports are named after the capability, not the tech:
  `user_repository.py`, `token_store.py`, `vector_store.py` — the domain
  never knows which vendor implements it.
- Services are named `<subject>_service.py`.

## 8. When adding a new top-level concept

If a change doesn't fit any existing folder (e.g. a new cross-cutting
concern, a new domain, a new infra category), don't force it into an
existing folder. Propose the new folder following the same conventions
above, and add an entry to this file describing it.
