# Issue #73: Ohio county map and accessible detail

Status: approved by the repository owner on October 16, 2026; implemented and verified; awaiting pull-request review.

Review record: [approved plan on #73](https://github.com/ShawnMcCollum/BroadbandMap/issues/73#issuecomment-6228212856).

Issue: [#73](https://github.com/ShawnMcCollum/BroadbandMap/issues/73), under
[#70](https://github.com/ShawnMcCollum/BroadbandMap/issues/70), delivering the
county-map scope of [#4](https://github.com/ShawnMcCollum/BroadbandMap/issues/4).
Proposed branch: `codex/73-county-map`, from merged `main` at `21e61f2`.
Planning and read-only profiling were performed on October 16, 2026.

## Outcome and accepted boundaries

Replace the shell's bounded summary-readiness message with a usable Ohio county
map, county selector, readable county table and selected-county detail. All
current counts and colors must belong to the displayed release date pair and
technology flag. Follow the approved [design](frontend-design.md),
[guidelines](../frontend-guidelines.md) and
[ADR 0018](../decisions/0018-county-geojson-map-output.md).

The design is already settled: Ohio county level, wired default with all three
flags, five blue served-share bins, neutral hatching for missing observations,
tile-free MapLibre 6.14.0, and selector/table alternatives to the canvas. Preserve
the existing routes, diagnostics, cross-app navigation and reset guidance.
The source flag's false value is **Not served (100/20 Mbps)**; make no regulatory
unserved/underserved classification.

No backend API, database/model field, constraint, migration, loader, deployment
setting or authentication change is needed. No data reload is needed.

## Evidence checked before planning

- #71 and #72 are closed; the approved design and React shell are merged. #73
  remains open and had no discussion comments when inspected.
- Inspected `App.tsx`, exploration state/rendering, HTTP/release/rollup clients,
  fixtures/tests, CSS, package/lock, Vite/TypeScript, Docker/Compose, OpenAPI,
  county serializers/views/tests, rollup serializers/queries and pagination.
- The current rollup client requests `page_size=1` and returns only readiness;
  it must become the complete-collection client, not remain as an extra probe
  before a second full download. The shared HTTP boundary already accepts
  GeoJSON, checks same-origin endpoint links, has a 30-second request deadline,
  parses Problem Details and supports aborts.
- Read-only requests through `http://localhost:5173/api` found two Ohio releases:
  D25 / `2025-12-31` / processed `2026-09-29`, and J25 / `2025-06-30` /
  processed `2026-10-01`.
- Ohio GeoJSON returned 88 MultiPolygon features, 122,526 coordinate positions,
  `boundary_vintage=2020`, and **3,344,412 response-body bytes**. Every feature
  string ID matched its `properties.code`. Bounds were approximately
  `[-84.820305, 38.403423, -80.518705, 42.327132]`. County names already include
  "County"; do not append it again.
- D25 complete summaries returned 88 rows for each flag, all matching geometry
  IDs, with no missing counties in this installation. Wired JSON was **12,251
  bytes**; any was 12,003; terrestrial was 12,224. All responses used `no-store`.
  D25 wired totals were 4,542,350 locations, 4,244,855 served, 297,495 not served.
  Adams County (`39001`) had 13,752 locations, 8,439 wired served and 5,313 not
  served; an exact-code read returned the same values and `observed` coverage.
- A `page_size=1` geometry read returned a web-origin next link; following it
  through the proxy succeeded. Geometry size failure is a 400 Problem Details
  field error at `/page_size` with code `geometry_payload_too_large`, not a
  top-level error code. Collection rollups report `stored_rollups_only`, including
  an empty collection; only exact-code reads resolve missing-area coverage.
- These are HTTP measurements, not render measurements. One sequential local
  sample took about 973 ms for geometry and 30–42 ms for the three summary reads;
  transport/database warmth and machine affect them. No runtime claim follows.
- Inspected published `maplibre-gl@6.14.0` metadata and its tar archive in memory,
  without installing it. It is ESM, declares Node >=16.14, exports bundled types
  and `dist/*`, and contains `maplibre-gl.css`, `maplibre-gl-worker.mjs`,
  `maplibre-gl.mjs`, `maplibre-gl.d.ts`, and BSD-3-Clause `LICENSE.txt`.
  Official documentation confirms the Vite worker URL import, feature-state
  paint updates, local images and WebGL lifecycle events. Installation, the
  resolved dependency graph, production build and actual WebGL remain checks
  after approval.
- Existing backend, database, Redis and web services were read only. Missing
  observations, races, byte-cap failures and context loss require fixtures or
  browser-local simulation; do not alter the owner's data to produce them.

## Exact files and responsibilities

Paths here are repository-relative. No speculative framework files are needed.

| File | Planned change |
| --- | --- |
| `web/package.json`, `web/pnpm-lock.yaml` | Add exact runtime dependency `maplibre-gl: 6.14.0`; lock its graph with the existing pnpm version. No other direct dependency. |
| `web/public/maplibre-LICENSE.txt` | Copy the pinned package's complete `LICENSE.txt` verbatim after installation; Vite copies it into the production artifact. Retain distributed third-party notices and existing license banners. |
| `web/src/api/types.ts` | Add county geometry/page/completed-collection types and completed county-summary type. Preserve existing shared selection and error contracts. |
| `web/src/api/counties.ts` | Decode county GeoJSON, validate/paginate complete collections, implement finite size-cap recovery. |
| `web/src/api/counties.test.ts` | County shape, collection, unsafe-link, restart, failure and cancellation cases below. |
| `web/src/api/rollups.ts`, `web/src/api/rollups.test.ts` | Replace the one-page readiness method with complete county summaries; add one-county diagnostic read and context/count checks. |
| `web/src/features/exploration/useExploration.ts` | Keep the one release/flag/county owner; replace readiness with current complete summaries, add county selection and summary-only retry, expose full-refresh version. Retain release rediscovery/race behavior. |
| `web/src/features/exploration/Exploration.tsx` | Keep existing controls/provenance/errors; remove readiness placeholder and mount the county explorer at a stable position. Keep controls mounted while data updates. |
| `web/src/features/map/useCountyGeometry.ts` | Route-lifetime geometry request state, independent of release/flag; full-refresh and geometry-only retry; abort/generation cleanup. |
| `web/src/features/map/useCountyDetail.ts` | Exact-code diagnosis only for the selected county missing from a complete collection; independent retry and obsolete-response protection. |
| `web/src/features/map/CountyExplorer.tsx` | Compose selector, selected detail, map, legend, hover preview, attribution and table; derive one joined view from shared selection/current data. |
| `web/src/features/map/CountyMap.tsx` | Direct MapLibre integration, bundled worker/CSS, stable map/source, event listeners, bounds/resize, styling updates and renderer fallback. |
| `web/src/features/map/CountyDetail.tsx` | Current selected-county counts/provenance or precise loading/coverage/error/recovery text; one polite live region. |
| `web/src/features/map/CountyTable.tsx` | Semantic caption/headers, exact counts and served share, county selection buttons, contained horizontal scrolling. |
| `web/src/features/map/join.ts`, `web/src/features/map/join.test.ts` | Pure string-ID joins, county option/table order, missing-observation representation and count/percentage formatting. |
| `web/src/features/map/style.ts`, `web/src/features/map/style.test.ts` | Shared scale/bin definitions, legend labels, bounds and local style/hatch definitions; test numerical edges and missing states. |
| `web/src/features/map/CountyMap.test.tsx` | Mock the MapLibre boundary to verify lifecycle, state/style updates, events, resizing and fallback. |
| `web/src/features/map/CountyExplorer.test.tsx` | Selector/table/detail parity, missing diagnostics, independent resource failures, focus and context changes. Exercise both new hooks through the rendered feature. |
| `web/src/test-fixtures/api.ts` | Add tiny valid closed-ring MultiPolygons and complete summary/exact-code fixtures, with distinct observed/missing/empty/error cases. |
| `web/src/test-fixtures/maplibre.ts` | Reusable mock with listener registration/removal, source/state/style/control calls and event emission. Used only by owning component/integrated tests. |
| `web/src/App.test.tsx` | Replace readiness assertions with complete-map/table behavior; retain shell, diagnostics, dates, refresh, re-entry, StrictMode and stale-response regression coverage. Route fetch mocks by endpoint, not by a generic fallback. |
| `web/src/styles.css` | Map/detail grid, responsive DOM order, bounded map height, legend/hatching, preview/table/detail/fallback, visible focus and tabular numbers. |
| `README.md` | Describe the implemented map, selection/table/fallback and refresh behavior; replace outdated readiness-only claims and link this plan/license. Keep dashboard/AI limitations accurate. |
| `docs/frontend-guidelines.md` | Correct the stale statement that both applications are stack checks; preserve approved conventions. |
| `docs/plans/issue-73-county-map.md` | This plan, review record and actual implementation verification results. |
| `docs/journal.md` | Record useful reasoning: separate geometry lifetime, complete current summaries, missing-data honesty and actual measured/browser outcomes. |

No change is planned to `App.tsx`, `main.tsx`, `api/http.ts`, Vite config,
Compose, `.env.example`, existing design decisions or dashboard/backend files.
The current HTTP helper already provides the needed JSON/GeoJSON boundary.
If a concrete incompatibility requires any excluded change, revise the plan
before implementing it.

## Client types and validation

Use structural GeoJSON-compatible TypeScript types, without a direct dependency
on a second type package: position `[number, number]`, MultiPolygon coordinates
`[number, number][][][]`, feature `{type: 'Feature', id: string,
properties: {code: string, name: string}, geometry: {type: 'MultiPolygon',
coordinates}}`. A page adds `{type: 'FeatureCollection', features, state: string,
boundary_vintage: number, count: number, next: string | null,
previous: string | null}`. A completed boundary collection contains the validated
features, state, vintage and count; it has no pending page link.

Validate nonempty five-digit county IDs, matching property code/state prefix,
nonempty names, finite longitude/latitude pairs in geographic range, nonempty
polygons/rings, at least four positions per ring and equal first/last position.
Preserve source precision and coordinates. Require state `39` and vintage 2020
for this feature. Do not implement topology repair or geometry simplification.

A completed county summary carries validated rows, count, returned release,
selection, threshold, vintage and collection coverage. The completed type is
returned only after every page succeeds. Keep locations >=1 and all count values
as safe nonnegative integers. Require each technology count <=locations,
served equal to the selected source count, and served + not_served = locations.
County methods additionally require five-digit string codes with the requested
state prefix. Do not impose county restrictions on general shared summary types.

## Complete reads, pagination and size recovery

1. `fetchCounties('39', signal)` starts at
   `/api/v1/geographies/county/?state=39&page_size=100`. Decode every page and
   follow `next` through the existing `resolvePageUrl` for this endpoint. Track
   visited URLs and unique feature IDs. Require stable state/vintage/count,
   strictly advancing unique county IDs and final accumulated count equality.
   Reject malformed, duplicate, cyclic or inconsistent collections; publish no
   partial success. Empty count=0 is a valid no-boundaries result.
2. On only the documented 400 field error `/page_size` /
   `geometry_payload_too_large`, discard the whole attempt and restart page one
   at sizes **100 → 50 → 25 → 12 → 6 → 3 → 1**. Each attempt follows its own
   server-provided links. At size 1, stop with an actionable boundary-unavailable
   message and request ID; a single oversized feature cannot be fixed by more
   pagination. Other errors have no automatic retry. Abort cancels the whole
   attempt sequence. No partial geometry is presented as a complete state.
3. `fetchCountySummaries(release, flag, signal)` starts with county/state=39,
   both explicit dates and `page_size=100`. Use the existing rollup decoder and
   endpoint link guard. Validate returned dates, filing metadata, selected flag,
   county level, state, null code, 100/20 threshold, vintage and returned coverage
   on each page. Require compatible returned release/state coverage across pages,
   stable count, unique advancing codes and final count equality. Failure clears
   current thematic values; it never promotes an initial successful page.
4. Collection coverage is `stored_rollups_only`, even when zero rows are stored.
   Derive loaded states from the returned release, not an assumption based on
   discovery. If Ohio disappeared, clear colors/counts and show that state.
   A collection with fewer rows than boundaries is valid: missing rows are
   unclassified. Do not require every boundary to have an observation.
5. `fetchCountySummaryByCode(release, flag, code, signal)` requests the same
   pinned context with one code and `page_size=100`. Require matching returned
   context and either one matching observed row or zero rows with
   `no_observations` / `outside_release_coverage`; no pagination or unrelated row.
   A missing stored rollup with underlying observations is the existing 503.
6. Preserve original pagination queries; validate origin/path before following
   them and validate response context afterward. Do not manufacture dates or
   rewrite next links to the Docker host. Count/context checks detect some
   concurrent changes, but separate page requests still are not a snapshot.
   On inconsistent collections show a safe Refresh action, not a snapshot claim.

## State ownership and resource lifetime

Keep `{as_of, processed_on, state: '39', flag, county}` in `useExploration`.
Add `selectCounty(string | null)`; selectors, table buttons and map clicks all
call it. Release/flag changes retain the county identifier while clearing its
values. After available complete collections establish a valid county set, clear
a county that is absent from both resources; do not clear merely during loading
or failure. Keep hover in the map feature, independent of persistent selection.

Replace `readiness` with summary load state. Only a matching `ready` result owns
current rows; loading/failure has no current summary values. Retain the current
release-404 rediscovery guard, selection-required state and fresh reads on Map
re-entry. A selected missing-county 404 must likewise request catalog rediscovery
once and show Refresh/selection guidance if the release still exists; do not
repeat indefinitely or silently substitute a different release.

Expose a full-refresh version and summary-only retry action. A full Refresh
refreshes discovery, summaries and geometry; summary retry rereads only summaries.
Exact-detail retry rereads only that diagnostic. Every GET uses the existing
no-store/deadline boundary; there is no polling or background prefetch.

`CountyExplorer` remains mounted at a stable position for the active Map route,
including summary loading, changed selections and failures. Do not key it or
`CountyMap` by release, flag or county. Its geometry hook starts after discovery
first identifies a usable Ohio selection. Successful geometry is retained for
that route lifetime and does not refetch when release/flag changes, including
switching temporarily to an Ohio-absent release. A full Refresh or geometry-only
Retry performs a fresh geometry traversal; re-entry starts fresh. Failed or
cancelled geometry has no usable new collection. Previously complete boundaries
may remain visible during replacement with a refreshing label; no new partial
collection replaces them. Unmount releases geometry and map resources.

Each request domain (catalog, summaries, geometry, missing detail) has an abort
controller and monotonic generation/request identity. The summary identity
includes both dates/state/flag and refresh/activation version. Detail adds county
and completed-summary generation. Check identity before accepting success or
failure, including A→B→A and transports that ignore abort. Selecting a county
must not refetch the complete summary collection: summary effect dependencies
use release/flag inputs, not the entire selection object.

When summary context changes, clear old counts/preview and apply neutral pending
fills before the next paint; use a narrow layout effect for imperative map
clearing if needed. Pending/failure neutral is labeled as loading/unavailable,
not as a proven missing observation. Hatch only genuinely unmatched counties
after a complete successful summary collection. Keep the camera and geometry.

## Joins and missing-county detail

Join string feature IDs to string summary codes with a Map. Return view rows
with code, optional API county name, optional boundary and optional observed
summary; calculate percentage only for an observed positive denominator. Sort
options/table by display name then GEOID, and retain GEOID for disambiguation.
Use an explicit union for observed versus missing, rather than invented zero
counts. Do not mutate the source feature coordinates or original response rows.

Use the union of known boundary IDs and observed summary IDs for the table and
selector. If geometry fails, valid summaries still render with `County GEOID
39001` style labels; do not hardcode a county-name list. If summaries fail but
geometry succeeds, county names/selection remain usable with unavailable values.
A summary without a matching boundary remains in the table with a boundary
unavailable note; there is no fabricated polygon.

Run an exact-code diagnostic only when the persistent selected county has a
boundary but no row in a complete current summary collection. Do not query
missing counties eagerly or on hover. While diagnosing show "No summary
observation" and checking detail. Then show the API's no-observations,
outside-coverage, or unavailable-rollups explanation, with safe errors/retry.
If the exact read now returns an observed row, separate reads have changed:
show "County summaries changed. Refresh to update the map and table." Do not
silently inject different-generation counts into just one view or retry in a loop.
After Refresh all views derive from the new complete collection.

## Map, layout and interaction

- Import MapLibre directly, its packaged CSS, and
  `maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url`. Set the worker URL before
  map creation. Use a local style-spec v8 object, a neutral background and one
  county GeoJSON source with its string IDs. No remote style/tiles/sprites/glyphs,
  token, wrapper or custom geographic aggregation.
- Register a generated 8×8 RGBA diagonal hatch with `addImage`; a local
  fill-pattern layer with a missing-ID filter draws it over unmatched counties.
  Update observed fill colors with feature-state paint values and update the
  hatch filter; source geometry is not resent for summary/flag/selection changes.
  At load or a genuine geometry refresh, populate the source then reapply current
  styling/selection. Preserve string identity (use `promoteId: 'code'` to make
  string property IDs authoritative for renderer state as well).
- Use the approved colors and unrounded served/location ratio: 0–<20%,
  20–<40%, 40–<60%, 60–<80%, 80–100%; actual 0% is the first bin and actual 100%
  the last. Display one decimal with locale-separated exact counts. A pure
  formatter guards absent/invalid denominators without division by zero.
- Draw county outlines, a lighter hover outline, then selected white halo/dark
  outline. Hover updates a short HTML preview without live announcements,
  network calls, changing persistent selection or moving focus. Clear hover on
  mouseleave, summary changes and renderer failure. Render API names as text.
- Click on a county, native select, or `Select [county]` table button updates
  the same selection. `All counties` clears it. Blank map clicks leave selection
  unchanged. Selecting a county does not automatically fly/zoom or move focus.
- Fit initial validated county bounds with 24px padding. Provide zoom controls
  and a native `Fit Ohio` button; hide compass/rotation, disable pitch/rotation
  and world copies. Use minZoom 5, maxZoom 12 and max bounds containing the fitted viewport with a one-degree margin.
  Refit on container resize so pan constraints cannot crop the state. Fit is immediate (`duration: 0`); no required
  animation. Keep page scrolling usable with cooperative gestures. Use a
  ResizeObserver to call map.resize and disconnect it on cleanup.
- On construction/load failure or context loss, show the documented interactive
  map-unavailable guidance and keep selector/table/detail/provenance usable.
  Tear down the failed instance; an explicit `Retry interactive map` recreates
  the renderer from current in-memory boundaries without refetching API data.
  Listen for error/context events with safe messages; do not dump raw errors.
  Use a 30-second renderer-load deadline so worker failures cannot leave an
  endless spinner. Clear its timer on load, failure and cleanup.
- StrictMode setup/cleanup must remove map listeners/controls, ResizeObserver,
  pending callbacks/timers and map exactly once per created instance. Guard
  updates before style load and after removal; apply the latest inputs at load.
  No map recreation for ordinary summary updates. Do not call prewarm or create
  a persistent shared worker/map pool.
- DOM order after release/flag controls is county selector, detail, map, legend,
  preview/provenance and county table. At >=64rem detail sits right of the map
  via grid placement; below 48rem it remains before the 20rem-high map. Desktop
  map height is 30rem. Body reflows at 320px; only the table wrapper scrolls
  horizontally. All key labels/context remain outside canvas/hover content.
- The legend has text ranges and a separate hatch label. Table columns are
  county, GEOID, locations, Served, Not served, Served share and selection
  action, with a descriptive caption and scoped headers. Provide accessible
  labels for map/controls and a focusable, labeled scroll region. Selection
  updates one politely announced detail region; hover is not live.
- Show selected flag/source-field meaning, 100/20 explanation, filing period,
  both dates, returned loaded-state coverage, FCC National Broadband Map source
  and Census TIGER/Line 2020 attribution. Keep MapLibre renderer credit/license
  link visible in HTML as well as its control. Source text uses current returned
  metadata, including after refresh. No statewide aggregate card is introduced.

## Required test cases and expected outcomes

Use existing Vitest/Testing Library, real Response objects, schema-aligned small
fixtures, deferred promises and fake timers where useful. Mock MapLibre for DOM
tests, not the collection/selection behavior under test. Do not add browser test
dependencies. Retain all relevant #72 regression cases, changing only readiness
expectations that this feature deliberately replaces.

Change the default `rollupPage` fixture to `count=rows.length`, `next=null` and
`previous=null`; its current one-row/count-88/next-page shape intentionally served
the readiness test and is not a complete collection. Multi-page tests explicitly
provide the total and links. Mock each endpoint separately so geometry requests
cannot accidentally receive a rollup response.

| Boundary / input | Expected outcome |
| --- | --- |
| County valid MultiPolygon with hole/multiple polygons and leading-zero generic join IDs | Coordinates preserved, string joins match; Ohio network reads still require prefix 39. |
| Numeric/mismatched ID; wrong state/vintage/type; missing name; empty/short/open ring; nonfinite/out-of-range position | Safe unexpected-response failure; no partial geometry/map initialization. |
| Two geometry pages / two summary pages | Do not mark complete until both succeed; preserve endpoint links and count/context. |
| Page-two network/JSON/shape failure, duplicate IDs, changed count/context, missing final rows, cyclic/nonadvancing pages | Discard attempt and show safe retry; no partial classified map/table. |
| Foreign/container origin, wrong endpoint, encoded traversal or credentials in a next link | Reject before follow-up fetch; shared HTTP URL tests remain intact. |
| Size error on first or later geometry page | Restart page one at next approved size, discard earlier pages. |
| Size errors at every size, or unrelated 400/503 | Seven attempts maximum for byte-cap failure; size=1 yields actionable error; unrelated failure is not retried. |
| Abort during a later page or byte-cap restart | No next request/publication after cancellation; no error notification for obsolete work. |
| Summary zero/negative/noninteger/unsafe counts, count >locations, selected flag mismatch, served+not_served mismatch | Reject invalid current data; do not color from it. |
| Summary wrong date pair/flag/state/code/threshold/vintage on later page | Whole collection rejected; no apparent success under current controls. |
| Observed served counts 0/100, 20/100, 40/100, 60/100, 80/100, 100/100 | Exact approved bin boundaries; visible 0.0% through 100.0%. |
| Ratio 19999/100000 | First bin although rounded display is 20.0%; never classify rounded text. |
| Boundary without summary; true observed zero served; summary without boundary | Missing remains absent/hatch, zero served stays blue, unmatched summary remains table-visible. |
| Invalid/zero denominator passed to pure ratio helper | No Infinity/NaN or invented percentage; network decoder rejects zero locations. |
| Initial/default selection and all three flag/date changes | Correct pinned queries/current metadata; complete table matches detail/map; no extra readiness GET. |
| Flag/date changes and county-only changes | Old colors/counts cleared; geometry not refetched, map not recreated; county-only change does not refetch summaries. |
| Full Refresh vs summary/geometry/detail retry vs renderer retry | Fresh reads only for their stated domains; full Refresh rereads visible resources; renderer retry performs no API read. |
| County select/table button/click, hover/leave and All counties | One persistent selection, transient independent hover, selection clear works; focus remains on originating control. |
| Selected missing county: no_observations / outside_release_coverage / 503 / malformed result | Precise explanation or safe error/request ID; no zero substitution; no eager calls for other counties. |
| Missing diagnostic returns newly observed row or 404 | Explicit refresh/catalog recovery; no mixed-view injection or automatic loop. |
| Empty releases / newest release without Ohio / Ohio vanishes in summary metadata | Existing guidance/controls remain correct; no older-release fallback or misleading thematic fills. |
| Empty stored-rollup collection | Label absence of stored summaries; each selected boundary can be diagnosed; do not claim statewide zero observations. |
| Geometry fails, summaries succeed; summaries fail, geometry succeeds | Table/counts with GEOID names, or named counties with unavailable counts, respectively; independent retry. |
| A→B and A→B→A late success/failure; county/detail change; ignored abort; departure/re-entry; StrictMode | Only current generation publishes; no post-unmount updates; re-entry fresh reads with preserved valid selection. |
| Delayed MapLibre load while props change | Apply only latest summary/selection when ready; no stale initial colors. |
| MapLibre throws, emits load error or context loss, or never loads | Usable table/selector fallback, safe message, bounded deadline and explicit renderer retry. |
| ResizeObserver, unmount and repeated mount | resize invoked when appropriate; observers/listeners/timers removed; map.remove once per instance. |
| Native select/legend/detail/table at narrow widths and missing/error states | Labeled controls, caption/headers/text alternatives; no hover-only required information. |

Pure style tests cover ratio/bin/missing behavior and bounds, not snapshots of
every renderer call. Lifecycle mock tests assert meaningful resource use and
updates; real browser checks below are required for actual paint and workers.

## Commands after approval

PowerShell from the repository root. Use the existing Docker installation;
reviewers need no host Node tooling. Stop on a failed command before continuing.

```powershell
$env:PATH = "C:\Program Files\Docker\Docker\resources\bin;$env:PATH"
git status --short
git switch -c codex/73-county-map
docker compose config --quiet
docker compose run --rm --no-deps web pnpm add --save-exact maplibre-gl@6.14.0 --store-dir /root/.local/share/pnpm/store
docker compose build web
docker compose run --rm --no-deps web sh -c 'mkdir -p public && cp node_modules/maplibre-gl/LICENSE.txt public/maplibre-LICENSE.txt'
```

The add command changes only the approved package/lock and container dependencies.
Inspect the lock diff before coding; the copy command preserves the package's
full license at the planned public path. Rebuild ensures a clean Docker image can install
with `--frozen-lockfile`. After implementation:

```powershell
docker compose run --rm --no-deps web pnpm check
docker compose run --rm --no-deps web pnpm build
docker compose run --rm --no-deps web pnpm list maplibre-gl --depth 0
docker compose up -d --no-deps --force-recreate --renew-anon-volumes web
git diff --check
git ls-files --others --exclude-standard
```

Recreating **only web** renews its anonymous `/app/node_modules` volume from the
rebuilt image; an existing anonymous volume can otherwise hide the new package.
No database/secret volume is renewed and no backend/worker/data service is
restarted. Confirm pnpm lists exactly 6.14.0, checks/build pass, production output
contains the bundled worker/CSS and complete license, and new-file whitespace
is reviewed too. Vite's worker URL handling requires no new config/type shim.
Record dependency notices and any build warnings with their disposition.

No dashboard/backend/full-data test run is required for this frontend-only
change. Any separately approved backend/configuration expansion adds its owning
checks and schema review. No hosted CI, browser automation package or test
platform is introduced.

## Real-browser acceptance after implementation

Use the existing Ohio data and a real browser with actual WebGL. Use an available
browser tool or bundled automation runtime, without a repository dependency.
Record browser/version, OS, viewport, renderer availability, warm/cold conditions,
commands, measurements and limitations. Browser tooling availability is a
verification prerequisite, not proof obtained from a DOM mock.

1. At the web origin, verify the current D25 wired selection, 88 county features,
   88 summary rows, five-bin legend, visible attribution and real county paint.
   Check Adams County against the profiled exact counts and independently against
   the current API, since the dataset can change after this plan.
2. Exercise hover/leave, map click, native keyboard selection, table selection,
   All counties, zoom and Fit Ohio. Confirm selected outline/detail parity and
   that keyboard focus is not moved by selection/refresh.
3. Change all three flags and both releases. Verify requests pin both dates and
   state, data becomes neutral/loading during updates, and values use the returned
   context. Once initial geometry is ready, ordinary flag/date/county changes
   cause no geography GET and no new map/worker instance. In development,
   StrictMode may start then cancel an initial effect; distinguish this from
   repeated downloads on settled filter changes.
4. Full Refresh rereads geometry/catalog/current summaries; resource-specific
   retries have the narrower behavior specified above. Navigate to Diagnostics
   and back: the old map is removed and data is reread; valid selection survives.
5. At 1280, 390 and 320px and browser zoom, inspect DOM/visual order, table scroll,
   wrapped provenance, legend, attribution, focus visibility and map bounds.
   Check keyboard-only operation and reduced motion. Record actual contrast
   checks for new text/control states; no blanket accessibility certification.
6. Demonstrate unavailable WebGL and simulated context loss without modifying
   server data. Selector/table/detail remain usable, and renderer retry recovers
   where the browser supports it. Check load/worker failure and resource cleanup.
7. Exercise byte-cap restart/single-feature exhaustion, page-two failure,
   missing observations, no releases, outside coverage, non-JSON and late responses
   with deterministic fixtures/browser-local interception. State which cases are
   simulated; do not replace/delete/rebuild the owner's dataset for this check.
8. Record actual response sizes/request counts and time from navigation to first
   classified map, plus flag-change behavior and production JS/CSS/worker sizes.
   Inspect console/network for unexpected errors and external tile/style/font
   requests. Confirm there are no new browser-storage entries. Timings are
   observations, not brittle automated performance thresholds.

## Exclusions, review gate and references

No location points/drill-down/export, dashboard changes, finer map geographies,
state selector, search/geocoder, basemap/tiles, paid accounts, geometry repair or
simplification, new aggregates/endpoints, auth/AI forms, persistent cache,
service worker, router/global store, deployment/hosting or original-feature
closure. Keep #4 open until its full acceptance is reviewed; this plan proposes
one issue branch and one reviewable PR for #73.

Owner review must precede feature code, configuration and dependency changes.
The local `CLAUDE.md` requires: "No code, configuration or dependency is written
until the plan is approved." This document is the concrete review artifact.
The issue requests the plan as an issue comment; posting externally requires
the owner's authorization. Once authorized, post this same plan in neutral
engineering language and link that review record here. Scope changes return
for review before implementation.

Rationale and references:

- [ADR 0018](../decisions/0018-county-geojson-map-output.md) and the
  [reviewed OpenAPI](../../backend/core/api/openapi.json) define the separate
  county/summary representations. Reusing them avoids API/aggregation drift
  and unnecessary polygon downloads as filters grow.
- [React shared state](https://react.dev/learn/sharing-state-between-components)
  supports the one selection owner; [effect cleanup/race guidance](https://react.dev/reference/react/useEffect#fetching-data-with-effects)
  supports cancellation plus ignoring obsolete results. Both keep future map,
  detail and analytical consumers aligned without a new state framework.
- [MapLibre Vite setup](https://maplibre.org/maplibre-gl-js/docs/#installation),
  [Map API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/),
  [style specification](https://maplibre.org/maplibre-style-spec/layers/),
  [tagged package metadata](https://github.com/maplibre/maplibre-gl-js/blob/v6.14.0/package.json)
  and [Vite worker assets](https://vite.dev/guide/assets.html#importing-script-as-a-worker)
  ground the renderer lifecycle and self-contained resource handling. Metadata
  inspection is not a substitute for Docker build and actual WebGL verification.
- [W3C use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
  and [keyboard access](https://www.w3.org/WAI/WCAG22/Techniques/general/G202)
  explain the readable table, selector and text/pattern alternatives. They also
  make the feature useful when the graphics subsystem is unavailable.


## Performed verification on October 16, 2026

- Owner approval was given in this implementation session after the local plan
  was presented; the approved plan was posted to #73 before feature changes.
  Work uses `codex/73-county-map` from `21e61f2`.
- Clean Docker image build installed the exact MapLibre 6.14.0 lock. Initial
  `pnpm add` needed `--store-dir /root/.local/share/pnpm/store` to match the
  image's dependency links. The license was copied after rebuilding the image,
  since each one-off container initially inherits the image's dependency volume.
  The commands above reflect this observed container behavior.
- Docker web `pnpm check` passed formatting, lint, strict TypeScript and **134
  tests across 11 files**. New cases cover complete pages/counts/context, invalid
  GeoJSON, size-cap restart/exhaustion, unsafe URLs, missing observations and exact
  diagnosis, unavailable rollups, newly observed detail requiring Refresh, one
  404 rediscovery, ignored-abort detail/geometry races, shared selection, full
  refresh, resource cleanup, hover persistence and renderer fallback/deadline.
  Existing shell/health/request-boundary regressions remain covered.
- Docker `pnpm build` passed with 37 modules. Production assets were 1,293.19 kB
  JavaScript (360.08 kB gzip), 87.11 kB CSS (12.00 kB gzip), and a separate
  507.71 kB worker. Vite reports its normal >500 kB chunk warning; it is recorded,
  not suppressed. The renderer increases initial download size; code splitting
  is a future measured optimization, not an added framework in this slice.
  `pnpm list maplibre-gl --depth 0` confirmed exactly 6.14.0.
- Real headless Microsoft Edge **155.0.4283.45 on Windows** rendered all 88 Ohio
  counties. Adams County wired detail matched 13,752 locations, 8,439 served,
  5,313 not served, 61.4%. Native keyboard selection retained focus on the county
  select. All three flags and the second release produced pinned-date requests.
  After geometry settled, that change sequence made **zero further geography
  requests** and retained one worker and one WebGL context. Browser storage
  remained empty and the acceptance run had no page exceptions or failed reads.
- Inspected actual map and responsive screenshots. At 1280, 390 and 320px,
  document/body width matched viewport width. Map heights were 480/320/320px;
  provenance wrapped and detail precedes the narrow map in DOM order. This is
  focused browser/keyboard evidence, not complete accessibility certification.
- Visual review found that constraining to the county envelope plus one degree
  made MapLibre increase zoom in a wide container and crop the state. The fitting
  helper now constrains to the union of the county envelope and fitted viewport,
  plus that margin, and refits on container resize. It preserves the approved
  bounded Ohio view and the camera across filter changes. Screenshots confirmed
  all counties fit with padding afterward.
- A real missing-county screenshot exposed that promoted feature IDs did not
  select features in the worker-side layer filter, despite being returned as
  string IDs in rendered queries. Layer filters now use the string `code`
  property; feature-state keys still use GEOIDs. Screenshot pixel inspection
  confirmed contrasting hatch strokes over the neutral missing-county fill.
  Hover/selection use the same property filter.
- Browser-local interception demonstrated a size-100 geometry rejection followed
  by real size-50 page one and page two, totaling 88 boundaries. A deliberately
  missing Adams summary remained hatched with exact no-observations guidance.
  A summary page-two HTML 502 left **zero current percentage cells**, with no raw
  response leakage. A simulated empty catalog hid the data view. No source data
  was changed for any failure case.
- Actual WebGL context loss kept the 88-row table and selected county usable;
  explicit renderer Retry recovered a canvas. A separate browser with WebGL
  deliberately unavailable still offered all 88 rows and an enabled selector.
- API byte measurements are recorded in the evidence section. Browser acceptance
  sequences took roughly 10–12 seconds including navigation, deliberate waits,
  filter changes, screenshots and fallback checks; these are not first-paint
  benchmarks or universal timing guarantees. No brittle timing assertion was
  added. Real API success and browser-local simulations are distinguished above.
- Only web was recreated to renew its anonymous dependency volume. Backend,
  database, secret volumes and loaded source data were not modified. No backend
  or dashboard checks are needed for the approved frontend-only scope. Final
  whitespace, relative-link and changed-file review accompany the PR.


## PR review follow-up on October 17, 2026

The [P2 review finding](https://github.com/ShawnMcCollum/BroadbandMap/pull/88#discussion_r4300893087)
identified a misleading boundary-loading status for an initially selected release
without Ohio. Geometry loading was deliberately disabled, but the hook's default
state was still loading. The return state now explicitly reports idle while
disabled, keeping the loading indicator tied to an enabled read. Previously
loaded geometry remains available for reuse.

The regression in `CountyExplorer.test.tsx` first reproduced the false status
without a geometry request. It then covers enabling an Ohio release with a
pending read, completion, switching to an uncovered release, and returning to
Ohio without a second geometry download or renderer recreation. This is a
correction to the approved loading/coverage behavior within the existing files;
no dependency, API or product-scope change is involved.

Verification: the targeted test failed against the original hook, then Docker
web `pnpm check` passed formatting, lint, strict TypeScript and 135 tests across
11 files after the fix. `pnpm build` passed; the existing bundle-size warning
remains (main JavaScript 1,293.20 kB / 360.09 kB gzip). No renderer behavior or
browser dependency changed, so the DOM regression covers the reported status
problem without repeating the full WebGL acceptance suite.
