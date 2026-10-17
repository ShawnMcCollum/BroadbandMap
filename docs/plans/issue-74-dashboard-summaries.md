# Issue #74: analyst county summaries, chart and CSV

Status: approved by the repository owner in this chat on October 17, 2026;
implemented and verified; awaiting pull-request review.

Review record: [posted implementation plan](https://github.com/ShawnMcCollum/BroadbandMap/issues/74#issuecomment-6240172550).

Issue: [#74](https://github.com/ShawnMcCollum/BroadbandMap/issues/74), under
[#70](https://github.com/ShawnMcCollum/BroadbandMap/issues/70), delivering the
summary portion of #16. Branch: `codex/74-dashboard-summaries`, created from
synced `main` at `128a601`. Planning date: October 17, 2026.

GitHub reports #74 closed without a closing pull request. The owner explicitly
confirmed in this chat to proceed with #74 as written. Leave its status and the
parent feature issues unchanged unless separately instructed.

## Outcome and reasons

Replace the dashboard stack-check landing page with Ohio county analysis:
release date-pair selection, Wired / Any technology / Terrestrial, observed
county totals, a horizontal served-share chart, a full table, county selection,
and a bounded summary CSV. Keep diagnostics available as a secondary view.

Follow [ADR 0004](../decisions/0004-streamlit-analyst-dashboard.md), the approved
[design](frontend-design.md#3-analyst-summaries--74), and
[frontend guidelines](../frontend-guidelines.md). API-only reads preserve one
business contract. One selection owner prevents mismatched filters and exports.
Complete collection reads prevent plausible-looking partial totals. The chart's
text table and native county selector keep analysis usable without color,
canvas, or pointer input. Pure aggregation/export modules let #75 reuse the
same selection without duplicating business rules.

## Evidence checked before implementation

- The checkout was clean. Main was fast-forwarded from `21e61f2` to `128a601`;
  #73 and the rollup-admin changes are merged. No dashboard implementation for
  #74 exists on main.
- Inspected dashboard code/tests, Compose/env, approved frontend documents,
  backend release/rollup/county serializers and views, pagination/errors, and
  the corresponding React clients. There is no county metadata-only endpoint.
- Releases return `results`, both dates, filing period and loaded `states`.
  Rollups return `results`, selected flag/counts, release, threshold,
  `boundary_vintage`, `summary_coverage`, and pagination. County GeoJSON returns
  `features` with matching string `id` / `properties.code` and county names.
- County geometry has a 5 MiB cap; the structured field error is
  `/page_size` / `geometry_payload_too_large`. Successful collections enumerate
  stored rollups only; exact-code rollups distinguish missing observations
  from unavailable summaries or outside coverage.
- A disposable dashboard container reports Streamlit 1.66.0, Altair 6.3.0,
  pandas 3.0.6. Its `st.bar_chart` supports `horizontal`, `sort`, and `alt`;
  `st.table` supports `alt`; `st.download_button` supports `on_click="ignore"`.
  Installed AppTest has `DownloadButton`, its protobuf, and widget interactions.
  No package upgrade is needed.
- Only the existing `broadbandmap` database and Redis containers were running
  when inspected. No live API/data measurement or browser pass is claimed.
  Use fixture evidence during implementation, then the real stack for smoke
  verification; preserve the owner's existing volumes and loaded data.

## Exact files

| File | Change |
| --- | --- |
| `dashboard/app.py` | Thin Streamlit orchestration: navigation, controls, loading/errors, provenance, totals, chart/table/download and county selection; diagnostics view. |
| `dashboard/api.py` | Bounded HTTP client, safe errors, strict response decoders, endpoint URL policy, complete release/county/summary reads, exact-code county diagnosis; retain and harden health reads. |
| `dashboard/selection.py` | Typed immutable selection and explicit transition helpers; one bounded session snapshot with current catalog, county names, summaries and selected-county diagnosis. |
| `dashboard/summaries.py` | Typed rows/context, pure county-name joins, ordering, totals, shares and display/chart datasets. |
| `dashboard/exports.py` | CSV column order, safe text serialization, UTF-8 BOM bytes, context and filename; only accepts a completed summary dataset. |
| `dashboard/config.py` | Parse server API origin and public web URL; validate scheme/host/credentials/query/fragment; build escaped same-tab navigation. |
| `dashboard/.streamlit/config.toml` | Supported native light theme using approved canvas/surface/text/action palette; no generated-DOM CSS overrides. |
| `dashboard/tests/conftest.py` | Small schema-aligned release, geometry and summary fixtures plus httpx transport factory. |
| `dashboard/tests/test_api.py` | Keep health regression cases; extend HTTP, decoding, paging, completeness and context tests below. |
| `dashboard/tests/test_selection.py` | Selection transitions, disappearance, clearing and bounded state tests. |
| `dashboard/tests/test_summaries.py` | Weighted totals, missing rows, ordering and string-identifier tests. |
| `dashboard/tests/test_exports.py` | Exact CSV headers/context/filename, safety and raw round trips. |
| `dashboard/tests/test_app.py` | Real Streamlit AppTest interactions with only the HTTP boundary mocked. |
| `dashboard/tests/test_config.py` | API/public URL and same-tab escaped navigation cases. |
| `docker-compose.yml` | Add dashboard `WEB_APP_URL: ${WEB_APP_URL:-http://localhost:${WEB_PORT:-5173}/}`; preserve server-side `API_BASE_URL`. |
| `.env.example` | Document optional browser-reachable `WEB_APP_URL` alongside `VITE_DASHBOARD_URL`. |
| `README.md` | Replace dashboard stack-check instructions with analysis, filters/refresh/export/reset behavior and diagnostics; document CSV import convention and checks. |
| `docs/frontend-guidelines.md` | Update stale dashboard-stack-check status; preserve approved behavior. |
| `docs/journal.md` | Record reasoning and actual test/browser/import evidence. |
| `docs/plans/issue-74-dashboard-summaries.md` | Approval record and implementation/verification outcomes for this plan. |

No dependency, lockfile, Dockerfile, database/model/constraint/migration, API
endpoint, or React code change is planned. There are no new database fields.
Use native Streamlit chart/table controls with dictionaries/lists, avoiding
direct imports of transitive pandas/Altair dependencies.

## Implementation decisions

### HTTP and complete collections

1. Use a context-managed `httpx.Client` with configured API origin,
   `httpx.Timeout(10.0, connect=5.0)`, `follow_redirects=False`, and explicit
   JSON/GeoJSON Accept headers. Close on each fetch operation. Never emit raw
   exception text, HTML, traceback, or payload into the page.
2. Resolve pagination with `urllib.parse.urljoin` against the exact current
   endpoint. Accept absolute same-origin links, root-relative links and
   query-relative links; require identical scheme, normalized host/effective
   port and endpoint path. Reject credentials, fragments, other origins/paths,
   malformed ports, non-HTTP schemes, control characters and backslash links.
   Preserve accepted query strings. Validate response selection/context even
   after an accepted URL, and never follow redirects to bypass the policy.
3. Fetch `/api/v1/releases/?page_size=100` to completion. Validate ISO date
   pairs, state string codes, filing period and page shape. Initial selection
   is latest `as_of`, then latest `processed_on`; keep distinct processing
   versions. The newest release lacking Ohio stays selected and says so.
4. Fetch `/api/v1/geographies/county/?state=39&page_size=100` to completion.
   Validate envelope, vintage 2020, feature IDs/properties, Ohio codes and
   nonempty names. Retain only the name/code mapping after each page, dropping
   coordinate payloads. On the size-cap field error discard the entire attempt
   and restart with 100, 50, 25, 12, 6, 3, then 1. Fail actionably at 1.
5. Fetch `/api/v1/served-unserved/rollups/` with `level=county`, `state=39`,
   selected `flag`, explicit `as_of`, `processed_on`, `page_size=100`. Validate
   collection coverage `stored_rollups_only`, threshold 100/20, vintage 2020,
   release/selection identity and identical context on every page. Counts must
   be integers (not Booleans), locations positive, all flag counts within
   locations, selected served equal selected flag count, and served plus
   not-served equal locations.
6. Require stable advertised count, ordered unique IDs, no repeated URLs,
   no empty intermediate page and exact final row count for every collection.
   A collection attempt has a 60-second monotonic deadline checked between
   pages, plus per-request timeouts; document that an in-flight request can
   consume its configured timeout. Retain only current attempt values; discard
   them completely on error. Do not claim separate pages form one snapshot.
7. Parse structured Problem Details status/code, request ID and field
   pointer/code/message safely; render text without HTML/Markdown evaluation.
   Use resource-specific fallback for network/timeout, non-JSON, malformed
   bodies, redirect, unexpected status and wrong content type. A 503 summary
   response explains summaries unavailable and suggests refresh/operator
   rebuild. Health still accepts its documented 200/503 reports, and malformed
   health is a safe failure.

### Selection, lifecycle and rendering

1. One immutable selection owns optional release date pair, `state="39"`,
   `flag` in `wired|any|terrestrial`, and `county: str | None`. Keep one current
   session snapshot, never a dictionary keyed by all previously visited
   releases/flags. No `st.cache_data`, `st.cache_resource`, filesystem/browser
   data persistence, background prefetch or growing rerun history.
2. First analysis entry discovers releases and county names. Release/flag
   changes synchronously clear prior summaries/export/diagnosis and county,
   then fetch the new summary selection. County changes clear only dependent
   county diagnosis/future drill-down state; they do not filter the full-state
   summary table/chart/export. This selector prepares #75's drill-down.
3. Keep only the current complete names and summary collection in session
   memory. Names are independent of release/flag and can be reused across
   those changes. Explicit Refresh rereads catalog/names/current summaries,
   discards former values before loading and preserves the explicit pair/flag.
   Returning from Diagnostics performs fresh reads. Retry rereads the failed
   resource and its dependents. No silent fallback if a selected release
   disappears: clear data, rediscover catalog and require a new selection.
4. Guard installation of fetched values with the selection identity they
   were requested for. Widgets and data render from the same owner. Streamlit
   reruns are synchronous, but callbacks must clear old derived values before
   showing new controls. Obsolete results cannot become current.
5. Render one title, labeled Analysis/Diagnostics control, validated same-tab
   Map link (`WEB_APP_URL` plus `#/map`), reset guidance, release select with
   full wrapping date-pair metadata, fixed Ohio label, flag select/help, Refresh,
   source/filing period/loaded states/100-20 threshold/vintage provenance.
   Do not pass filter state across applications.
6. Show counts with separators and shares with one decimal. Label aggregates
   `Observed county totals`, computed from sum(served)/sum(locations). No
   observations means unavailable share, not 0%. A boundary without a summary
   appears as `No summary observation` with blank counts/share and is excluded
   from totals/chart/CSV. Report observed county count against loaded names.
7. Chart: native horizontal `st.bar_chart` of observed served share with a
   0-100 interpretation, explicit axes/alt text and stable descending raw-share
   order then GEOID (`sort=False`). Height grows with county count so labels
   remain readable; no horizontal page overflow. Pair it with a semantic native
   `st.table` containing county name/GEOID, exact locations/served/not-served,
   percentage or missing label, ordered by county name then GEOID. The table
   carries the chart's complete text alternative. Test and verify narrow
   scrolling and keyboard behavior in a real browser.
8. County selector uses complete names; a selected missing row triggers one
   exact-code rollup read with the current pair/flag. Show no observations,
   outside coverage or unavailable summaries from that response. If a name
   collection fails, observed rows remain readable under GEOIDs; warn that
   county names/coverage count are unavailable and disable CSV until names
   successfully load. An observed code absent from a successful name collection
   gets a GEOID fallback and explicit missing-name notice, never a fabricated
   county name. No working View locations action until #75; show concise
   forthcoming-drill-down guidance.
9. Loading uses Streamlit status/spinner text, errors stay in normal reading
   order with retry, and there are no stale totals/export during failures.
   No releases and API unavailable have specific recovery text. Diagnostics
   retains API/PostGIS/Redis/worker reports without requiring analysis reads.

### CSV contract

- Generate from current observed summary rows only after every summary and
  name page succeeds; sort by county name then GEOID, matching the table's
  observed subset. Missing observations never become synthetic CSV rows.
- Header order: `county_geoid`, `county_name`, `locations`, `served`,
  `not_served`, `served_share_percent`, `flag`, `as_of`, `processed_on`,
  `loaded_state_codes`, `fcc_source`, `boundary_vintage`.
- Use Python `csv.writer`, UTF-8 BOM and raw integer counts. Decimal share
  uses up to six places; authoritative source counts are untouched. Context
  comes from the validated summary response; source is `FCC National Broadband
  Map Served/Unserved`, vintage is 2020 and states are semicolon-separated codes.
- Always prefix GEOID and loaded-state text with one literal apostrophe. For
  arbitrary text prefix an apostrophe if first nonspace character is `=`, `+`,
  `-`, `@`, or the original starts with tab/CR/LF. CSV writer handles commas,
  quotes and embedded newlines. Never emit an executable formula for an ID.
- Filename: `ohio-county-summary-{as_of}-processed-{processed_on}-{flag}.csv`.
  Explain the text prefix beside download and in README, including its removal
  by programmatic consumers. Record actual spreadsheet-import behavior without
  promising identical automatic typing across spreadsheet software.
- Download bytes/filename derive together from the same completed selection;
  use `on_click="ignore"` so a download does not reread data. Failed/incomplete
  reads have no downloadable prior media payload in the newly rendered view.

## Test inputs and expected results

| Boundary | Cases and expected outcome |
| --- | --- |
| HTTP/paging | Two-page releases, summaries and county features return every item once; absolute/root/query-relative same-endpoint links pass unchanged. Wrong scheme/host/port/path, credentials/fragments, backslashes/control characters and redirect destinations fail before another fetch. Cycle, duplicate/out-of-order ID, changed count/context, truncated final page and empty intermediate page fail the entire collection. |
| Releases | Same data period with two processings remains two options; latest pair selected initially. Newest without Ohio shows absence and issues no rollup read. No releases shows load instructions. Disappeared selected pair clears dependent data and asks for selection. |
| Schemas/errors | Malformed JSON/HTML, wrong envelope/types, numeric identifier, Boolean/negative/inconsistent counts, mismatched flag/date/state/threshold/vintage fail safely. Structured 400 preserves safe pointers/request ID, 503 explains unavailable summaries; timeout/connection/redirect/non-JSON error has resource-specific fallback. Health 200/503 remains supported. |
| Geometry | Multi-page names joined by exact string IDs, no hard-coded list, coordinates not retained. Cap on later page discards the partial attempt; lower sizes retry from first page; failure at size 1 terminates. Geometry/name failure still permits GEOID table but disables CSV. |
| Aggregation | County counts 1/1 and 1/9 produce 2/10 = 20%, never 55.6%; all-served and zero-served retain correct endpoints. Empty observations has no rate. Missing county remains blank/unclassified, excluded from totals/chart/CSV. Name/share tie order uses GEOID. |
| CSV | Decode with `utf-8-sig` and `csv.reader`: exact headers, raw counts, six-place share, date pair, flag, all loaded states, source/vintage and filename. ID `01001` stays string `'01001`; loaded text `'01;39` is preserved. Comma/quote/newline names round-trip; formula triggers with leading spaces and tab/CR/LF get safe prefixes; ordinary text untouched. Incomplete collection cannot yield export. |
| Selection | Release/flag clears county/summary/export/diagnosis; county clears diagnosis only; Refresh replaces rather than appends snapshots, preserves existing pair/flag; obsolete identity cannot commit; diagnostics return refreshes. |
| AppTest | Start from two releases/three flag fixtures; change release and flag and assert table data, chart spec, totals, CSV generation arguments/filename and selection agree. Use real chart/download widgets; inspect chart protobuf and instrument the export boundary to record exact bytes passed (AppTest does not itself download a browser file). Assert disabled/missing export after second-page failure, no releases, no Ohio, names failure and API unavailable; Refresh recovery, selected missing county diagnosis and diagnostic navigation. Check no uncaught Streamlit exceptions. |
| State bounds | Repeated release/flag/county/rerun/refresh leaves only one current snapshot; no coordinate arrays, historical datasets or process-wide cached responses accumulate. Download with ignore does not cause fresh API requests. |

## Commands and verification after approval

Run format/check inside the existing dashboard container:

```powershell
docker compose run --rm --no-deps dashboard ruff format .
docker compose run --rm --no-deps dashboard sh check.sh
docker compose config --quiet
git diff --check
```

Expect formatting/lint, strict mypy and pytest including AppTest all to pass.
No dependency changes are planned. If a dependency change becomes necessary,
revise the plan first and rebuild the dashboard before checks.

Start the application's services with the existing data volume configuration,
checking existing Compose project ownership first to avoid creating an empty
second installation. Do not delete/reload the owner's database or secret volume.
The normal startup command, when this checkout owns the stack, is:

```powershell
docker compose up -d backend worker web dashboard
```

Use a real browser at `http://localhost:8501/`: verify actual release discovery,
all three flags, table/chart/totals alignment, CSV downloaded contents/filename,
refresh, county selection, diagnostics, keyboard focus, 320px reflow and zoom.
Follow Map and return to the dashboard with explicit reset guidance. Verify a
non-default public URL configuration. Simulate failures using fixtures or
browser/session-local controls, preserving the loaded dataset. Record which
spreadsheet application/import workflow was actually tested; if unavailable,
record that limitation instead of claiming it was verified.

Record the actual command outcomes, browser evidence and limitations in this
plan/journal. Create one reviewable PR for #74 after implementation review;
do not close #16 or #10 on the strength of this summary-only slice.

## Exclusions

No location request/page/export (#75), API/database writes or new endpoints,
multi-geography dashboard, location points, React implementation, real AI,
authentication changes, caching infrastructure, hosted CI or destructive data
operations. Changes beyond the listed scope require plan review first.

## Reference practices

- [ADR 0004](../decisions/0004-streamlit-analyst-dashboard.md): API-only
  dashboard; avoids a second implementation of data access and business rules.
- [HTTPX timeout controls](https://www.python-httpx.org/advanced/timeouts/):
  bounded connect/read/write/pool waiting prevents indefinitely stalled reads.
- [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest):
  test widget reruns and resulting elements at the application boundary.
- [Streamlit bar charts](https://docs.streamlit.io/develop/api-reference/charts/st.bar_chart)
  and [download buttons](https://docs.streamlit.io/develop/api-reference/widgets/st.download_button):
  use supported native rendering and download lifecycle controls.
- [Approved frontend guidelines](../frontend-guidelines.md): complete collection
  semantics, weighted rates, text alternatives and documented spreadsheet-safe
  CSV conventions are existing project requirements.

## Implementation and verification record — October 17, 2026

- Implemented the files and boundaries above without changing dependencies,
  lockfiles, API endpoints, backend code or database models. The native chart
  uses raw shares for ordering and one-decimal plotted values/tooltips, while
  CSV keeps six-place derived precision and authoritative raw counts.
- Strict response validation and complete collection constructors keep failed
  or partial traversals out of the result/export path. County names are read
  from county GeoJSON and polygons are discarded rather than retained in session.
- AppTest exposed the installed `vega_lite_chart` node (not the older node name).
  Tests inspect its actual Arrow dataset and spec as well as table values and
  captured CSV bytes across filter changes. Installed horizontal chart input
  labels are swapped by Streamlit; final output axes were verified in the spec
  and real browser. Native table output has six `th[scope=col]` headers.
- Development source reload initially retained old domain-class instances in
  session. Reinitializing a snapshot when its class no longer matches prevents
  invalid old/new dataclass comparisons. A regression test covers that reset.
- Final `docker compose run --rm --no-deps dashboard sh check.sh`: formatting,
  lint, strict mypy (14 Python files), and **108 tests passed**. This includes
  malformed responses, deadlines, finite geometry-size recovery, rejected paging
  links including port 0, missing observations/rollups, weighted rates, CSV
  prefixes and the real Streamlit filter/refresh/error lifecycle.
- `docker compose config --quiet` and `git diff --check` passed. No dashboard
  dependency change or rebuild was needed. No backend behavior changed, so no
  backend schema or full-data suite was required for this slice.
- Browser smoke used the Codex in-app browser against the existing
  `broadbandmap` installation and its loaded volume, with current checkout
  bind mounts. D25 / 2025-12-31 / processed 2026-09-29 returned 88 named counties:

  | Flag | Locations | Served | Not served | Displayed Served share |
  | --- | ---: | ---: | ---: | ---: |
  | Wired | 4,542,350 | 4,244,855 | 297,495 | 93.5% |
  | Any technology | 4,542,350 | 4,542,218 | 132 | 100.0% |
  | Terrestrial | 4,542,350 | 4,393,052 | 149,298 | 96.7% |

- Actual Terrestrial download:
  `ohio-county-summary-2025-12-31-processed-2026-09-29-terrestrial.csv`.
  Parsed the downloaded file, not just a generated test string: 88 rows and
  exact aggregate counts matching the table above; all rows had the Terrestrial
  flag and correct date/context fields. Adams retained `'39001`, 13,752 locations,
  9,696 served, 4,056 not served and 70.506108% in the CSV. Browser download
  completion reporting was unusually slow; this is not a measured performance
  claim for CSV generation.
- At 320px, measured document width 320px and no body overflow. The native table
  had a 276px scroll container with 383px content, keeping horizontal scrolling
  inside the table. Full date-pair/provenance text wraps outside the truncated
  native release control. Verified keyboard Arrow/Enter release selection,
  county selection and readable selected detail. J25 / 2025-06-30 / processed
  2026-10-01 showed 4,552,967 locations, 4,210,002 served, 342,965 not served,
  and 92.5%; Adams showed 13,868 / 7,401 / 6,467 / 53.4%.
- Verified Diagnostics and fresh Analysis return preserving the selected pair.
  Both same-tab links worked; returning through React reset to the default
  D25/Wired entry. A disposable dashboard on port 8502 with
  `WEB_APP_URL=http://localhost:5173/review/` produced and followed
  `http://localhost:5173/review/#/map`. That container was stopped and removed.
- Existing web/worker images lagged already-merged dependencies. Refreshed the
  web development container with `pnpm install --frozen-lockfile` (noninteractive
  `CI=true`), restarted it and rebuilt/recreated the worker from its existing
  lockfile. No dependency source changed. Removed the generated workspace
  `.pnpm-store` cache. Final live Diagnostics showed all four checks healthy.
- Saved a desktop browser screenshot as a chat artifact. Browser viewport
  overrides were reset after the narrow/desktop checks. A browser zoom shortcut
  did not change the in-app browser scale, so actual zoom is **not verified**.
  Desktop spreadsheet import is also **not verified**; raw leading-zero and
  formula-safety round trips are covered by pytest and the downloaded CSV was
  parsed with PowerShell. No WCAG conformance claim follows from this smoke pass.
- Location pages/export, real AI and broader feature reconciliation remain
  excluded. #16/#10 and #74's pre-existing issue status were not changed.
