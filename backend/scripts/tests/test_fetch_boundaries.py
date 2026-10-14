import io
import zipfile
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.fetch_boundaries import FetchError, fetch, main

URL = "https://example.test/TRACT/tl_2020_39_tract.zip"


def make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("tl_2020_39_tract.shp", b"shapes")
    return buffer.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, length: int | None = None) -> None:
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body) if length is None else length)}


def serve(body: bytes, length: int | None = None) -> AbstractContextManager[object]:
    return patch("scripts.fetch_boundaries.urlopen", return_value=FakeResponse(body, length))


def test_fetch_downloads_and_leaves_no_partial_file(tmp_path: Path) -> None:
    body = make_zip()
    with serve(body):
        assert fetch(URL, tmp_path) is True

    assert (tmp_path / "tl_2020_39_tract.zip").read_bytes() == body
    assert list(tmp_path.iterdir()) == [tmp_path / "tl_2020_39_tract.zip"]


def test_fetch_skips_a_file_already_downloaded(tmp_path: Path) -> None:
    body = make_zip()
    (tmp_path / "tl_2020_39_tract.zip").write_bytes(body)

    with serve(body):
        assert fetch(URL, tmp_path) is False


def test_fetch_replaces_a_file_of_the_wrong_size(tmp_path: Path) -> None:
    body = make_zip()
    (tmp_path / "tl_2020_39_tract.zip").write_bytes(b"stale")

    with serve(body):
        assert fetch(URL, tmp_path) is True

    assert (tmp_path / "tl_2020_39_tract.zip").read_bytes() == body


def test_fetch_rejects_a_truncated_download(tmp_path: Path) -> None:
    body = make_zip()
    with serve(body, length=len(body) + 100), pytest.raises(FetchError, match="expected"):
        fetch(URL, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_fetch_rejects_a_file_that_is_not_a_zip(tmp_path: Path) -> None:
    with serve(b"<html>error page</html>"), pytest.raises(FetchError, match="valid zip"):
        fetch(URL, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_main_reports_failure_and_keeps_going(tmp_path: Path) -> None:
    with patch("scripts.fetch_boundaries.fetch", side_effect=[FetchError("boom"), *[True] * 6]):
        assert main(["--dest", str(tmp_path)]) == 1


def test_main_downloads_zcta_only_when_asked(tmp_path: Path) -> None:
    with patch("scripts.fetch_boundaries.fetch", return_value=True) as fetch_mock:
        assert main(["--dest", str(tmp_path)]) == 0
        assert not any("zcta" in call.args[0] for call in fetch_mock.call_args_list)

        fetch_mock.reset_mock()
        assert main(["--dest", str(tmp_path), "--include-zcta"]) == 0
        assert any("zcta" in call.args[0] for call in fetch_mock.call_args_list)
