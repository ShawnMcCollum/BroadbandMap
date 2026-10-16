# Issue #31 plan, revision 2: persistent AI configuration

Status: approved by the repository owner on October 16, 2026; implemented and
verified, awaiting pull-request review. This replaces the environment-only plan.

## Requirements settled during review

- An application administrator configures AI through the web frontend. Editing
  `.env`, running commands, and restarting containers are not part of that flow.
- One configuration belongs to the installation. It persists across sign-outs,
  browser sessions, backend restarts, and container recreation while persistent
  volumes are retained. Individual users do not supply installation credentials.
- Only authorized application administrators may read/change detailed settings.
  No API response returns the provider key, including to an administrator.
- Provider choices can wait. This plan settles configuration first; it selects
  no provider, advertises no working provider integration, and makes no provider
  requests. Saved provider/model identifiers are explicitly unverified.
- #31 owns persistence, credential protection, API contracts, permissions, and
  tests. #32 must include an application-admin settings screen and question
  panel. A usable frontend setup flow is required for the combined feature.

## Starting point and design

Branch: `codex/31-natural-language-query`, from `5fa7933`, the fetched main on
October 16, 2026. Only plan documents have changed. Reuse Django/DRF, session
authentication, explicit operation permissions, CSRF, Problem Details, strict
query validation, and OpenAPI checks. Add cryptography for authenticated secret
encryption; use no provider SDK or generated SQL.

Configuration is writable application metadata. The question service and all
imported broadband data remain read-only. The service obtains a current settings
snapshot per request; changes apply immediately without process-local caching.
Live provider access, quotas, cost controls, provider-specific parameter checks,
and supported provider/model choices require a later plan.

## Persistent model

Create a `natural_language` app and singleton `AIConfiguration` model. A migration
creates its disabled row, ID 1. No generic create/delete endpoint or Django admin
model registration exposes its credential fields.

| Field | Type/options | Help text |
|---|---|---|
| `id` | PositiveSmallIntegerField, primary_key=True, default=1, editable=False | Installation-wide AI configuration; identifier must be 1. |
| `enabled` | BooleanField, default=False | Enable the configured natural-language stub. |
| `provider` | CharField(max_length=64, blank=True, default='') | Provider identifier reserved for future integration; not verified by the stub. |
| `model_name` | CharField(max_length=200, blank=True, default='') | Model identifier supplied by the administrator; not verified by the stub. |
| `api_key_ciphertext` | TextField(blank=True, default='', editable=False) | Encrypted provider credential; never serialize or log. |
| `timeout_seconds` | PositiveSmallIntegerField(default=30) | Future provider timeout, from 1 through 120 seconds. |
| `max_output_tokens` | PositiveIntegerField(default=1024) | Future provider output limit, from 1 through 8192 tokens. |
| `updated_at` | DateTimeField(auto_now=True) | Time of the last successful configuration change. |
| `updated_by` | Nullable/blank FK to AUTH_USER_MODEL, SET_NULL, editable=False | Administrator who last changed the configuration. |

Named checks: `nl_ai_config_singleton` (id=1), `nl_ai_config_timeout_range`
(1..120), `nl_ai_config_output_range` (1..8192),
`nl_ai_config_provider_format` (empty or `^[a-z][a-z0-9_.-]{0,63}$`), and
`nl_ai_config_enabled_complete` (disabled, or nonempty provider, model, ciphertext).
The API additionally rejects whitespace-only model names and credentials.

Set `default_permissions=()` and a custom permission
`('manage_ai_configuration', 'Can manage AI configuration')`. Configuration
views use existing `IsAdministratorWithOperationPermission`, declaring
`required_operation_permissions=('natural_language.manage_ai_configuration',)`.
Require an active staff account with this permission; active staff superusers
follow Django's permission semantics. Ordinary users remain denied even if
granted that permission. Existing admin user management assigns permissions.

Save using transaction.atomic and select_for_update on the singleton. Validate
the merged final state, then commit the settings, encrypted credential, updater,
and timestamp together. Concurrent updates serialize; last successful save wins.

## Credentials without a manual setup step

Use Fernet from `cryptography>=46,<51`. Generate a random encryption key and keep
it outside PostgreSQL, separate from Django SECRET_KEY. Add a backend-only named
volume `ai_secrets:/run/broadbandmap-secrets`; the application manages
`/run/broadbandmap-secrets/ai-credentials.key`. Neither clients nor worker mount
that volume. No provider-key environment setting or environment fallback is used.

