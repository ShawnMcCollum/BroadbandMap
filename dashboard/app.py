"""Ohio analyst view. HTTP, transformations and selection live in separate modules."""

import os

import streamlit as st

from api import (
    ApiUnavailableError,
    client_for,
    fetch_counties,
    fetch_health,
    fetch_releases,
    fetch_summary,
)
from config import base_url, map_link
from exports import summary_csv
from selection import Snapshot
from summaries import FCC_SOURCE, FLAGS, Release, chart_data, join_counties, table_data, totals

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
LABELS = {"database": "PostGIS", "redis": "Redis", "worker": "Celery worker"}
LOAD_HELP = "https://github.com/ShawnMcCollum/BroadbandMap#load-the-ohio-data"


def change_filters(snapshot: Snapshot) -> None:
    snapshot.change(
        release=st.session_state["release_control"],
        flag=st.session_state["flag_control"],
    )
    snapshot.needs_selection = snapshot.selection.release is None


def change_county(snapshot: Snapshot) -> None:
    snapshot.choose_county(st.session_state["county_control"])


def change_view(snapshot: Snapshot) -> None:
    if st.session_state["view"] == "Analysis":
        snapshot.refresh()


def failure(snapshot: Snapshot, resource: str, headline: str) -> bool:
    if resource not in snapshot.errors:
        return False
    st.error(headline)
    # Server pointers/names are plain text, never interpreted as Markdown or HTML.
    st.text(snapshot.errors[resource])
    if st.button(f"Retry {resource}", key=f"retry_{resource}"):
        snapshot.errors.pop(resource, None)
        st.rerun()
    return True


def catalog(snapshot: Snapshot) -> None:
    if snapshot.releases is None and "releases" not in snapshot.errors:
        with st.spinner("Loading releases…"):
            try:
                with client_for(API_BASE_URL) as client:
                    snapshot.reconcile(fetch_releases(client))
            except ApiUnavailableError as error:
                snapshot.errors["releases"] = error.explanation


def load_analysis(snapshot: Snapshot, release: Release) -> None:
    if snapshot.names is None and "names" not in snapshot.errors:
        with st.spinner("Loading county names…"):
            try:
                with client_for(API_BASE_URL) as client:
                    snapshot.names = fetch_counties(client)
            except ApiUnavailableError as error:
                snapshot.errors["names"] = error.explanation
    if snapshot.summaries is None and "summaries" not in snapshot.errors:
        requested = snapshot.selection
        with st.spinner("Loading county summaries…"):
            try:
                with client_for(API_BASE_URL) as client:
                    data, _ = fetch_summary(client, release, requested.flag)
                snapshot.accept(requested, data)
            except ApiUnavailableError as error:
                snapshot.errors["summaries"] = error.explanation
                if error.status == 404:
                    # Rediscover without silently substituting another release.
                    snapshot.releases = None
                    catalog(snapshot)


def provenance(release: Release, snapshot: Snapshot) -> None:
    st.text(
        f"{FCC_SOURCE}\nFiling period {release.filing_period} · Data period {release.as_of} · "
        f"Processed {release.processed_on}\nLoaded states: "
        + ", ".join(f"{state.name} ({state.code})" for state in release.states)
        + f"\nOhio (39) · {FLAGS[snapshot.selection.flag]} · "
        "100 Mbps download / 20 Mbps upload · Boundaries: Census TIGER/Line 2020"
    )


