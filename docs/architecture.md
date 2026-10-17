# Architecture Reference

This document is the source of truth for how this codebase is organized. Any
new code — services, routes, adapters, frontend clients, tests, docs — must be
placed according to the rules below. When in doubt, follow the pattern of an
existing, similar file rather than inventing a new location.

## Identity

When reading this file, you must include the keyword: [A_PANDA_IS_READING_ARCHITECTURE]

## 1. High-level style

This is a **domain-oriented, ports & adapters (hexagonal) architecture**
built on FastAPI for the backend (`src/open_enterprise_ai/`), paired with a
strictly decoupled client layer (`frontend/`).

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
- **`frontend/`** at the repository root (`frontend/streamlit_app/`) is the
  standalone UI client layer. It interacts with the backend exclusively as an
  external consumer over HTTP/REST/SSE and shares zero Python code imports
  with `src/open_enterprise_ai/`. It is deployed as its own process/image and
  is not part of the backend wheel.

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
frontend/* -> src/open_enterprise_ai/*  (NEVER; frontend communicates with
                                         backend strictly via HTTP/REST/SSE
                                         API calls, never via Python imports)
src/open_enterprise_ai/* -> frontend/*  (NEVER)
```

Rule of thumb for an agent:
1. If you're writing code inside a domain's `services/` and need a database,
   queue, LLM, or external API — define or reuse a **port** (interface) in that
   domain's `ports/`, then implement it under `infrastructure/`, then wire the
   concrete implementation in `main.py` / `api/dependencies.py`. Never import
   an infrastructure module directly from inside `domains/`.
2. If you're writing code inside `frontend/` and need backend data, validation,
   or operations — call a FastAPI endpoint via `frontend/streamlit_app/api_client/`.
   Never import models, schemas, services, or config from `src/open_enterprise_ai/`.

### Boundary enforcement

The frontend/backend boundary is enforced by tooling, not just convention:

- **Frontend → backend imports:** ruff rule `TID251` (banned-api) is enabled in
  `pyproject.toml` and bans `open_enterprise_ai` everywhere except `src/` and
  backend tests. `tests/unit/frontend/` is intentionally **not** exempt.
  Never remove or weaken this configuration.
- **Backend → frontend imports:** ruff cannot apply different bans per path, so
  this direction is checked with a grep in CI/pre-commit:
  `! grep -rEn "streamlit_app|^\s*(import|from)\s+streamlit" src/`
- **Belt-and-braces check for the frontend:**
  `! grep -rEn "open_enterprise_ai" frontend/`

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
| Backend environment/config values                        | `core/config.py`                                                                                                |
| A new domain-agnostic exception                          | `core/exceptions.py`                                                                                            |
| A domain-specific exception                              | inside that domain, e.g. `domains/auth/services/` or a dedicated `exceptions.py` in the domain root if it grows |
| A Streamlit UI page or reusable widget                   | `frontend/streamlit_app/pages/` or `frontend/streamlit_app/components/`                                         |
| An HTTP API client method for the frontend UI            | `frontend/streamlit_app/api_client/<domain>_client.py`                                                          |
| Request/response models for a frontend API client        | `frontend/streamlit_app/api_client/models/<domain>.py` (frontend-owned; never imported from the backend)        |
| Frontend session state or UI-specific config             | `frontend/streamlit_app/state/` or `frontend/streamlit_app/config.py`                                           |

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

### 4a. Frontend structure & API contract

```
frontend/streamlit_app/
├── app.py            # Streamlit entrypoint
├── config.py         # UI config (backend base URL from env, timeouts)
├── pages/
├── components/
├── state/            # st.session_state helpers
└── api_client/
    ├── <domain>_client.py   # httpx calls to backend endpoints
    └── models/              # frontend-owned request/response models
```

- The **contract** between frontend and backend is the HTTP API, described by
  the backend's OpenAPI document (exported to `docs/api/` when it changes).
  The frontend re-declares only the fields it needs in its own
  `api_client/models/`; it never imports backend schema classes.
- The backend base URL and any frontend settings come from environment
  variables read in `frontend/streamlit_app/config.py`, never from
  `core/config.py`.
- Access/refresh tokens live only in in-memory Streamlit session state, are
  never logged, and are sent to the backend as `Authorization` headers.
  All authn/authz decisions are made by the backend, never by UI state.
- Frontend dependencies go in the `ui` dependency group only.

## 5. Tests mirror `src/` and `frontend/`

`tests/` structure follows `src/open_enterprise_ai/` and `frontend/`:

- `tests/unit/domains/<domain>/` — unit tests for services/ports, mocked
  dependencies, no I/O.
- `tests/unit/frontend/` — unit tests for frontend API clients (mocked HTTP)
  and session state helpers. These must not import `open_enterprise_ai`.
  `pyproject.toml` sets `pythonpath = ["frontend"]` so `streamlit_app` is
  importable; run with both groups installed (`uv sync --group dev --group ui`)
  when state helpers import `streamlit`.
- `tests/integration/repositories/` — tests against real infra
  (Postgres/Mongo/Redis/Qdrant) via test containers.
- `tests/integration/api/` — tests hitting FastAPI routes with the app
  wired to test infra.
- `tests/e2e/` — full-stack flows (backend and frontend as separate
  processes talking over HTTP).
- `tests/factories/` — shared test data builders.

A new domain, infra adapter, or frontend API client should always come with a
corresponding test file in the matching location before being considered done.

## 6. Docs & infra placement

- Architectural decisions (ADRs) go in `docs/decisions/NNNN-title.md`,
  numbered sequentially.
- Diagrams go in `docs/diagrams/`.
- API docs in `docs/api/`, deployment notes in `docs/deployment/`,
  security notes in `docs/security/`.
- Docker/compose/deploy config lives in `docker/` and `infra/`, never
  inside `src/` or `frontend/`. The backend and frontend are built and run as
  separate images/services (e.g. `docker/backend.Dockerfile`,
  `docker/frontend.Dockerfile`); the frontend image installs only the `ui`
  dependency group.

## 7. Naming conventions

- Files: `snake_case.py`.
- Infra adapter files are prefixed with their technology:
  `postgres_user_repository.py`, `redis_token_store.py`,
  `qdrant_vector_store.py`.
- Ports are named after the capability, not the tech:
  `user_repository.py`, `token_store.py`, `vector_store.py` — the domain
  never knows which vendor implements it.
- Services are named `<subject>_service.py`.
- Frontend HTTP client files are suffixed with `_client.py`:
  `auth_client.py`, `chat_client.py`.

## 8. When adding a new top-level concept

If a change doesn't fit any existing folder (e.g. a new cross-cutting
concern, a new domain, a new infra category), don't force it into an
existing folder. Propose the new folder following the same conventions
above, and add an entry to this file describing it.