Initialize encryption material on the first credential save while holding the
singleton row lock. Reuse a valid existing key file. If no saved credential
depends on the material and the file is missing or malformed, create a random
Fernet key using a temporary file, flush/fsync, then atomic rename before committing
ciphertext. Directory mode 0700, file mode 0600 in the Linux container. All key
initialization uses that same row lock. Tests use temporary directories, never
the installation volume.

Reuse valid existing material. If the key is missing/malformed or ciphertext
cannot be decrypted, report unavailability without exposing paths or secrets.
Never silently replace material needed by an existing saved credential. Metadata
reads and explicit credential clearing remain available. Once the administrator
explicitly clears the credential, a new credential save may regenerate missing
or malformed key material because no saved credential then depends on it.

Do not put plaintext keys in URLs, logs, exceptions, model repr/str output,
browser storage, response bodies, or prefilled forms. Configuration responses
report only whether a key exists and is readable. Frontend password inputs clear
after successful saves. Encryption protects against database-only disclosure;
it cannot protect against compromise of the running backend and its key volume.

Document database and secret-volume backup/restore together. Named volumes
provide persistence, not backups. Deleting them destroys installation state.
Rotation and external secret managers remain deployment concerns, separate from
the application administrator's normal setup flow.

## Configuration API for the web frontend

`GET /api/v1/natural-language/configuration/` returns HTTP 200 with exactly:
`enabled`, `provider`, `model_name`, `timeout_seconds`, `max_output_tokens`,
`key_configured`, `key_available`, `is_stub`, `provider_validated`, `updated_at`.
Booleans have their ordinary JSON types; is_stub is always true and
provider_validated always false. updated_at is an ISO timestamp. No key,
ciphertext, storage path, or updater identity is returned. key_configured means
ciphertext exists; key_available means it can currently be decrypted.

GET also obtains a Django CSRF token so middleware sets a CSRF cookie for the
authenticated frontend's subsequent PATCH. Use session authentication on this
resource and enforce the operation permission on every method.

`PATCH /api/v1/natural-language/configuration/` accepts a nonempty object with
any subset of enabled, provider, model_name, timeout_seconds, max_output_tokens,
api_key, clear_api_key. Return HTTP 200 with the same sanitized representation.

- enabled/clear_api_key must be JSON booleans. Timeout/tokens must be JSON
  integers in the model bounds; reject bools, floats, and numeric strings.
- provider/model_name must be strings; trim them. Allow empty while disabled;
  enforce the provider format and model-name length above.
- api_key is optional, write-only, trimmed, 1..4096 characters. Omission means
  preserve; null/blank is invalid. An empty password box cannot erase the key.
- clear_api_key=true removes ciphertext and disables atomically. Combining
  clear_api_key=true with api_key or enabled=true is a 400 validation error.
- Changing provider while ciphertext exists requires replacement api_key or
  explicit clear, preventing accidental reuse of another provider's key.
- Enabling requires complete provider/model/key settings and readable credential
  storage. Completeness is not provider validity: this feature is still a stub.
- Reject unknown fields, including read-only metadata/ciphertext, with field
  code unknown_field. Reject empty/non-object bodies and wrong JSON scalar types.
- Anonymous, nonstaff, inactive, and unpermitted staff callers receive shared
  403 errors. PATCH requires a valid CSRF token. HEAD/OPTIONS respect permissions.
  POST, PUT, DELETE return 405 for authorized callers.

Reject query parameters with an empty StrictQuerySerializer. Use no-store on
successful responses. Operation IDs: natural_language_configuration_read and
natural_language_configuration_update. Declare shared 400, 403, 405, 406, 415,
500 and recognized 503 errors as applicable.

## Status and query service

`GET /api/v1/natural-language/`: public GET/HEAD/OPTIONS only. Return 200 with
enabled:boolean, is_stub:true, message:string. enabled requires the stored
enable flag, complete configuration, and available credentials. Disabled guidance:
`Ask an application administrator to enable AI in the application settings.`
Enabled guidance explicitly states no provider or broadband queries are performed.
No detailed configuration is public. Operation ID: natural_language_status.

`POST /api/v1/natural-language/query/`: retain the original strict JSON contract:
exactly one required string question; trim; nonblank; maximum 2000 characters.
Reject nonstrings, extra fields, and all query parameters. Validate before the
feature gate. Public POST/OPTIONS is allowed while this remains an inert stub;
other methods return shared 405 errors. Live paid calls require a separate access
and cost policy before activation.