def county_selection(snapshot: Snapshot, release: Release) -> None:
    data = snapshot.summaries
    if data is None:
        return
    names = snapshot.names or {}
    observed = {row.code: row for row in data.rows}
    options = sorted(names.keys() | observed.keys(), key=lambda code: (names.get(code, code), code))
    if snapshot.selection.county not in options:
        snapshot.choose_county(None)
    st.session_state["county_control"] = snapshot.selection.county
    code = st.selectbox(
        "County",
        options,
        index=None,
        placeholder="Choose a county",
        format_func=lambda code: f"{names.get(code, code)} ({code})",
        key="county_control",
        on_change=change_county,
        args=(snapshot,),
    )
    if code is None:
        return
    row = observed.get(code)
    if row:
        st.text(
            f"{names.get(code, code)} ({code}): {row.locations:,} locations; "
            f"{row.served:,} Served; {row.not_served:,} Not served; {row.share:.1f}% Served."
        )
    else:
        if snapshot.diagnosis is None and "diagnosis" not in snapshot.errors:
            requested = snapshot.selection
            with st.spinner("Checking county coverage…"):
                try:
                    with client_for(API_BASE_URL) as client:
                        _, coverage = fetch_summary(client, release, requested.flag, code=code)
                    if snapshot.selection == requested:
                        snapshot.diagnosis = {
                            "no_observations": (
                                "No locations were observed in this area for this release."
                            ),
                            "outside_release_coverage": (
                                "This area is outside the loaded coverage of this release."
                            ),
                            "observed": (
                                "County data changed. Refresh summaries "
                                "to read current observations."
                            ),
                        }[coverage]
                except ApiUnavailableError as error:
                    snapshot.errors["diagnosis"] = error.explanation
        if not failure(snapshot, "diagnosis", "County coverage could not be checked."):
            st.info(snapshot.diagnosis or "No summary observation.")
    st.caption("Location details will be available here in a future update.")


def results(snapshot: Snapshot, release: Release) -> None:
    names_failed = failure(snapshot, "names", "County names and boundary coverage are unavailable.")
    if names_failed:
        st.info("Observed rows use GEOIDs. Retry county names before downloading CSV.")
    if failure(snapshot, "summaries", "County summaries could not be loaded completely."):
        return
    data = snapshot.summaries
    if data is None:
        return
    counties = join_counties(data, snapshot.names or {})
    st.header("Observed county totals")
    locations, served, not_served, share = totals(data)
    if locations:
        st.text(
            f"{locations:,} locations · {served:,} Served · {not_served:,} Not served · "
            f"{share:.1f}% Served"
        )
    else:
        st.info(
            "No county summary observations are available. A served share cannot be calculated."
        )
    if snapshot.names is not None:
        st.caption(
            f"{len(data.rows)} observed counties; {len(snapshot.names)} county boundaries loaded."
        )
        if any(row.code not in snapshot.names for row in data.rows):
            st.warning(
                "Some observed county names are missing from the boundary resource; "
                "GEOIDs are shown."
            )
    st.caption(
        "Served / Not served (100/20 Mbps) uses the selected source flag and its complement. "
        "Not served is not a regulatory unserved classification. "
        "Missing observations are not zeros. "
        "Separate API pages are fresh reads and may change during replacement or rebuilding."
    )
    st.header("County served share")
    if data.rows:
        st.bar_chart(
            chart_data(counties),
            x="County",
            y="Served share (%)",
            horizontal=True,
            sort=False,
            # Streamlit swaps these input-axis titles for horizontal bars.
            x_label="County",
            y_label="Served share (%) — from 0 to 100",
            color="#155b83",
            height=max(280, len(data.rows) * 28),
            alt="County Served share, highest first. "
            "Exact counts and percentages follow in County summaries.",
        )
    st.header("County summaries")
    st.caption("Chart text alternative. All counts use the displayed release and technology.")
    st.table(
        table_data(counties),
        hide_index=True,
        alt="County GEOIDs, locations, Served, Not served and Served share.",
    )
    if snapshot.names is not None:
        filename, payload = summary_csv(data, snapshot.names)
        st.download_button(
            "Download summary CSV",
            payload,
            file_name=filename,
            mime="text/csv",
            key="summary_csv",
            on_click="ignore",
        )
    else:
        st.button("Download summary CSV", disabled=True)
    st.caption(
        "CSV contains observed county summaries only. GEOIDs and loaded-state codes have a literal "
        "apostrophe prefix to preserve text; potentially executable text is prefixed too. "
        "Programmatic readers remove the identifier prefix. Spreadsheet import behavior varies."
    )
    county_selection(snapshot, release)


