import re
from datetime import date

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from bdc.models import Release
from core.admin import CappedCountPaginator
from geography.models import Block, State
from geography.tests.helpers import boundary_fields
from served_unserved.admin import RollupAdmin, ServedStatusAdmin
from served_unserved.models import Rollup, ServedStatus

CHANGELIST = "admin:served_unserved_servedstatus_changelist"
ROLLUPS = "admin:served_unserved_rollup_changelist"


def test_changelist_lists_the_status(admin_client: Client, served_status: ServedStatus) -> None:
    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert served_status in response.context["cl"].result_list


def test_changelist_shows_the_block_and_cell(
    admin_client: Client, served_status: ServedStatus
) -> None:
    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert "390490001101000" in response.text
    assert "882a91ae3bfffff" in response.text


def add_status(
    release: Release, block: Block, location_id: int, h3_res8: str = "882a91ae3bfffff"
) -> ServedStatus:
    """A status of the location in the release, block and cell, served by every technology."""
    return ServedStatus.objects.create(
        release=release,
        location_id=location_id,
        block=block,
        h3_res8=h3_res8,
        any_100_20=True,
        wired_100_20=True,
        terrestrial_100_20=True,
    )


def status_queries(queries: CaptureQueriesContext) -> list[str]:
    return [
        query["sql"]
        for query in queries.captured_queries
        if '"served_unserved_servedstatus"' in query["sql"]
    ]


# Release IDs follow load order, not date order: December 2026 is added last but is the newest.
# The list follows the IDs, the order of the unique (release, location_id) index (ADR 0022).
def test_changelist_lists_by_release_id_then_location_id(
    admin_client: Client, served_status: ServedStatus, j25_status: ServedStatus, block: Block
) -> None:
    earlier = add_status(served_status.release, block, 1000000001)
    d26 = Release.objects.create(
        filing_period="D26", as_of=date(2026, 12, 31), processed_on=date(2027, 9, 29)
    )
    newest = add_status(d26, block, 1000000001)

    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [earlier, served_status, j25_status, newest]


def test_changelist_page_is_ordered_like_the_unique_index(
    admin_client: Client, served_status: ServedStatus
) -> None:
    with CaptureQueriesContext(connection) as queries:
        admin_client.get(reverse(CHANGELIST))

    page = next(sql for sql in status_queries(queries) if "ORDER BY" in sql)
    order = re.search(r"ORDER BY (.*?)(?: LIMIT \d+)?$", page)
    assert order is not None
    assert order.group(1) == (
        '"served_unserved_servedstatus"."release_id" ASC, '
        '"served_unserved_servedstatus"."location_id" ASC'
    )


# No column sorts the list, since no index serves another order (ADR 0022).
def test_changelist_columns_do_not_sort(admin_client: Client, served_status: ServedStatus) -> None:
    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert 'href="?o=' not in response.text


# The count stops after the cap, and no filter counts its choices, even when asked to.
@pytest.mark.parametrize("params", [{}, {"_facets": ""}])
def test_changelist_reads_the_statuses_twice(
    admin_client: Client, served_status: ServedStatus, params: dict[str, str]
) -> None:
    with CaptureQueriesContext(connection) as queries:
        response = admin_client.get(reverse(CHANGELIST), params)

    assert response.status_code == 200
    count, page = status_queries(queries)
    assert count.startswith("SELECT COUNT(*) FROM (SELECT ")
    assert count.endswith(" LIMIT 10001) subquery")
    assert page.startswith('SELECT "served_unserved_servedstatus"."id", ')
    assert "Show counts" not in response.text


@pytest.fixture
def capped(monkeypatch: pytest.MonkeyPatch, served_status: ServedStatus, block: Block) -> None:
    """Three statuses, a cap of two and one status per page."""
    monkeypatch.setattr(CappedCountPaginator, "cap", 2)
    monkeypatch.setattr(ServedStatusAdmin, "list_per_page", 1)
    for location_id in (1000000001, 1000000002):
        add_status(served_status.release, block, location_id)


@pytest.mark.usefixtures("capped")
def test_count_stops_at_the_cap(admin_client: Client) -> None:
    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert response.context["cl"].result_count == 2
    assert response.context["cl"].paginator.capped
    assert "More than 2 served statuses" in response.text
    assert "More than 2 results" in response.text


