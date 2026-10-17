# 0024 — Rollup admin pages read an index

- **Status:** Accepted
- **Date:** 2026-10-16
- **Amends:** [0022](0022-status-admin-pages-read-an-index.md), decision 3
- **Related:** [0017](0017-national-releases-loaded-by-state.md), [0021](0021-indexes-only-where-queries-read.md), [0023](0023-status-admin-searches-blocks-and-cells.md), [#83](https://github.com/ShawnMcCollum/BroadbandMap/issues/83)

## Context

The admin's list of rollups is where an administrator browses the stored
counts by area. With two Ohio releases, 757,792 rollups, a page of the
list took 431 ms unfiltered and 384 ms for one release, and the time grew
with every state and release. It had the faults that
[0022](0022-status-admin-pages-read-an-index.md) removed from the list of
served statuses:

- **The order.** `Rollup.Meta.ordering` was
  `["release", "level", "code", "state"]`. Ordering by a foreign key orders
  by the related model's ordering: the release's dates and the state's
  GEOID. Django's admin then appended the primary key. No index serves an
  order on other tables' columns, so each page joined every rollup to its
  release and state and sorted them all, before taking 100.
- **The count.** The paginator counted every rollup that the page's filters
  selected.
- **Sorting by a column and "Show counts"** each read every rollup.

The search read every rollup too. It matched the code alone, and no index
leads with the code.

The unique index `served_unserved_rollup_unique_area_per_state` is on
`(release_id, level, code, state_id)`. Within a release, it holds each
level's rollups together, with the levels in the order of their stored
names, from `block` to `tract`.

## Decision

1. **Rollups are ordered by release ID, level, code, then state ID:**
   `Rollup.Meta.ordering = ["release_id", "level", "code", "state_id"]`. The
   unique index serves the order. With all four of its columns in the order,
   Django's admin appends nothing. A page reads 100 entries of the index.
   - Within a release, rollups are listed by level name, then code, then
     state. Across releases, the first one loaded comes first. The release
     filter lists the releases newest first.
   - `Release.Meta.ordering` stays a date order
     ([0022](0022-status-admin-pages-read-an-index.md), decision 2).
     Nothing else reads the rollup order: the API's summaries order by code,
     and the loader and the rollup build clear the order.
2. **The rollup admin names every release in its queryset.** With the new
   order alone, a filter on a level, with no release chosen, read the unique
   index in order. The planner expects that level's rollups to be spread
   through the index, but in each release they lie after every level whose
   name sorts before it. A prototype took up to 27.36 ms for places, against
   1.44 ms before, and the time grows with each state. With the release IDs
   named, the index goes straight to the level in each release: at most
   0.14 ms.
   - The status admin's search names the releases in the same way
     ([0023](0023-status-admin-searches-blocks-and-cells.md)).
3. **The search names each level whose codes have the term's form,** from
   the area keys' patterns: 5 digits for a county, 7 for a place, 10 for a
   county subdivision, 11 for a tract, 12 for a block group and 15 for a
   block, and 15 lowercase hex characters for an H3 cell. With the releases
   named, the unique index finds the code with one probe per release and
   level.
   - Fifteen digits also fit the H3 form, since digits are hex, so such a
     term names both levels. That costs one more probe per release, and
     relies on no rule about which cell indexes exist.
   - A term that fits no level's form finds nothing, as before. The search
     is still an exact match on the whole code.
4. **The count stops after 10,000 rollups,** through `CappedCountPaginator`
   with the status admin's cap.
   - Its two templates, `pagination.html` and `search_form.html`, move from
     `admin/served_unserved/servedstatus/` to `admin/served_unserved/`.
     Django looks for an admin's inclusion templates per model, then per
     app, so both of this app's admins use them, and no other app's admin
     does. This amends [0022](0022-status-admin-pages-read-an-index.md),
     decision 3, which made them per-model copies.
5. **No column header sorts the list** (`sortable_by = ()`), and **the
   filters do not count their choices** (`show_facets = ShowFacets.NEVER`).
6. **No index is added or dropped**
   ([0021](0021-indexes-only-where-queries-read.md)).

## Measurements

Measured on the development database with Ohio's December 2025 and
June 2025 releases, 757,792 rollups, PostgreSQL 17.5. Each page was built
and rendered in-process for a superuser, as the admin does. Times are
medians of three runs after a warm-up. The machine was also running
another project's development server, which kept part of a core busy, so a
page's render time varied by tens of milliseconds from run to run. The
before and after runs below were taken one after the other. With no slow
query, a page rendered in 56–102 ms. The level filters whose queries already
took at most 13 ms, for block groups, counties, county subdivisions, places
and tracts, with and without a release, render in the same time before and
after, within that variance.

**Admin list pages, render time:**

| Page | Before | After |
|---|---|---|
| No filter | 431 ms | 63 ms |
| December 2025 | 384 ms | 65 ms |
| December 2025, page 100 | 516 ms | 70 ms |
| No filter, blocks | 322 ms | 68 ms |
| No filter, block groups | 68 ms | 70 ms |
| No filter, counties | 67 ms | 71 ms |
| No filter, county subdivisions | 66 ms | 71 ms |
| No filter, H3 cells | 223 ms | 102 ms |
| No filter, places | 59 ms | 70 ms |
| No filter, tracts | 63 ms | 79 ms |
| December 2025, counties | 56 ms | 64 ms |
| December 2025, tracts | 72 ms | 72 ms |
| December 2025, H3 cells | 226 ms | 77 ms |
| County search | 109 ms | 19 ms |
| Block search | 100 ms | 17 ms |
| H3 cell search | 103 ms | 18 ms |
| December 2025, county search | 111 ms | 18 ms |
| "Show counts" | 558 ms | 75 ms |

**Their queries, "No filter" and "December 2025":** the count took 49.61 ms
and 27.53 ms, reading every rollup. It now takes 2.35 ms and 2.82 ms,
reading at most 10,001 index entries. The page took 421.37 ms and
408.59 ms, with a sort of every rollup. It now takes 0.11 ms and 0.20 ms,
reading the unique index.

**A filter on a level with no release chosen, page query:**

| Level | Before | Order alone (prototype) | After |
|---|---|---|---|
| `block` | 286.43 ms | 0.07 ms | 0.11 ms |
| `block_group` | 12.87 ms | 10.09 ms | 0.09 ms |
| `county` | 0.44 ms | 0.26 ms | 0.14 ms |
| `county_subdivision` | 3.29 ms | 16.66 ms | 0.12 ms |
| `h3_res8` | 168.25 ms | 17.53 ms | 0.10 ms |
| `place` | 1.85 ms | 27.36 ms | 0.11 ms |
| `tract` | 4.36 ms | 23.74 ms | 0.13 ms |

"Before" and "After" are the page query as the admin runs it. The
prototype's queries, measured while planning, had its join, filter, order
and limit, with four of its columns.

**Searches:** each query took 39.38 ms to 46.72 ms, a sequential scan of
the rollups. It now takes 0.05 ms to 0.10 ms, reading the unique index.

## Alternatives considered

- **Newest release first, `["-release_id", "-level", "-code", "-state_id"]`.**
  The index serves it read backwards, but it lists codes in descending
  order, and levels from `tract` back to `block`.
- **Set the order on the admin only, keeping the model's.** Every other
  rollup query without an order of its own would still join and sort, and
  nothing reads the date order.
- **The new order without naming the releases.** The filters on places,
  tracts, county subdivisions and block groups would be slower than before,
  and slower with each state (decision 2).
- **Name the releases in a custom level filter only.** The same queries,
  with more code, and the search would still have to name them itself.
- **An index that leads with the level,** such as
  `(level, release, code, state)`. It would be about the unique index's
  size, 69 MB for two releases, maintained by every load for the admin
  alone.
- **Per-model copies of the templates for the rollups,** or one global
  override of Django's. The first copies the same text twice. The second
  reaches every app's admin.
- **Keep the search on the code alone.** It read every rollup twice per
  search.

## Consequences

- **Positive:** A page of the list reads at most 10,001 index entries for
  its count, and as many for its rows. Its cost no longer grows with the
  number of states and releases loaded.
- **Positive:** A filter on a level reads only that level's rollups, and a
  search reads one index entry per release and level.
- **Positive:** The status and rollup admins share one copy of each
  template.
- **Negative:** Beyond 10,000 rollups, the list no longer shows how many
  there are.
- **Negative:** Across releases, the list starts with the first release
  loaded, not the newest. Within a release, levels follow their stored
  names, not their size.
- **Negative:** Each page first reads the release IDs, one more query of
  the small releases table.
- **Negative:** A sort typed into the URL (`?o=`) is still applied, and
  sorts every rollup.
