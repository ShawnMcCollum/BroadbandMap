# 0019 — Location drill-down with release-wide cursor generations

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Issue #26 exposes locations behind the summaries implemented by #3. Ohio alone
has more than 4.5 million rows, so a response must be bounded and deep pages
must avoid reading and discarding all earlier pages. Clients need to distinguish
an empty status filter from an area outside the release's coverage.

ADR 0017 allows state additions, replacements and deletions to preserve the
release row. Its identity alone can no longer detect a changed dataset. A
read-only repeatable-read transaction keeps one response consistent, but does
not retain a snapshot across HTTP requests.

## Decision

- Add `GET /api/v1/served-unserved/locations/`. Require `level` and `code`,
  reuse summary release selection, geography keys, state filtering and the
  `wired` flag default. An optional `status=served|not_served` filters that flag.
- Reuse `statuses_in` for membership at all seven levels. Places and county
  subdivisions use the block's assigned area, never a fabricated prefix rule.
  H3 can include contributions from multiple loaded states.
- Return FCC location IDs, block GEOIDs and H3 cells as strings, plus the three
  Boolean flags. Return release, selection, threshold, boundary vintage and
  area coverage metadata. Do not include geometry or a location count.
- Seek by ascending `location_id`, unique within a release. Fetch at most
  `page_size + 1` rows, default 100 and maximum 1,000. Support next and previous
  links using range predicates, with no OFFSET or full filtered COUNT.
- Sign opaque versioned cursors using Django signing with a resource-specific
  salt. Bind dates, release ID, generation, geography, state, flag, status,
  page size, direction and position. Altered tokens or context return 400.
  Links carry explicit resolved dates. If a caller supplies the cursor without
  dates, its signed dates still pin the release; explicit conflicting dates fail.
- Add a release-wide `data_generation` counter. The loader, state deletion
  command and rollup rebuild command advance it in the transaction that changes
  the release, under the existing writer guard. Deleted releases are detected
  by absence or a different row identity after reloading. Older cursors return
  409 `dataset_changed` with an instruction to restart without a cursor.
- Evaluate release identity, generation, coverage, page rows, links and serialized
  data in one short read-only repeatable-read transaction. Readers take no writer
  guard. A write committed during the request is visible to its next request.

## Alternatives and consequences

Per-state generations would avoid restarting Ohio county traversals when another
state changes. They also require composing generations for cross-state H3 cells
and managing state additions and removal. Release-wide tracking was selected for
this implementation: it is easier to audit, at the cost of conservative restarts.
Rebuilding rollups also invalidates cursors, keeping the generation meaningful
for the release's complete derived state.

Unsigned stock cursor tokens do not enforce the project's context or write
detection rules. Offset pagination gets more expensive as a traversal advances.
Long-lived database snapshots would retain transactions across HTTP requests and
complicate cleanup. The signed keyset and restart contract avoids those costs.

The internal generation has a default for existing releases; migration requires
no data reload. Writers must be restarted with the new code when deploying this
change so every writer advances the generation. Django secret-key changes can
invalidate signatures (400); clients restart without the cursor in that case.

Tests independently establish membership and ordering, exercise real writers and
rollback, validate actual responses against OpenAPI, and commit changes from a
separate connection during reads. The optional full-data test compares first and
deep pages to the raw Ohio CSV and reports query plans without machine-dependent
latency assertions.

## Query planning evidence

Read-only profiling against the full Ohio December load found that a direct
`ORDER BY location_id LIMIT 101` could choose the release/location unique index,
then discard millions of rows before reaching the requested area. For the
largest county (39035, 430,799 locations), its first page discarded 3,876,894
unrelated rows. Large place/subdivision queries similarly walked locations
before looking up each block's membership.

Location pages explicitly sort by the exact bigint identity expression
`location_id + 0`. This retains numeric order and keyset range predicates while
preventing that ordered-index shortcut. PostgreSQL then uses geography indexes
to filter candidates before a top-N sort. No schema denormalization, new indexes,
or global planner settings are needed. Existing `(release, block)` and
`(release, h3_res8)` indexes serve census prefixes, exact blocks and H3;
the block's place/subdivision indexes support those membership joins.

Representative `EXPLAIN (ANALYZE, BUFFERS)` observations, selecting 101 rows with
all response columns, on the development database:

| Area | Locations | Direct order, first page | Explicit sort, first page | Explicit sort, 90% position |
|---|---:|---:|---:|---:|
| County 39035 | 430,799 | 1,537.8 ms | 86.2 ms | 47.8 ms |
| Place 3918000 | 235,546 | 1,532.6 ms | 98.4 ms | 67.3 ms |
| Subdivision 3904918000 | 230,564 | 2,322.6 ms | 87.6 ms | 60.2 ms |
| Tract 39159050601 | 5,211 | 2.5 ms | 2.5 ms | 1.6 ms |
| H3 882a930f45fffff | 1,282 | 0.6 ms | 0.6 ms | 0.2 ms |

For the county, the explicit-sort plan read 5,670 shared buffers on the first
page and 2,725 at the deep position, versus 58,914 for direct first-page order.
Served/Not served plans for all three flags used the geographic bitmap index;
first-page SQL took 42.6–96.1 ms and deep-page SQL 29.3–55.5 ms.
These are individual measurements, with differing cache state, not guarantees.
Deep direct-order pages can be faster than an explicit sort; the deliberate
tradeoff is avoiding the much worse first-page and sparse-filter scans.

The sort bounds returned rows and sort working storage, not every geography's
candidate scan. Query cost still depends on area size, filtering and available
statistics. Re-profile before extending the geography model or data scale;
if a future workload warrants additional indexes or denormalized membership,
measure its read benefit against load time and storage costs first.

References: [DRF cursor pagination](https://www.django-rest-framework.org/api-guide/pagination/#cursorpagination),
[Django signing](https://docs.djangoproject.com/en/5.2/topics/signing/),
[API consistency rules](../api-guidelines.md#5-bound-large-reads-and-define-pagination-consistency).