@pytest.mark.usefixtures("capped")
def test_pages_up_to_the_cap_are_offered(admin_client: Client) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"p": "2"})

    assert response.status_code == 200
    assert [status.location_id for status in response.context["cl"].result_list] == [1000000002]


@pytest.mark.usefixtures("capped")
def test_pages_beyond_the_cap_are_refused(admin_client: Client) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"p": "3"})

    assert response.status_code == 302
    assert response["Location"].endswith("?e=1")


def test_count_below_the_cap_is_exact(
    admin_client: Client,
    served_status: ServedStatus,
    block: Block,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(CappedCountPaginator, "cap", 3)
    monkeypatch.setattr(ServedStatusAdmin, "list_per_page", 1)
    for location_id in (1000000001, 1000000002):
        add_status(served_status.release, block, location_id)

    response = admin_client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert response.context["cl"].result_count == 3
    assert not response.context["cl"].paginator.capped
    assert "3 served statuses" in response.text
    assert "3 results" in response.text
    assert "More than" not in response.text


def test_change_view_opens(admin_client: Client, served_status: ServedStatus) -> None:
    url = reverse("admin:served_unserved_servedstatus_change", args=[served_status.pk])

    assert admin_client.get(url).status_code == 200


def test_status_cannot_be_added_changed_or_deleted(
    admin_client: Client, served_status: ServedStatus
) -> None:
    add = reverse("admin:served_unserved_servedstatus_add")
    change = reverse("admin:served_unserved_servedstatus_change", args=[served_status.pk])
    delete = reverse("admin:served_unserved_servedstatus_delete", args=[served_status.pk])

    assert admin_client.get(add).status_code == 403
    assert admin_client.post(change, {}).status_code == 403
    assert admin_client.post(delete, {"post": "yes"}).status_code == 403


def test_search_by_location_id_finds_the_status(
    admin_client: Client, served_status: ServedStatus
) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"q": "1000338835"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [served_status]


@pytest.fixture
def j25_status(block: Block) -> ServedStatus:
    """The served_status fixture's location, in the June 2025 release."""
    j25 = Release.objects.create(
        filing_period="J25", as_of=date(2025, 6, 30), processed_on=date(2026, 10, 1)
    )
    return ServedStatus.objects.create(
        release=j25,
        location_id=1000338835,
        block=block,
        h3_res8="882a91ae3bfffff",
        any_100_20=True,
        wired_100_20=False,
        terrestrial_100_20=True,
    )


def test_search_by_location_id_finds_it_in_every_release(
    admin_client: Client, served_status: ServedStatus, j25_status: ServedStatus
) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"q": "1000338835"})

    assert response.status_code == 200
    assert set(response.context["cl"].result_list) == {served_status, j25_status}
    assert response.context["cl"].result_count == 2


def test_search_by_location_id_within_one_release(
    admin_client: Client, served_status: ServedStatus, j25_status: ServedStatus
) -> None:
    response = admin_client.get(
        reverse(CHANGELIST), {"q": "1000338835", "release__id__exact": str(j25_status.release_id)}
    )

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [j25_status]


@pytest.fixture
def elsewhere(served_status: ServedStatus, block: Block) -> ServedStatus:
    """A status in the served_status fixture's release, in another block and another cell."""
    other_block = Block.objects.create(
        geoid="390490001101001",
        name="Block 1001",
        block_group=block.block_group,
        place=block.place,
        county_subdivision=block.county_subdivision,
        population_2020=12,
        housing_units_2020=5,
        urban_rural="U",
        **boundary_fields(),
    )
    return add_status(served_status.release, other_block, 1000000002, h3_res8="882a91ae3a7ffff")


AREA_TERMS = pytest.mark.parametrize(
    "term", ["390490001101000", "882a91ae3bfffff"], ids=["block", "cell"]
)


@AREA_TERMS
@pytest.mark.usefixtures("elsewhere")
def test_search_by_area_finds_its_statuses_in_every_release(
    admin_client: Client, served_status: ServedStatus, j25_status: ServedStatus, term: str
) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"q": term})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [served_status, j25_status]
    assert response.context["cl"].result_count == 2


@AREA_TERMS
@pytest.mark.usefixtures("elsewhere", "j25_status")
def test_search_by_area_within_one_release(
    admin_client: Client, served_status: ServedStatus, term: str
) -> None:
    response = admin_client.get(
        reverse(CHANGELIST), {"q": term, "release__id__exact": str(served_status.release_id)}
    )

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [served_status]


