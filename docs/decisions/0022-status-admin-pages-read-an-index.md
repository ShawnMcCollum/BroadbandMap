# 0022 — Status admin pages read an index

- **Status:** Accepted
- **Date:** 2026-10-16
- **Amends:** [0021](0021-indexes-only-where-queries-read.md), decision 7
- **Related:** [0013](0013-release-scoped-data-loads.md), [0019](0019-location-cursors.md), [#80](https://github.com/ShawnMcCollum/BroadbandMap/issues/80)

## Context

The admin's list of served statuses is where an administrator browses the
loaded locations. With two Ohio releases, 9.1 million statuses, its pages
took 1.9 s unfiltered and 2.6 s filtered to one release, and about 0.5 s
with a filter on a service flag. The time grew with every state and
release. Two queries read every status on each page:

- **The order.** `ServedStatus.Meta.ordering` was `["release", "location_id"]`.
  Ordering by a foreign key orders by the related model's ordering,
  `Release.Meta.ordering = ["-as_of", "-processed_on"]`. Django's admin then
  appends the primary key, to make the order total. No index serves an order
  on another table's columns, so each page joined every status to its release
  and sorted them all, before taking 100.
- **The count.** The admin's paginator counts the statuses that the page's
  filters select, to number the pages: every status of the table, or of the
  release. The other count Django can add, of the whole table on each
  filtered page, was already off: `ReadOnlyModelAdmin` sets
  `show_full_result_count = False`.

Two features of the admin read every status as well. Sorting by a column
header reads them all, since no column alone has an index. "Show counts"
counts each choice of each filter with a scan of the table.

Release IDs follow load order, not date order. June 2025 was loaded after
December 2025, so it has the higher ID and the earlier date. The API's
release list and its default, latest release follow the dates, through
`Release.Meta.ordering` ([0013](0013-release-scoped-data-loads.md),
decision 6).

Few statuses lack 100/20 Mbps service by any technology, since any
technology includes satellite: 132 of 4,542,350 in December 2025, and 162 of
4,552,967 in June 2025. Statuses without wired service are 6.5% of a
release, and those without terrestrial service 3.3%. The check constraints
make wired service imply terrestrial, and terrestrial imply any.

## Decision

1. **Statuses are ordered by release ID, then location ID:**
   `ServedStatus.Meta.ordering = ["release_id", "location_id"]`. Ordering by
   the `_id` column orders by the stored ID, with no join. The unique index
   `served_unserved_unique_location_per_release` serves the order, and with
   both of its columns in the order Django's admin appends nothing. A page
   reads 100 entries of the index.
   - Within a release, locations are listed by ascending ID, as in the
     location drill-down ([0019](0019-location-cursors.md)). Across
     releases, the first one loaded comes first, not the newest. The release
     filter lists the releases newest first.
2. **`Release.Meta.ordering` stays a date order.** The API's release list and
   its default release depend on it, and two tests check both:
   `test_catalog_orders_period_then_version_and_reports_per_release_states`
   and `test_latest_order_explicit_dates_and_pinned_links`. A comment on it
   says that another model orders by `release_id`.
3. **The count stops after 10,000 statuses.** `CappedCountPaginator`
   (`core/admin.py`) counts at most 10,001 rows, unordered, so the database
   stops as soon as it has found them. Only the first 10,000 statuses are
   paged: 100 pages of 100. A later page number redirects to the list, as an
   invalid page does. Beyond the cap, the list says "More than 10000 served
   statuses". It does so through per-model copies of Django's
   `pagination.html` and `search_form.html`.
   - The rows beyond the 10,000th are reached by a filter or a search, not
     by paging. A page's `OFFSET` reads the index up to it, so the cap also
     bounds the cost of the last page offered.
   - The cap must exceed the admin's `list_per_page` (100) and
     `list_max_show_all` (200). The admin shows a list it does not page in
     full.
4. **No column header sorts the list** (`sortable_by = ()`). No index serves
   another order.
5. **The filters do not count their choices**
   (`show_facets = ShowFacets.NEVER`).
6. **A partial index serves the not-served filter:** `servedstatus_not_served`
   on `(release, location_id)`, where `NOT any_100_20`. It takes 32 kB for
   two releases. Without it, the new order made that filter slower than the
   sort it replaced. The planner reads the unique index in order, expecting
   to fill a page soon, and scans nearly every status: a prototype took
   740 ms for December 2025 and 1,053 ms for both releases. With it, each
   takes 42 ms.
   - The location drill-down's pages of statuses not served by any
     technology can read it too, where the planner expects it to be the
     cheaper path. The first page of county 39035, none of whose 430,799
     statuses are in that list, read it: 0.06 ms instead of 49.14 ms. For
     county 39163, with the most such statuses (12), the planner kept the
     block index: 1.45 ms instead of 2.17 ms.
   - It amends [0021](0021-indexes-only-where-queries-read.md), decision 7:
     the statuses' indexes that stay include `servedstatus_not_served`, and
     the inventory test lists it.
   - The other filters need no index. A page of statuses without wired or
     terrestrial service finds 100 within a few thousand index entries.

## Measurements

Measured on the development database with Ohio's December 2025 and
June 2025 releases, 9,095,317 statuses, PostgreSQL 17.5. Each page was
built and rendered in-process for a superuser, as the admin does. Times
are medians of three runs after a warm-up.

**Admin list pages, render time:**

| Page | Before | After |
|---|---|---|
| No filter | 1.9 s | 43 ms |
| December 2025 | 2.6 s | 43 ms |
| December 2025, page 100 | 2.4 s | 47 ms |
| December 2025, not served (any) | 507 ms | 42 ms |
| Both releases, not served (any) | 475 ms | 42 ms |
| December 2025, not wired | 595 ms | 62 ms |
| Wired but not terrestrial (matches nothing) | 494 ms | 816 ms |
| Location ID search | 12 ms | 12 ms |
| "Show counts" | 3.1 s | 45 ms |

**Their queries, "No filter" and "December 2025":** the count took 448 ms
and 223 ms, reading every status. It now takes 2.0 ms for each, reading at
most 10,001 index entries. The page took 2,014 ms and 2,920 ms, a
sequential scan and a sort. It now takes 0.06 ms and 0.11 ms, reading the
unique index.

**Location drill-down, December 2025, statuses not served by any
technology, first page:**

| County | Before | After |
|---|---|---|
| 39035, the most locations (430,799; none of them in this list) | 49.14 ms | 0.06 ms |
| 39163, the most in this list (12) | 2.17 ms | 1.45 ms |

Migrating the loaded database added the index in 0.482 s.

## Alternatives considered

- **Newest release first, `["-release_id", "-location_id"]`.** The index
  serves it read backwards, but it lists a release's locations in descending
  ID, unlike the drill-down. A mixed order, with releases descending and
  locations ascending, has no index.
- **Keep the date order and serve it another way,** for example a release
  rank stored on every status. That adds a column and an index on
  4.5 million rows per release, for the admin alone.
- **Set the order on the admin only, keeping the model's.** Every other
  status query without an order of its own would still join and sort, and
  nothing reads the date order: the drill-down orders its pages explicitly.
- **Order releases by ID everywhere.** That would change the API's default
  release and its release list. See decision 2.
- **An estimated count** from the planner's row estimate. The count would be
  quick, but the page links would reach the last pages, whose `OFFSET` reads
  millions of index entries. A combined filter's estimate can also be far
  off.
- **No partial index.** That accepts a not-served filter up to 2.2 times
  slower than before (740 ms against 507 ms, 1,053 ms against 475 ms), and
  slower with every release.

## Consequences

- **Positive:** A page of the list reads at most 10,001 entries of an index
  for its count, and as many for its rows. Its cost no longer grows with the
  number of states and releases loaded.
- **Positive:** The admin lists the statuses not served by any technology
  in milliseconds. The location drill-down reads the same index where the
  planner expects it to be cheaper, and its first pages of those statuses
  were no slower in either county measured.
- **Negative:** Beyond 10,000 statuses, the list no longer shows how many
  there are. The rollups hold exact counts by area.
- **Negative:** Across releases, the list starts with the first release
  loaded, not the newest. Filtering by release chooses one.
- **Negative:** Two Django admin templates are copied. A Django upgrade that
  changes them leaves these copies as they were.
- **Negative:** A filter on a combination that the check constraints forbid,
  for example wired service without terrestrial, still reads every status:
  816 ms.
- **Negative:** A sort typed into the URL (`?o=`) is still applied, and
  sorts every status.
- **Negative:** Every data load maintains one more index, with about 150
  entries per Ohio release.
