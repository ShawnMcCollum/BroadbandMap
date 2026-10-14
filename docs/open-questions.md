# Open questions

Questions that came up while planning the project, with their resolutions.
Each entry points to where the answer is acted on. Raised and answered in
[#8](https://github.com/ShawnMcCollum/BroadbandMap/issues/8).

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

### Data and domain

| # | Question | Resolution | Where |
|---|----------|------------|-------|
| 1 | Which 100/20 flag (`any`, `wired`, `terrestrial`) does the map show by default? | **Wired.** It is what most people mean by "broadband". The other flags can be selected. | #2, #4 |
| 2 | The file cannot tell *unserved* (<25/3) apart from *underserved* (25/3–100/20). How should the map be labelled? | Label the map **"Served / Not served (100/20)"**. The threshold question stays open (above). | #4 |
| 3 | The file is a `D25` filing but is stamped `29sep2026`. What is the release called? | Call it the **December 2025** data, as the FCC does, and note the processing date. | [README](../README.md#data-source) |
| 4 | The data has no geometry. Where do block and county boundaries come from? | Boundary data is a separate download and is now a **blocking requirement** for the ETL. | [#9](https://github.com/ShawnMcCollum/BroadbandMap/issues/9) blocks #2 |
| 5 | Keep all ~4.5M location rows, or only rollups? | **Keep every location**, and offer both summary and full-data views. | [#10](https://github.com/ShawnMcCollum/BroadbandMap/issues/10) |

### Tooling

| # | Question | Resolution | Where |
|---|----------|------------|-------|
| 6 | H3 through the `h3-pg` extension (which needs a custom image) or in Python? | **Python.** The stock PostGIS image is enough. | #1, #2 |
| 7 | Which migration tool? | **Plain SQL.** See the [guiding principle](#guiding-principle). | #1 |
| 8 | Toolchain? | Python 3.12 with uv, ruff, mypy and pytest. Node 22 LTS with pnpm, ESLint, Prettier and Vitest. | #1 |
| 9 | Run the ETL as a Compose service or on the host? | **Compose service.** Reviewers need only Docker. | #1, #2 |
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
