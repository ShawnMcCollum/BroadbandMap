# Development journal

A running log of the reasoning behind day-to-day work: what was tried, what
was learned, and why things changed direction. Formal decisions are recorded
in [decisions/](decisions/), and unresolved questions are in
[open-questions.md](open-questions.md).

Newest entries first.

---

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
