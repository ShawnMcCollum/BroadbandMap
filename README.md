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

The data load takes about six minutes and replaces any data loaded before. The
application keeps running meanwhile. If a file is missing or malformed, or the
loaded counts do not match the files, it stops with an error and leaves the
database unchanged.

Each data load also counts the Served/Not served locations in every county. To
rebuild those counts from the loaded data without a full reload, run:

```powershell
docker compose run --rm backend python manage.py build_rollups
```

### Checks

Formatting, lint, type checks and tests run inside the containers:

```powershell
docker compose run --rm backend sh check.sh
docker compose run --rm --no-deps dashboard sh check.sh
docker compose run --rm --no-deps web pnpm check
```

The full-data suite loads the real files in `data/raw/` and checks the result
against independent readers of those files. It takes about 13 minutes:

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

Together these leave a clear trail from issue to branch to decision to code.

## License

[MIT](LICENSE)
