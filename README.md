# Open Enterprise AI

An open-source enterprise AI harness to manage, secure, and deploy AI access across your teams with provider-agnostic support for any LLM.

## Configuration Management

Configuration is centralized and managed via [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). All configuration settings are validated at startup to fail fast on invalid or incompatible inputs.

### Setup

To configure your local environment:

1. Copy the tracked template `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. (Optional) Create environment-specific overrides, such as `.env.development` or `.env.staging`:
   ```bash
   cp .env.example .env.development
   ```
3. Customize the values in your `.env` or `.env.<APP_ENV>` file. Real `.env*` files are ignored by git and docker to prevent credential leakage.

### Environment Resolution & Precedence

The application determines configuration using a strict precedence order (highest to lowest):

1. **OS Environment Variables** (e.g. `export APP_PORT=9000`)
2. **Environment-specific `.env` file** (`.env.<APP_ENV>`)
3. **Base `.env` file** (`.env`)
4. **Field defaults in `Settings`**

#### Bootstrap Rule: `APP_ENV`

> **Important**: `APP_ENV` must be set as an **OS environment variable** (not inside a `.env` file).

The application reads `APP_ENV` directly from the OS environment during bootstrap to determine which `.env.<APP_ENV>` file to load. If `APP_ENV` is unset, it defaults to `local`.

Supported environments:
- `local` (default)
- `development`
- `test`
- `staging`
- `production`

Example:
```bash
export APP_ENV=development
uv run open-enterprise-ai
```

### Production Guardrails

In `production` (`APP_ENV=production`):
- `DEBUG` must be set to `False`. If `DEBUG=True` is detected, application startup fails fast with a validation error.
- `SECRET_KEY` must be configured to a secure, custom value. Startup fails immediately if `SECRET_KEY` is left as the development default (`insecure-dev-secret-change-in-production`), matches the `.env.example` placeholder (`change-this-insecure-dev-secret-to-a-secure-random-value`), or has fewer than 16 characters.

### Secrets Handling

Sensitive values (such as `SECRET_KEY`, API keys, or database credentials) use `pydantic.SecretStr`. Their values are automatically masked as `**********` in string representations, tracebacks, and logs. To access the raw secret value in code, use `.get_secret_value()`.

Containerized deployments can mount secrets into `/run/secrets` or specify a directory via the `SECRETS_DIR` environment variable:
- If `/run/secrets` exists and is a directory, it is automatically checked as a secret directory when `SECRETS_DIR` is not explicitly set.
- `SECRETS_DIR` is ignored if the specified path does not exist or is not a directory.
- Each mounted secret file must have a filename matching the lowercase configuration field name (e.g. `/run/secrets/secret_key`).

### Adding a New Setting

When adding new configuration settings:

1. Add the typed field with sensible defaults and validation constraints to `Settings` in [`src/open_enterprise_ai/core/config.py`](src/open_enterprise_ai/core/config.py):
   ```python
   NEW_FEATURE_ENABLED: bool = False
   ```
2. If the field is sensitive, use `SecretStr`:
   ```python
   EXTERNAL_API_KEY: SecretStr | None = None
   ```
3. Add the key and a descriptive comment to [`.env.example`](.env.example):
   ```bash
   # Enable experimental new feature
   NEW_FEATURE_ENABLED=false
   ```
4. The automated test suite (`tests/unit/core/test_config.py`) will automatically verify that all fields in `Settings` have a corresponding key in `.env.example`, preventing template drift.
