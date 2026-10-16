# REST API guidelines

These guidelines define the API conventions adopted by
[ADR 0015](decisions/0015-rest-api-contract-and-tests.md).
They apply as business endpoints are implemented in #3 and #26; operational API work is tracked in
#15/#45,
and multi-state release identity in #54.

The resource paths and numerical starting limits below are project guidance for endpoint planning.
Framework behavior is identified separately where relevant. Endpoint plans settle exact inputs,
response fields, and implementation details before the corresponding endpoints are built. The
examples do not imply that these business endpoints already exist.

## 1. Organize around the existing domains

Keep models, domain rules, and database query functions in their existing Django apps. Use small
`api/` packages inside the relevant apps rather than a second, competing domain model:

```text
backend/
  core/api/               # shared errors, pagination, and request conventions
  bdc/api/                # release discovery and release input validation
  geography/api/          # area metadata and later map representations
  served_unserved/api/    # summary and location endpoints
```

Create a module only when an endpoint needs it. Keep tests with the owning app under its existing
`tests/` package. `config/urls.py` composes the app URL configurations.

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

Illustrative resource families:

| Resource | Proposed route | Responsibility |
|---|---|---|
| Releases | `GET /api/v1/releases/` | Discover loaded periods, processing dates, and geographic coverage |
| Area metadata | `GET /api/v1/geographies/{level}/{code}/` | Describe a known area without automatically returning its polygon |
| Summary counts | `GET /api/v1/served-unserved/rollups/` | Read stored rollups for one release and geographic level |
| Area locations | `GET /api/v1/served-unserved/locations/` | Read bounded, paginated statuses behind one area |

These families guide later endpoint plans. #3 must settle exact summary selection parameters and map
output before implementation. No operational HTTP routes are added by #33.

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
- Return geographic coverage explicitly. Currently it is one state per database; a date pair must
  not imply nationwide completeness. #54 decides the future cross-state model.
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
  zero service: #3 must define how summary coverage distinguishes no observations from unavailable
  derived data.

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

Proposed semantics:

| Status | Meaning |
|---|---|
| 200 | Successful read, including an empty filtered collection |
| 400 | Malformed dates, incomplete date pair, invalid level/code form, invalid filter, or malformed cursor |
| 403 | An operation denied under the planned session-based administrator access model |
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

Ordinary summary and location JSON should omit polygon geometry. Separate geometry representation
from summary counts so tables do not download large shapes. #3 should compare county GeoJSON
payloads with the needs of the first map before choosing its initial map format; block-level or
nationwide tiles remain a later measured decision.

If GeoJSON is selected, use RFC 7946 Feature/FeatureCollection structures, WGS84 longitude/latitude
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

Keep operational actions in authenticated Django admin or existing commands until #15 needs an API.
Any later operational endpoint requires authentication, staff status, and the relevant operation
permission. `IsAdminUser` alone means `is_staff`; it does not check a particular model or operation
permission. Do not confuse authenticated users with administrators.

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

Use DRF with `drf-spectacular` when #3 introduces the business API. DRF's built-in OpenAPI
generation is deprecated and its documentation recommends this replacement. This updates ADR 0002's
tooling assumption without changing its Django/DRF architecture.

Generate an OpenAPI 3 schema from the implementation, supplementing inference with explicit query
serializers, error responses, cursor envelopes, examples, and stable operation IDs. Start with
OpenAPI 3.0.3 for broad client tooling compatibility; revisiting that version requires checking both
clients. Document identifiers as strings, geographic enumerations, date formats, public security,
and administrator operations accurately.

Use `python manage.py spectacular --file /tmp/broadbandmap-openapi.yaml --validate --fail-on-warn`
in the container once the dependency exists. Schema generation and validation become part of local
checks. Review a generated schema diff with endpoint changes, with a checked-in baseline updated
intentionally. Code remains the implementation source; do not maintain a second independent
handwritten schema.

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

Use normal transactional database fixtures for ordinary endpoint tests. Use `transaction=True` or
equivalent true transaction tests and independent connections for commit/visibility scenarios; an
enclosing test transaction cannot prove those guarantees. Do not use forced authentication as the
only test of an authentication or CSRF policy.

Keep schema validation and selected response-to-schema checks separate from business assertions. A
response can match its schema and still count the wrong locations. Avoid testing a query by
calculating its expected answer with the same query helper.

Run existing backend formatting, lint, strict typing, migration checks, and fast tests through
`check.sh`. Keep full-data profiling separate, use a test database or documented disposable copy,
and run affected client checks when their contracts change. This guidance preserves the project's
current local-check policy and does not introduce CI.

References: [DRF testing](https://www.django-rest-framework.org/api-guide/testing/),
[Django test tools and query assertions](https://docs.djangoproject.com/en/5.2/topics/testing/tools/).
