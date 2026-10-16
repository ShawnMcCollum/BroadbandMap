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
| Web (React) | <http://localhost:5173> | **Test page:** stack connection check |
| Dashboard (Streamlit) | <http://localhost:8501> | **Test page:** stack connection check |
| API (Django) | <http://localhost:8000/api/health/> | Health of PostGIS, Redis and the Celery worker, as JSON |

### Check that the stack is connected

1. Wait for startup to finish. The first build takes a few minutes. The
   stack is ready when the log shows both of these lines:

   ```text
   web-1        |   ➜  Local:   http://localhost:5173/
   dashboard-1  |   You can now view your Streamlit app in your browser.
   ```

2. Open the web test page: <http://localhost:5173>
3. Open the dashboard test page: <http://localhost:8501>
4. Both pages should show four checks:

   ```text
   ✓ API
   ✓ PostGIS
   ✓ Redis
   ✓ Celery worker
   ```

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
one running, for example `another writer is running: load of June 2025
(processed 2026-10-01), process 4321, since 2026-10-16 03:36:57 UTC; try again
once it has finished`
([ADR 0015](docs/decisions/0015-one-writer-at-a-time.md)).

Once the load has committed, the command vacuums and analyzes the loaded
tables, which takes a few seconds: the space of any rows the load deleted is
reused by the next one, and queries are planned with statistics that include
the new release
([ADR 0014](docs/decisions/0014-vacuum-after-each-data-load.md)).

Each data load also assigns every census block to the place and county
subdivision that hold its internal point, then counts the Served/Not served
locations in every county, census tract, block group, census block, H3 cell,
place and county subdivision. To rebuild those counts from the loaded data
without a full reload, run:

```powershell
docker compose run --rm backend python manage.py build_rollups
```

It rebuilds every loaded release, about half a minute each for Ohio, then
vacuums and analyzes the rollups. To rebuild one release, name it by the date
its data describes and the date the FCC processed it, for example
`--as-of 2025-06-30 --processed-on 2026-10-01`.

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

Each data load adds one release beside those already loaded, and never
changes another. To add the June 2025 release, download it as described in
[`data/README.md`](data/README.md#3-a-second-release-optional). Since
`data/raw/` then holds two FCC files, name the one to load:

```powershell
docker compose run --rm backend python manage.py load_served_unserved --fcc-file bdc_39_fixed_broadband_served_unserved_J25_01oct2026.zip
```

It takes about three minutes, since the census boundaries are already
loaded. Releases can be loaded in any order. Loading a release that is
already loaded stops with an error; add `--replace` to load it again. Until
the replacement is committed, readers see the release as it was.

#### Delete a release

Deleting a release undoes its data load
([ADR 0006](docs/decisions/0006-data-model-for-locations-and-boundaries.md)).
Name the release by its two dates, as for `build_rollups`:

```powershell
docker compose run --rm backend python manage.py delete_release --as-of 2025-06-30 --processed-on 2026-10-01
```

The command asks for confirmation; add `--no-input` to skip the question. It
deletes the release with its statuses and rollups, in one transaction, and
changes no other release. If no release has those dates, it lists the dates of
the releases that are loaded. Readers see the release until the deletion
commits, and no query waits for it. The command then vacuums and analyzes the
tables it changed, so the next data load reuses their space. For Ohio, it
takes about ten seconds.

### API foundation

The shared REST API infrastructure is available for endpoint work. New data
routes will live under `/api/v1/`; summaries and locations are still being
implemented in #3 and #26. The current clients continue to use `/api/health/`.

The generated OpenAPI 3.0.3 document is available at
<http://localhost:8000/api/schema/>. Its business paths are initially empty;
it describes implemented resources as they are added. The health endpoint
keeps its separate operational contract.

API views deny access until they explicitly choose a permission policy.
Public data views allow anonymous reads and expose no write methods. Future
operations require an active staff user with the declared operation
permissions, using session authentication and CSRF protection.

API errors use Problem Details JSON, with stable codes, structured validation
errors, and a request identifier for diagnosing unexpected failures. The
[API guidelines](docs/api-guidelines.md) explain the shared modules, error
contract, query validation, and how to add an endpoint.

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

The adopted REST API conventions and implementation guidance are in
[docs/api-guidelines.md](docs/api-guidelines.md).

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
