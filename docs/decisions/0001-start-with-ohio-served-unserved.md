# 0001 — Start with Served/Unserved data for Ohio

- **Status:** Accepted
- **Date:** 2026-10-14

## Context

The FCC National Broadband Map publishes several categories of downloadable
data for each state and filing period, including:

- **Availability data grouped by technology** (e.g., fiber, cable, DSL, fixed
  wireless, satellite) — one record per location, provider, and technology.
- **Served/Unserved data** — a summary classification of broadband service
  status by location.

Loading and visualizing every category at once would spread effort thinly and
delay a working end-to-end slice. A narrow first slice proves the full pipeline
(download → ETL → PostgreSQL → API → map) before it is widened.

## Decision

The first iteration will ingest and visualize **only the Served/Unserved data
for the state of Ohio**, from the December 2025 data release.

Other data categories and visualization types are **stretch goals** and will be
added only after the Ohio Served/Unserved slice works end to end.

## Stretch goals

- Availability by technology (fiber, cable, DSL, fixed wireless, satellite)
- Provider competition (number of providers per area)
- Advertised speed tiers
- Change between filing periods (e.g., June 2025 vs. December 2025)
- Additional states, or a nationwide view
- Natural-language querying (stubbed; requires the user's own API key)

## Consequences

- **Positive:** A smaller, well-understood dataset keeps the ETL, schema, and
  map simple and testable. The end-to-end architecture is proven early.
- **Positive:** One state keeps download size and load time reasonable for
  reviewers running the project locally.
- **Negative:** The first iteration cannot answer questions about technology
  mix, providers, or speeds.
- **Follow-up:** The schema and ETL should be designed so additional
  categories and states can be added without reworking the Served/Unserved
  pipeline. Each expansion gets its own decision record.