Disabled/incomplete settings give 503 natural_language_disabled with the guidance
above. Enabled settings whose credentials are unreadable give 503
ai_credentials_unavailable with fixed detail: `AI credentials are unavailable.
An application administrator must restore or replace the saved credential.`
Map recognized encryption/storage failures safely; do not propagate sensitive
library exception messages. Configuration saves with unavailable storage also
use that safe 503 rather than partially persisting a change.

Successful queries return 200 with question (normalized input), answer
(`This is a natural-language query stub. No broadband data was queried and no external provider was contacted.`),
and is_stub:true. Use no-store. Operation ID: natural_language_query. Document
400/405/406/415/500/503. Unexpected errors retain the existing generic 500 and
request ID. Treat SQL-like instructions as inert text.

Use a frozen QueryAnswer dataclass with question:str, answer:str, is_stub:bool=True
and answer_question(question:str)->QueryAnswer. This service accepts validated
normalized questions, loads a current configuration snapshot, enforces its
availability, and returns the fixed answer without broadband model/network access.

## Frontend completion in #32

Provide an authorized-admin AI Settings screen: provider/model identifiers,
enable switch, masked replacement-key input, explicit remove action, and advanced
timeout/output limits with defaults. Show persisted nonsecret settings and
key-present status after signing in again. Never imply provider validation or
prefill a saved key. Changes apply immediately; validation/recovery errors use
plain application language. Ordinary users are directed to contact an admin.

Use existing Django admin sessions/login rather than a second identity system.
The #32 plan must settle its frontend routes, login navigation, and same-origin
proxy/CSRF integration. #31 provides CSRF bootstrap on protected configuration
GET. Hiding controls does not authorize requests; backend permissions remain
authoritative. #31 alone completes the backend layer; the combined feature is
not finished until the frontend setup and query flow work together.

## File set

Create under backend/natural_language:

- __init__.py, apps.py, models.py.
- migrations/__init__.py and 0001_initial.py: schema, checks, permission, and
  disabled singleton seed operation.
- credentials.py: Fernet, atomic application-managed key initialization,
  safe storage errors, and deliberate recovery after clearing credentials.
- configuration.py: sanitized reads, merged-state validation, atomic settings
  updates, change metadata, and current availability.
- services.py: QueryAnswer and typed disabled/unavailable service behavior.
- api/__init__.py, serializers.py, views.py, urls.py: three resources and
  explicit request/response/error/security annotations.
- tests/__init__.py, conftest.py, test_models.py, test_credentials.py,
  test_configuration.py, test_services.py, test_api.py, test_permissions.py,
  test_api_schema.py.

Create docs/decisions/0020-natural-language-query-stub.md documenting runtime
configuration, permissions, credentials/recovery, read-only stub boundaries,
frontend completion, and deferred provider decisions.

