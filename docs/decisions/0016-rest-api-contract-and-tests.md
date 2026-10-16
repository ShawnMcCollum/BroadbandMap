# 0016 — REST API contract and tests

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

The React map and Streamlit dashboard need a shared interface to data held in the existing
Django/GeoDjango model. API conventions should keep domain rules with their Django apps, make
public data representations explicit, and give later endpoint work a consistent basis for
validation, performance, and tests. Data releases can be replaced or deleted, so API identity
and pagination must account for that behavior.

## Decision

- Organize API modules within the owning Django domain apps. Keep DRF views focused on HTTP
  orchestration and reuse existing domain selection rules.
- Make data reads public and read-only. Restrict operational actions to authenticated
  administrators with the relevant operation permission; retain session CSRF protections for
  unsafe browser requests.
- Use `/api/v1/` for business endpoints and preserve the current `/api/health/` behavior.
- Identify releases by `(as_of, processed_on)`, disclose the resolved release and geographic
  coverage, and represent identifiers as JSON strings. Use explicit serializers and validate
  documented inputs.
- Use RFC 9457 Problem Details for business API errors and consistent HTTP status semantics.
- Bound location reads with stable, opaque cursors tied to release generation and request
  context. Require clients to restart traversal if a release is replaced or deleted. Initial
  page-size guidance is 100, with a maximum of 1,000, subject to endpoint-specific verification.
- Read stored rollups for summaries. Keep geometry separate from ordinary summary and location
  responses, and do not infer point coordinates for locations.
- Generate and validate OpenAPI from the implementation with `drf-spectacular`. Review schema
  changes with endpoint changes.
- Continue pytest and pytest-django with DRF APIClient and real PostGIS integration where
  appropriate. Test contracts, release and geography rules, validation, pagination, permissions,
  transaction visibility, and query behavior using independently stated expected results.

The detailed conventions, rationale, test matrix, and references are maintained in
[API guidelines](../api-guidelines.md). Exact endpoint parameters and response fields are settled
in the owning implementation plans.

## Alternatives considered

- **A separate API domain model:** rejected because it would duplicate existing Django models
  and domain rules.
- **Unbounded location responses:** rejected because large datasets require bounded response
  sizes and predictable query work.
- **Built-in DRF OpenAPI generation:** replaced by `drf-spectacular`, following DRF's documented
  deprecation of its built-in schema generation.
- **Hand-maintained OpenAPI as a second contract:** rejected because it can drift from the
  implementation.
- **Public operational endpoints:** rejected; administration remains in Django admin or commands
  until an approved operational API is needed.

## Consequences

- **Positive:** Both clients can build against one explicit and reviewable contract, while
  domain ownership and existing selection rules remain authoritative.
- **Positive:** Bounded pagination and replacement detection give clients a clear recovery path
  when release data changes.
- **Positive:** Contract, permissions, and query expectations are agreed before endpoint
  implementation, improving future review and regression coverage.
- **Tradeoff:** Cursor binding, shared error handling, and generated schema checks require
  deliberate implementation beyond DRF defaults.
- **Follow-up:** #3 decides initial map output and summary selection; #26 specifies location
  response fields and cursor implementation; #15/#45 own operational permissions and
  concurrency; #54 owns multi-state release identity.
- **Supersedes:** ADR 0002's assumption that built-in DRF schema generation is the chosen
  tooling. Its Django, GeoDjango, and DRF architecture remains in effect.
