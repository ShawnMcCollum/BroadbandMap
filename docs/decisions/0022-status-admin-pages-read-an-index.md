# 0022 — Status admin pages read an index

- **Status:** Accepted
- **Date:** 2026-10-16
- **Amends:** [0021](0021-indexes-only-where-queries-read.md), decision 7
- **Amended by:** [0024](0024-rollup-admin-pages-read-an-index.md), which shares the two templates with the rollup admin, and on 2026-10-17 by [#84](https://github.com/ShawnMcCollum/BroadbandMap/issues/84), which adds decisions 7 and 8
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
   - *Amended by [0024](0024-rollup-admin-pages-read-an-index.md):* the
     templates are shared by both of the app's admins, at
     `admin/served_unserved/pagination.html` and
     `admin/served_unserved/search_form.html`. The rollup admin's count
     stops at the same cap.
   - *Amended by decision 8:* the rows are counted in the list's order, not
     unordered.
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
7. **One filter of service categories replaces the three flag filters.**
   *Added on 2026-10-17 ([#84](https://github.com/ShawnMcCollum/BroadbandMap/issues/84)).*
   The check constraints nest the flags, so a status falls in exactly one of
   four categories. The filter "100/20 Mbps service" offers them:

   | Choice | `service=` | Selected by | December 2025 |
   |---|---|---|---|
   | Wired | `wired` | `wired_100_20` | 4,244,855 |
   | Terrestrial, not wired | `terrestrial` | `terrestrial_100_20 AND NOT wired_100_20` | 148,197 |
   | Any technology, not terrestrial | `any` | `any_100_20 AND NOT terrestrial_100_20` | 149,166 |
   | Not served | `none` | `NOT any_100_20` | 132 |

   - The three yes/no filters it replaces also offered combinations the
     constraints forbid, such as wired service without terrestrial. Those
     matched nothing, but read every status: 917 ms.
   - Each category is selected by the fewest flags that set it apart. The
     constraints make that the same statuses as naming all three flags, but
     the planner estimates a condition on several flags as if they were
     independent. With all three named, it expected 9,602 June 2025 statuses
     with service by any technology but not terrestrial, against 176,259.
     Expecting fewer than the count's 10,001, it sorted every match for the
     count: 303 ms, against 10 ms.
   - "Not served" is `NOT any_100_20`, the predicate of
     `servedstatus_not_served` (decision 6), which serves both its queries.
   - The choices are named as the map names the flags: "Wired", "Any
     technology" and "Terrestrial". Their values are the API's `flag`
     values, and `none`.
   - An unknown value redirects to the list, as an invalid value of a flag
     filter did.
8. **The count reads the rows in the list's order.**
   *Added on 2026-10-17 ([#84](https://github.com/ShawnMcCollum/BroadbandMap/issues/84)).*
   Decision 3 counted unordered, so that the database could stop at the
   first rows it found. For a filter on a flag, the planner then chose a
   sequential scan, expecting matches throughout the table. The table holds
   the releases in the order they were loaded, so a count within June 2025
   read all of December 2025's statuses first: 384.33 ms for wired service,
   and 147.88 ms and 138.61 ms for the two middle categories. In the list's
   order, the count reads the index that serves the page, from the release's
   first entry, and stops after 10,001 matches: at most 15.78 ms in either
   release.
   - Where the unordered scan found its matches at once, at the start of
     the table, the ordered count is a few milliseconds slower. For the two
     middle categories, with no release or December 2025 chosen, it took
     12.44–15.78 ms, against 6.85–8.28 ms.
   - A sequential scan usually starts where the last scan of the table
     stopped (`synchronize_seqscans`). An unordered count therefore took
     anywhere between its times at the start and at the end of the table,
     and the worst case grew with each state and release loaded.
   - `CappedCountPaginator` serves both admins, so the rollup admin counts
     in its list's order too, through its unique index
     ([0024](0024-rollup-admin-pages-read-an-index.md)). Its capped counts
     took 2.63–2.90 ms, against 2.06–2.75 ms.
   - A search's count now sorts the statuses it found: the block search's
     took 0.72 ms against 0.39 ms, and the H3 cell search's 1.41 ms
     against 0.59 ms.
   - A sort typed into the URL (`?o=`) now orders the count as well.

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

**Service categories ([#84](https://github.com/ShawnMcCollum/BroadbandMap/issues/84)):**
measured on 2026-10-17 on the same data. Each sequential scan started at
the table's first page (`synchronize_seqscans` off), so that the runs
repeat: December 2025 lies at the start of the table and June 2025 after
it. "Before" is the three flag filters, with the combination that selects
each category, and the unordered count. "After" is the service filter and
the ordered count. This project's web development server was using about 9%
of a core during the runs, so render times differ by about ten milliseconds
from run to run.

| Page | Render before | Render after | Count before | Count after |
|---|---|---|---|---|
| No filter, wired | 50 ms | 57 ms | 3.07 ms | 3.65 ms |
| December 2025, wired | 56 ms | 59 ms | 3.17 ms | 3.54 ms |
| June 2025, wired | 421 ms | 53 ms | 384.33 ms | 4.16 ms |
| No filter, terrestrial, not wired | 58 ms | 60 ms | 8.28 ms | 12.56 ms |
| December 2025, terrestrial, not wired | 72 ms | 60 ms | 7.48 ms | 15.78 ms |
| June 2025, terrestrial, not wired | 201 ms | 67 ms | 147.88 ms | 11.85 ms |
| No filter, any technology, not terrestrial | 56 ms | 58 ms | 8.03 ms | 13.65 ms |
| December 2025, any technology, not terrestrial | 58 ms | 69 ms | 6.85 ms | 12.44 ms |
| June 2025, any technology, not terrestrial | 191 ms | 63 ms | 138.61 ms | 10.94 ms |
| No filter, not served | 46 ms | 55 ms | 0.10 ms | 0.10 ms |
| December 2025, not served | 50 ms | 52 ms | 0.10 ms | 0.05 ms |
| June 2025, not served | 54 ms | 47 ms | 0.09 ms | 0.08 ms |
| Wired but not terrestrial (offered before, typed into the URL after) | 917 ms | 1.6 s | 689.75 ms | 1,493.15 ms |

Every page query of the twelve category rows read the unique index, or
`servedstatus_not_served` for "Not served", in at most 0.24 ms.
Page 100 of the two middle categories took 15.22 ms and 15.05 ms.

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
  - *Amended by decision 7:* the admin no longer offers such a combination.
    Typed into the URL, it is still applied, and its ordered count reads the
    whole unique index: 1.6 s.
- **Negative:** A sort typed into the URL (`?o=`) is still applied, and
  sorts every status.
- **Negative:** Every data load maintains one more index, with about 150
  entries per Ohio release.
- **Positive (decisions 7 and 8):** The filters offer only the categories
  the data holds. Each category's page took 47–69 ms in either release, and
  its cost no longer grows with the releases stored before the one chosen.
- **Negative (decision 7):** A filter on a flag typed into the URL, such as
  `?any_100_20__exact=0`, is still applied, as a typed sort is.
- **Negative (decision 8):** A filter that matches fewer than 10,001 rows,
  with no index of its own, makes the count read the list's index to its
  end. None of the admins' filters is one; only a URL typed by hand reaches
  one.
