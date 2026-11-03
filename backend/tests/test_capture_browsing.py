"""Saved-date browsing applies filters and ordering before cursor pagination."""
import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from second_brain.api import install_error_handlers, router
from second_brain.models import Capture
from second_brain.records import digest
from test_records import assert_error, create, records, update


@pytest.fixture
def client(records):
    app = FastAPI()
    app.state.records = records
    app.include_router(router)
    install_error_handlers(app)
    with TestClient(app) as client:
        yield client


def saved_at(records, instant, **values):
    capture = create(records, **values)
    with records.db.write() as session:
        session.get(Capture, capture["id"]).created_at = instant
    return capture


def ids(page):
    return [item["id"] for item in page["items"]]


def test_local_month_is_half_open_and_filtered_before_pages(records, client):
    saved_at(records, "2026-10-31T14:59:59.999Z", title="학습 이전", kinds=["knowledge"])
    first = saved_at(records, "2026-10-31T15:00:00.000Z", title="학습 시작", kinds=["knowledge"])
    middle = saved_at(records, "2026-11-15T10:00:00.000Z", title="학습 중간", kinds=["knowledge"])
    last = saved_at(records, "2026-11-30T14:59:59.999Z", title="학습 마지막", kinds=["knowledge"])
    saved_at(records, "2026-11-30T15:00:00.000Z", title="학습 다음 달", kinds=["knowledge"])
    saved_at(records, "2026-11-20T00:00:00.000Z", title="학습 경험", kinds=["episode"])
    saved_at(records, "2026-11-21T00:00:00.000Z", title="다른 제목", kinds=["knowledge"])
    params = {"created_from": "2026-11-01T00:00:00+09:00", "created_before": "2026-12-01T00:00:00+09:00",
              "query": "학습", "kinds": "knowledge", "limit": 2}
    response = client.get("/api/v1/captures", params=params)
    assert response.status_code == 200
    page = response.json()["data"]
    assert ids(page) == [last["id"], middle["id"]]
    assert page["items"][0]["created_at"] == "2026-11-30T14:59:59.999Z"
    next_page = client.get("/api/v1/captures", params={**params, "cursor": page["next_cursor"]}).json()["data"]
    assert ids(next_page) == [first["id"]]
    assert next_page["next_cursor"] is None


def test_single_bound_and_fractional_instants_do_not_round_to_milliseconds(records):
    first = saved_at(records, "2026-11-01T00:00:00.000Z")
    last = saved_at(records, "2026-11-01T00:00:00.001Z")
    assert ids(records.list(created_from="2026-11-01T00:00:00.000001Z")) == [last["id"]]
    assert ids(records.list(created_before="2026-11-01T00:00:00.000001Z")) == [first["id"]]


def test_title_sort_is_global_casefolded_and_deterministic_with_missing_titles(records, client):
    beta = create(records, title="Beta")
    untitled = create(records)
    alpha = create(records, title=" alpha ")
    duplicate = create(records, title="ALPHA")
    street = create(records, title="Straße")
    street_upper = create(records, title="STRASSE")
    korean = create(records, title="한글")
    expected = [*sorted([alpha["id"], duplicate["id"]]), beta["id"],
                *sorted([street["id"], street_upper["id"]]), untitled["id"], korean["id"]]
    collected = []
    params = {"sort": "title_asc", "limit": 2}
    while True:
        response = client.get("/api/v1/captures", params=params)
        assert response.status_code == 200
        page = response.json()["data"]
        collected.extend(ids(page))
        if page["next_cursor"] is None:
            break
        params["cursor"] = page["next_cursor"]
    assert collected == expected
    assert len(set(collected)) == len(expected)


@pytest.mark.parametrize("field", ["created_from", "created_before"])
@pytest.mark.parametrize("value", [
    "2026-11-01", "2026-11-01T00:00:00", "20261101T00:00:00Z", "2026-W44-7T00:00:00Z",
    "2026-02-30T00:00:00Z", "2026-11-01T24:00:00Z", "2026-11-01T00:00:00+24:00",
    "2026-11-01T00:00:00+09:60", "2026-11-01T00:00:00+0900", "",
])
def test_invalid_saved_date_boundaries_fail_in_domain_and_http(records, client, field, value):
    assert_error("VALIDATION_ERROR", lambda: records.list(**{field: value}))
    response = client.get("/api/v1/captures", params={field: value})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("value", [False, 20261101, [], {}])
def test_direct_domain_rejects_non_string_boundaries(records, value):
    assert_error("VALIDATION_ERROR", lambda: records.list(created_from=value))


@pytest.mark.parametrize("end", ["2026-11-01T00:00:00Z", "2026-10-31T23:59:59Z"])
def test_empty_or_reversed_ranges_fail_in_domain_and_http(records, client, end):
    params = {"created_from": "2026-11-01T09:00:00+09:00", "created_before": end}
    assert_error("VALIDATION_ERROR", lambda: records.list(**params))
    response = client.get("/api/v1/captures", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("sort", ["updated_desc", "created_asc", "TITLE_ASC", ""])
def test_invalid_sort_fails_in_domain_and_http(records, client, sort):
    assert_error("VALIDATION_ERROR", lambda: records.list(sort=sort))
    response = client.get("/api/v1/captures", params={"sort": sort})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cursor_binds_dates_sort_and_snapshot_but_accepts_equivalent_offsets(records):
    first = saved_at(records, "2026-11-02T00:00:00.000Z", title="Alpha")
    second = saved_at(records, "2026-11-03T00:00:00.000Z", title="Beta")
    outside = saved_at(records, "2026-12-02T00:00:00.000Z", title="Outside")
    filters = {"created_from": "2026-11-01T00:00:00Z", "created_before": "2026-12-01T00:00:00Z", "sort": "title_asc"}
    page = records.list(**filters, limit=1)
    assert ids(page) == [first["id"]]
    cursor = page["next_cursor"]
    equivalent = {**filters, "created_from": "2026-11-01T09:00:00+09:00", "created_before": "2026-12-01T09:00:00+09:00"}
    assert ids(records.list(**equivalent, limit=1, cursor=cursor)) == [second["id"]]
    for changes in [{"created_from": "2026-11-02T00:00:00Z"}, {"created_before": "2026-12-02T00:00:00Z"}, {"sort": "created_desc"}]:
        assert_error("CURSOR_STALE", lambda: records.list(**(filters | changes), limit=1, cursor=cursor))
    # Preserve the existing full-store snapshot even when the changed record
    # falls outside this view's saved-date range.
    update(records, outside, title="Changed outside range")
    assert_error("CURSOR_STALE", lambda: records.list(**filters, limit=1, cursor=cursor))


def test_default_order_and_cursor_fingerprint_remain_compatible(records):
    first = saved_at(records, "2026-11-01T00:00:00.000Z", title="Zebra")
    second = saved_at(records, "2026-11-01T00:00:00.000Z", title="Alpha")
    newest = saved_at(records, "2026-11-02T00:00:00.000Z", title="Beta")
    page = records.list(limit=1)
    assert ids(page) == [newest["id"]]
    cursor = json.loads(base64.urlsafe_b64decode(page["next_cursor"]))
    assert cursor["filter"] == digest({"query": None, "kinds": [], "concept_ids": []})
    assert ids(records.list(sort="created_desc", cursor=page["next_cursor"])) == sorted([first["id"], second["id"]], reverse=True)
    assert_error("CURSOR_STALE", lambda: records.list(sort="title_asc", cursor=page["next_cursor"]))
