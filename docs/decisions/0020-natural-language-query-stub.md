# 0020 — Natural-language stub with persistent application configuration

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Issue #31 establishes a natural-language service contract for a later provider
integration. Application administrators must be able to configure it through
the application without editing environment files or restarting containers.
Their settings must survive browser sessions and application restarts. The
web frontend for setup and question submission belongs to #32.

An application administrator has permission to manage the application; that
does not imply access to the deployment host or system-administration skills.
An environment-only provider key would make routine configuration depend on
deployment operations. Returning or storing plaintext keys would also create
unnecessary exposure through clients, database copies, and logs.

## Decision

- Keep one installation-wide `AIConfiguration` row in a `natural_language` app.
  It starts disabled. Store provider/model identifiers, enable state, timeout,
  output-token limit, encrypted credential, and last-change metadata.
- Provide session-authenticated GET/PATCH at
  `/api/v1/natural-language/configuration/`. Require an active staff account
  with `natural_language.manage_ai_configuration`, using the shared operation
  permission policy. Retain CSRF protection for PATCH; protected GET sets the
  CSRF cookie needed by the frontend. Existing Django admin manages accounts
  and permission assignment.
- Accept provider credentials only as write-only configuration input. Omission
  preserves the saved key; replacement changes it; explicit clearing removes
  it and disables the feature. Changing provider requires a replacement or
  clearing. Never return the key or ciphertext, even to an administrator.
- Encrypt credentials with Fernet from `cryptography`. Automatically provision
  separate random encryption material in the backend-only `ai_secrets` named
  volume on the first credential save. Do not derive it from Django SECRET_KEY
  or store it with the database. Initialization uses the singleton row lock,
  restricted file permissions, and atomic file replacement.
- Do not silently replace a missing/corrupt encryption key while saved
  ciphertext depends on it. Metadata remains readable and the application
  administrator can explicitly clear and replace the credential to recover.
  Translate recognized storage failures into safe, fixed API errors.
- Serialize settings updates under a database transaction and row lock. Validate
  the merged configuration and commit it atomically. Read current configuration
  on each request so changes apply without restarting services.
- Expose public status at `/api/v1/natural-language/`, with only `enabled`,
  `is_stub`, and guidance. Disabled guidance directs users to an application
  administrator, rather than instructing them to modify the environment.
- Accept questions as JSON POST at `/api/v1/natural-language/query/`. The body
  contains a single nonblank string of at most 2,000 characters. Use the shared
  validation/error/schema infrastructure and mark every answer as a stub.
  POST keeps the question out of ordinary URL access logs; it does not grant
  permission to change broadband data.
- Provider selection is deferred. Stored provider/model identifiers and limits
  are not verification of provider support. The stub never contacts a provider,
  queries broadband data, interprets SQL, or executes model-supplied tools.
  Its answer explicitly discloses these limits.

## Access and frontend completion

The inert question stub is public. Configuration is an administrator operation
and remains protected independently of frontend visibility. Enabling real paid
provider requests requires a separate decision on supported providers/models,
who may submit questions, quotas, timeouts, costs, and guarded data access.
An installation's configured key is not a user's authorization credential.

Issue #32 must provide an application-admin settings screen with a masked
replacement-key input, explicit remove action, saved nonsecret values, and
clear errors. It must integrate the existing login/session and same-origin
CSRF flow. No browser storage or prefilled password field holds saved keys.
Provider configuration and changes must be possible without terminal access.
The backend alone completes #31, not the combined frontend/backend feature.

## Alternatives and consequences

Environment-only configuration was rejected because it requires deployment
access for routine application administration. Per-user credentials were not
selected: the owner chose shared configuration managed by application admins.
Custom cryptography and signing-only storage were rejected in favor of a
standard authenticated-encryption implementation.

The database and separate secret volume form the installation's backup/restore
set. Named volumes survive container recreation but do not provide automatic
backups; deleting them destroys state. This separation protects against a
database-only disclosure. It does not protect against an attacker controlling
the running backend and its mounted key material. Deployment operators remain
responsible for backup, host access, and eventual key rotation or external
secret-manager integration. These are separate from the application admin's
ordinary settings workflow.

Tests cover permission/CSRF boundaries, persistence across clients and credential
readers, strict validation, encrypted storage and deliberate recovery, concurrent
updates, safe errors, and actual responses against generated OpenAPI. The stub
adds no dependency on loaded FCC data and changes no imported-data write path.

References: [Fernet](https://cryptography.io/en/stable/fernet/),
[OWASP secrets management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html),
[Docker volumes](https://docs.docker.com/engine/storage/volumes/),
[DRF session authentication](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication),
[HTTP POST semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.3),
[shared API guidance](../api-guidelines.md).