def analysis(snapshot: Snapshot) -> None:
    st.button("Refresh", on_click=snapshot.refresh)
    # Explicitly replace the prior result block before doing any fresh reads.
    output = st.empty()
    output.empty()
    with output.container():
        analysis_body(snapshot)


def analysis_body(snapshot: Snapshot) -> None:
    catalog(snapshot)
    if failure(snapshot, "releases", "The release catalog could not be loaded."):
        return
    releases = snapshot.releases or ()
    if not releases:
        st.info(
            "No data releases are loaded. Follow the README data-load instructions, then refresh."
        )
        st.markdown(f"[Data-load instructions]({LOAD_HELP})")
        return
    by_key = {release.key: release for release in releases}
    st.session_state["release_control"] = snapshot.selection.release
    st.session_state["flag_control"] = snapshot.selection.flag
    st.selectbox(
        "Release",
        list(by_key),
        index=None,
        key="release_control",
        format_func=lambda key: by_key[key].label,
        on_change=change_filters,
        args=(snapshot,),
        placeholder="Choose a release",
    )
    st.selectbox(
        "Technology",
        list(FLAGS),
        key="flag_control",
        format_func=lambda flag: FLAGS[flag],
        on_change=change_filters,
        args=(snapshot,),
        help="Wired: wired_100_20; Any technology: any_100_20; Terrestrial: terrestrial_100_20. "
        "Each source Boolean indicates 100 Mbps download / 20 Mbps upload.",
    )
    release = by_key.get(snapshot.selection.release) if snapshot.selection.release else None
    if release is None:
        st.warning("The selected release is no longer available. Choose a release to continue.")
        return
    provenance(release, snapshot)
    if not release.has_ohio:
        st.info("Ohio is not loaded for this release.")
        return
    load_analysis(snapshot, release)
    if snapshot.selection.release != release.key:
        st.rerun()
    results(snapshot, release)


def diagnostics() -> None:
    st.header("Stack diagnostics")
    st.button("Refresh diagnostics")
    with client_for(API_BASE_URL) as client:
        try:
            health = fetch_health(client)
        except ApiUnavailableError as error:
            st.error("The API cannot be reached or returned an unexpected health report.")
            st.text(error.explanation)
        else:
            st.success("✓ API")
            for name, up in health.items():
                if up:
                    st.success(f"✓ {LABELS[name]}")
                else:
                    st.error(f"✗ {LABELS[name]}")


def main() -> None:
    st.set_page_config(page_title="BroadbandMap Analyst dashboard", layout="wide")
    st.title("BroadbandMap: Analyst dashboard")
    try:
        st.html(map_link(os.environ.get("WEB_APP_URL", "http://localhost:5173/")))
    except ValueError:
        st.warning("Map navigation is unavailable. An operator must correct WEB_APP_URL.")
    st.caption("Map opens in this tab with default filters. Dashboard filters are not transferred.")
    # A source reload can replace the domain classes while retaining session objects.
    # Rediscover rather than compare stale dataclass instances with new API values.
    if not isinstance(st.session_state.get("exploration"), Snapshot):
        st.session_state["exploration"] = Snapshot()
    snapshot: Snapshot = st.session_state["exploration"]
    view = st.radio(
        "Dashboard view",
        ["Analysis", "Diagnostics"],
        horizontal=True,
        key="view",
        on_change=change_view,
        args=(snapshot,),
    )
    try:
        base_url(API_BASE_URL, origin_only=True)
    except ValueError:
        st.error("API configuration is invalid. An operator must correct API_BASE_URL.")
        return
    if view == "Diagnostics":
        diagnostics()
    else:
        analysis(snapshot)


if __name__ == "__main__":
    main()