# Nothing indexes location_id, block_id or h3_res8 alone, so each query of the search names the
# releases, for an index that leads with the release (ADRs 0021 and 0023).
@pytest.mark.parametrize(
    ("term", "condition"),
    [
        ("1000338835", '"location_id" = 1000338835'),
        ("390490001101000", "\"block_id\" = '390490001101000'"),
        ("882a91ae3bfffff", "\"h3_res8\" = '882a91ae3bfffff'"),
    ],
    ids=["location", "block", "cell"],
)
@pytest.mark.usefixtures("served_status", "j25_status")
def test_search_names_the_releases(admin_client: Client, term: str, condition: str) -> None:
    with CaptureQueriesContext(connection) as queries:
        admin_client.get(reverse(CHANGELIST), {"q": term})

    searches = [query["sql"] for query in queries.captured_queries if condition in query["sql"]]
    # The page's count and its rows
    assert len(searches) >= 2
    assert all('"release_id" IN (' in sql for sql in searches)


# A block or a cell without statuses finds nothing. So does a cell index in capitals, which is not
# a cell's form, and a county GEOID, which is read as a location ID.
@pytest.mark.parametrize(
    "term",
    ["390490001109999", "882a91ae38fffff", "882A91AE3BFFFFF", "39049"],
    ids=["block", "cell", "capitals", "county"],
)
def test_search_for_an_area_without_statuses_finds_nothing(
    admin_client: Client, served_status: ServedStatus, term: str
) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"q": term})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == []


# "²" passes str.isdigit() but int() rejects it.
@pytest.mark.parametrize("term", ["abc", "²"])
def test_search_for_text_finds_nothing(
    admin_client: Client, served_status: ServedStatus, term: str
) -> None:
    response = admin_client.get(reverse(CHANGELIST), {"q": term})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == []


def test_rollup_changelist_lists_the_rollup(admin_client: Client, rollup: Rollup) -> None:
    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert rollup in response.context["cl"].result_list


def test_rollup_change_view_opens(admin_client: Client, rollup: Rollup) -> None:
    url = reverse("admin:served_unserved_rollup_change", args=[rollup.pk])

    assert admin_client.get(url).status_code == 200


def test_rollup_cannot_be_added_changed_or_deleted(admin_client: Client, rollup: Rollup) -> None:
    add = reverse("admin:served_unserved_rollup_add")
    change = reverse("admin:served_unserved_rollup_change", args=[rollup.pk])
    delete = reverse("admin:served_unserved_rollup_delete", args=[rollup.pk])

    assert admin_client.get(add).status_code == 403
    assert admin_client.post(change, {}).status_code == 403
    assert admin_client.post(delete, {"post": "yes"}).status_code == 403


