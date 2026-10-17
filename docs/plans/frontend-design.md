# Issue #71: frontend screen and interaction design

Status: approved by the repository owner on October 16, 2026, as recorded in
[issue #71](https://github.com/ShawnMcCollum/BroadbandMap/issues/71#issuecomment-6224452648).
Branch: `codex/71-frontend-design`, originally based on `5bb75c9`. This document
defines the approved frontend design; the screens are not yet implemented.

The owner approved the design package in PR #81 at `e979c01`, including the
decision table, responsive wireframes and shared interaction conventions. The
owner had already selected **explicit filter reset when navigating between apps**.
Existing ADR decisions remain accepted; the new choices below are approved design
decisions, with implementation and runtime checks owned by the following issues.

## Scope and review method

Deliver four documentation changes: this plan, the self-contained
[responsive wireframes](frontend-wireframes.html), the
[frontend guidelines](../frontend-guidelines.md), and a README entry linking
them. The wireframes contain illustrative values and schematic map/chart
placeholders, not real observations. Open the HTML file directly in a browser;
it requires no installation, network access, or running application.

The six workflows are map exploration, county detail, analyst summaries,
location paging, administrator settings, and stub questions. Each wireframe
reflows from desktop to a narrow viewport; its state examples show the important
empty/error alternatives. The guidelines define behavior beyond the sketches.

Owner approval of the choices below satisfies the
design-first boundary in [#70](https://github.com/ShawnMcCollum/BroadbandMap/issues/70)
and [#71](https://github.com/ShawnMcCollum/BroadbandMap/issues/71).
Following implementation issues still require their own concrete plan review.
No package installation, feature implementation, backend/API change, issue
rewrite, or original-feature closure belongs to this slice.

## Tasks and information hierarchy

The map answers: **Where in Ohio is the selected 100/20 service flag available,
and what are the counts behind a county's percentage?** The dashboard answers:
**How do counties compare, and which location records support a county summary?**
The question screen demonstrates an inert interaction contract; it cannot answer
either analytical question.

Every exploration view places the title and short explanation first, then
release, fixed state (Ohio), technology flag, and optional county. One release
control displays a date pair, for example "December 2025 · processed 2026-09-29";
distinct processings are separate options. Use returned metadata rather than
hardcoded period text. Show loaded-state coverage beside it. No state selector
or finer-geography control advertises unsupported screens.

### 1. County map — #73

Desktop: full-width selection controls above a two-column map/detail area,
roughly two-thirds map and one-third detail. The map has zoom buttons and
"Fit Ohio", a sequential served-percentage legend, county outlines, and source
attribution. Below it, a readable county table provides an equal alternative.

Narrow: navigation wraps; controls, county selector, selected detail, map, legend,
and county table stack in that order. Map height is bounded (about 20rem), so it
does not consume the whole page. No essential content requires hover or gestures.

The legend encodes **Served share**, not Not served share. The approved bins are
0–<20%, 20–<40%, 40–<60%, 60–<80%, and 80–100%. Classify unrounded ratios;
display percentages to one decimal. Missing observations use a separate neutral
hatched category labeled "No summary observation"; an actual 0% stays in the
first blue bin. The table/detail always supplies text and exact counts.

### 2. County detail — #73

Hover shows a short, transient county preview without changing selection. Click,
native county select, or a table's "Select [county]" button establishes persistent
selection. Leaving the canvas clears only the hover preview. Selecting "All
counties" clears detail. Changing release/flag keeps the county identifier but
clears and reloads its values; selection survives only if the county is valid.

Desktop detail stays beside the map. Narrow detail sits before the map. It shows
county name, GEOID, location total, Served and Not served counts, served percentage,
and the selected flag and date pair. Selection updates one politely announced
detail region without moving keyboard focus. A native selector is the keyboard
path; users do not have to tab through 88 canvas features. When WebGL fails,
the selector, table, counts, and data provenance remain usable.

For a boundary without a summary, issue an exact-code lookup to distinguish
no observations, outside coverage, and unavailable rollups. Until then, display
"No summary observation" rather than a more precise unproven diagnosis.

### 3. Analyst summaries — #74

Desktop: filters above a weighted statewide summary, horizontal county served-share
chart, full county table, and "Download summary CSV". The table is the chart's
text alternative. Chart ordering is descending served share, then GEOID; table
ordering is county name, then GEOID. All rows derive from the same complete data.
Do not show statewide totals or enable export while any summary page is missing.
Call aggregates "Observed county totals" and report observation coverage rather
than asserting a full statewide observation set from boundaries alone.

Narrow: filters and totals stack; chart stays readable vertically; the table
scrolls inside its own labeled region. Identifiers never truncate without a way
to read/copy the full value. County selection uses a native control, then an
explicit "View locations" button, rather than relying on table-row click support.

CSV contains only summary rows and the selected context; it never exports all
location records. Use the columns, filename and identifier convention in the
guidelines; #74 verifies serialization/import behavior. A visible refresh action starts
a fresh read of the current explicit selection.

### 4. County location pages — #75

Remain within the dashboard below summaries, with "Back to county summaries".
Display the county, date pair, flag, status filter (All / Served / Not served),
and rows per request (100 / 250 / 500 / 1,000; default 100). Show one page of
location ID, block GEOID, H3 res-8, and all three Boolean source flags as Yes/No.
"Previous" and "Next" follow the API links; "100 rows shown" describes this
response, not a total or page number. Both controls fit side by side on narrow
screens; the table alone may scroll horizontally.

Any context or page-size change starts without a cursor. A 409 dataset change
clears the page and links and offers "Restart locations". A cursor-specific
400 also offers restart; a non-cursor validation error keeps its own correction.
A deleted release requires rediscovery. Empty filtered results say "No locations
match this status filter" only when `area_coverage` is `observed`.

### 5. Administrator AI settings — #76

A dedicated React page shows "AI settings — application administrators".
Public visitors see sign-in/access guidance until the protected GET succeeds.
Do not infer logged-out versus unpermitted identity from a generic 403. A sign-in
link is available; a successful protected read establishes access for this page.

Desktop: a form (enabled, provider identifier, model identifier, timeout, output
limit) beside saved nonsecret status. Narrow: form, saved status, and removal
section stack. All inputs have labels, constraints, and error associations.
Timeout/output limits are explicitly future-provider settings, not promises of
current provider calls. Provider/model identifiers are unverified free text,
not a fabricated provider catalog.

The masked "Replacement provider key" field starts blank. Blank means preserve
the saved key by omitting `api_key`; a replacement is 1–4,096 nonblank trimmed
characters. Show only Key configured / Key available
indicators. "Save settings" has a pending state; after success clear the key
input and re-read persisted metadata. After an uncertain network result, say
"Save could not be confirmed; reload saved settings before retrying". Never
claim the previous state must have survived an ambiguous transport failure.

"Remove key" reveals an inline confirmation: "Remove the saved key and disable
the stub?" with Cancel / Remove key and disable. Confirming sends only
`clear_api_key: true`. It does not save unrelated unsaved form edits. A provider
change requires replacement or this explicit removal first. If storage is
unavailable, explain the deliberate remove-then-replace recovery. Clear replacement
input when leaving, signing out, or losing authorization; never persist it.

### 6. Stub questions — #77

A separate React "Ask (stub)" page has a persistent statement: "Demonstration
stub: no provider is contacted and no broadband data is queried. Map filters
are not sent." Enabled: labeled question textarea, 2,000-character guidance,
submit button, normalized submitted question and answer rendered as plain text.
Desktop uses a bounded reading width; narrow stacks the same elements.

Disabled: administrator guidance and a link to AI settings, with submission
unavailable. Status-read failure offers Retry status, distinct from disabled.
Submitting prevents duplicates; no silent POST retry. Retain correctable input
on failure, and ignore late results after navigation or a newer request.
Re-entering the page refreshes status after administrator changes. Questions
and answers are transient and do not become conversation history.

## Navigation and browser integration

Use native links and a small hash-route switch: `/#/map`, `/#/ask`,
`/#/settings/ai`, `/#/diagnostics`; bare `/` opens map. This avoids adding a
router or server route fallback for four screens. Unknown hashes show a helpful
page with a map link. On route changes update the document title and focus the
main heading; do not move focus on ordinary data updates. Keep exploration
selection in the root owner while visiting other React pages, but refresh reads
when returning. Clear protected metadata and key input when leaving settings.

React navigation: Map / Analyst dashboard / Ask (stub) / AI settings.
Diagnostics is a secondary footer link. Dashboard navigation links to Map and
Ask (stub); its diagnostics is a secondary view. All cross-app links open in the
same tab with adjacent text: **"Opens the other app with default filters."**
Each destination starts a fresh application load: latest available date pair,
Ohio, wired, no county. No query-string transfer, shared storage, or claim of
synchronized selection. Browser Back/Forward may restore historical state;
each app must label and validate any restored selection, not promise a reset
for history navigation it does not control.

Approved configuration design, to be implemented by #72/#74:

| Setting | Default and use |
| --- | --- |
| `VITE_DASHBOARD_URL` in web | Browser-visible dashboard URL, default `http://localhost:8501/` |
| `WEB_APP_URL` in dashboard | Browser-visible web URL, default `http://localhost:5173/` |
| Compose interpolation | Derive those defaults from `DASHBOARD_PORT` / `WEB_PORT`; optional explicit public URL overrides support non-local browser hosts |
| Existing `API_PROXY_TARGET` | Server-only web proxy target `http://backend:8000`; never a navigation destination |
| Existing `API_BASE_URL` | Dashboard server-to-API target `http://backend:8000`; never a browser link |

Validate configured navigation URLs as HTTP(S) without embedded credentials.
Document that Vite environment changes require restarting/rebuilding the affected
frontend; ordinary AI settings saves do not. These settings are planned rather
than currently available: #72/#74 wire them through Compose and `.env.example`
and test port overrides.

For #76, use the existing Django admin session at the **web origin**:

1. GET protected configuration. On 403 show "Sign in with an authorized staff
   account, or ask an application administrator for access" without exposing settings.
2. Link to `/admin/login/?next=%2F%23%2Fsettings%2Fai`. URL-encode the fragment
   inside the same-origin return path; a literal unencoded `#` would not reach Django.
3. Extend Vite proxying to `/admin/` and `/static/`, alongside `/api`. Preserve the
   browser Host/Origin for Django's allowed-host and CSRF checks; confirm web-origin
   requests and redirects in a real browser. Use the existing development static
   serving; production static hosting is separate work. No CSRF disabling/CORS workaround.
4. Re-read configuration after login to obtain the current CSRF cookie, then
   PATCH same-origin with session credentials and `X-CSRFToken`. Django login
   can rotate the token; do not retain an earlier token across sign-in.
5. Sign out with a CSRF-protected native POST form to `/admin/logout/`, including
   `csrfmiddlewaretoken` and the fixed `next=/#/settings/ai` form value. Clear
   sensitive client state before departure; recheck access on return.

An already authenticated staff user visiting Django admin login can be redirected
to the admin index instead of `next`. #76 should add a small admin base-template
override with an "AI settings" return link, including on the logged-out page;
do not invent a session/capabilities API. Plan the template, proxy settings and
integration tests explicitly. A staff login alone never grants configuration
permission. Use disposable accounts/credentials for verification.

## Map dependency and resource review

The approved dependency is **`maplibre-gl` 6.14.0**, to be pinned exactly in #73
and locked with pnpm.
Its [tagged package metadata](https://github.com/maplibre/maplibre-gl-js/blob/v6.14.0/package.json)
declares ESM, bundled TypeScript types, Node >=16.14, and TypeScript 6 / Vite 8
development dependencies. The repo's Node 22, TypeScript 6.0.3 and Vite 8.3.4
are compatible on those declared constraints; this is a metadata review, not a
successful install/build/WebGL test. #73 must verify the locked dependency graph,
Docker checks/build and actual browser rendering before claiming compatibility.

Follow the [MapLibre Vite installation instructions](https://maplibre.org/maplibre-gl-js/docs/):
import `maplibre-gl/dist/maplibre-gl.css`, bundle
`maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url`, and call `setWorkerUrl`
before constructing the map. Use direct MapLibre APIs without a React wrapper.
Include the shipped CSS and package license in the built dependency handling.

Use a local style-spec version 8 object: neutral background, county GeoJSON
source, served-share fill, county outlines, and selected outline/hover treatment.
No tile source, sprite, remote style, glyph request, web font, or API key is
needed: county labels and detail are HTML. Attribution remains visible: FCC
National Broadband Map, selected data period/processing; Census TIGER/Line 2020
boundaries; MapLibre renderer credit. A neutral background is intentional; no
basemap geography is implied.

ADR 0018 measures all 88 Ohio counties at 3,344,412 bytes and the matching summary
at 12,251 bytes. Load unchanged boundaries separately from selection-dependent
counts, preserving the in-memory map during flag changes. Honor `no-store` for
network reads and release resources on unmount. Do not introduce tiles or geometry
simplification without new measurements and a reviewed decision.

## Decisions, ownership, and remaining checks

| Choice | Status | Why / next owner |
| --- | --- | --- |
| React map, Streamlit analytics, API-only reads | Accepted ADRs 0004/0018 | Preserve established responsibilities; #73/#74 |
| Wired default, 100/20 complement wording, explicit date pair | Accepted API/domain decisions | Avoid inconsistent interpretation; #72–#77 |
| Cross-app links reset filters with clear guidance | Owner selected during #71 | Avoid unsupported synchronization; #72/#74 |
| Four hash routes; diagnostics secondary | Owner approved in #71 | Small navigation surface without a router; #72 |
| Five sequential blue bins, hatch missing observations, table alternative | Owner approved in #71 | Stable comparable scale and non-color access; #73 |
| Tile-free MapLibre 6.14.0 with bundled CSS/worker | Owner approved; metadata checked | Fits existing county geometry; runtime proof in #73 |
| Light analytical palette, system fonts, native controls | Owner approved in #71 | Small dependency/maintenance surface; #72/#74 |
| Dashboard county selector and explicit drill-down action | Owner approved in #71 | Predictable keyboard and Streamlit behavior; #74/#75 |
| Context-bearing summary CSV with text-prefixed identifiers | Owner approved in #71 | Keep release provenance and avoid numeric identifier inference; #74 verifies import behavior |
| Existing Django sign-in/POST sign-out plus return-link template | Owner approved in #71 | Reuse sessions/CSRF; real redirect/static proof in #76 |
| Future-provider settings and plain-text stub answer | Accepted ADR 0020 | No live provider or analytical claims; #76/#77 |

Owner review approved the new design choices on October 16, 2026; the approval
link above is the record of that decision.
Remaining engineering checks have explicit owners; they are not unanswered UX
choices: #73 verifies the pinned package and WebGL/payload behavior; #76 proves
same-origin login/logout/return, static assets, cookie rotation and denial; #74
checks native Streamlit layout/selection/export behavior. Any failed check that
changes these choices returns for review rather than silently changing the design.

## Validation and handoff

For #71: check relative links, terminology and endpoints against the reviewed
OpenAPI and ADRs 0004/0018/0019/0020. Inspect all six wireframes at desktop
(1,280px), narrow (390px), and 320px widths, including keyboard navigation,
long IDs, state examples and print/readability. Run `git diff --check`; include
new files in whitespace validation. No app test suite is necessary for this
documentation-only change. The performed checks are recorded below.

The [guidelines](../frontend-guidelines.md#implementation-boundaries) identify
proposed files, owning slices and their tests. Each implementation issue still
needs its own exact plan, dependency review, container commands and expected
outcomes. #78 records real cross-app, WebGL, authentication and accessibility
evidence; these sketches are not that evidence.

### Checks performed on October 16, 2026

- Reviewed the six desktop and six narrow-screen screenshots in local headless
  Microsoft Edge through the bundled Playwright runtime. No dependency was added
  to the repository. Counts and geography placeholders remain explicitly illustrative.
- At 1,280px, 390px and 320px, including all seven expanded state-example groups,
  document width equaled viewport width. Wide tables scroll within their own region.
- Browser checks found six workflow sections, no duplicate IDs, no unlabeled
  form controls, no JavaScript errors and no external resource requests.
- Keyboard checks reached the skip link first and expanded a state example with
  Enter. Narrow map/detail DOM reading order matches the visual stack. A later
  real-product accessibility pass is still required.
- All relative file links in README and the two Markdown design documents resolve.
  Endpoint names, coverage fields, cursor errors and input limits were compared
  with the local OpenAPI and serializers. Print media kept the body at viewport
  width; this is not a full print-layout certification.
- Whitespace and final changed-file scope are checked before delivery. No app
  tests, real data queries, configuration writes, package installation or WebGL
  runtime verification belong to these document checks.

## References

- [API guidelines](../api-guidelines.md) and
  [reviewed OpenAPI](../../backend/core/api/openapi.json).
- [ADR 0004](../decisions/0004-streamlit-analyst-dashboard.md),
  [ADR 0018](../decisions/0018-county-geojson-map-output.md),
  [ADR 0019](../decisions/0019-location-cursors.md),
  [ADR 0020](../decisions/0020-natural-language-query-stub.md).
- [React shared-state guidance](https://react.dev/learn/sharing-state-between-components):
  one selection owner prevents divergent map/detail/export state.
- [W3C use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
  and [keyboard access](https://www.w3.org/WAI/WCAG22/Techniques/general/G202):
  text/table controls accompany the canvas and its colors.
- [Django CSRF](https://docs.djangoproject.com/en/5.2/howto/csrf/) and
  [Django admin implementation](https://github.com/django/django/blob/stable/5.2.x/django/contrib/admin/sites.py):
  preserve session/CSRF behavior and account for admin redirects.
