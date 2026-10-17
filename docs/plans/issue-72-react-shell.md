# Issue #72: React API client, release selection, and application shell

Status: implemented and verified; awaiting pull-request review. The repository
owner approved the posted plan on October 16, 2026 with "Yes, move forward" and
selected the real bounded summary readiness status during planning.
Posted for review in [issue #72](https://github.com/ShawnMcCollum/BroadbandMap/issues/72#issuecomment-6227281379).

Issue: [#72](https://github.com/ShawnMcCollum/BroadbandMap/issues/72), under
[#70](https://github.com/ShawnMcCollum/BroadbandMap/issues/70).
Branch: `codex/72-react-shell`, based on merged `main` at `0f8cc48`.

## Review findings and settled scope

- #71 is closed and its approved design is merged in PR #81. Follow
  [frontend design](frontend-design.md) and
  [frontend guidelines](../frontend-guidelines.md); do not reopen their choices.
- React currently renders only stack health. Existing dependencies already
  provide React, TypeScript, Vite, Vitest, Testing Library, jsdom and Prettier.
  Add no dependency, generator, router, global store, cache or UI framework.
- The reviewed OpenAPI and backend serializers already support release discovery,
  summary reads, structured errors and coverage. No backend contract change,
  migration, model field, database constraint or source-data reload is required.
- The owner selected a **real county-summary readiness status** during planning.
  A bounded summary GET will demonstrate date/flag requests, loading, failure
  and stale-response protection. It renders no county rows, totals or map. This
  narrowly brings the rollup client's first-page read into #72; #73 extends it
  for complete collections and county rendering rather than adding another client.
- Keep diagnostics on a secondary route using the unchanged `health.ts`
  contract, including health's meaningful HTTP 503 response. Ask and AI settings
  routes have truthful feature-unavailable content linking to #77/#76; no forms,
  login integration, availability checks or provider requests in this slice.

## Evidence checked before writing this plan

- Inspected `web/src/{App.tsx,App.test.tsx,health.ts,main.tsx}`, Vite, TypeScript,
  lint, package/lock settings, Compose and `.env.example`.
- Compared `backend/core/api/openapi.json` with release, rollup, geography and
  Problem Details serializers, release ordering tests and pagination construction.
- Read-only requests to the running API returned two loaded releases. With
  `page_size=1`, the first was `D25`, `as_of=2025-12-31`,
  `processed_on=2026-09-29`, states `39 / Ohio / OH`; `next` was an absolute URL
  on the origin used for the request. Headers included `application/json`,
  `Cache-Control: no-store` and `X-Request-ID`.
- `GET /api/v1/served-unserved/rollups/?level=county&state=39&flag=wired&page_size=1`
  returned HTTP 200, count 88, one row, a pinned date pair, matching selection,
  100/20 threshold, boundary vintage 2020 and `stored_rollups_only` coverage.
  This confirms a small request can establish endpoint readiness; one row is
  not a complete county collection or a statewide observation claim.
- Before changes, Docker web `pnpm check` passed formatting, lint, type checks
  and all three existing tests. Docker web `pnpm build` passed too. Docker is
  installed at `C:\Program Files\Docker\Docker\resources\bin\docker.exe` but
  is absent from this terminal's PATH; commands below add that directory locally.
- Existing data was read only. New failure/coverage/race cases use fixtures.
  Actual browser/proxy behavior remains an implementation verification step.

## Exact file changes and responsibilities

Paths below are repository-relative. Do not create additional framework modules
or change dependencies without revising the plan.

| Action | File | Responsibility |
| --- | --- | --- |
| Change | `web/src/App.tsx` | Shell landmarks/navigation, root selection owner, hash-route content, heading focus and title updates |
| Change | `web/src/App.test.tsx` | User-visible shell, routes, controls, coverage, refresh, errors and integrated request races |
| Change | `web/src/main.tsx` | Import shared CSS; retain StrictMode |
| Change | `web/vite.config.ts` | Approved amendment: preserve browser Host in `/api` proxy for pagination links |
| Create | `web/src/navigation.ts` | Four hash routes, unknown-route handling, validated dashboard destination |
| Create | `web/src/navigation.test.ts` | Hash mapping and configured public-URL validation |
| Create | `web/src/styles.css` | Approved tokens, native controls, focus, responsive shell and status/error presentation |
| Create | `web/src/api/types.ts` | Handwritten types for consumed release, summary, selection and Problem Details contracts |
| Create | `web/src/api/http.ts` | Same-origin GET boundary, JSON/GeoJSON media handling, timeouts, safe failures, pagination URL resolver |
| Create | `web/src/api/http.test.ts` | Transport, response parsing, URL policy, abort and timeout behavior |
| Create | `web/src/api/releases.ts` | Release page decoder and complete catalog discovery |
| Create | `web/src/api/releases.test.ts` | Catalog paging, date versions, invalid pages and failed/incomplete discovery |
| Create | `web/src/api/rollups.ts` | Decode and fetch one bounded county summary page for readiness |
| Create | `web/src/api/rollups.test.ts` | Exact selection queries, metadata matching and bounded first-page behavior |
| Create | `web/src/features/exploration/useExploration.ts` | Root-invoked hook owns selection, catalog, refresh and active summary read lifecycle |
| Create | `web/src/features/exploration/Exploration.tsx` | Controlled release/flag inputs, provenance, Ohio coverage and real readiness status |
| Create | `web/src/features/diagnostics/Diagnostics.tsx` | Existing health UI moved to diagnostics with GET Retry and obsolete-result guard |
| Create | `web/src/features/diagnostics/Diagnostics.test.tsx` | Existing health success/503/failure behavior plus navigation/unmount safety |
| Create | `web/src/test-fixtures/api.ts` | Shared schema-aligned fixture builders and deferred read helper; no production imports |
| Change | `docker-compose.yml` | Web `VITE_DASHBOARD_URL` interpolation only; preserve proxy/backend configuration |
| Change | `.env.example` | Optional browser-visible dashboard URL override and restart guidance |
| Change | `README.md` | Shell/routes, readiness limitation, diagnostics, navigation configuration and verification commands |
| Change | `docs/journal.md` | Brief implementation reasoning and actual verification evidence after approval |
| Create/update | `docs/plans/issue-72-react-shell.md` | Review record, approval link and performed-check outcomes |

No changes to `health.ts`, package manifests, lockfile or dashboard source.
The minimal `/api` proxy amendment below is approved. `WEB_APP_URL` belongs to
#74; admin/static proxy and sessions belong to #76.
Test behavior through `App`, rather than testing hook implementation details.

### Approved proxy amendment

During implementation, a real request through `http://localhost:5173/api` returned
`next: http://backend:8000/api/v1/releases/?page=2&page_size=1`. Inspection of the
installed Vite implementation confirmed that a string proxy target implicitly
sets `changeOrigin: true`. A read-only backend probe preserving
`Host: localhost:5173` produced the correct browser-origin link.

The owner explicitly approved adding `web/vite.config.ts` to scope on October 16,
2026: replace the string target with `{ target: ..., changeOrigin: false }` and
verify real pagination through the web origin. No path rewrite, backend change,
authentication workaround or relaxation of client URL validation is included.
See [Vite proxy options](https://vite.dev/config/server-options#server-proxy).

## Types and HTTP boundary

1. Handwrite the small consumed surface from OpenAPI: `StateSummary` has string
   `code/name/abbreviation`; `ReleaseSummary` has string `filing_period/as_of/processed_on`
   and `states: StateSummary[]`; `ReleasePage` has integer `count`, nullable-string
   `next/previous` and `results: ReleaseSummary[]`. Identifiers stay strings.
2. `Flag = 'wired' | 'any' | 'terrestrial'`. An exploration selection has both
   date strings, `state: '39'`, `flag`, and `county: string | null`. Unselected
   dates are represented by `selection: null`, never half a date pair.
3. Model `RollupPage` and its row, `release`, nullable-code/state `selection`,
   `threshold`, nullable `boundary_vintage`, and all four `summary_coverage`
   values exactly as reviewed. Do not add feature-specific location/AI types
   until those features consume them.
4. Problem Details includes `type/title/status/detail/code/request_id` and optional
   `errors: {pointer, code, message}[]`. Preserve empty/global pointers and field
   pointers. Client failure kinds distinguish HTTP problem, HTTP fallback,
   unexpected response, network, timeout and cancellation. Status is taken from
   HTTP; require a matching status before trusting a structured problem.
5. Parse untrusted response bodies as `unknown`. Use small endpoint decoders to
   check required fields, real ISO calendar dates, arrays, nullable links,
   enum values and finite integer counts. Allow additive unknown properties.
   Do not cast JSON directly into a response type. No runtime schema package.
6. All data reads use origin-relative `/api/...`, `cache: 'no-store'`, explicit
   `credentials: 'same-origin'`, `redirect: 'error'` and an AbortSignal. Accept
   JSON and `application/geo+json` for success and `application/problem+json`
   for errors, including optional content-type parameters. GeoJSON collection
   consumers will decode `features`, not `results`; no GeoJSON network read yet.
7. Use a 30-second per-request deadline through body parsing. Caller abort and
   deadline both settle the client operation even if the transport ignores its
   abort signal. Clear timers/listeners on every exit; consume late rejections.
   Caller cancellation is silent; timeout offers a resource-specific Retry.
8. Decode valid Problem Details into safe plain text. Otherwise show a local
   resource-specific message; never render raw HTML, unexpected response JSON,
   traceback or request body. Accept a valid 32-hex-digit `X-Request-ID` as the
   preferred correlation ID, falling back to a valid body `request_id`.
   Render validation summaries plus messages associated with known release/flag
   controls; retain unknown/global pointers in the summary. No HTML injection.
9. Do not retry automatically. GET Retry is an explicit user action. This
   read-only helper and its abort controllers are not a future mutation queue;
   #76/#77 own write payloads, CSRF and uncertain-save semantics separately.

### Pagination policy

Export a resolver taking a link and the expected endpoint URL. Resolve relative
links against that endpoint, then require HTTP(S), the exact configured web API
origin, exact endpoint pathname, no embedded credentials and no fragment.
Reject container origins, other ports/protocols, protocol-relative foreign
origins, sibling API endpoints and encoded path tricks. Check before fetching.
Retain the resolved query string byte-for-byte, including ordering, `%` escapes,
`+` and opaque cursors; never rebuild a server link using `URLSearchParams`.
Do not rewrite a foreign link to the local origin.

Release discovery follows `results` pages sequentially until `next=null`, using
page size 100. Track visited destinations and reject cycles. Do not expose a
partial collection after a page failure. Deduplicate identical date pairs and
reject conflicting duplicate metadata. Separate pages are fresh reads: do not
promise a snapshot or infer one from the `count` field. Sort complete results
by `as_of` descending, then `processed_on` descending.

Keep endpoint policies distinct: the readiness read returns only its current
bounded summary page and never follows `next`; future complete summaries and
GeoJSON have feature-owned collection behavior, and location pagination will
remain bounded with no fetch-all operation. Test the resolver with an opaque
location link without creating a location client or making a location request.

## Selection and observable behavior

1. `App` invokes `useExploration` once above the route switch. Native controls
   receive values and event handlers from that owner; no editable copy in a page.
   The fixed state is Ohio, initial flag wired, county null. County controls/data
   are deferred; do not build speculative detail or paging state.
2. On first map entry, show `Loading releases…`, discover the complete catalog,
   then use the first/latest release returned by the API's documented ordering.
   Pin its returned date pair before requesting dependent data. There is no
   date-less dependent read that could drift to another period.
3. Each processing is its own select option, keyed by both dates. Show returned
   filing period and full dates in option labels and repeat them as wrapping
   metadata outside the select. Display all loaded state names/codes, FCC source,
   fixed Ohio, selected flag/source field, 100 Mbps download / 20 Mbps upload,
   and Census TIGER/Line 2020 boundary context for the forthcoming county view.
4. Empty catalog: show the approved no-releases copy, a README data-load link
   and Refresh. Keep selection null and make no summary read. Ohio absent:
   show `Ohio is not loaded for this release.`, preserve release selection and
   flag controls, and make no summary read or fallback to an older release.
5. Ohio present: GET `/api/v1/served-unserved/rollups/` with `level=county`,
   `state=39`, selected `flag`, explicit `as_of/processed_on` and `page_size=1`.
   Show `Checking county summaries…`; on a valid matching response with rows,
   show `County summary API responded for this selection.` alongside a clear
   statement that the county map/table will arrive in #73. Do not claim the
   single row establishes all-county completeness. Discard the row after decoding;
   retain only needed response metadata/status in the current component lifecycle.
6. Match returned dates, `state`, `level`, null `code`, flag and threshold to
   the requested selection before accepting the response. Use returned coverage
   metadata. An Ohio-absent response updates that state honestly. An empty stored
   collection says `No county summary rows were returned for this selection.`;
   do not call it zero service or invent a precise no-observations diagnosis.
   A 503 uses the approved unavailable-summary copy and GET Retry.
7. Every release/flag change clears readiness/error synchronously and advances
   a request generation. Abort the obsolete read and ignore both late success
   and late failure using request identity and the entire selection key. Gate
   rendered status by that key as well, so old status never appears beneath
   new labels, including before effect cleanup. Preserve any future county
   identifier; #73 validates it and owns its data reset.
8. Explicit Refresh rediscovers all releases and rereads the same selected
   date pair/flag. Re-entering map does the same while retaining root selection.
   Neither action silently upgrades to a new release. A disappeared selection
   clears readiness and selection, presents `This release is no longer loaded.
   Choose a release.`, and requires an explicit choice from the refreshed catalog.
   A summary 404 triggers one catalog rediscovery; if the pair still exists,
   present a summary failure rather than looping or asserting release deletion.
9. Route departure/unmount aborts data reads and invalidates their generations.
   Preserve selection across React pages, not accepted data from obsolete reads.
   Diagnostics has its own health controller and identity guard. React StrictMode
   cleanup must work without duplicate applied results or leaked listeners/timers.
10. Keep everything transient. No local/session storage, IndexedDB, service worker,
    persistent questions/credentials, module-level response cache or prefetch.

## Shell, navigation and configuration

- Bare `/` and `/#/map` show the exploration shell. Implement native links for
  Map, Analyst dashboard, Ask (stub), AI settings; footer Diagnostics. Routes are
  `/#/map`, `/#/ask`, `/#/settings/ai`, `/#/diagnostics`. Unknown hashes have a
  helpful heading and map link. Listen to `hashchange`, including Back/Forward.
- Each route has one h1 inside main, descriptive document title, header/nav/main/
  footer landmarks, skip link, and `aria-current=page` on its active internal link.
  Explicit route changes focus a `tabIndex=-1` heading; refresh/filter changes do
  not move focus. Loading/results use one polite status region. Errors are in the
  flow with resource-specific GET Retry. Associate labels, help and field errors.
- Ask says the question panel is not available yet and links to #77. Settings
  says AI settings is not available yet and links to #76. Do not imply a disabled
  backend, available form, authorization state or completed feature.
- Set Compose web environment to
  `VITE_DASHBOARD_URL: ${VITE_DASHBOARD_URL:-http://localhost:${DASHBOARD_PORT:-8501}/}`.
  Code fallback outside Compose is `http://localhost:8501/`. Use an ordinary
  same-tab link with `Opens the other app with default filters.` adjacent.
  Do not transfer filters, read `API_PROXY_TARGET` into browser links or promise
  Back/Forward resets. Reject non-HTTP(S), embedded credentials, query and hash
  in this public app-base setting. Preserve a valid deployment path. An invalid
  setting displays navigation-configuration guidance and omits the unsafe link.
- Add commented optional `VITE_DASHBOARD_URL` to `.env.example`; leaving it unset
  allows port-derived defaults. Document browser-reachable public URLs and
  restarting/rebuilding web when Vite environment values change.
- Use approved light palette, system fonts and 4/8/12/16/24/32px spacing. Native
  controls target 44px; focus has the approved visible outline. Wrap navigation
  and metadata, stack below 48rem, and reflow at 320px/zoom. No map canvas or
  decorative fake data. No animation is necessary. Verify actual text/control
  contrast; a smoke check is not a WCAG conformance claim.
- Preserve browser Host with the approved explicit `/api` proxy option above,
  and verify that browser-origin next links are fetchable. Do not weaken client
  URL validation. Admin proxy work stays #76.

## Test cases and expected results

Use Vitest, Testing Library and `vi.stubGlobal('fetch', ...)`; mock the network
boundary only. Response fixtures specify realistic content types, nullable
links and required schema fields. Reset hash/title, globals, timers and mocks.

| Owner | Inputs/action | Required outcome |
| --- | --- | --- |
| `App.test.tsx` | Deferred first release page | Loading status; no invented dates/counts; no summary read yet |
| `App.test.tsx` | D25 versions processed 2026-09-30 and 2026-09-29; older J25 processed 2026-10-01 | Select D25/09-30 initially, wired; all processings selectable; metadata and request carry full selected pair |
| `App.test.tsx` | Select older processing, then any/terrestrial | Controlled values and source-help change together; each subsequent GET pins both dates, state 39 and selected flag |
| `App.test.tsx` | Empty release page | Approved no-releases guidance and Refresh; no summary request |
| `App.test.tsx` | Latest release contains only WV, older contains Ohio | Select latest WV-only release; explicit Ohio-absent copy; no automatic fallback/read; choosing Ohio release enables read |
| `App.test.tsx` | Summary success/empty/503 | Readiness/empty/unavailable distinctions; no county values, total or completeness claim; Retry stays on selected pair |
| `App.test.tsx` | Structured 400 has `/flag`, `/as_of`, empty and unknown pointers plus request ID | Associated known-field messages and summary for global/unknown; useful plain text and request ID; no raw response |
| `App.test.tsx` | Deferred A, choose B, resolve B, then resolve/reject A even after abort | Only B status/coverage/metadata visible; no stale success or error under B controls |
| `App.test.tsx` | Navigate away/unmount while catalog/summary pending; resolve ignored-abort transport | Signal aborted; no old result/error; returning refreshes same selection |
| `App.test.tsx` | Refresh introduces newer release; selected pair stays/deletes | Preserve existing pair; deletion clears dependent state and requires explicit selection; 404 with existing pair does not loop |
| `App.test.tsx` | Map/Ask/settings/Diagnostics/unknown hash and history events | Correct content/title/current link/heading focus; selection retained; automatic data changes do not steal focus |
| `http.test.ts` | JSON and GeoJSON with charset; malformed JSON, HTML 502, wrong/missing required shapes, network rejection | Valid body goes to endpoint decoder; safe typed failures otherwise, no raw HTML/object leak |
| `http.test.ts` | Valid problem body, malformed problem, invalid/missing ID, header/body ID disagreement | Preserve valid structured fields; safe fallback; valid header takes precedence; no fabricated ID |
| `http.test.ts` | Pre-aborted signal, abort during body read, 30-second fake-timer timeout, ignored-abort transport | Settle with correct cancellation/timeout kind, clean resources; late transport cannot publish data |
| `http.test.ts` | Same-origin absolute, endpoint-relative `?page=2`, root-relative endpoint and opaque `%2B/+/%3D` cursor | Allowed only on expected endpoint; preserve query bytes/order exactly |
| `http.test.ts` | Foreign host, backend:8000, different port, wrong path, credentials, fragment, non-HTTP scheme, encoded slash/dot traversal, redirect | Reject before follow-up fetch/credential forwarding; redirect errors safely |
| `releases.test.ts` | Two pages, page-two error, malformed second page, cycle, duplicate/conflicting pair | Complete successful catalog only; distinct processings retained; failures discard partial data; cycles/conflicts stop |
| `rollups.test.ts` | `count=88`, one valid row and non-null next | Exactly one GET; no next-page fetch; dates/flag validated; no complete-collection representation |
| `rollups.test.ts` | Wrong returned pair/flag/state or malformed threshold/count/coverage | Reject as unexpected response; never show ready for another selection |
| `Diagnostics.test.tsx` | Health 200, valid health 503, transport failure, Retry, late completion after departure | Preserve existing API/PostGIS/Redis/worker labels and 503 semantics; safe failure, fresh retry, ignored obsolete result |
| `navigation.test.ts` | Default/configured HTTP(S) deployment path, credential URL, javascript URL, query/hash | Correct same-tab destination or explicit invalid-configuration state; no credentials or filter transfer |

Run integrated tests under StrictMode for request lifecycle cases. Use actual
`Response` objects, deferred promises and fake timers where useful; do not rely
on a mock that automatically rejects on abort for the stale-response tests.

## Commands and verification after approval

PowerShell, from the repository root:

```powershell
$env:PATH = "C:\Program Files\Docker\Docker\resources\bin;$env:PATH"
git status --short
git branch --show-current
docker compose config --quiet
docker compose run --rm --no-deps web pnpm check
docker compose run --rm --no-deps web pnpm build
docker compose up -d --no-deps web
git diff --check
git ls-files --others --exclude-standard
```

Expected branch: `codex/72-react-shell`. All commands succeed; web check includes
formatting/lint/types/tests and build emits production assets. Review whitespace
in new files too before staging. No image rebuild is needed for dependencies
because none change. Compose recreates web as needed for changed environment.

Check interpolation without changing `.env` or starting another stack:

```powershell
(docker compose config --format json | ConvertFrom-Json).services.web.environment.VITE_DASHBOARD_URL
$env:DASHBOARD_PORT = '18501'
(docker compose config --format json | ConvertFrom-Json).services.web.environment.VITE_DASHBOARD_URL
$env:VITE_DASHBOARD_URL = 'https://analysis.example.test/analyst/'
(docker compose config --format json | ConvertFrom-Json).services.web.environment.VITE_DASHBOARD_URL
```

Inspect only web `environment.VITE_DASHBOARD_URL`, not the full config in shared
logs. With overrides initially absent, expect `http://localhost:8501/`, then
`http://localhost:18501/`, then the explicit HTTPS URL. Save and restore existing
process environment values in `try/finally`; do not remove a pre-existing user
value. Use a disposable shell for override checks if simpler.

Use the existing running backend for read-only browser verification. Start
other services only if needed; no reload/delete/rebuild of the owner's data.
At `http://localhost:5173/`, record:

1. Real release discovery and a summary readiness response; selected dates and
   flag match Network requests. With test/probe page size 1, an absolute release
   next link received **through `/api`** has web origin/port and remains fetchable.
   A direct backend-origin response alone does not prove the proxy check.
2. Tab reaches skip link first, all navigation and labeled controls; native
   selects work from keyboard; visible focus; route h1 receives navigation focus;
   refresh and flag changes preserve control focus.
3. Diagnostics reports actual health through the original contract. A stopped
   worker can show unreachable without treating valid health 503 as bad JSON.
   Do not stop a user service solely for this check.
4. Desktop 1280px, narrow 390px and 320px, plus browser zoom: wrapping dates,
   coverage/navigation/help, no body horizontal overflow or hidden actions.
5. Cross-app href/configuration and reset guidance match defaults/override tests.
   The dashboard remains its existing stack check until #74; do not claim its
   reciprocal navigation or product workflow is implemented.
6. Fixture-driven unavailable/non-JSON/late-response checks supplement real API
   success, with browser console/network checked for unexpected requests/errors.
   Record which states were mocked and which were real.

Document actual results and limitations in the plan/journal/PR. No hosted CI,
browser automation dependency, screenshots containing credentials, or claims
that this slice proves map WebGL, sessions/CSRF, or full accessibility compliance.
Backend checks are unnecessary unless a separately approved backend change is
needed; a Compose web-navigation environment value does not change the API.

## Rationale and references

- One root owner keeps release, flag and future county/detail/export values
  consistent as consumers are added: [React shared-state guidance](https://react.dev/learn/sharing-state-between-components).
- Abort plus identity checks handle both real cancellation and transports that
  finish after cleanup: [React effect cleanup/race guidance](https://react.dev/reference/react/useEffect#fetching-data-with-effects).
- Fetch does not reject merely because HTTP status is an error. Check status,
  decode safely and cancel reads deliberately: [MDN Fetch guidance](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch).
- Native controls, landmarks and predictable focus support keyboard use as the
  shell grows: [W3C focus order](https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html).
- Small handwritten types and decoders keep dependencies small while enforcing
  the [reviewed API contract](../../backend/core/api/openapi.json) at the network
  boundary. Complete catalogs prevent hidden processings; strict URL checks
  preserve opaque pagination without forwarding credentials to another origin.
- Readiness proves the shared owner/client with a real dependent request before
  #73 adds geometry and full summary collections. Its bounded page prevents a
  foundation change from quietly becoming the county-map implementation.

## Exclusions and review gate

No county rendering, joins, legend, county table/detail, exports, dashboard code,
AI forms/status/query calls, authentication/static proxy, provider integration,
business API changes, browser persistence, global architecture refactor, new
packages or original-feature closure. #4 and #32 remain open.

Owner approval of this concrete plan, including the bounded readiness read and
exact file scope, preceded implementation. The measured proxy amendment was
separately approved before its patch. The repository's `CLAUDE.md` says:
"No code, configuration or dependency is written until the plan is approved."
The posted issue plan is the review record; any further expansion returns for
plan review first. Produce one reviewable PR for #72.

## Performed verification on October 16, 2026

- Docker web `pnpm check` passed formatting, lint, strict TypeScript and **64
  tests across six files**. Tests include all release pages and processing
  versions, absent Ohio, coverage changing after discovery, malformed responses,
  structured field/global errors and request IDs, URL rejection, abort/deadline,
  late success/failure, unmount, A→B→A, StrictMode re-entry, disappearance and
  404 rediscovery/recovery. The original diagnostic success/failure/503 contract
  remains covered. No lint rule was relaxed.
- Docker web `pnpm build` passed: 25 modules, 240.52 kB JavaScript (75.15 kB gzip)
  and 2.34 kB CSS (1.00 kB gzip). No package or lockfile changed.
- `docker compose config --quiet` passed. Interpolation produced
  `http://localhost:8501/`, `http://localhost:18501/` with the port override,
  and `https://analysis.example.test/analyst/` with the explicit override.
  Existing process environment values were restored; `.env` was not modified.
- Real headless Microsoft Edge on Windows read the loaded D25 release with both
  dates, started wired, and made a keyboard-driven change to any technology.
  Network requests retained the chosen pair, state 39, flag and page size 1.
  A release next link obtained through the web proxy used `localhost:5173`,
  and following it returned 200 with `no-store`.
- Edge reached the skip link first with Tab; Enter focused main without changing
  the route. Native select keyboard operation retained control focus. Explicit
  route navigation focused h1 and updated titles; Back retained selection and
  made fresh reads. Unknown routes and unavailable AI feature pages were checked.
  The dashboard link used its configured URL and same-tab navigation semantics.
- Diagnostics read the real health report: API, PostGIS and Redis reachable,
  existing Celery worker unreachable. That valid 503 remained a component report.
  No user service was stopped or data changed for this scenario.
- Inspected desktop/narrow screenshots. At 1280, 390 and 320px, document/body
  width equaled viewport width; dates, coverage, controls and navigation wrapped.
  A separate 200% text-resize check also had no body overflow. This is a smoke
  check rather than a full browser-zoom or accessibility certification.
- Calculated implemented color contrast: primary/canvas 13.67:1,
  secondary/canvas 7.14:1, link and button/surface 7.35:1, control border/surface
  4.56:1 and focus/surface 14.55:1. These exceed the relevant planned 4.5:1 text
  and 3:1 control/focus targets for the measured pairs.
- Browser runs had no page exceptions and no local/session storage entries.
  Success/proxy/health checks used the real existing API; exceptional data states
  and ignored-abort transports used fixtures. No geometry, AI, credential or
  provider requests were introduced. Existing data was only read.
- Final review corrected stale coverage labels, an old-success/new-404 priority
  case, catalog errors without mounted fields, request IDs on malformed success
  responses, and rejection of a non-string coverage enum. Focused regression
  tests cover these fixes. Documentation links, changed-file scope and whitespace
  are checked before commit, including newly added files.
