import csv
import io
import json
from pathlib import Path

import pytest
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df
from streamlit.testing.v1 import AppTest

import api
import exports
from api import COUNTIES, RELEASES, ROLLUPS
from selection import Snapshot
from summaries import CountySummaries
from tests.conftest import FixtureApi, release_json

APP = Path(__file__).parents[1] / "app.py"


def start(monkeypatch: pytest.MonkeyPatch, fixture: FixtureApi) -> AppTest:
    monkeypatch.setattr(api, "client_for", fixture.client)
    return AppTest.from_file(APP, default_timeout=15).run()


def text_values(app: AppTest) -> str:
    return "\n".join(str(element.value) for element in app.text)


def plotted_shares(app: AppTest) -> list[float]:
    chart = app.get("vega_lite_chart")[0]
    frame = convert_arrow_bytes_to_pandas_df(chart.proto.datasets[0].data.data)
    return list(frame["Served share (%)"])


def test_filters_chart_table_export_and_county_share_one_selection(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
) -> None:
    exported: list[tuple[str, bytes]] = []
    original = exports.summary_csv

    def capture(data: CountySummaries, names: dict[str, str]) -> tuple[str, bytes]:
        result = original(data, names)
        exported[:] = [result]
        return result

    monkeypatch.setattr(exports, "summary_csv", capture)
    app = start(monkeypatch, fixture_api)
    assert not app.exception
    assert "20.0% Served" in text_values(app)
    assert app.table[0].value["Served share"].tolist() == [
        "100.0%",
        "11.1%",
        "No summary observation",
    ]
    assert len(app.get("vega_lite_chart")) == 1
    chart = app.get("vega_lite_chart")[0]
    spec = json.loads(chart.proto.spec)
    assert spec["encoding"]["x"]["field"] == "Served share (%)"
    assert spec["encoding"]["x"]["title"] == "Served share (%) — from 0 to 100"
    assert spec["encoding"]["y"]["title"] == "County"
    assert plotted_shares(app) == [100, 11.1]
    assert len(app.get("download_button")) == 1
    assert app.get("download_button")[0].proto.ignore_rerun
    assert exported[0][0].endswith("2026-09-29-wired.csv")
    initial_geometry_reads = sum(r.url.path == COUNTIES for r in fixture_api.requests)
    app.selectbox(key="county_control").set_value("39005").run()
    assert not app.exception
    assert "No locations were observed" in app.info[-1].value
    assert app.session_state["exploration"].selection.county == "39005"
    for flag, expected in [("any", "100.0% Served"), ("terrestrial", "0.0% Served")]:
        app.selectbox(key="flag_control").set_value(flag).run()
        assert not app.exception
        assert expected in text_values(app)
        assert app.selectbox(key="county_control").value is None
        assert exported[0][0].endswith(f"{flag}.csv")
        assert plotted_shares(app) == ([100, 100] if flag == "any" else [0, 0])
        rows = list(csv.DictReader(io.StringIO(exported[0][1].decode("utf-8-sig"))))
        assert {r["flag"] for r in rows} == {flag}
        assert len(rows) == 2
    app.selectbox(key="flag_control").set_value("wired").run()
    app.selectbox(key="release_control").set_value(("2025-12-31", "2026-09-28")).run()
    assert not app.exception
    assert "0.0% Served" in text_values(app)
    assert exported[0][0].endswith("2026-09-28-wired.csv")
    assert app.table[0].value["Served"].tolist() == ["0", "0", "—"]
    assert plotted_shares(app) == [0, 0]
    assert sum(r.url.path == COUNTIES for r in fixture_api.requests) == initial_geometry_reads
    assert len(app.get("vega_lite_chart")) == len(app.get("download_button")) == 1


def test_partial_read_drops_prior_export_and_refresh_recovers(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
) -> None:
    app = start(monkeypatch, fixture_api)
    fixture_api.summary_second_page = fixture_api.fail_second_page = True
    app.button[0].click().run()
    assert not app.exception
    assert not app.table
    assert not app.get("download_button")
    assert not app.get("vega_lite_chart")
    assert app.session_state["exploration"].summaries is None
    fixture_api.fail_second_page = False
    app.button(key="retry_summaries").click().run()
    assert not app.exception
    assert "20.0% Served" in text_values(app)
    assert len(app.get("download_button")) == 1


