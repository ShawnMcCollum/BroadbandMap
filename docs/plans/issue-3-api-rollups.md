# Issue #3: Served/Not served API implementation plan

Status: implemented and verified; awaiting pull-request review. The approved plan is recorded in
[issue #3](https://github.com/ShawnMcCollum/BroadbandMap/issues/3#issuecomment-6219882234).

## Starting point and decisions

- Local `main` was fast-forwarded to `160a671`, matching fetched `origin/main` on
  October 16, 2026. The working tree was clean before this plan was added.
- Issue #54 is completed. Releases retain their date-pair identity and may contain
  different subsets of states. Read `states_in_release`; sum H3 rows across states.
- The user selected county GeoJSON for the first map output. JSON summaries cover
  all seven existing `RollupLevel` values. Geometry and counts remain separate.
- Proposed branch: `feat/3-served-unserved-api`, following the repository's branch
  naming convention. No models, migrations, dependencies, ETL, or client changes.
- Use existing DRF, drf-spectacular, GeoDjango, and Problem Details infrastructure.

## HTTP contract

All three endpoints permit anonymous GET, HEAD, and OPTIONS only, explicitly set
`AllowAny` and disable authentication processing. Reject other methods with 405.
Use explicit serializers and `StrictQuerySerializer`; reject unknown parameters,
repeated singleton parameters, blank values, and out-of-range pagination with 400.
Successful responses set `Cache-Control: no-store`.

### Release discovery

`GET /api/v1/releases/?page=1&page_size=100`

`page` is an integer >= 1; `page_size` is an integer from 1 through 100, default
100. Order by descending `as_of`, then descending `processed_on`. Return the
page-number envelope `count`, `next`, `previous`, `results`. Each result has:

- `filing_period`: string;
- `as_of`, `processed_on`: ISO dates;
- `states`: list of `{code, name, abbreviation}`, in state-code order, obtained
  through `states_in_release`. Never include state geometry or release IDs.

No releases yields 200 with an empty first page. An out-of-range subsequent page
returns 404. Do not assume that the newest processing date means the latest period.

### Summary counts

`GET /api/v1/served-unserved/rollups/`

Accepted query fields:

| Field | Contract |
|---|---|
| `level` | Required existing `RollupLevel` choice |
| `code` | Optional string; validate against that level's `AREA_KEYS` pattern |
| `state` | Optional two-digit state code; restrict contributing rows to that state |
| `as_of`, `processed_on` | Both ISO dates or neither; omission resolves the latest release |
| `flag` | `any`, `wired`, or `terrestrial`; default `wired` |
| `page` | Integer >= 1; default 1 |
| `page_size` | Integer 1 through 1000; default 100 |

An unknown release, unknown state, or correctly formed but unknown area is 404.
A census area is known if its boundary exists. An H3 cell is known if it has a
status in any loaded release; hexadecimal formatting alone does not establish
that the dataset knows a cell. If both `code` and `state` select a census area,
require the code's state prefix to agree, otherwise return 400. H3 state filters
restrict contributions rather than establishing cell containment.

Read stored rollups, never aggregate raw statuses for summary counts. Clear
model default ordering before grouping. Group selected rollup rows by `code`,
sum `locations`, `any_100_20`, `wired_100_20`, `terrestrial_100_20`, and order by
ascending code before pagination. With no state filter, an H3 border cell includes
all loaded states' contributions; with a filter, it includes only that state.

Return `count`, `next`, `previous`, `results`, plus:

- `release`: the same public release representation as discovery;
- `selection`: `{level, code, state, flag}`, with null for omitted code/state;
- `threshold`: `{download_mbps: 100, upload_mbps: 20}`;
- `boundary_vintage`: `2020` at census levels, null for H3;
- `summary_coverage`: `stored_rollups_only` for collection requests;
  `observed`, `no_observations`, or `outside_release_coverage` for a selected code.

Each result contains the string `code`, the four integer counts named above,
and integer `served` and `not_served`. `served` is the count for the selected
flag; `not_served = locations - served`. Do not call it regulatory "unserved".
Do not include surrogate IDs, location records, or geometry.

For a selected known code with no rollup, use an indexed `statuses_in(...).exists()`
probe, narrowed to the requested state when supplied. If statuses exist, return
503 `service_unavailable` instead of fabricating zero counts. If there are no
statuses, return 200 with empty results: `no_observations` when its state is in
the release, otherwise `outside_release_coverage`. For H3 without a state filter,
use `no_observations`; a cell alone does not assert statewide coverage.

Collection responses intentionally enumerate stored observations. An omitted
area is not a zero and is not a completeness guarantee. The documented workflow
for verifying one missing area's status is the `code` query. This avoids scanning
millions of statuses to verify collection completeness on every request.

Pagination links explicitly retain the resolved date pair, selected flag, state,
level, code, and page size. Page-number summaries are fresh reads; they provide
no cross-request snapshot or replacement-detection guarantee. This limitation
must be documented. The stronger location cursor contract remains issue #26.

### County GeoJSON

`GET /api/v1/geographies/county/?state=39&page=1&page_size=100`

Require `state` as a two-digit known state code. Use integer `page >= 1` and
`page_size` from 1 through 100, default 100. Order by county GEOID. Unknown state
or out-of-range page is 404; an empty first page is a valid empty collection.

Return `application/geo+json`, with RFC 7946 `type: FeatureCollection`, `features`,
and foreign members `count`, `next`, `previous`, `state`, `boundary_vintage: 2020`.
Each Feature has string `id` equal to the county GEOID, properties `{code, name}`,
and MultiPolygon `geometry` in WGS84 longitude/latitude. Do not add a `crs` member.
Use the same county code as summaries so clients can join geometry and counts.
This endpoint describes boundaries independently of release coverage; it carries
no inferred availability or location coordinates.

Use GeoDjango database geometry functions to force RFC-compliant ring orientation
and emit GeoJSON at full available coordinate precision. Avoid simplification
and coordinate rounding in this first implementation. Enforce a 5 MiB compact,
uncompressed response limit, in addition to the 100-feature limit. Measure the
geometry byte total before materializing a page; a page over the cap returns 400
with a structured `/page_size` error code `geometry_payload_too_large` and advice
to request fewer features. Check the complete serialized response as well.
Bound serialization memory even if a single polygon is unusually large.

The downloaded Ohio county shapefile contains 88 counties and 122,526 coordinate
vertices. A read-only standard-library profile produced approximately 2.79 MB of
compact polygon geometry at six decimal places, with the largest approximately
97.6 KB. This is a planning estimate, not the final MultiPolygon response size.
Measure full-precision output during implementation before accepting the cap.
Record GeoJSON versus tiles in ADR 0018: county scale fits a bounded GeoJSON
response, uses existing tools, and gives both clients stable identifiers. Tile
infrastructure is deferred until finer-level or larger-area measurements justify it.

## Consistency and query behavior

Use a shared small context manager in `core/api/transactions.py` for each endpoint's
read orchestration: enter `transaction.atomic()` and issue
`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` before its first data
query. Resolve releases, collect state coverage, evaluate querysets, and serialize
within that transaction. This gives each response one database snapshot during
load, replacement, deletion, or rollup rebuild. Do not acquire writer locks or
hold transactions across requests. Exercise this using transaction-enabled tests
and independent database connections, rather than relying on ordinary atomic
blocks at read-committed isolation.

No serializer may perform an accidental per-result query. Summary counts and page
queries must not fetch polygon columns. Measure state-discovery query work
separately: the existing helper intentionally performs existence probes by state.
No new index is planned without real-data query-plan evidence.

## Files to create or change

Create:

- `backend/core/api/pagination.py`: strict page-number envelope/link construction;
- `backend/core/api/transactions.py`: request-scoped read snapshot;
- `backend/bdc/api/{__init__,serializers,queries,views,urls}.py`: release catalog,
  reusable date-pair validation/resolution, and explicit release metadata;
- `backend/served_unserved/queries.py`: grouped rollup reads and missing-area probes;
- `backend/served_unserved/api/{__init__,serializers,views,urls}.py`: summary HTTP contract;
- `backend/geography/api/{__init__,serializers,queries,renderers,views,urls}.py`:
  known-area lookup, bounded county selection, and GeoJSON response;
- `backend/bdc/tests/test_api.py`;
- `backend/served_unserved/tests/test_api.py`;
- `backend/geography/tests/test_api.py`;
- `backend/core/tests/api/test_read_support.py`;
- `backend/served_unserved/tests/test_api_consistency.py`;
- `backend/served_unserved/tests/test_api_schema.py`;
- `docs/decisions/0018-county-geojson-map-output.md`.

Change:

- `backend/core/api/urls.py`: include the three domain URL modules;
- `backend/core/tests/api/test_schema.py`: replace the empty-production-path
  expectation with the three implemented paths; preserve baseline/public-access checks;
- `backend/core/api/openapi.json`: intentionally generated and reviewed baseline;
- `backend/config/settings.py`: update schema description to describe implemented resources;
- `README.md`: routes, PowerShell examples, checks, and ADR link;
- `docs/api-guidelines.md`: implemented contracts and consistency/coverage limitations;
- `docs/journal.md`: the geometry measurement and resulting decision, if useful.

Keep test-only APIClient fixtures local to their owning modules; reuse the existing
root Ohio and West Virginia domain fixtures. No root fixture restructuring is needed.

## Acceptance tests

1. Release list: empty catalog; descending period before processing-date ordering;
   latest processing version within a period; different per-release state subsets;
   no internal IDs or polygons; strict pagination and invalid-page behavior.
2. All seven summary levels: directly create independently stated rollups with
   `locations=10`, `any=8`, `wired=4`, `terrestrial=6`; expect respective
   `(served, not_served)` of `(8,2)`, `(4,6)`, `(6,4)`. Default is wired.
3. H3 border cell: Ohio `(10,8,4,6)` and West Virginia `(5,5,2,3)` produce one
   cell `(15,13,6,9)` without a state filter; Ohio-only returns `(10,8,4,6)`.
4. Release selection: dates together, neither defaults latest, malformed or lone
   dates return 400, unknown pair/no loaded latest returns 404, and links retain
   explicit resolved dates even if a later release is subsequently loaded.
5. Geography validation: each AREA_KEYS shape; preserved leading zeros; unknown
   but well-formed code; state/code disagreement; unknown state; valid H3 format
   with no known statuses; state-filtered H3 contribution selection.
6. Coverage: known area with no observations returns an empty successful list;
   outside-release state is explicitly identified; existing statuses with no
   selected-area rollup return 503; collections identify their sparse semantics.
7. Pagination: sorted stable code order, exact grouped count, boundaries, previous
   and next links, invalid sizes including 0/negative/over-cap/noninteger, repeated
   and unknown parameters, and no duplicate H3 cells across pages.
8. Public access: anonymous, ordinary, and staff reads succeed; every write method
   is 405; correct Allow header, HEAD/OPTIONS behavior, no-store, request ID, and
   Problem Details media type for errors, including GeoJSON negotiation failures.
9. GeoJSON: FeatureCollection/Feature structure, string IDs matching summary codes,
   MultiPolygon coordinate order and orientation, no CRS member, no availability
   claims, full coordinate precision, deterministic county order, empty page,
   feature cap, byte cap, and a single oversized feature. Use small injected caps
   for deterministic boundary tests rather than oversized fixture files.
10. Schema: all three real production GET paths, exact required fields/types/media
    types/query constraints, explicit response/error schemas, no write operations,
    actual success/error payload validation, no test-only paths, zero warnings.
11. Queries: no summary polygon retrieval or per-row serializer queries; bound
    query growth as page rows increase; H3 grouping occurs before pagination.
12. Concurrency: a replacement/delete/state addition or rollup rebuild committed
    between release/coverage/count reads leaves one internally consistent response;
    the next request sees committed data; readers do not block the writer.

## Commands and review

Commands are PowerShell from the repository root. Docker is installed at
`C:\Program Files\Docker\Docker\resources\bin\docker.exe`, but is absent from
this session's PATH. Prefix calls with the full path where necessary.

```powershell
git switch -c feat/3-served-unserved-api
docker compose build backend
docker compose run --rm backend pytest bdc/tests/test_api.py served_unserved/tests/test_api.py geography/tests/test_api.py core/tests/api/test_read_support.py served_unserved/tests/test_api_consistency.py served_unserved/tests/test_api_schema.py
docker compose run --rm backend python manage.py check_api_schema --update
git diff -- backend/core/api/openapi.json
docker compose run --rm backend sh check.sh
```

The local Compose database currently has no `bdc_release` table. After implementation,
run migrations and load the available Ohio source file through the normal loader;
do not reset or delete volumes. Then run representative APIClient requests inside
the backend container for default county summaries, an explicit old release, H3
summaries, a fine-level page, and all 88 county polygons. Record bytes, query counts,
timings, and EXPLAIN plans in the review notes. Confirm counts against stored
rollups and the existing independent fixture expectations. Start the backend for
PowerShell HTTP smoke checks of JSON, GeoJSON, schema, and error responses.

At planning time, only Git synchronization, code/issue inspection, database
availability checks, and source profiling had run. Implementation verification
now includes 464 passing backend tests, final focused checks, HTTP smoke checks,
and both real Ohio releases. Measurements are recorded in `docs/journal.md`.

After approved implementation and passing checks, review the full diff and create
one issue-focused pull request for owner review/merge. Future implementation plans
may be written directly as issue comments, as authorized by the repository owner.

## References and rationale

- ADRs 0013, 0016, and 0017 and `docs/api-guidelines.md` establish release identity,
  explicit contracts, snapshot/coverage requirements, and cross-state H3 meaning.
- [DRF pagination](https://www.django-rest-framework.org/api-guide/pagination/)
  documents bounded page-number collections. Strict caps remain application policy.
- [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946.html) defines GeoJSON media type,
  coordinate order, ring orientation, and FeatureCollection structure.
- [GeoDjango functions](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/functions/)
  supply the existing database geometry conversion tools.

Explicit public fields prevent future model additions from silently changing the
contract. Reusing stored rollups keeps response work separate from source-data
volume. Separate county geometry avoids repeated polygon downloads for dashboard
tables or flag switches. State metadata and explicit missing-data semantics prevent
clients from mistaking partial release coverage for measured zero service.
