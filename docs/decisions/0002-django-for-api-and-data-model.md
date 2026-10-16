# 0002 — Django for the API and data model

- **Status:** Accepted
- **Date:** 2026-10-14

The API contract and testing conventions, including the choice of
`drf-spectacular` for generated OpenAPI, are recorded in
[ADR 0015](0015-rest-api-contract-and-tests.md). That decision supersedes the
schema-tooling assumption below; the Django, GeoDjango, and DRF architecture
remains in effect.

## Context

The API was first planned in TypeScript. It moved to Python so that one
language covers the data path from file to endpoint (see
[open-questions.md](../open-questions.md#project-and-process), P8). That left
the choice of Python framework open.

The project is designed for growth: more states, more data categories, more
views (see P7). The backend therefore needs:

- A spatial data model over PostGIS, with migrations that evolve with it
- A REST API that serves both summaries and map-ready geometry
- An admin interface for inspecting data and operating loads
- A natural home for background jobs ([0003](0003-celery-for-background-loads.md))

The candidates were **Django** (with GeoDjango and Django REST Framework) and
a lighter framework such as **FastAPI** with SQLAlchemy and GeoAlchemy2.

## Decision

The backend is a single **Django 5.2 LTS** project using:

- **GeoDjango** for spatial models and queries on PostGIS
- **Django REST Framework** for the API, with a generated OpenAPI schema
- **Django migrations** for the schema
- **Django admin** for inspecting data and operating loads

The ETL lives in the same project as a Django app, so the loader, the API and
the background jobs share one data model.

### Repository layout

| Directory | Contents |
|-----------|----------|
| `backend/` | Django project: data model, ETL, API, Celery tasks |
| `web/` | TypeScript/React map |
| `dashboard/` | Streamlit analyst dashboard ([0004](0004-streamlit-analyst-dashboard.md)) |
| `data/` | Download instructions; data files are never committed |

### Bulk loading

The ORM is not used to insert the ~4.5M location rows. The loader streams the
CSV into PostgreSQL with `COPY`, which is many times faster than row-by-row
inserts. The ORM handles everything else.

## Alternatives considered

- **FastAPI + SQLAlchemy.** Lighter and fast, but the admin, migrations,
  spatial model support and Celery integration would each be assembled by
  hand. The project would end up rebuilding much of what Django provides.
- **TypeScript API.** The original plan. Dropped so that Python covers the ETL
  and the API, with TypeScript kept for the front end.

## Consequences

- **Positive:** One data model serves the loader, the API, the admin and the
  background jobs. New data categories are new Django apps.
- **Positive:** Django's migrations, admin and DRF's schema generation come
  with the framework, so they cost little to adopt.
- **Negative:** Django is heavier than the API alone requires, and GeoDjango
  needs GDAL and GEOS in the backend image.
- **Supersedes:** the plain SQL migrations chosen in #8 (open question 7).
  Django migrations are the framework's own tool, so writing SQL by hand
  alongside them would add work rather than remove it. Raw SQL is still used
  where it is the better fit, such as `COPY` and materialized views, through
  Django migrations.
- **Follow-up:** The map output format (GeoJSON or vector tiles) is decided in
  #3.
