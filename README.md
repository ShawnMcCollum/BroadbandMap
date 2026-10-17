# BroadbandMap

An interactive map and analysis tool for FCC broadband availability data,
built with Python (Django, Celery, Streamlit), TypeScript (React), and
PostgreSQL/PostGIS.

> **Status:** Early development. The first milestone is an end-to-end view of
> broadband Served/Unserved status for Ohio. See
> [docs/decisions](docs/decisions/) for the design decisions behind the project.

## Data source

All data comes from the FCC National Broadband Map, **December 2025** release:

<https://broadbandmap.fcc.gov/data-download/nationwide-data?version=dec2025&pubDataVer=dec2025>

> **Note on the release date:** the FCC calls this the December 2025 release
> (filing period `D25`), and this project does too. The Ohio Served/Unserved
> file itself, however, is stamped with a later processing date
> (`bdc_39_fixed_broadband_served_unserved_D25_29sep2026.zip`).

The Served/Unserved file has no geometry. Boundaries for counties, census
blocks and other areas come from the U.S. Census Bureau's 2020 TIGER/Line
files
([ADR 0005](docs/decisions/0005-census-tiger-2020-boundaries.md)).

Data files are not included in this repository. Download instructions, and a
script that fetches the boundary files, are in
[`data/README.md`](data/README.md).

## Running locally

