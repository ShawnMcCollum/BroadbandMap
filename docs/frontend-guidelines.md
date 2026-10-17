# Frontend guidelines

Status: approved by the repository owner on October 16, 2026, as recorded in
[issue #71](https://github.com/ShawnMcCollum/BroadbandMap/issues/71#issuecomment-6224452648).
API and accepted ADR requirements cited here also apply.
See the [design and decision table](plans/frontend-design.md) and
[responsive wireframes](plans/frontend-wireframes.html). These describe planned
screens. The React application now provides the county map and accessible
table/detail; the Streamlit dashboard provides county summaries, technology
filters, a chart and summary CSV, with diagnostics as a secondary view.

## Vocabulary and provenance

| Display | Meaning |
| --- | --- |
| Served / Not served (100/20 Mbps) | Selected source Boolean flag and its complement; never infer regulatory unserved/underserved categories |
| Wired (default) | Source `wired_100_20` flag |
| Any technology | Source `any_100_20` flag |
| Terrestrial | Source `terrestrial_100_20` flag |
| Data period / Processed | Returned `as_of` and `processed_on`, always treated as a pair |
| Loaded states | Returned release `states`; national release identity does not imply nationwide loaded data |
| Boundaries | Census TIGER/Line 2020; geometry is independent of observations |
| No summary observation | A county has no joined summary; investigate coverage rather than substituting zero |
| Ask (stub) | No external provider, broadband query, or map-filter context |
| AI settings | Installation-wide configuration for authorized application administrators |

Explain 100 Mbps download / 20 Mbps upload and the three source flag names in
visible help. Do not expand them into unsupported provider/technology claims.
Retain the FCC source, selected filing period, both dates, loaded-state coverage
and boundary vintage in every data view/export context. Identifiers remain
strings; never convert GEOIDs, FCC location IDs or H3 IDs to numeric values.
Format counts with locale separators; use exact counts and one-decimal percentages
in UI. CSV carries raw counts and explicit identifiers/context.
Repeat the full date pair as wrapping metadata outside the native release select,
whose selected option can be visually truncated on narrow screens.

## Selection, requests, and pagination

Each app has one exploration selection owner:
`{as_of, processed_on, state: "39", flag, county: string | null}`.
The dashboard adds location `{status, page_size, current response links}`.
Views derive data from that owner; they do not keep independently editable copies
of release or flag. On a fresh app entry discover all release pages, choose
latest by data period then processing date, and pin both returned dates. Never
silently fall back to an older release if Ohio is absent.

| Event | Required response |
| --- | --- |
| Release or flag changes | Clear dependent summary/detail/export values and location traversal; cancel/ignore obsolete results |
| County changes | Clear prior detail/location page; issue the new exact selection |
| Location status or page size changes | Start without the old cursor |
| New navigation result arrives | Verify it still belongs to the current selection/request before applying |
| Re-enter exploration or explicit Refresh | Fresh reads for the visible selection; no silent switch of date pair |
| Selected release disappears | Clear dependent data, rediscover releases and ask for a selection; no automatic substitution |
| Cross-app link | Full same-tab navigation to configured destination with default filters; visible reset guidance |

While updating, retain the geometry but clear old thematic fills to neutral and
mark counts/details as loading; never show old colors beneath new filter labels.
Disable export and location navigation until the current data is valid. A failed
read must not convert previously displayed values into apparent current values.

Read only through the documented API. TypeScript uses `/api` on the web origin;
Python uses server-side `API_BASE_URL` and bounded timeouts. Parse Problem Details
safely, including field pointers and request IDs; handle non-JSON or unexpected
shapes without dumping raw payloads. Cancellation prevents work where possible;
a request/selection identity check prevents late results even if abort is ignored.

Release/summary collections are complete only after all their pages succeed.
GeoJSON uses `features`; releases/summaries use `results`. Validate API-provided
pagination destinations against the configured origin **and the current endpoint
path**, without changing their query strings. Relative links resolve only within
that endpoint. The Vite-proxied API should generate web-origin links; reject
unexpected origins and diagnose proxy configuration, rather than blindly trusting
container-host links. No arbitrary URL fetch, credential forwarding, or browser
navigation to internal container names.

Location pages are different: keep only the current bounded page and opaque
next/previous links; never fetch all locations. No fabricated total, page count,
random jump, or full location CSV. Invalid cursor means a structured 400 field
error pointing at `/cursor`; there is no invented top-level `invalid_cursor`
code. A 409 `dataset_changed` clears the traversal and requires explicit restart.
The backend does not currently promise time-based cursor expiry.

All reads honor `Cache-Control: no-store`: transient in-memory component/session
state may hold the visible response, but no process-wide or browser persistent
data cache, background prefetch, or persistent questions/credentials. A stable
geometry object can remain mounted during flag/release changes; no unnecessary
boundary reload. Explicit date pairs do not make separate API pages one snapshot.

## Counts, missing data, and export

Compute `served / locations * 100` from the selected flag. The observed aggregate
is `sum(served) / sum(locations)`, never an average of county percentages.
Example: 1/1 and 1/9 aggregate to 2/10 = 20%, not 55.6%.
An absent summary has no percentage; never assign it 0%. Classify colors before
rounding and give 100% the last bin. Use exact-code reads for precise missing
coverage diagnosis. Location `area_coverage` describes the area before filtering.

CSV is disabled until the selected summary collection is complete. Approved
column order: `county_geoid`, `county_name`, `locations`, `served`, `not_served`,
`served_share_percent`, `flag`, `as_of`, `processed_on`, `loaded_state_codes`,
`fcc_source`, `boundary_vintage`. Percentage is a derived decimal (up to six
places); raw counts remain authoritative. Encode loaded-state codes as a
semicolon-separated list. Filename example:
`ohio-county-summary-2025-12-31-processed-2026-09-29-wired.csv`.

Use a real CSV writer, UTF-8 with BOM for the intended spreadsheet workflow,
and quote fields as required. Quoting alone neither prevents spreadsheet
formulas nor preserves leading zeros. Prefix county GEOIDs and the loaded-state
text with a literal apostrophe, and prefix arbitrary text whose first nonspace
character is a formula trigger (`=`, `+`, `-`, `@`) or begins with tab/CR/LF.
Do not emit spreadsheet formulas such as `="39001"`. Explain the text prefix
beside the download; programmatic consumers remove the documented prefix from
identifier fields. #74 tests raw CSV round trips and records actual spreadsheet
import behavior; do not promise identical automatic typing in every spreadsheet.

## State inventory and recovery copy

| Condition | Visible behavior and action | Owner |
| --- | --- | --- |
| Initial load | "Loading releases…" / "Loading county summaries…"; status region and no invented zeros | #72/#74 |
| Ready | Data, date pair, flag and coverage belong to one selection | All features |
| No releases | "No data releases are loaded. Follow the README data-load instructions, then refresh." Link to instructions; no operational controls | #72/#74 |
| Ohio absent from selected release | "Ohio is not loaded for this release." Keep release control available | #72/#74 |
| Missing joined summary | "No summary observation." Neutral hatch; selected exact-code lookup refines the explanation | #73/#74 |
| `no_observations` | "No locations were observed in this area for this release." No served classification | #73/#75 |
| `outside_release_coverage` | "This area is outside the loaded coverage of this release." Offer release selection | #73/#75 |
| 503 unavailable rollups | "County summaries are unavailable. Try refreshing; an application operator may need to rebuild them." Never show all counties as Not served | #73/#74 |
| Empty observed location filter | "No locations match this status filter." Keep area coverage separate; change filter | #75 |
| 409 dataset change | "The data changed. Restart locations to read a fresh page." Clear links/data; explicit Restart locations | #75 |
| 400 cursor error | "This location link is no longer valid. Restart locations." Other 400s keep field-specific correction | #75 |
| Geometry payload too large | For `/page_size` error code `geometry_payload_too_large`, restart geometry collection with 100 → 50 → 25 → 12 → 6 → 3 → 1; discard partial attempt; stop at 1 with actionable failure | #73 |
| WebGL unavailable/context lost | "Interactive map unavailable. Use the county selector and table below." Counts/selection still usable | #73 |
| Network, non-JSON or unexpected response | Safe resource-specific failure, Retry for GET, request ID when available; no traceback/raw body | All features |
| Protected GET 403 | Sign-in/access guidance, no configuration or identity guess | #76 |
| PATCH 403 / expired session / CSRF rejection | "Settings were not saved. Sign in or reload saved settings, then try again." No automatic write retry | #76 |
| Save transport failure | "Save could not be confirmed. Reload saved settings before retrying." Do not assert rollback | #76 |
| Stub disabled | "Ask an application administrator to enable the stub in AI settings." No provider key form for public users | #77 |
| Public status request fails | "Could not check stub availability." Retry status; do not label disabled | #77 |
| Query 503 disabled/unavailable credentials | Retain question, distinguish backend codes, direct administrator action, refresh status | #77 |
| Form validation | Summary plus field-associated messages; focus summary/first invalid field after submit; retain nonsecret correctable input | #76/#77 |

Keep safe server messages and structured pointers where useful; add request ID
as supporting text, not an intimidating error headline. Announce loading and
results with a polite status region; announce blocking submit errors once.
Do not announce every hover or move focus on automatic refreshes.

## Visual and accessibility conventions

Approved light analytical palette (first version has no theme switch):

| Token | Value / use |
| --- | --- |
| Canvas / surface | `#f6f8fa` / `#ffffff` |
| Primary / secondary text | `#172b3a` / `#40566b` |
| Action / link | `#155b83`, underlined links, white text on filled primary buttons |
| Focus | 3px `#172b3a` outline with 2px white separation, visible on all surfaces |
| Error | `#a82020` text and icon/label, never color alone |
| Served scale low → high | `#eff3ff`, `#bdd7e7`, `#6baed6`, `#3182bd`, `#08519c` |
| Unclassified | `#e5e7eb` with dark hatch and text label; not part of the percentage scale |
| Selected / hover county | Dark selected outline with white halo; hover uses lighter outline without changing persistent selection |

Check actual foreground/background contrast in implementation: targets are
4.5:1 for ordinary text and 3:1 for control/focus boundaries. Scale swatches do
not carry essential text internally; pair every geographic color with table
values and labels. Do not claim WCAG conformance from a palette or smoke pass.

Use system sans-serif, body 1rem/1.5 line height, secondary text at least 0.875rem;
headings 2rem and 1.5rem. Use tabular numerals for counts. Spacing units:
4/8/12/16/24/32px. Native selects, labeled inputs, checkboxes and buttons; action
targets aim for 44px. No custom dropdowns, hover-only menus, decorative metric
cards, web fonts, or component framework. Streamlit uses supported native theme
and layout controls; do not patch generated DOM classes to imitate React exactly.

At >=64rem use map/detail columns; 48–64rem lets filter rows wrap; below 48rem
stack content and navigation in DOM reading order. Body must reflow at 320px and
browser zoom; only data tables may have contained horizontal scrolling. Keep
source/coverage text visible at narrow widths. No modal drawer for county detail.
Avoid sticky overlays that cover content, focus, or the map's attribution.

Use landmarks, one main heading, a skip link, visible focus, semantic table
headers/captions, associated form help/errors, and native keyboard activation.
Focus navigation headings after explicit route changes, not after map selection.
Keep error/recovery actions in the flow. Disable motion under reduced-motion
preferences; no required animation. Chart tables and county selection must work
without canvas, color discrimination, pointer input, or external tile services.

## Implementation boundaries

These are planned file responsibilities, not instructions to create empty
frameworks. Each issue reviews exact files before coding and tests behavior at
the owning boundary. Types/fixtures align with OpenAPI; do not add a generator
without a concrete benefit.

| Slice | Proposed files / responsibilities | Verification |
| --- | --- | --- |
| #72 | `web/src/App.tsx`, `navigation.ts`, `styles.css`; `api/http.ts`, `api/types.ts`, `api/releases.ts`; `features/exploration/` selection owner/controls; `features/diagnostics/` reuses `health.ts`; Compose/env navigation configuration | Vitest/Testing Library: release pages, date pairs, Ohio absent, errors, URL rejection, A→B late response; Docker web check/build; keyboard shell |
| #73 | `web/src/api/counties.ts`, `api/rollups.ts`; `features/map/CountyMap.tsx`, `CountyDetail.tsx`, `CountyTable.tsx`, `join.ts`, `style.ts`; matching tests, package/lock changes | Pure join/ratio/missing fixtures; component races/fallback/paging; real 88-county WebGL, payload and cleanup check |
| #74 | `dashboard/app.py` orchestration; `api.py` HTTP/errors/origin policy; `selection.py`, `summaries.py`, `exports.py`, tests; Compose/env public web navigation | pytest/httpx paging/errors/weighted totals/CSV; Streamlit AppTest filters/chart/table/export; browser narrow layout |
| #75 | `dashboard/locations.py` page/reset/recovery UI; extend client/selection and tests | Opaque next/previous, no all-page fetch, 409/cursor recovery, coverage/filter-empty AppTest |
| #76 | `web/src/api/ai.ts`; `features/ai/AISettings.tsx`, tests; `web/vite.config.ts`; backend admin base template override and focused routing/auth tests identified in its plan | GET/CSRF/PATCH/key semantics, denial, actual login/static/logout/return and expired session; backend checks if changed |
| #77 | Extend `api/ai.ts`; `features/ai/QuestionPanel.tsx`, tests | Exact question-only POST, normalization/limits, escaped answer, enabled/disabled/failure/races; no provider calls |
| #78 | `docs/frontend-verification.md`, README; focused missing integration checks | Actual cross-app/port overrides, accessibility, failure, WebGL and auth evidence; reconcile original features |

Use schema-aligned fixtures in each existing test suite, with documented common
examples rather than cross-language client-code sharing: same period with two
processings; newest release excluding Ohio; missing county; 1/1 + 1/9 weighted
example; multi-page collections; malformed/non-JSON; generation conflict;
disabled stub and unavailable credentials. Dummy credentials never appear in
published screenshots, logs or documentation.

Run the owning container commands:

```powershell
docker compose run --rm --no-deps web pnpm check
docker compose run --rm --no-deps web pnpm build
docker compose run --rm --no-deps dashboard sh check.sh
```

Backend/configuration changes also run backend `sh check.sh` and schema drift
checks as documented in README. Record command outcomes and actual manual checks.
Mocks do not prove WebGL or real sessions/CSRF; final evidence must cover those
boundaries. Avoid hosted CI, broad new test infrastructure and destructive
changes to the owner's loaded data for a demonstration.

## Design references

The [design plan](plans/frontend-design.md#references) links accepted ADRs,
React's shared-state guidance, W3C keyboard/color guidance, Django's CSRF
documentation and MapLibre's package/resource instructions. Their practical
purpose here is to prevent divergent selection state, inaccessible canvas-only
workflows, duplicate business rules, and a second authentication system as
features grow.
