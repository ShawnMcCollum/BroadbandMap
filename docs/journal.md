# Development journal

A running log of the reasoning behind day-to-day work: what was tried, what
was learned, and why things changed direction. Formal decisions are recorded
in [decisions/](decisions/), and unresolved questions are in
[open-questions.md](open-questions.md).

Newest entries first.

---

## 2026-10-14 — Sourcing boundary data

- The FCC file has no geometry, so boundary files had to be sourced before the
  loader (#2) could start (#9). Census TIGER/Line 2020 was chosen; the reasons
  are in [ADR 0005](decisions/0005-census-tiger-2020-boundaries.md).
- The guiding idea: **fetch broadly, load narrowly.** Raw files are cheap to
  load later, while sourcing and documenting a new dataset is the harder part.
  Every geography that could plausibly be useful is downloaded now, and the
  loader decides what to populate.
- Download size was the only real cost. Nothing in `data/` is committed, so
  Git LFS was considered and not needed. The one large outlier, nationwide ZIP
  code areas (528 MB), was made opt-in.
- The first map will be the smallest useful view: Served/Not served by
  county. #2 was updated to say so.

## 2026-10-14 — Choosing the application stack

- The open stack questions were settled in ADRs 0002–0004 (#14): Django for
  the API and data model, Celery for data loads, Streamlit for an analyst
  dashboard.
- Simplicity still matters, but each tool here replaces something that would
  otherwise be built by hand: the admin and migrations, load tracking, and
  chart-heavy analysis views.
- Django and Streamlit build on existing experience. **Celery is new to the
  project's author.** It is adopted deliberately, to show how AI-assisted
  development shortens the path from learning a tool to using it well in
  production.
- Two earlier answers from #8 were superseded and marked as such in
  [open-questions.md](open-questions.md): plain SQL migrations gave way to
  Django migrations, and the one-shot ETL service gave way to Celery tasks.
- Issues #1, #2 and #3 were rewritten for the new stack. #15 (Celery loads) and
  #16 (Streamlit dashboard) were opened.

## 2026-10-14 — Project-level questions

- Before more feature work, the project's goals and working conventions were
  written down (#12), so every later session starts from the same
  understanding. The answers are in
  [open-questions.md](open-questions.md#project-and-process).
- The main change in direction: **the API moves from TypeScript to Python.**
  Python then covers both the ETL and the API, and TypeScript stays in the web
  front end. #1 and #3 will need updating once the framework is chosen.
- Django, Celery and Streamlit came up as tools worth showing. They are logged
  as open questions rather than adopted, because each has to solve a real
  problem in this design first.

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
