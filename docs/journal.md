# Development journal

A running log of the reasoning behind day-to-day work: what was tried, what
was learned, and why things changed direction. Formal decisions are recorded
in [decisions/](decisions/), and unresolved questions are in
[open-questions.md](open-questions.md).

Newest entries first.

---

## 2026-10-16 — Ohio county map and accessible detail

- Issue #73 replaces the one-row readiness probe with complete county summaries
  and a tile-free MapLibre map. The existing selection owner drives map, county
  selector, table and detail; changing a flag updates colors without downloading
  the 3.34 MB geometry again or rebuilding the WebGL map.
- Missing summaries remain separate from observed zero service. A selected
  missing county gets one exact-code diagnosis. If that later read now has an
  observation, an explicit Refresh updates every view together instead of mixing
  new detail counts into an older map/table collection.
- Real screenshots caught two gaps that DOM mocks cannot prove: narrow geographic
  pan limits cropped Ohio in a wide viewport, and ID-based worker filters omitted
  hatch/selection features. Fitting the viewport before constraining it and
  filtering on the string county-code property resolved them. Promoted GEOIDs
  remain feature-state keys. Actual hatch pixels were checked afterward.
- The [approved plan and verification](plans/issue-73-county-map.md) records 134
  passing tests, the Docker build, real 88-county Edge rendering, unchanged
  worker/geometry counts across filters, keyboard/narrow layout checks, context
  loss recovery and browser-local failure simulations. The MapLibre bundle-size
  warning remains visible as a measured future optimization opportunity.

## 2026-10-16 — React shell and release selection

- Issue #72 replaces the React health-only landing page with the approved shell,
  date-pair and technology controls, loaded-state coverage and a real, bounded
  county-summary readiness check. The county map, analytical views and AI forms
  remain with their feature issues; diagnostics keeps the existing health API.
- A single root selection owner prevents dates and flags from drifting between
  consumers. Complete release discovery keeps distinct processing versions
  selectable. Abort signals reduce obsolete work, while request and selection
  identities prevent late results from appearing beneath newer labels, including
  refresh, route re-entry and a return to an earlier selection.
- The owner selected the bounded readiness read and approved the concrete
  [implementation plan](plans/issue-72-react-shell.md) before implementation.
  No dependency or persistent browser cache is needed for this slice.
- A real proxy check found that Vite's string target enables `changeOrigin`:
  Django emitted `http://backend:8000` pagination links even for web-origin
  requests. The owner approved the minimal explicit `changeOrigin: false`
  correction. Pagination now preserves the browser Host and port; the client
  still rejects unexpected origins and endpoint paths rather than rewriting them.
- Real Microsoft Edge checks covered release/flag request parameters, a fetched
  next release page through the web proxy, skip-link and native-select keyboard
  behavior, route heading focus, Back selection retention, diagnostics and
  same-tab dashboard navigation. Widths 1280/390/320 and 200% text resizing had
  no body overflow. Diagnostics correctly showed the existing stopped worker;
  no services or source data were changed to fabricate a health scenario.
- Docker web checks passed formatting, lint, TypeScript and 64 tests; the
  production build and Compose validation passed. Final review corrected stale
  coverage metadata, old-result/new-404 precedence and malformed-response request
  IDs, with focused regressions. Full outcomes are recorded in the plan. Browser
  success uses the existing API; exceptional coverage, malformed responses and
  ignored-abort races use fixtures. This does not claim map, authentication or
  complete accessibility verification.

---

## 2026-10-16 — Paging through the locations behind a summary

- Issue #26 reuses the summary API's geography rules and release metadata for
  location drill-down at all seven levels. Coverage is reported before the
  optional status filter, so an empty filter is distinguishable from an area
  with no observations or a state outside the release.
- A release ID stopped being a valid generation token when loading became
  state-scoped: replacement, state addition and deletion can keep that ID.
  The selected release-wide counter is advanced by each writer in its existing
  transaction. Real-writer tests verify committed changes, rollbacks, and an
  API request reading while a second connection commits a write.
- Keyset pagination alone did not fix bad query plans. PostgreSQL sometimes
  assumed it would quickly find the requested area in location-ID order and
  scanned millions of unrelated locations. Explicitly sorting the numeric
  identity expression `location_id + 0` lets existing geography indexes filter
  first. Measured first-page SQL for the largest county, place and subdivision
  fell from about 1.5–2.3 seconds to 86–98 milliseconds. The tradeoff is scanning
  the area's candidates for the sort, including on deep pages; the reasoning,
  plans and limitations are recorded in
  [ADR 0019](decisions/0019-location-cursors.md).
- Validation passed 590 fast backend tests plus the dedicated full-Ohio source
  reconciliation and profiling test (4,542,350 locations). The running API also
  served an initial filtered page and its next link over HTTP. Full-data timings,
  including the cold first request, are recorded in ADR 0019.

---

## 2026-10-16 — Exposing stored rollups and county geometry

- Issue #3 builds on the shared API foundation and the multi-state release
  decision. Release discovery discloses actual states; H3 border cells sum
  contributions before pagination. Public identifiers remain strings and release
  dates remain independent of database row IDs.
- County GeoJSON was selected for the first map. Profiling the source file found
  88 counties and 122,526 vertices. The implemented full-precision response is
  3,344,412 bytes; county summary JSON is 12,251 bytes. Separate geometry means
  dashboard tables and flag changes can request counts without downloading shapes.
  [ADR 0018](decisions/0018-county-geojson-map-output.md) records the choice.