@pytest.mark.parametrize("kind", ["empty", "network", "no_ohio", "names", "summaries"])
def test_unavailable_states(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
    kind: str,
) -> None:
    if kind == "empty":
        fixture_api.releases = []
    elif kind == "no_ohio":
        fixture_api.releases = [release_json(ohio=False), release_json("2026-09-28")]
    else:
        fixture_api.failure = kind
    app = start(monkeypatch, fixture_api)
    assert not app.exception
    assert not app.get("download_button")
    if kind == "empty":
        assert "No data releases are loaded" in app.info[0].value
    elif kind == "no_ohio":
        assert "Ohio is not loaded" in app.info[0].value
        assert not any(r.url.path == ROLLUPS for r in fixture_api.requests)
    elif kind == "names":
        assert app.table[0].value["County"].tolist() == ["39001", "39003"]
        assert any(b.disabled for b in app.button)
    else:
        assert app.error
    assert "secret" not in text_values(app)


def test_refresh_and_diagnostics_are_fresh_and_preserve_pair(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
) -> None:
    app = start(monkeypatch, fixture_api)
    app.selectbox(key="release_control").set_value(("2025-12-31", "2026-09-28")).run()
    app.selectbox(key="flag_control").set_value("any").run()
    before = len(fixture_api.requests)
    app.run()
    assert len(fixture_api.requests) == before
    app.radio(key="view").set_value("Diagnostics").run()
    assert not app.exception
    assert len(app.success) == 4
    app.radio(key="view").set_value("Analysis").run()
    assert not app.exception
    assert app.selectbox(key="release_control").value == ("2025-12-31", "2026-09-28")
    assert app.selectbox(key="flag_control").value == "any"
    assert sum(r.url.path == RELEASES for r in fixture_api.requests) == 2
    assert sum(r.url.path == COUNTIES for r in fixture_api.requests) == 2


def test_disappeared_release_requires_explicit_choice(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
) -> None:
    app = start(monkeypatch, fixture_api)
    fixture_api.releases = fixture_api.releases[1:]
    app.button[0].click().run()
    assert not app.exception
    assert app.selectbox(key="release_control").value is None
    assert not app.get("download_button")
    assert "no longer available" in app.warning[0].value
    app.selectbox(key="release_control").set_value(("2025-12-31", "2026-09-28")).run()
    assert not app.exception
    assert app.get("download_button")


def test_refresh_after_first_data_load_chooses_latest(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
) -> None:
    fixture_api.releases = []
    app = start(monkeypatch, fixture_api)
    fixture_api.releases = [release_json()]
    app.button[0].click().run()
    assert not app.exception
    assert app.selectbox(key="release_control").value == ("2025-12-31", "2026-09-29")
    assert app.get("download_button")


def test_session_retains_only_current_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
) -> None:
    app = start(monkeypatch, fixture_api)
    for flag in ["any", "wired", "terrestrial", "any", "wired"]:
        app.selectbox(key="flag_control").set_value(flag).run()
    snapshot: Snapshot = app.session_state["exploration"]
    assert not app.exception
    assert snapshot.summaries is not None
    assert len(snapshot.summaries.rows) == 2
    assert snapshot.names is not None and len(snapshot.names) == 3
    assert "coordinates" not in repr(snapshot)


def test_source_reload_discards_old_session_objects(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
) -> None:
    app = start(monkeypatch, fixture_api)
    app.session_state["exploration"] = object()
    app.run()
    assert not app.exception
    assert isinstance(app.session_state["exploration"], Snapshot)
    assert "20.0% Served" in text_values(app)


@pytest.mark.parametrize(
    "variable,value,expected",
    [
        ("API_BASE_URL", "file:///private", "API configuration is invalid"),
        ("WEB_APP_URL", "javascript:alert(1)", "Map navigation is unavailable"),
    ],
)
def test_invalid_configuration_is_safe(
    monkeypatch: pytest.MonkeyPatch,
    fixture_api: FixtureApi,
    variable: str,
    value: str,
    expected: str,
) -> None:
    monkeypatch.setenv(variable, value)
    app = start(monkeypatch, fixture_api)
    assert not app.exception
    assert expected in " ".join(str(e.value) for e in [*app.error, *app.warning])
