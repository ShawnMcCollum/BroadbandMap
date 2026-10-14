# Open questions

Questions that came up while planning the project, with their resolutions.
Each entry points to where the answer is acted on. Planning questions were
raised and answered in
[#8](https://github.com/ShawnMcCollum/BroadbandMap/issues/8); project-level
questions in [#12](https://github.com/ShawnMcCollum/BroadbandMap/issues/12).

When a question is resolved, its entry stays here with the answer, so the
reasoning behind it can still be traced. Significant decisions are written up
as ADRs in [decisions/](decisions/).

## Still open

### Which speed thresholds define "served"?

The source file only carries 100/20 Mbps flags. The 2024 Section 706 report
raised the FCC's fixed broadband benchmark from 25/3 to 100/20. The 2025
inquiry under the current FCC proposed dropping the 1 Gbps / 500 Mbps
long-term goal. Secondary sources indicate that the August 2026 report kept
the 100/20 benchmark. **This still needs to be checked against the report
itself.** The BEAD program's statutory definitions (unserved below 25/3,
underserved below 100/20) are a separate question.

*Impact:* only the map's labels and explanatory text. The data can only
express 100/20 either way.

## Resolved

### Application stack

Answered in [#14](https://github.com/ShawnMcCollum/BroadbandMap/issues/14).

| # | Question | Resolution | Where |
|---|----------|------------|-------|
| S1 | Which Python framework serves the API? | **Django**, with GeoDjango and Django REST Framework. The ETL lives in the same project. | [ADR 0002](decisions/0002-django-for-api-and-data-model.md) |
| S2 | Does Celery have a place in the design? | **Yes.** Data loads run as Celery tasks, with Redis as the broker, and each load is recorded. | [ADR 0003](decisions/0003-celery-for-background-loads.md), [#15](https://github.com/ShawnMcCollum/BroadbandMap/issues/15) |
| S3 | Does Streamlit have a place in the design? | **Yes.** An analyst dashboard alongside the map, reading data only through the API. | [ADR 0004](decisions/0004-streamlit-analyst-dashboard.md), [#16](https://github.com/ShawnMcCollum/BroadbandMap/issues/16) |

### Project and process

Answered in [#12](https://github.com/ShawnMcCollum/BroadbandMap/issues/12).

| # | Question | Resolution |
|---|----------|------------|
| P1 | Who reads this repository? | Readers range from non-technical to technical. The README and docs must work for both: a clear story up front, technical depth behind it. |
| P2 | Is the product the map, or the engineering? | **The engineering.** The project shows how an architect uses AI-assisted development to take domain knowledge to production quickly. The map is the evidence. |
| P3 | Should the project try to say something new about the domain? | **No.** It shows skill at working with broadband data, not new insights for people who already know the field. |
| P4 | What is the timeline? | The repository is public from the first commit, and its history is part of the work. It shows the project going from nothing to something real, step by step. |
| P5 | What does "done" look like? | **The process is the project.** Each merged issue should leave the repository in a coherent, presentable state. |
| P6 | What quality bar? | **Production grade.** Tests, validation, error handling and documentation are expected, not optional. |
| P7 | Design for growth, or keep everything minimal? | **Design for growth.** Structure each layer so new states, data categories and features can be added without reworking what exists. |
| P8 | Which languages go where? | **Python** for the ETL and the API. **TypeScript** for the web front end. **PostgreSQL/PostGIS** for storage. The API framework is Django (S1). |
| P9 | Who manages issues and pull requests? | Claude opens pull requests. The owner always merges. Each PR resolves its issue completely when merged, unless the PR says otherwise (for example, when a new blocking issue is found but the work so far is worth merging). |
| P10 | How are PRs merged? | **Merge commits.** |
| P11 | Which branch prefixes are used? | `feat/`, `fix/`, `docs/` and `chore/`, followed by the issue number and a short name (e.g., `docs/12-project-questions`). |
| P12 | When is something a journal entry and when is it an ADR? | The **journal** is about the process: how the work went and why it changed direction. An **ADR** records a decision about the product or its features. |
| P13 | Who writes the journal, and how often? | Neutral voice. Add an entry only when there is reasoning worth recording. |
| P14 | What do reviewers need installed, and on what platform? | **Only Docker.** Assume reviewers use Windows: commands in the docs must work in PowerShell, and line endings are normalized in the repository. |

### Data and domain

| # | Question | Resolution | Where |
|---|----------|------------|-------|
| 1 | Which 100/20 flag (`any`, `wired`, `terrestrial`) does the map show by default? | **Wired.** It is what most people mean by "broadband". The other flags can be selected. | #2, #4 |
| 2 | The file cannot tell *unserved* (<25/3) apart from *underserved* (25/3–100/20). How should the map be labelled? | Label the map **"Served / Not served (100/20)"**. The threshold question stays open (above). | #4 |
| 3 | The file is a `D25` filing but is stamped `29sep2026`. What is the release called? | Call it the **December 2025** data, as the FCC does, and note the processing date. | [README](../README.md#data-source) |
| 4 | The data has no geometry. Where do block and county boundaries come from? | Boundary data is a separate download and is now a **blocking requirement** for the ETL. **Census TIGER/Line 2020**, fetched by a script. | [ADR 0005](decisions/0005-census-tiger-2020-boundaries.md), [#9](https://github.com/ShawnMcCollum/BroadbandMap/issues/9) |
| 5 | Keep all ~4.5M location rows, or only rollups? | **Keep every location**, and offer both summary and full-data views. | [#10](https://github.com/ShawnMcCollum/BroadbandMap/issues/10) |

### Tooling

| # | Question | Resolution | Where |
|---|----------|------------|-------|
| 6 | H3 through the `h3-pg` extension (which needs a custom image) or in Python? | **Python.** The stock PostGIS image is enough. | #1, #2 |
| 7 | Which migration tool? | ~~Plain SQL.~~ **Superseded:** Django migrations, the framework's own tool. | [ADR 0002](decisions/0002-django-for-api-and-data-model.md) |
| 8 | Toolchain? | Python 3.12 with uv, ruff, mypy and pytest. Node 22 LTS with pnpm, ESLint, Prettier and Vitest. | #1 |
| 9 | Run the ETL as a Compose service or on the host? | ~~Compose service.~~ **Superseded:** Celery tasks run by a worker service. Reviewers still need only Docker. | [ADR 0003](decisions/0003-celery-for-background-loads.md) |
| 10 | Make CI a required status check? | **No CI for this project.** Lint, type checks and tests run locally. | #1 |

### Repo and process

| # | Question | Resolution | Where |
|---|----------|------------|-------|
| 11 | License? | **MIT.** | [LICENSE](../LICENSE) |
| 12 | Are ADRs enough, or should there also be a running journal? | **Add a journal** for day-to-day reasoning. ADRs stay for decisions. | [journal.md](journal.md) |
| 13 | Where does this list live? | Here, tracked by [#8](https://github.com/ShawnMcCollum/BroadbandMap/issues/8). | — |

## Guiding principle

> Keep tools as simple as they can be — without sacrificing sanity by
> ignoring a ridiculously easy solution.

New tools and dependencies have to earn their place. When a plain approach
works (SQL files, standard library, the stock image), use it. When a
well-known tool removes real pain at little cost, use that instead.
