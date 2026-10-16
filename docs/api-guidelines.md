# REST API guidelines

These guidelines define the API conventions adopted by
[ADR 0016](decisions/0016-rest-api-contract-and-tests.md).
Issue #62 implements the shared HTTP foundation described here. Issue #3 adds release discovery,
summary reads, and county GeoJSON. Location endpoints remain in #26; operational API work remains
in #15, and multi-state release identity is settled by
[ADR 0017](decisions/0017-national-releases-loaded-by-state.md). The writer guard from #45 is
already implemented and is independent of HTTP access policy.

The general resource paths and numerical starting limits below guide endpoint planning;
section 11 specifies the three implemented read contracts.
Framework behavior is identified separately where relevant. Endpoint plans settle exact inputs,
response fields, and implementation details before the corresponding endpoints are built. The
examples do not imply that these business endpoints already exist.

## 1. Organize around the existing domains

Keep models, domain rules, and database query functions in their existing Django apps. Use small
`api/` packages inside the relevant apps rather than a second, competing domain model:

```text
backend/
  core/api/               # implemented shared HTTP infrastructure
  bdc/api/                # release discovery and release input validation
  geography/api/          # area metadata and later map representations
  served_unserved/api/    # summary and location endpoints
```

Create a module only when an endpoint needs it. Keep tests with the owning app under its existing
`tests/` package. `config/urls.py` mounts the `api_v1` namespace at `/api/v1/`;
`core/api/urls.py` composes the release, geography, and summary URL configurations.

The implemented shared modules are:

| Module under `core/api/` | Responsibility |
|---|---|
| `permissions.py` | Deny-all default and administrator/operation permission pattern |
| `validation.py` | Strict singleton query serializers |
| `problems.py` | Safe Problem Details payloads and DRF exception translation |
| `middleware.py` | API boundary errors and request correlation |
| `serializers.py` | Explicit Problem, ValidationProblem, and FieldError schema components |
| `schema.py` | Shared problem-response annotations for drf-spectacular |
| `openapi.json` | Generated, reviewed production schema baseline |

Shared bounded page-number reads live in `core/api/pagination.py`; request-scoped read snapshots
live in `core/api/transactions.py`. Release metadata and date validation belong to `bdc/api/`.

Views coordinate request validation, permissions, query selection, pagination, and serialization.
Reusable read queries belong in a domain module such as `queries.py`; existing `statuses_in`
remains the authoritative geography selection rule. Services are appropriate for multi-step
operations such as starting a load, when those features are implemented. Avoid generic repository
wrappers that merely duplicate Django QuerySets.