def test_search_by_code_finds_the_rollup(admin_client: Client, rollup: Rollup) -> None:
    response = admin_client.get(reverse(ROLLUPS), {"q": "39049"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [rollup]


def test_search_by_h3_cell_finds_the_rollup(
    admin_client: Client, release: Release, state: State
) -> None:
    cell = Rollup.objects.create(
        release=release,
        state=state,
        level="h3_res8",
        code="882a91ae3bfffff",
        locations=10,
        any_100_20=8,
        wired_100_20=4,
        terrestrial_100_20=6,
    )

    response = admin_client.get(reverse(ROLLUPS), {"q": "882a91ae3bfffff"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [cell]


def test_rollup_changelist_shows_the_state(
    admin_client: Client, release: Release, state: State, wv_state: State
) -> None:
    for each in (state, wv_state):
        Rollup.objects.create(
            release=release,
            state=each,
            level="h3_res8",
            code="882a91ae3bfffff",
            locations=10,
            any_100_20=8,
            wired_100_20=4,
            terrestrial_100_20=6,
        )

    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert '<td class="field-state_id">39</td>' in response.text
    assert '<td class="field-state_id">54</td>' in response.text


# The search is an exact match, so a prefix finds nothing.
@pytest.mark.parametrize("term", ["3904", "abc"])
def test_rollup_search_matches_the_whole_code(
    admin_client: Client, rollup: Rollup, term: str
) -> None:
    response = admin_client.get(reverse(ROLLUPS), {"q": term})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == []


def add_rollup(release: Release, state: State, level: str, code: str) -> Rollup:
    """A rollup of ten locations of the state, in the release, level and area."""
    return Rollup.objects.create(
        release=release,
        state=state,
        level=level,
        code=code,
        locations=10,
        any_100_20=8,
        wired_100_20=4,
        terrestrial_100_20=6,
    )


def rollup_queries(queries: CaptureQueriesContext) -> list[str]:
    return [
        query["sql"]
        for query in queries.captured_queries
        if '"served_unserved_rollup"' in query["sql"]
    ]


@pytest.fixture
def j25_rollup(rollup: Rollup) -> Rollup:
    """The rollup fixture's county, in the June 2025 release."""
    j25 = Release.objects.create(
        filing_period="J25", as_of=date(2025, 6, 30), processed_on=date(2026, 10, 1)
    )
    return add_rollup(j25, rollup.state, "county", "39049")


# Release IDs follow load order, not date order: December 2026 is added last but is the newest.
# The list follows the IDs, then the level, code and state, the order of the unique
# (release, level, code, state) index (ADR 0024).
def test_rollup_changelist_lists_by_release_id_level_code_then_state_id(
    admin_client: Client, rollup: Rollup, j25_rollup: Rollup, wv_state: State
) -> None:
    cell_wv = add_rollup(rollup.release, wv_state, "h3_res8", "882a91ae3bfffff")
    cell_oh = add_rollup(rollup.release, rollup.state, "h3_res8", "882a91ae3bfffff")
    earlier = add_rollup(rollup.release, rollup.state, "county", "39035")
    d26 = Release.objects.create(
        filing_period="D26", as_of=date(2026, 12, 31), processed_on=date(2027, 9, 29)
    )
    newest = add_rollup(d26, rollup.state, "county", "39049")

    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [
        earlier,
        rollup,
        cell_oh,
        cell_wv,
        j25_rollup,
        newest,
    ]


def test_rollup_changelist_page_is_ordered_like_the_unique_index(
    admin_client: Client, rollup: Rollup
) -> None:
    with CaptureQueriesContext(connection) as queries:
        admin_client.get(reverse(ROLLUPS))

    page = next(sql for sql in rollup_queries(queries) if "ORDER BY" in sql)
    order = re.search(r"ORDER BY (.*?)(?: LIMIT \d+)?$", page)
    assert order is not None
    assert order.group(1) == (
        '"served_unserved_rollup"."release_id" ASC, '
        '"served_unserved_rollup"."level" ASC, '
        '"served_unserved_rollup"."code" ASC, '
        '"served_unserved_rollup"."state_id" ASC'
    )


# No column sorts the list, since no index serves another order (ADR 0024).
def test_rollup_changelist_columns_do_not_sort(admin_client: Client, rollup: Rollup) -> None:
    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert 'href="?o=' not in response.text


# The count stops after the cap, and no filter counts its choices, even when asked to.
@pytest.mark.parametrize("params", [{}, {"_facets": ""}])
def test_rollup_changelist_reads_the_rollups_twice(
    admin_client: Client, rollup: Rollup, params: dict[str, str]
) -> None:
    with CaptureQueriesContext(connection) as queries:
        response = admin_client.get(reverse(ROLLUPS), params)

    assert response.status_code == 200
    count, page = rollup_queries(queries)
    assert count.startswith("SELECT COUNT(*) FROM (SELECT ")
    assert count.endswith(" LIMIT 10001) subquery")
    assert page.startswith('SELECT "served_unserved_rollup"."id", ')
    assert "Show counts" not in response.text


# The unique index leads with the release, so each query names the releases. Without them, a
# filter on a level reads past every other level's rollups in each release (ADR 0024).
@pytest.mark.parametrize(
    "params",
    [{}, {"level__exact": "county"}, {"q": "39049"}],
    ids=["no-filter", "level", "search"],
)
@pytest.mark.usefixtures("j25_rollup")
def test_rollup_changelist_names_the_releases(admin_client: Client, params: dict[str, str]) -> None:
    with CaptureQueriesContext(connection) as queries:
        response = admin_client.get(reverse(ROLLUPS), params)

    assert response.status_code == 200
    reads = rollup_queries(queries)
    # The page's count and its rows
    assert len(reads) == 2
    assert all('"served_unserved_rollup"."release_id" IN (' in sql for sql in reads)


def test_rollup_changelist_without_releases_is_empty(admin_client: Client) -> None:
    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == []
    assert "0 rollups" in response.text


def test_rollup_level_filter_lists_the_level_in_every_release(
    admin_client: Client, rollup: Rollup, j25_rollup: Rollup
) -> None:
    add_rollup(rollup.release, rollup.state, "tract", "39049000110")

    response = admin_client.get(reverse(ROLLUPS), {"level__exact": "county"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [rollup, j25_rollup]


@pytest.fixture
def capped_rollups(monkeypatch: pytest.MonkeyPatch, rollup: Rollup) -> None:
    """Three rollups, a cap of two and one rollup per page."""
    monkeypatch.setattr(CappedCountPaginator, "cap", 2)
    monkeypatch.setattr(RollupAdmin, "list_per_page", 1)
    for code in ("39035", "39041"):
        add_rollup(rollup.release, rollup.state, "county", code)


@pytest.mark.usefixtures("capped_rollups")
def test_rollup_count_stops_at_the_cap(admin_client: Client) -> None:
    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert response.context["cl"].result_count == 2
    assert response.context["cl"].paginator.capped
    assert "More than 2 rollups" in response.text
    assert "More than 2 results" in response.text


@pytest.mark.usefixtures("capped_rollups")
def test_rollup_pages_up_to_the_cap_are_offered(admin_client: Client) -> None:
    response = admin_client.get(reverse(ROLLUPS), {"p": "2"})

    assert response.status_code == 200
    assert [rollup.code for rollup in response.context["cl"].result_list] == ["39041"]


@pytest.mark.usefixtures("capped_rollups")
def test_rollup_pages_beyond_the_cap_are_refused(admin_client: Client) -> None:
    response = admin_client.get(reverse(ROLLUPS), {"p": "3"})

    assert response.status_code == 302
    assert response["Location"].endswith("?e=1")


def test_rollup_count_below_the_cap_is_exact(
    admin_client: Client, rollup: Rollup, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(CappedCountPaginator, "cap", 3)
    monkeypatch.setattr(RollupAdmin, "list_per_page", 1)
    for code in ("39035", "39041"):
        add_rollup(rollup.release, rollup.state, "county", code)

    response = admin_client.get(reverse(ROLLUPS))

    assert response.status_code == 200
    assert response.context["cl"].result_count == 3
    assert not response.context["cl"].paginator.capped
    assert "3 rollups" in response.text
    assert "3 results" in response.text
    assert "More than" not in response.text


@pytest.mark.parametrize(
    ("level", "code"),
    [
        ("county", "39049"),
        ("tract", "39049000110"),
        ("block_group", "390490001101"),
        ("block", "390490001101000"),
        ("h3_res8", "882a91ae3bfffff"),
        ("place", "3918000"),
        ("county_subdivision", "3904918000"),
    ],
)
def test_rollup_search_finds_a_code_at_each_level(
    admin_client: Client, release: Release, state: State, level: str, code: str
) -> None:
    found = add_rollup(release, state, level, code)

    response = admin_client.get(reverse(ROLLUPS), {"q": code})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [found]


def test_rollup_search_finds_the_code_in_every_release(
    admin_client: Client, rollup: Rollup, j25_rollup: Rollup
) -> None:
    add_rollup(rollup.release, rollup.state, "county", "39035")

    response = admin_client.get(reverse(ROLLUPS), {"q": "39049"})

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [rollup, j25_rollup]
    assert response.context["cl"].result_count == 2


def test_rollup_search_within_one_release(
    admin_client: Client, rollup: Rollup, j25_rollup: Rollup
) -> None:
    response = admin_client.get(
        reverse(ROLLUPS), {"q": "39049", "release__id__exact": str(j25_rollup.release_id)}
    )

    assert response.status_code == 200
    assert list(response.context["cl"].result_list) == [j25_rollup]


# The search names each level whose codes have the term's form. Fifteen digits are a block GEOID,
# and also have the form of an H3 cell index (ADR 0024).
@pytest.mark.parametrize(
    ("term", "levels"),
    [
        ("39049", "('county')"),
        ("390490001101000", "('block', 'h3_res8')"),
        ("882a91ae3bfffff", "('h3_res8')"),
    ],
    ids=["county", "block", "cell"],
)
@pytest.mark.usefixtures("rollup")
def test_rollup_search_names_the_levels_of_the_terms_form(
    admin_client: Client, term: str, levels: str
) -> None:
    with CaptureQueriesContext(connection) as queries:
        admin_client.get(reverse(ROLLUPS), {"q": term})

    reads = rollup_queries(queries)
    # The page's count and its rows
    assert len(reads) == 2
    assert all(f'"served_unserved_rollup"."level" IN {levels}' in sql for sql in reads)
