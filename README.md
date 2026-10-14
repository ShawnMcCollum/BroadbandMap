# BroadbandMap

An interactive map and analysis tool for FCC broadband availability data,
built with TypeScript, Python, and PostgreSQL/PostGIS.

> **Status:** Early development. The first milestone is an end-to-end view of
> broadband Served/Unserved status for Ohio. See
> [docs/decisions](docs/decisions/) for the design decisions behind the project.

## Data source

All data comes from the FCC National Broadband Map, **December 2025** release:

<https://broadbandmap.fcc.gov/data-download/nationwide-data?version=dec2025&pubDataVer=dec2025>

Data files are not included in this repository. Download instructions will be
provided in [`data/`](data/) as the loading pipeline is built.

## Design decisions

Architectural and scope decisions are recorded in
[docs/decisions](docs/decisions/):

- [0001 — Start with Served/Unserved data for Ohio](docs/decisions/0001-start-with-ohio-served-unserved.md)

## Development approach

This project is developed with AI assistance. Work is organized so that each
working session is focused on a single issue and ends in a single pull
request. Keeping each session narrow keeps the working context to a minimum,
makes every change easy to review, and leaves a clear trail from issue to
decision to code.