- Missing rollups cannot safely mean zero. Collections explicitly list stored
  observations; a selected code probes for source statuses when its rollup is
  absent, distinguishing no observations from unavailable derived data. Boundaries
  alone do not establish coverage in a release.
- An ordinary atomic block does not make multiple reads one PostgreSQL snapshot.
  Read endpoints use short read-only repeatable-read transactions. Tests with
  independent connections verify old-but-consistent responses while replacements,
  deletion, state additions, and rollup rebuilding commit without reader blocking.
- The normal loader reconciled 4,542,350 Ohio December 2025 locations. County API
  totals also matched an independent raw-status aggregate: 4,542,218 any,
  4,244,855 wired, and 4,393,052 terrestrial locations served at 100/20.
- Loading June 2025 alongside it reconciled 4,552,967 locations. HTTP checks
  confirmed that explicit June requests return that total, while default reads
  and pagination still select December, despite June's later processing date.

Representative local request measurements after loading December 2025:

| Request | Rows returned | Bytes | SQL statements | Elapsed |
|---|---:|---:|---:|---:|
| Ohio county summaries | 88 | 12,251 | 9 | 9.5 ms |
| First H3 page | 100 | 12,779 | 8 | 69.2 ms |
| H3 page 100 | 100 | 12,920 | 8 | 51.3 ms |
| First block page, size 1000 | 1000 | 124,277 | 8 | 130.4 ms |
| Ohio county GeoJSON | 88 | 3,344,412 | 7 | 644.7 ms |

These are individual development-machine observations, not timing guarantees.
SQL counts include transaction begin/isolation/commit statements. EXPLAIN ANALYZE
used the existing rollup unique index for summaries and the release/cell index
for an H3 status lookup. The first H3 row page took about 0.2 ms in PostgreSQL;
page 100 took about 8.7 ms, while grouped total counts add work to each HTTP
request. No new index or caching policy was justified by these measurements.

## 2026-10-14 — Sourcing boundary data

- The FCC file has no geometry, so boundary files had to be sourced before the
  loader (#2) could start (#9). Census TIGER/Line 2020 was chosen; the reasons
  are in [ADR 0005](decisions/0005-census-tiger-2020-boundaries.md).
- The guiding idea: **fetch broadly, load narrowly.** Raw files are cheap to
  load later, while sourcing and documenting a new dataset is the harder part.
  Every geography that could plausibly be useful is downloaded now, and the
  loader decides what to populate.
- Download size was the only real cost. Nothing in `data/` is committed, so
  Git LFS was considered and not needed. The one large outlier, nationwide ZIP
  code areas (528 MB), was made opt-in.
- The first map will be the smallest useful view: Served/Not served by
  county. #2 was updated to say so.

## 2026-10-14 — Choosing the application stack

- The open stack questions were settled in ADRs 0002–0004 (#14): Django for
  the API and data model, Celery for data loads, Streamlit for an analyst
  dashboard.
- Simplicity still matters, but each tool here replaces something that would
  otherwise be built by hand: the admin and migrations, load tracking, and
  chart-heavy analysis views.
- Django and Streamlit build on existing experience. **Celery is new to the
  project's author.** It is adopted deliberately, to show how AI-assisted
  development shortens the path from learning a tool to using it well in
  production.
- Two earlier answers from #8 were superseded and marked as such in
  [open-questions.md](open-questions.md): plain SQL migrations gave way to
  Django migrations, and the one-shot ETL service gave way to Celery tasks.
- Issues #1, #2 and #3 were rewritten for the new stack. #15 (Celery loads) and
  #16 (Streamlit dashboard) were opened.

## 2026-10-14 — Project-level questions

- Before more feature work, the project's goals and working conventions were
  written down (#12), so every later session starts from the same
  understanding. The answers are in
  [open-questions.md](open-questions.md#project-and-process).
- The main change in direction: **the API moves from TypeScript to Python.**
  Python then covers both the ETL and the API, and TypeScript stays in the web
  front end. #1 and #3 will need updating once the framework is chosen.
- Django, Celery and Streamlit came up as tools worth showing. They are logged
  as open questions rather than adopted, because each has to solve a real
  problem in this design first.

## 2026-10-14 — Planning and open questions

- Inspected the Ohio Served/Unserved file: one 222 MB CSV with ~4.5M
  locations. Its columns are `location_id`, `block_geoid`, `h3_res8_id`, and
  three 100/20 flags (`any`, `wired`, `terrestrial`). **There is no geometry.**
  Mapping by H3 is self-contained. Mapping by county or block needs Census
  boundary files, so that work is now its own issue (#9) and blocks the ETL (#2).
- The flags only express 100/20, so the map will say "Served / Not served
  (100/20)" rather than claim the unserved/underserved distinction. **Wired** is
  the default view because it matches what most people mean by "broadband".
- Every location row is kept, not just rollups. 4.5M rows is comfortable for
  PostGIS, and keeping them makes drill-down views possible later (#10).
- Tooling stays deliberately small: H3 in Python rather than a custom Postgres
  image, plain SQL migrations, the ETL as a Compose service, and no CI. The
  guiding principle is recorded in
  [open-questions.md](open-questions.md#guiding-principle).