Change backend/config/settings.py (app, encryption-key file path, API description),
backend/pyproject.toml and backend/uv.lock (cryptography), docker-compose.yml
(backend-only ai_secrets volume), backend/core/api/urls.py (three routes),
backend/core/api/problems.py (two fixed feature error codes/translations),
backend/core/api/serializers.py (Problem code choices),
backend/core/api/openapi.json (generated baseline),
backend/core/tests/api/test_schema.py (expected paths), README.md (application
setup, persistence, backup/recovery responsibilities, #32 handoff, ADR), and
docs/api-guidelines.md (configuration/stub contracts). Maintain this plan.

No .env.example, broadband models, ETL, frontend code, or worker configuration
changes. Do not alter issue #32's body as part of this plan publication.

## Required validation

- Database checks reject wrong singleton IDs, invalid bounds/provider formats,
  and incomplete enabled rows. Migration creates one disabled row. Updater
  deletion preserves configuration. Ordinary tests use the real PostGIS test DB.
- Permission matrix: anonymous/ordinary/inactive/unpermitted staff receive 403;
  permitted active staff and staff superusers succeed. An ordinary account with
  the permission remains denied. Use real session and missing/wrong/valid CSRF
  tests on PATCH; valid token is obtained through protected configuration GET.
- Save from one client, sign out, read from another authenticated client: same
  persisted configuration. A fresh credential reader using the same database
  and temporary key file decrypts successfully; no in-memory/browser dependency.
- Plaintext never appears in stored ciphertext or responses. Omitted key
  preserves it; replacement changes it; explicit clear removes it and disables.
  Provider change requires replacement/clear. Read-only fields cannot be written.
- First save initializes a valid restrictive key file; subsequent saves reuse it.
  Missing/malformed key, tampered ciphertext, and unwritable storage fail safely,
  never silently replacing material. Metadata/clear remain usable. Explicit clear
  followed by replacement recovers. Concurrent updates cannot commit mixed-key
  state; failed writes preserve previous database settings.
- PATCH input cases: empty/nonobject, unknown fields, null/blank/over-4096 key,
  provider regex violation, model name over 200, timeout 0/121, output 0/8193,
  wrong scalar types, and conflicting clear/enable/key all yield structured 400.
  Bounds 1/120 and 1/8192 succeed. Changes are atomic.
- Service: unconfigured/disabled gives admin-guidance 503; enabled complete
  settings give fixed stub answer; fresh requests see edits immediately;
  unavailable credentials use their safe 503. No broadband or network operations.
- Questions in both feature states: missing/null/numeric/bool/list/object/blank,
  over-2000 and extra fields give 400. `  Hello  ` normalizes; 2000 chars pass;
  SQL-like text is inert. Patch the adapter boundary to verify service forwarding.
- Unknown/repeated query parameters give 400; malformed JSON gives parse_error;
  text/plain gives 415; unacceptable Accept gives 406; wrong methods give 405
  with Allow; HEAD omits bodies; OPTIONS honors access; no-store on sensitive
  successful responses. Unexpected failures give safe shared 500/request IDs.
- Actual 200/400/403/405/406/415/500/503 responses validate against generated
  OpenAPI with OAS30Validator. Verify route methods, operation IDs, session
  security, write-only request credential, and absent response secrets. Generate
  with warnings treated as errors and review only intentional baseline changes.

## Commands after implementation approval

Use a process-local PowerShell alias if needed:
`Set-Alias docker 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'`.

1. Implement the approved files and review within this scope before committing.
2. `docker compose run --rm --no-deps backend uv lock`; then
   `docker compose build backend` for the new dependency. No host Python setup.
3. `docker compose run --rm backend python manage.py makemigrations natural_language`;
   add/review the disabled singleton seed and named constraints.
4. `docker compose run --rm backend ruff format .` and
   `docker compose run --rm backend ruff check .`.
5. `docker compose run --rm backend python manage.py check_api_schema --update`;
   inspect `git diff -- backend/core/api/openapi.json`.
6. `docker compose run --rm backend pytest natural_language/tests core/tests/api`.
7. `docker compose run --rm backend sh check.sh`: formatting/lint, strict mypy,
   migration drift, schema drift, ordinary test suite. Full-data loads are
   unnecessary because the feature does not change broadband reads.
8. `git diff --check`; final diff review for credentials and unrelated edits.
   Report checks before a pull request; the owner merges, never commit to main.

## References and reasons

Verification on October 16, 2026: `docker compose run --rm backend sh check.sh`
passed formatting, Ruff, strict mypy (164 files), migration drift, reviewed
OpenAPI drift, and all 672 ordinary tests; 26 full-data tests were deselected by
the normal suite configuration. Full-data loading is outside this change.
The generated contract adds exactly three paths and leaves all existing path
contracts unchanged. `git diff --check` passed. The local backend applied
`natural_language.0001_initial` successfully; HTTP smoke tests returned status
200, anonymous configuration 403 `not_authenticated`, and query 503
`natural_language_disabled`. No provider credentials were installed or external
provider calls made. Frontend implementation remains in #32.

- [API guidance](../api-guidelines.md): use explicit operation permissions,
  session/CSRF, validation/errors, and schema checks for consistent client behavior.
- [Fernet](https://cryptography.io/en/stable/fernet/): authenticated encryption
  for small retrievable secrets without custom cryptographic primitives.
- [OWASP secrets management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html):
  restrict secret access and separate encryption material from protected data.
- [Docker volumes](https://docs.docker.com/engine/storage/volumes/): persist
  application-managed key material across container recreation.
- [DRF session authentication](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication):
  retain CSRF protection for authenticated unsafe requests.
- [DRF serializers](https://www.django-rest-framework.org/api-guide/serializers/):
  explicit fields/validation; installed CharField coerces numerics and normal
  Serializer ignores unknown fields, requiring strict guards for these contracts.