Prefer DRF `ListAPIView` and `RetrieveAPIView` for simple reads, and read-only viewsets when several
related resource operations make that clearer. Use `APIView` where its explicit orchestration is
useful. Do not inherit writable CRUD actions for imported FCC data. These are project conventions
built on [DRF's generic views](https://www.django-rest-framework.org/api-guide/generic-views/).

## 2. Make the contract explicit before implementing an endpoint

For each endpoint, agree on its purpose, route, inputs, defaults, validation, permissions, response
fields, ordering, paging, errors, and performance checks. Review examples with both client
applications in mind.

Use `/api/v1/` for new business endpoints. This API version describes the HTTP contract; FCC data
releases are separate inputs. Keep the existing `/api/health/` behavior because both current clients
use it. URL versioning is a project choice supported by
[DRF's versioning mechanisms](https://www.django-rest-framework.org/api-guide/versioning/).

Implemented resources and planned resource families:

| Resource | Route | Responsibility |
|---|---|---|
| Releases | `GET /api/v1/releases/` | Discover loaded periods, processing dates, and geographic coverage |
| County geometry | `GET /api/v1/geographies/county/?state=39` | Bounded county GeoJSON, implemented in #3 |
| Area metadata | `GET /api/v1/geographies/{level}/{code}/` | Describe a known area without automatically returning its polygon |
| Summary counts | `GET /api/v1/served-unserved/rollups/` | Read stored rollups for one release and geographic level |
| Area locations | `GET /api/v1/served-unserved/locations/` | Read bounded, paginated statuses behind one area |

Area metadata and location routes remain proposals. The three implemented read contracts are
specified in section 11. Operational HTTP routes remain outside these resources.

Use JSON and `snake_case` for ordinary representations. Explicit serializer field lists prevent
future database fields becoming public accidentally. A `ModelSerializer` is suitable for a direct
model representation; a plain `Serializer` is suitable for query input or a composed response. Never
use `fields = '__all__'` for a public contract. See
[DRF serializers](https://www.django-rest-framework.org/api-guide/serializers/).

## 3. Preserve release and geography meaning

- Identify a release publicly by `as_of` and `processed_on`, following ADR 0013. Do not publish a
  database primary key as its durable identity.
- Accept both dates together, or neither. Omitting both selects the latest loaded release ordered by
  `as_of`, then `processed_on`. An incomplete pair is invalid.
- Return the resolved release in every release-backed JSON response and pagination link. A
  subsequent page must not silently select a newly loaded period.
- Return geographic coverage explicitly: the states each release holds
  (`served_unserved.release_states.states_in_release`). A release is national and can hold any
  subset of states ([ADR 0017](decisions/0017-national-releases-loaded-by-state.md)), so a date pair
  must not imply nationwide completeness. An H3 cell on a state line has one rollup row per state;
  add up a cell's rows before returning it.
- Use `AREA_KEYS` and `RollupLevel` for permitted levels, key validation, and location selection.
  Avoid copying their regexes or lookup logic into views.
- Represent location IDs, GEOIDs, and H3 cells as strings in JSON. They are identifiers, not
  quantities; strings preserve leading zeros and avoid tying future identifier sizes to JavaScript's
  integer precision. Counts remain integers, and flags remain booleans.
- Preserve the three explicit flags: `any_100_20`, `wired_100_20`, and `terrestrial_100_20`. For
  a selected flag, define `not_served = locations - served`. Do not relabel this as the regulatory
  unserved/underserved distinction.
- Return threshold and source metadata with summaries: 100 Mbps down, 20 Mbps up; the FCC period and
  processing date; and boundary vintage 2020 where applicable.
- A known area with no matching locations returns a successful empty list. A valid area key that
  identifies no known area returns 404. Missing rollups must not be silently interpreted as measured
  zero service: section 11 defines how summary coverage distinguishes no observations from
  unavailable derived data and areas outside a release's states.

Example location request:

```http
GET /api/v1/served-unserved/locations/?as_of=2025-12-31&processed_on=2026-09-29&level=county&code=39049&flag=wired&status=not_served
```

Proposed filter choices: `flag=any|wired|terrestrial`, default `wired`; optional
`status=served|not_served`, with omission meaning both. Location lists require an area. Exact
response fields and examples are acceptance criteria for #26.

## 4. Validate inputs and use HTTP consistently

Validate query inputs through DRF serializers with `is_valid(raise_exception=True)`, including
cross-field rules. Restrict filtering and ordering to documented choices. Reject unknown query names
and repeated singleton parameters explicitly: ordinary serializers do not establish this policy
automatically. Catching `flga=wired` is more useful than silently ignoring it.

Use `core.api.validation.StrictQuerySerializer` for endpoint query serializers. It rejects unknown
names and repeated declared parameters before ordinary field validation, including a repeated value
such as `limit=1&limit=1`. Read-only serializer fields are not accepted as query inputs. Invoke it
with `data=request.query_params`, then call `is_valid(raise_exception=True)`. Put the endpoint's
fields, defaults, bounds, and cross-field rules in its owning app. Plain dictionary input remains
supported, but only a multi-value input such as QueryDict can reveal repeated names.

Unknown names receive the field code `unknown_parameter`; repeated singleton names receive
`repeated_parameter`. Name/multiplicity errors are reported deterministically by field name.
Endpoints accepting repeated list parameters require an explicit extension to this convention.

Proposed semantics:

| Status | Meaning |
|---|---|
| 200 | Successful read, including an empty filtered collection |
| 400 | Malformed dates, incomplete date pair, invalid level/code form, invalid filter, or malformed cursor |
| 403 | An operation denied under session-based administrator access |
| 404 | Unknown release or area; no loaded release when a latest release is requested |
| 405 | Unsupported method on a known read-only resource |
| 409 | Pagination cannot continue because its underlying release was replaced or deleted |
| 429 | Application throttling limit reached, when throttling is configured |
| 500 / 503 | Unexpected failure / recognized temporary dependency unavailability |

Do not send HTTP 200 with an error flag. Keep exception translation in one shared API handler. Adopt
RFC 9457 Problem Details for business API errors, with `application/problem+json`, `type`, `title`, `status`, `detail`, and a stable `code` extension; validation errors also include structured
field errors. `about:blank` is sufficient as a type until dedicated problem documentation exists.
Preserve HTTP headers such as `Allow` and `Retry-After` when wrapping framework responses. Unknown
API routes and unexpected failures need boundary coverage too; a DRF exception handler alone does
not cover every Django failure.

Do not expose exception traces, SQL, or local paths in responses. Log unexpected failures with a
request correlation identifier. Expected validation failures are not server errors. The existing
health response is an explicit operational exception to the new business error format.

The implemented validation response has this form:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Request validation failed.",
  "code": "validation_error",
  "request_id": "ceef3c797be74cef8f2cdba04463ad2ce",
  "errors": [
    {
      "pointer": "/limit",
      "code": "invalid",
      "message": "A valid integer is required."
    }
  ]
}
```

`type`, `title`, `status`, `detail`, `code`, and `request_id` are required. The title is the HTTP
reason phrase; the status matches the response. Validation adds a nonempty `errors` list, while
other problems omit it. Each field error contains a JSON Pointer into the serializer input, a
stable leaf code, and a message. Multiple messages for a field retain its pointer; nested input
arrays include their index. Cross-field errors use `/non_field_errors`, root errors use the empty
pointer, and pointer segments escape `~` and `/` according to RFC 6901.

The shared top-level codes are:

| HTTP | Codes |
|---|---|
| 400 | `validation_error`, `parse_error`, `bad_request` |
| 403 | `not_authenticated`, `authentication_failed`, `permission_denied` |
| 404 / 405 / 406 / 415 | `not_found`, `method_not_allowed`, `not_acceptable`, `unsupported_media_type` |
| 429 | `throttled` (no throttle policy is configured yet) |
| 500 | `internal_error` |
| 503 | `service_unavailable` for explicit `ServiceUnavailable` exceptions |
| Other errors | `http_error` for other 4xx statuses; generic `internal_error` for other 5xx statuses |

Raise DRF exceptions, including serializer validation exceptions, rather than constructing endpoint
error bodies. Use `core.api.problems.ServiceUnavailable` only for a recognized temporary failure;
arbitrary database exceptions remain unexpected failures. Nonvalidation details are fixed, safe
messages, including `An unexpected error occurred.` for unexpected failures.

The boundary covers `/api` and `/api/...`, including unknown routes, Django view errors, rendering
failures, and errors returned by inner middleware. It sanitizes errors with DEBUG on and off and
preserves their HTTP status, relevant headers, and cookies. Problem JSON is independent of the
successful response renderer, including when Accept negotiation fails. `/api/health/` retains its
existing JSON and status contract; non-API routes retain Django behavior. Successful responses and
normal redirects pass through. Failures before Django receives a request or after streaming has
started are outside this boundary.

Each covered request gets a fresh UUID4 hex value in `X-Request-ID`; problems carry the same value
in `request_id`. Incoming identifiers are ignored. Unexpected failures are correlated in server
logs without including query strings in the shared log message. Expected validation and permission
failures do not create shared-infrastructure error logs.

References: [HTTP semantics](https://www.rfc-editor.org/rfc/rfc9110.html),
[Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html),
[DRF exception handling](https://www.django-rest-framework.org/api-guide/exceptions/).

## 5. Bound large reads and define pagination consistency

Use cursor pagination for location lists, ordered by ascending `location_id` within one release.
That value is unique within the release and the model already has a `(release, location_id)`
uniqueness constraint. Do not use the status row's surrogate primary key as the public traversal
order, since replacing a release recreates its rows.

Proposed initial location page size: 100, configurable up to 1,000. Reject invalid sizes and
requests over the cap with 400; this stricter behavior must be implemented explicitly rather than
assuming DRF's defaults do it. Return `next`, `previous`, `results`, and metadata identifying the
release and area. Do not execute a full filtered `COUNT(*)` for every location page. Total counts
are separate summary concerns.

Bind each cursor to the resolved release, its current database generation, the area, filters, and
page size. Treat the cursor as opaque and signed. Reject altered tokens or changed query context
with 400. If the release generation changed or disappeared, return 409 with code `dataset_changed`
and a restart instruction. The current release row's identity can serve internally as a generation
token because replacement deletes and recreates it; it is not a new public resource identity. This
binding is additional project behavior, beyond DRF's stock cursor token.

Use a consistent database snapshot for release resolution and page selection within one request. A
short read-only repeatable-read transaction is a candidate to verify in #26; ordinary `atomic()` at
PostgreSQL's default read-committed isolation does not guarantee that snapshot. Do not hold a
transaction across HTTP page requests. Across requests, restart detection is the guarantee, not a
persistent snapshot of deleted data.

Use simpler page-number pagination for bounded release catalogs or small summary lists where exact
totals are useful. Keep each endpoint's envelope documented. Never offer an unbounded all-location
response. Geometry payloads require feature and payload limits as well as pagination; an arbitrarily
large polygon is not made cheap by a row-count cap.

References: [DRF pagination](https://www.django-rest-framework.org/api-guide/pagination/),
[Django PostgreSQL isolation](https://docs.djangoproject.com/en/5.2/ref/databases/#isolation-level).

## 6. Measure the database work behind the API

Read stored `Rollup` rows for summaries instead of aggregating millions of statuses for each
request. Use the existing domain queries for location drill-down. Fetch only required columns and
related rows; use `select_related` or `prefetch_related` when the representation actually needs
relationships. Serializers should not hide per-row database lookups.

Verify first and deep location pages against the real Ohio data with query plans. An indexed
location ordering does not alone guarantee a fast plan when combined with geographic and flag
filters. New indexes require measured evidence and their own migration plan. Record response bytes,
query count, and timings for representative summary and largest-county requests. Avoid
machine-specific timing assertions in fast tests.

Start release-backed responses with explicit `Cache-Control: no-store`. Dates are stable
identities, but `--replace` makes their contents replaceable. A later cache decision must address
replacement, deletion, rollup rebuilding, query inputs, representation, and any latest-release
alias. Do not advertise immutable caching solely because dates appear in a URL.

Reference:
[Django database optimization](https://docs.djangoproject.com/en/5.2/topics/db/optimization/).

## 7. Keep geography representations honest

Ordinary summary and location JSON omit polygon geometry. County GeoJSON is a separate bounded
resource, following [ADR 0018](decisions/0018-county-geojson-map-output.md). Tables and flag changes
need not download shapes. Block-level or nationwide tiles remain a later measured decision.

For GeoJSON, use RFC 7946 Feature/FeatureCollection structures, WGS84 longitude/latitude
coordinates, stable feature identifiers, and `application/geo+json`. GeoDjango's serializer is
useful for geometry conversion, but it is not a substitute for the API's validation, permissions,
query selection, and response contract.

Do not manufacture location point coordinates from block centroids or H3 centers. The source locates
records within areas, not at known coordinates. A census internal point may be used as an area label
point if clearly identified as such.

References:
[GeoDjango GeoJSON serialization](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/serializers/), [GeoJSON standard](https://www.rfc-editor.org/rfc/rfc7946.html).

## 8. Public reads and restricted operations

Set an explicit restrictive default permission policy and opt public GET/HEAD/OPTIONS views into
`AllowAny`. Public data views can disable authentication processing when they have no user-specific
behavior. Public resources expose no write methods, even to staff users.

The configured default is `core.api.permissions.DenyAll`, which denies every caller, including
staff and superusers. A public read explicitly declares:

```python
permission_classes = [AllowAny]
authentication_classes = []
http_method_names = ["get", "head", "options"]
```

Keep operational actions in authenticated Django admin or existing commands until #15 needs an API.
Any later operational endpoint requires authentication, staff status, and the relevant operation
permission. `IsAdminUser` alone means `is_staff`; it does not check a particular model or operation
permission. Do not confuse authenticated users with administrators.

For a future operation, explicitly select
`core.api.permissions.IsAdministratorWithOperationPermission` and declare a nonempty
`required_operation_permissions` tuple of Django permission names. It checks authentication,
active status, staff status, and `user.has_perms(...)`; missing, empty, or invalid declarations deny
access. Django's normal superuser permission semantics apply. The owning operation plan chooses
its permissions; the foundation creates none and adds no operation route. Retain the configured
session authentication and test unsafe requests using a real session and CSRF token.

Use Django session authentication for browser-based administrator operations initially and retain
CSRF protection for unsafe requests. A public GET API does not require introducing JWTs or API keys.
Do not install global `LoginRequiredMiddleware` and assume it secures DRF views: DRF permissions
must remain explicit.

Deployment guidance should require HTTPS and intentional cross-origin settings. Same-origin client
routing avoids adding a CORS dependency for the current setup. Bound queries and response sizes from
the outset. Configure throttling only with a defined traffic policy; DRF describes its throttling as
an application policy, not a denial-of-service defense.

References: [DRF permissions](https://www.django-rest-framework.org/api-guide/permissions/),
[authentication and CSRF](https://www.django-rest-framework.org/api-guide/authentication/),
[throttling limitations](https://www.django-rest-framework.org/api-guide/throttling/).

## 9. Generate and review OpenAPI with the implementation

The foundation installs DRF with `drf-spectacular`. DRF's built-in OpenAPI
generation is deprecated and its documentation recommends this replacement. This updates ADR 0002's
tooling assumption without changing its Django/DRF architecture.

The dependency constraints keep DRF and its typing stubs on the matched 3.16 line alongside Django
5.2 LTS and django-stubs 5.2. The newer typing line requires newer Django stubs; review these
constraints together when upgrading rather than independently advancing one package. Strict mypy
checking remains enabled with the Django and DRF plugins.

Generate an OpenAPI 3 schema from the implementation, supplementing inference with explicit query
serializers, error responses, cursor envelopes, examples, and stable operation IDs. Start with
OpenAPI 3.0.3 for broad client tooling compatibility; revisiting that version requires checking both
clients. Document identifiers as strings, geographic enumerations, date formats, public security,
and administrator operations accurately.

`GET /api/schema/` serves OpenAPI JSON anonymously, with HEAD/OPTIONS support and no unsafe
methods. The provider supports its standard schema query options and OpenAPI JSON media types
(`application/vnd.oai.openapi+json` and `application/json`). Schema delivery excludes itself from
generation. Health is also outside this business schema. Its `paths` contains the three implemented
read resources from #3.
Test-only endpoints exercise shared contracts without appearing in the production document.

Run these commands from the repository root in PowerShell:

```powershell
# Rebuild after dependency changes.
docker compose build backend

# Validate and compare the production schema; differences fail without changing the baseline.
docker compose run --rm backend python manage.py check_api_schema

# Accept an intentional contract change, then review the generated diff.
docker compose run --rm backend python manage.py check_api_schema --update
git diff -- backend/core/api/openapi.json

# Export a validated standalone document inside the temporary container.
docker compose run --rm backend python manage.py spectacular --format openapi-json --file /tmp/broadbandmap-openapi.json --validate --fail-on-warn

# Run focused HTTP/health coverage, then all backend checks.
docker compose run --rm backend pytest core/tests/api core/tests/test_health.py
docker compose run --rm backend sh check.sh
```

`check_api_schema` generates into a temporary directory with validation and warnings treated as
failures. It compares the entire parsed document with `core/api/openapi.json`, ignoring only object
key order and formatting. It prints a unified diff and fails on drift; only `--update` writes the
baseline. `check.sh` includes this check before pytest. Code remains the implementation source;
do not maintain a second independent handwritten schema or generate the baseline from test routes.

Annotate endpoint methods with explicit operation IDs, query/success serializers, and relevant
errors. Merge `core.api.schema.problem_responses(*statuses)` into the responses passed to
`extend_schema`; it sets `application/problem+json` and uses a disjoint union of Problem and
ValidationProblem for 400, since malformed JSON does not have field errors. Other error statuses
use Problem. These components appear when referenced by an implemented endpoint; unused
components are not appended to the production schema.

Within v1, preserve field meanings, types, defaults, and error codes. Add optional fields carefully;
clients should ignore unknown response fields. Adding enum values still requires consumer review
because clients may use exhaustive switches. Removing fields, changing their meaning, or changing
defaults requires an explicit compatibility decision. Generated TypeScript/Python clients may follow
when useful; they are not required to settle #33.

References: [DRF schema deprecation](https://www.django-rest-framework.org/api-guide/schemas/),
[drf-spectacular](https://drf-spectacular.readthedocs.io/en/stable/),
[client generation considerations](https://drf-spectacular.readthedocs.io/en/stable/client_generation.html).

## 10. Test behavior, contracts, and real query characteristics

Continue pytest and pytest-django, with DRF `APIClient` for API requests. Use a real PostGIS test
database for geography, query, and serialization integration. Mock external dependencies and
failures where appropriate, not the ORM results that a query test is intended to verify.

Each endpoint plan includes concrete fixtures and independently stated expected results:

| Test group | Required evidence |
|---|---|
| Contract | Status, content type, fields/types, identifiers as strings, release metadata, and representative schema-valid responses |
| Release selection | Explicit dates; latest chosen by period then processing date; later processing of an older period; incomplete dates; unknown/no loaded release |
| Geographic rules | Each supported level agrees with independent fixture membership; no accidental prefix rule for place/subdivision; locations outside places remain accounted for |
| Status filters | All three flags; both status choices; wired default; unfiltered results; empty filtered area |
| Validation | Malformed and nonexistent keys distinguished; unknown/repeated query inputs; invalid page sizes and tokens |
| Pagination | First/last/empty pages; every expected ID exactly once; stable ordering; changed context rejected; newer period does not switch an active traversal |
| Replacement/deletion | Separate database connections verify behavior during commit; old cursors restart with 409; failed replacement preserves old traversal |
| Permissions | Anonymous reads; rejected public writes; denied non-staff operations; required operation permissions; real session/CSRF checks for future unsafe endpoints |
| Performance | Query-count regression checks at more than one page size; no N+1 growth; full-data query plans and measured payload limits |
| Consumers | React and Streamlit handle documented successes, empty data, validation failures, and restart-required responses |

Business read endpoints open a read-only repeatable-read transaction before their first data query.
Their integration tests use `transaction=True` so an enclosing pytest transaction does not prevent
setting isolation. Shared HTTP tests that do not open these snapshots can use ordinary database
fixtures. Commit/visibility tests also use independent connections; an enclosing test transaction
cannot prove those guarantees. Do not use forced authentication as the only test of an
authentication or CSRF policy.

Keep schema validation and selected response-to-schema checks separate from business assertions. A
response can match its schema and still count the wrong locations. Avoid testing a query by
calculating its expected answer with the same query helper.

Run existing backend formatting, lint, strict typing, migration checks, and fast tests through
`check.sh`. Keep full-data profiling separate, use a test database or documented disposable copy,
and run affected client checks when their contracts change. This guidance preserves the project's
current local-check policy and does not introduce CI.

References: [DRF testing](https://www.django-rest-framework.org/api-guide/testing/),
[Django test tools and query assertions](https://docs.djangoproject.com/en/5.2/topics/testing/tools/).

When adding an endpoint, consume the foundation in this order:

1. Settle its contract and owning domain app; add its route through the `api_v1` namespace.
2. Choose explicit access and method policies; retain session/CSRF enforcement for operations.
3. Validate query input with StrictQuerySerializer and keep domain validation in the owning app.
4. Reuse domain queries and explicit serializers; raise exceptions for shared error translation.
5. Annotate success, inputs, security, and applicable problem responses with drf-spectacular.
6. Test actual responses against the generated schemas using the APIClient/contract helpers in
   `core/tests/api/`, alongside independently stated behavior assertions and real session checks.
7. Update and review the production schema baseline intentionally, then run the backend and
   affected client checks. Add endpoint-specific data and performance evidence from the matrix
   above rather than treating the foundation tests as coverage of new business queries.

## 11. Implemented public read contracts

All three endpoints permit anonymous GET/HEAD/OPTIONS, reject writes with 405,
validate singleton inputs strictly, and set `Cache-Control: no-store` on successful
reads. Each response is evaluated and serialized in a short read-only repeatable-read
transaction; release identity, state coverage, totals, and page rows see the same
snapshot. Readers take no writer guard. No transaction spans HTTP requests.

Pagination inputs use ASCII integer notation before numeric bounds are applied.
Decimal forms such as `1.0` and `10.00`, exponent notation, and surrounding
whitespace are rejected with 400. Leading zeros are accepted; signed integers
still pass through the documented minimum/maximum checks. The shared
`IntegerQueryField` applies this policy to every pagination input, including the
summary endpoint's larger page-size cap. Response count fields remain integers.

### Releases

`GET /api/v1/releases/` accepts `page` (default 1, minimum 1) and `page_size`
(default 100, range 1–100). The JSON envelope has `count`, nullable `next` and
`previous` absolute URLs, and `results`. Results are ordered by descending `as_of`,
then descending `processed_on`, with these fields:

```json
{
  "filing_period": "D25",
  "as_of": "2025-12-31",
  "processed_on": "2026-09-29",
  "states": [{"code": "39", "name": "Ohio", "abbreviation": "OH"}]
}
```

State coverage is based on statuses, not on which nationwide boundaries happen
to be loaded. State entries are ordered by code. The release's surrogate key and
state polygons are not public fields. An empty catalog returns 200 with empty
results on page 1. An out-of-range subsequent page returns 404.

### Served/Not served summaries

`GET /api/v1/served-unserved/rollups/` accepts:

| Query input | Meaning |
|---|---|
| `level` | Required: `county`, `tract`, `block_group`, `block`, `h3_res8`, `place`, `county_subdivision` |
| `code` | Optional area identifier, validated against the level's `AREA_KEYS` form |
| `state` | Optional two-digit state code, limiting contributing rows |
| `as_of`, `processed_on` | Both strict `YYYY-MM-DD` dates or neither; omission selects latest |
| `flag` | `any`, `wired`, `terrestrial`; default `wired` |
| `page` | Integer >= 1; default 1 |
| `page_size` | Integer 1–1000; default 100 |

A census `code` and `state`, if both provided, must agree. A known state or census
area must exist in the boundary tables; a known H3 cell has a status in at least
one loaded release. Unknown but correctly formed keys, an unknown release, and
no release to resolve as latest are 404. Malformed keys, lone dates, and invalid
filters are 400.

The envelope has `count`, `next`, `previous`, and `results`, plus:

- `release`: the discovery representation above, including all its states even
  when the summary is state-filtered;
- `selection`: `level`, nullable `code`, nullable `state`, and resolved `flag`;
- `threshold`: `download_mbps: 100`, `upload_mbps: 20`;
- `boundary_vintage`: 2020 for census levels, null for H3;
- `summary_coverage`: the semantics below.

Results are ordered by ascending string `code`. Each result includes `locations`,
`any_100_20`, `wired_100_20`, `terrestrial_100_20`, and the selected flag's `served`
and `not_served` integer counts. The latter is `locations - served`. H3 rows are
grouped and summed across contributing states before counting/pagination, so a
border cell appears once. No `state` means all loaded contributions; selecting
one state counts only its contribution. No geometry is returned.

`summary_coverage` distinguishes these cases:

| Value | Meaning |
|---|---|
| `stored_rollups_only` | Collection of stored rows; omitted areas have no implied zero or completeness guarantee |
| `observed` | A selected code has stored rollup counts |
| `no_observations` | A selected known area has neither a rollup nor matching statuses in the selected release/filter |
| `outside_release_coverage` | A selected area's state, or an explicit H3 state filter, is absent from the release |

For a selected known code without a rollup, an indexed status existence probe
distinguishes absence of observations from missing derived data. Existing statuses
without that rollup yield 503 `service_unavailable`. The successful no-observations
response has empty results rather than invented zero counts. An H3 cell without
a state filter does not assert statewide coverage and uses `no_observations`
when absent from the selected release. Sparse collection reads do not scan all
statuses to certify rollup completeness; use `code` to investigate an omitted area.

Every pagination link contains the resolved dates, selection, flag, and page size.
A new latest release cannot switch a traversal to a different date pair. Replacement,
deletion, or rebuilding between page requests can change results; page-number
summaries provide no cross-request snapshot or generation check. Restart a summary
traversal when a coherent multi-page export is needed after such a change. The
stronger cursor contract for location drill-down remains issue #26.

### County GeoJSON

`GET /api/v1/geographies/county/?state=39` requires a known two-digit `state`.
Optional `page` defaults to 1 (minimum 1); `page_size` defaults to 100 (range 1–100).
Counties are ordered by GEOID. An empty known state's first page succeeds; unknown
states and subsequent pages beyond the collection return 404.

The response is `application/geo+json`, a FeatureCollection with `features` and
foreign members `count`, `next`, `previous`, `state`, and `boundary_vintage: 2020`.
Each Feature has a string county GEOID `id`, properties `{code, name}`, and WGS84
MultiPolygon `geometry`. IDs equal summary codes. Geometry is independent of data
releases, so a boundary feature must not be treated as evidence of observations.
Coordinates use longitude/latitude order, RFC 7946 ring winding, and 15 decimal
places of precision; no simplification or `crs` member is introduced.

The response cap is 5 MiB, including the envelope and negotiated indentation.
PostgreSQL checks the selected geometry size before transferring it into Python;
the completed representation is checked again. Exceeding the cap returns 400
`validation_error` with `/page_size` leaf code `geometry_payload_too_large`.
Request fewer features. If a single county exceeds the cap, this representation
cannot serve it; pagination alone cannot solve that case. See
[ADR 0018](decisions/0018-county-geojson-map-output.md).

GeoJSON successes use the registered GeoJSON media type. Requesting only
`application/json` from this resource yields 406; use `application/geo+json` or
`*/*`. All error responses still use `application/problem+json`.