The only prerequisite is [Docker Desktop](https://www.docker.com/products/docker-desktop/).
Commands below are for PowerShell.

```powershell
git clone https://github.com/ShawnMcCollum/BroadbandMap.git
cd BroadbandMap
docker compose up --build
```

Every setting has a working default. To change one, copy `.env.example` to
`.env` and edit it.

The database container gets 256 MB of shared memory for PostgreSQL's
parallel queries, in place of Docker's default 64 MB
([ADR 0011](docs/decisions/0011-database-shared-memory.md)). A `db`
container created before this setting keeps 64 MB until Compose recreates
it, which the next `docker compose up` or `docker compose run` does. The
loaded data is kept.

| Service | URL | What it shows |
|---------|-----|---------------|
| Web (React) | <http://localhost:5173> | Ohio map shell and release readiness |
| Dashboard (Streamlit) | <http://localhost:8501> | **Test page:** stack connection check |
| API (Django) | <http://localhost:8000/api/health/> | Health of PostGIS, Redis and the Celery worker, as JSON |

### Check that the stack is connected

1. Wait for startup to finish. The first build takes a few minutes. The
   stack is ready when the log shows both of these lines:

   ```text
   web-1        |   ➜  Local:   http://localhost:5173/
   dashboard-1  |   You can now view your Streamlit app in your browser.
   ```

2. Open the web app: <http://localhost:5173>. It discovers loaded releases and
   checks whether the selected Ohio county-summary endpoint responds. This is
   a bounded first-page readiness check; it does not render county data or
   establish that every county has a summary. Diagnostics at
   [Diagnostics](http://localhost:5173/#/diagnostics) retains the API/PostGIS/Redis/worker
   health check.
3. Open the dashboard test page: <http://localhost:8501>
4. The dashboard test page should show four checks:

   ```text
   ✓ API
   ✓ PostGIS
   ✓ Redis
   ✓ Celery worker
   ```

The web navigation includes [Map](http://localhost:5173/#/map), Analyst dashboard,
[Ask (stub)](http://localhost:5173/#/ask) and
[AI settings](http://localhost:5173/#/settings/ai). The Ask and AI settings routes
explain that their forms are not available yet; Diagnostics is in the footer.
The dashboard opens in the same tab with its default filters. For a deployment
where the browser cannot reach `localhost`, set `VITE_DASHBOARD_URL` to the
browser-reachable dashboard base URL (HTTP or HTTPS, without credentials,
query or fragment). The default follows `DASHBOARD_PORT`. Restart or rebuild
the web service after changing Vite environment values; they are read when the
frontend starts/builds.

The shell starts with the latest loaded data period and processing date,
Ohio, and the Wired flag. Different processings remain selectable. Refresh and
returning to Map retain the selected date pair and flag while making fresh
reads. A disappeared release requires a new selection; a release without Ohio
shows that explicitly. API data stays in transient memory, with no browser
storage or persistent cache.

#### If something shows ✗

- **"The API cannot be reached"**: the backend is still starting or has
  stopped. Check it with `docker compose ps` and `docker compose logs backend`.
- **✗ next to one component**: that service is not running. Start it with
  `docker compose up -d <service>`, where `<service>` is `db`, `redis` or
  `worker`.
- **A page does not load**: another program may be using port 5173 or 8501.
  Set `WEB_PORT` or `DASHBOARD_PORT` in `.env` to a free port, then run
  `docker compose up` again.

### Load the Ohio data

1. Download the source files into `data/raw/`, as described in
   [`data/README.md`](data/README.md).
2. Run the data load:

   ```powershell
   docker compose run --rm backend python manage.py load_served_unserved
   ```

The first data load takes about six minutes: it loads the census boundaries
and the December 2025 release. If a file is missing or malformed, or the
loaded counts do not match the files, it stops with an error and leaves the
database unchanged. The application keeps running meanwhile, and no query
waits for a data load
([ADR 0013](docs/decisions/0013-release-scoped-data-loads.md)).

Only one data load, release deletion or rollup rebuild runs at a time. One
started while another is running stops at once, changes nothing, and names the
one running, for example `another writer is running: load of state 39 into
June 2025 (processed 2026-10-01), process 4321, since 2026-10-16 03:36:57 UTC;
try again once it has finished`
([ADR 0015](docs/decisions/0015-one-writer-at-a-time.md)).

Once the load has committed, the command vacuums and analyzes the loaded
tables, which takes a few seconds: the space of any rows the load deleted is
reused by the next one, and queries are planned with statistics that include
the new release
([ADR 0014](docs/decisions/0014-vacuum-after-each-data-load.md)).

Each data load also assigns every census block of its state to the place and
county subdivision that hold its internal point, then counts the Served/Not
served locations in every county, census tract, block group, census block, H3
cell, place and county subdivision. To rebuild those counts from the loaded
data without a full reload, run:

```powershell
docker compose run --rm backend python manage.py build_rollups
```

It rebuilds every loaded release, for every state in it, about half a minute
per release for Ohio, then vacuums and analyzes the rollups. To rebuild one
release, name it by the date its data describes and the date the FCC processed
it, for example `--as-of 2025-06-30 --processed-on 2026-10-01`.

A database loaded before places and county subdivisions had rollups has
census blocks without them, and data loads and `build_rollups` stop with an
error on it. A data load never reloads the census boundaries, so empty the
database and load it again: `docker compose down -v` removes the database and
everything in it.

Starting the backend applies any pending database migrations. On a database
loaded before [ADR 0012](docs/decisions/0012-location-placement-per-release.md),
the first start copies each location's census block and H3 cell onto its
Served/Unserved statuses. It takes about two minutes for Ohio, and no reload
is needed.

#### Add another release

Each data load adds one state's file to its release, and never changes
another release, or another state of the same release
([ADR 0017](docs/decisions/0017-national-releases-loaded-by-state.md)). To add
the June 2025 release, download it as described in
[`data/README.md`](data/README.md#3-a-second-release-optional). Since
`data/raw/` then holds two FCC files, name the one to load:

```powershell
docker compose run --rm backend python manage.py load_served_unserved --fcc-file bdc_39_fixed_broadband_served_unserved_J25_01oct2026.zip
```

It takes about three minutes, since the census boundaries are already
loaded. Releases can be loaded in any order. Loading a state into a release
that already holds it stops with an error; add `--replace` to load it again.
Until the replacement is committed, readers see the release as it was.

#### Add another state

A release is national: the FCC processes every state's file of it together,
and each data load adds one state. To add West Virginia beside Ohio, download
its file and its census boundaries as described in
[`data/README.md`](data/README.md#4-another-state-optional), then name the
file to load:

```powershell
docker compose run --rm backend python manage.py load_served_unserved --fcc-file bdc_54_fixed_broadband_served_unserved_D25_13oct2026.zip
```

The first load of a state also loads its census boundaries. It never changes
Ohio's rows. An H3 cell that crosses the state line has one row per state,
and its counts are the sum of the two. The FCC offers only the latest
processing of each release, so a file downloaded today can belong to a newer
processing than an Ohio file downloaded earlier, and so to a different
release. Download every state's file from the same processing to put them in
one release.

#### Delete a release

Deleting a release undoes its data load
([ADR 0006](docs/decisions/0006-data-model-for-locations-and-boundaries.md)).
Name the release by its two dates, as for `build_rollups`:

```powershell
docker compose run --rm backend python manage.py delete_release --as-of 2025-06-30 --processed-on 2026-10-01
```

The command asks for confirmation; add `--no-input` to skip the question. It
deletes the release with the statuses and rollups of every state in it, in one
transaction, and changes no other release. If no release has those dates, it
lists the dates of the releases that are loaded. Readers see the release until
the deletion commits, and no query waits for it. The command then vacuums and
analyzes the tables it changed, so the next data load reuses their space. For
Ohio, it takes about 15 seconds.

To delete one state from a release, such as a state loaded from the wrong
file, add `--state` with its two-digit FIPS code:

```powershell
docker compose run --rm backend python manage.py delete_release --as-of 2025-12-31 --processed-on 2026-10-13 --state 54
```

It deletes that state's statuses and rollups in the release, and changes no
other state or release. The state's census boundaries stay loaded, so loading
its file again does not reload them. Deleting the release's last state also
deletes the release; the confirmation question says so first. If the state
becomes the release's last while the question is open, nothing is deleted,
and the command asks you to run it again. If the release does not hold the
state, the command lists the states it holds. As for a whole release, the
deletion is one transaction, no query waits for it, and the tables it changed
are then vacuumed and analyzed. For Ohio, it takes about 15 seconds.

### Read the data through the API

The public, read-only API exposes loaded releases, Served/Not served summaries,
and county boundaries. The React shell reads releases and a bounded county
summary page; Diagnostics and the current dashboard use `/api/health/`.
Location drill-down uses signed cursors that detect release changes.

| Route | Response |
|---|---|
| `/api/v1/releases/` | Loaded release dates and the states each holds |
| `/api/v1/served-unserved/rollups/?level=county&state=39` | Ohio county counts, wired 100/20 by default |
| `/api/v1/geographies/county/?state=39` | County GeoJSON, with GEOIDs matching summary codes |
| `/api/v1/served-unserved/locations/?level=county&code=39049` | Locations behind Franklin County's summary, in FCC location ID order |

For example, from PowerShell after loading Ohio:

```powershell
Invoke-RestMethod 'http://localhost:8000/api/v1/releases/'
Invoke-RestMethod 'http://localhost:8000/api/v1/served-unserved/rollups/?level=county&state=39'
Invoke-RestMethod 'http://localhost:8000/api/v1/geographies/county/?state=39'
```

Summaries support `county`, `tract`, `block_group`, `block`, `h3_res8`, `place`,
and `county_subdivision`. Add `code` to select one area, and choose
`flag=any|wired|terrestrial`. `served` is the selected 100/20 flag's count;
`not_served` is the remaining locations, not a regulatory unserved classification.
H3 cells on state lines sum all loaded states unless `state` restricts them.

Omitting both `as_of` and `processed_on` selects the latest period, then its
latest processing version. Supplying dates requires both, in `YYYY-MM-DD` form.
Responses disclose the resolved release and its states; this is not a promise
of nationwide coverage. Summary pagination links pin those dates. Each request
uses one database snapshot, while separate pages are fresh reads and can change
after replacement or rebuilding.

Collections list stored rollups: a missing area does not mean zero locations or
zero service. Use a `code` query to distinguish no observations, a state outside
the release, and unavailable rollups (503). GeoJSON describes boundaries, not
release coverage; join its feature IDs to summary codes and leave missing
observations visibly unclassified.

Releases, summaries and boundaries are paginated with `count`, `next`, and
`previous`. Default `page_size` is 100, maximum 1,000 for summaries and 100 for
releases/boundaries.
County GeoJSON also has a 5 MiB response cap; request fewer features if exceeded.
Geometry is separate so tables and flag changes do not download polygons again.

Location drill-down requires `level` and `code`, with the same release, state
and flag selection as summaries. Add `status=served` or `status=not_served` to
filter the selected flag. It returns location IDs, block GEOIDs, H3 cells and
the three Boolean flags; it does not infer point coordinates. `area_coverage`
distinguishes observations from an area outside the release, before the optional
status filter.

Location pages default to 100 rows, maximum 1,000, with `next` and `previous`
links and no total count. Follow those links unchanged: they pin the selection
and resolved release. Any committed load, state deletion or rollup rebuild in
that release invalidates old cursors with 409 `dataset_changed`; restart without
the cursor. The generation is release-wide, so even another state's change
requires a restart. A failed write preserves a traversal. See
[ADR 0019](docs/decisions/0019-location-cursors.md).

The generated OpenAPI 3.0.3 document is available at
<http://localhost:8000/api/schema/>. It describes the implemented data and
natural-language resources, including validation and errors. The health endpoint
keeps its separate operational contract.

API views deny access until they explicitly choose a permission policy.
Public data views allow anonymous reads and expose no write methods. AI
configuration requires an active staff user with the declared operation
permissions, using session authentication and CSRF protection.

API errors use Problem Details JSON, with stable codes, structured validation
errors, and a request identifier for diagnosing unexpected failures. The
[API guidelines](docs/api-guidelines.md) explain the shared modules, error
contract, query validation, and how to add an endpoint.

### Natural-language query stub and AI settings

The backend provides a natural-language stub, with installation-wide AI settings
managed by an application administrator. It makes no provider requests or
broadband queries. Every answer says it is a stub; saved provider/model identifiers
have not been verified against a provider.

| Route | Access and purpose |
|---|---|
| `GET /api/v1/natural-language/` | Public enabled/disabled status and guidance |
| `GET /api/v1/natural-language/configuration/` | Authorized admin reads saved nonsecret settings and obtains a CSRF cookie |
| `PATCH /api/v1/natural-language/configuration/` | Authorized admin saves settings or replaces/removes the provider key |
| `POST /api/v1/natural-language/query/` | Public stub processes `{"question": "How many locations are served?"}` |

Configuration requires an active staff account with
`natural_language.manage_ai_configuration`; active staff superusers also qualify.
Account and permission assignment use the existing Django admin interface at
<http://localhost:8000/admin/>. Configuration requests use the administrator's
session; PATCH also requires a valid CSRF token.

Settings include provider/model identifiers, enable state, timeout (1–120 seconds,
default 30), and output limit (1–8,192 tokens, default 1,024). The provider key is
write-only: omit it to retain the saved key, supply a replacement to change it,
or use `clear_api_key: true` to remove it and disable the feature. Changing
provider requires replacement or explicit clearing. API responses show only
whether a key is configured and available, never the key itself.

Settings persist in PostgreSQL and apply on the next request. The application
automatically manages separate encryption material in the backend-only
`ai_secrets` Docker volume; configuring AI requires no provider-key `.env`
setting or container restart. Preserve both the database and secret volume in
deployment backups. Named volumes survive container recreation, but are not
backups; `docker compose down -v` destroys this installation state too.

If encryption material is lost or corrupted, AI stays unavailable rather than
silently discarding the saved credential. An administrator can explicitly clear
and replace the provider key to recover; deployment operators can instead
restore matching database and secret-volume backups.

The web frontend's administrator settings screen and question panel are planned
in [#32](https://github.com/ShawnMcCollum/BroadbandMap/issues/32); this change
provides their backend contract. The completed frontend must let application
administrators configure AI through normal sign-in without terminal access.
Provider integration and access/cost policies for paid calls remain future work.
See [ADR 0020](docs/decisions/0020-natural-language-query-stub.md).

### Checks

Formatting, lint, type checks and tests run inside the containers:

```powershell
docker compose run --rm backend sh check.sh
docker compose run --rm --no-deps dashboard sh check.sh
docker compose run --rm --no-deps web pnpm check
```

The backend checks also generate and validate OpenAPI, treating warnings as
failures, and compare it with the reviewed baseline in
`backend/core/api/openapi.json`. To accept an intentional API contract change,
generate the baseline and review its diff before rerunning checks:

```powershell
docker compose run --rm backend python manage.py check_api_schema --update
git diff -- backend/core/api/openapi.json
docker compose run --rm backend python manage.py check_api_schema
```

After dependency changes, rebuild the backend image with
`docker compose build backend` before running its checks. The
[API guidelines](docs/api-guidelines.md#9-generate-and-review-openapi-with-the-implementation)
include the standalone schema export command and focused API test command.

The full-data suite loads the real files in `data/raw/` and checks the result
against independent readers of those files. It takes about 12 minutes:

```powershell
docker compose run --rm backend pytest -m full_data
```

## Design decisions

Architectural and scope decisions are recorded in
[docs/decisions](docs/decisions/):

- [0001 — Start with Served/Unserved data for Ohio](docs/decisions/0001-start-with-ohio-served-unserved.md)
- [0002 — Django for the API and data model](docs/decisions/0002-django-for-api-and-data-model.md)
- [0003 — Celery for background data loads](docs/decisions/0003-celery-for-background-loads.md)
- [0004 — Streamlit for an analyst dashboard](docs/decisions/0004-streamlit-analyst-dashboard.md)
- [0005 — Census TIGER/Line 2020 for boundary geometries](docs/decisions/0005-census-tiger-2020-boundaries.md)
- [0006 — Data model for locations and boundaries](docs/decisions/0006-data-model-for-locations-and-boundaries.md)
- [0007 — Loading and verifying the source data](docs/decisions/0007-loading-and-verifying-the-source-data.md)
- [0008 — Served/Not served rollups by geography](docs/decisions/0008-served-not-served-rollups.md)
- [0009 — Rollups by tract, block group, block and H3 cell](docs/decisions/0009-rollups-for-finer-levels.md)
- [0010 — Rollups by place and county subdivision](docs/decisions/0010-place-and-county-subdivision-rollups.md)
- [0011 — Shared memory for the database container](docs/decisions/0011-database-shared-memory.md)
- [0012 — A location's block and H3 cell are stored per release](docs/decisions/0012-location-placement-per-release.md)
- [0013 — A data load adds one release](docs/decisions/0013-release-scoped-data-loads.md)
- [0014 — Vacuum and analyze after each data load](docs/decisions/0014-vacuum-after-each-data-load.md)
- [0015 — One writer of the loaded tables at a time](docs/decisions/0015-one-writer-at-a-time.md)
- [0016 — REST API contract and tests](docs/decisions/0016-rest-api-contract-and-tests.md)
- [0017 — A release is national, and a data load adds one state](docs/decisions/0017-national-releases-loaded-by-state.md)
- [0018 — County GeoJSON for initial map output](docs/decisions/0018-county-geojson-map-output.md)
- [0019 — Location drill-down with release-wide cursor generations](docs/decisions/0019-location-cursors.md)
- [0020 — Natural-language stub with persistent application configuration](docs/decisions/0020-natural-language-query-stub.md)
- [0021 — An index only where a query reads through it](docs/decisions/0021-indexes-only-where-queries-read.md)
- [0022 — Status admin pages read an index](docs/decisions/0022-status-admin-pages-read-an-index.md)
- [0023 — Status admin searches a block or a cell in every release](docs/decisions/0023-status-admin-searches-blocks-and-cells.md)

The adopted REST API conventions and implementation guidance are in
[docs/api-guidelines.md](docs/api-guidelines.md).

The approved frontend layouts and interaction conventions for issue #71 are in
the [frontend design](docs/plans/frontend-design.md), with
[responsive wireframes](docs/plans/frontend-wireframes.html) that open directly
in a browser. The [frontend guidelines](docs/frontend-guidelines.md) collect
shared labels, selection/error behavior, accessibility, and implementation
boundaries. The React shell now implements release selection and readiness as
described in the [Issue #72 plan](docs/plans/issue-72-react-shell.md). The county
map, analyst workflows, and AI forms remain planned; the dashboard is still a
stack check.

Questions still being worked out, and how earlier ones were answered, are kept
in [docs/open-questions.md](docs/open-questions.md). Day-to-day reasoning is
logged in [docs/journal.md](docs/journal.md).

## Development approach

This project is developed with AI assistance. The workflow follows a few rules:

- **One issue per session.** Each working session is focused on a single
  issue and ends in a single pull request. Keeping each session narrow keeps
  the working context to a minimum and makes every change easy to review.
- **One branch per issue.** All issue work is done on a branch, preferably
  one branch per issue, named after the issue (e.g., `docs/6-branch-pr-workflow`).
- **Pull requests only.** All merges to `main` go through a pull request.
  Nothing is committed directly to `main`.

- **Simple tools.** Keep tools as simple as they can be, without ignoring a
  ridiculously easy solution that removes real pain.

The [API guidelines](docs/api-guidelines.md) document the contract and testing
conventions for endpoint work.

Together these leave a clear trail from issue to branch to decision to code.

## License

[MIT](LICENSE)
