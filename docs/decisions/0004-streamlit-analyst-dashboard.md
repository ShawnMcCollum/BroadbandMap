# 0004 — Streamlit for an analyst dashboard

- **Status:** Accepted
- **Date:** 2026-10-14

## Context

The React map ([#4](https://github.com/ShawnMcCollum/BroadbandMap/issues/4))
answers "where?" It is the right tool for exploring the data geographically.
Analysts also need tables, charts, comparisons and exports. Building those in
React is slow, and the work would duplicate what Python data tools already do
well.

## Decision

Add an analyst dashboard built with **Streamlit**, as its own Docker Compose
service in `dashboard/`.

- The dashboard reads data **only through the Django API**. It has no
  database access. The API stays the single, documented contract for every
  client, and the dashboard tests that contract as a second consumer
  alongside the web app.
- It focuses on tables, charts, filters and CSV export of summary views. The
  map stays in the React app.

Implementation is tracked in
[#16](https://github.com/ShawnMcCollum/BroadbandMap/issues/16).

## Alternatives considered

- **Build the analysis views in React.** One front end instead of two, but
  much more code for charts and tables.
- **Streamlit reading the database directly.** Faster to build, but it would
  bypass the API and spread query logic across two places.
- **Jupyter notebooks.** Good for one-off analysis, but not a shared,
  always-running tool.

## Consequences

- **Positive:** Analyst views take little code and are written in Python, next
  to the rest of the data work.
- **Positive:** A second API client keeps the API honest. Anything the
  dashboard needs must be available from a documented endpoint.
- **Negative:** One more service and one more UI to keep consistent with the
  map (labels, attribution, the 100/20 wording).
- **Negative:** Large location-level queries go through the API's paging,
  which is slower than direct SQL. Summary views are the intended use.
