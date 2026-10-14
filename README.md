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

The Served/Unserved file has no geometry. Mapping by county or census block
needs separate Census boundary files
([#9](https://github.com/ShawnMcCollum/BroadbandMap/issues/9)).

Data files are not included in this repository. Download instructions will be
provided in [`data/`](data/) as the loading pipeline is built.

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
| Web (React) | <http://localhost:5173> | Stack check page |
| Dashboard (Streamlit) | <http://localhost:8501> | Stack check page |
| API (Django) | <http://localhost:8000/api/health/> | Health of PostGIS, Redis and the Celery worker |

### Checks

Formatting, lint, type checks and tests run inside the containers:

```powershell
docker compose run --rm backend sh check.sh
docker compose run --rm --no-deps dashboard sh check.sh
docker compose run --rm --no-deps web pnpm check
```

## Design decisions

Architectural and scope decisions are recorded in
[docs/decisions](docs/decisions/):

- [0001 — Start with Served/Unserved data for Ohio](docs/decisions/0001-start-with-ohio-served-unserved.md)
- [0002 — Django for the API and data model](docs/decisions/0002-django-for-api-and-data-model.md)
- [0003 — Celery for background data loads](docs/decisions/0003-celery-for-background-loads.md)
- [0004 — Streamlit for an analyst dashboard](docs/decisions/0004-streamlit-analyst-dashboard.md)

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
