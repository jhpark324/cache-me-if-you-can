"""All user-facing record filters use the same current topic ownership rules."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from second_brain.schemas import EventTime
from second_brain.search import EventFilter
from test_search import create, edit, services


def assign(records, capture, *, parent=(), node=()):
    return records.set_concepts({"request_id": str(uuid4()), "capture_id": capture["id"],
        "expected_revision_id": capture["revision_id"], "expected_state_version": capture["state_version"],
        "concept_ids": list(parent), "node_concepts": [
            {"node_id": capture["nodes"][0]["id"], "concept_ids": list(node)}] if capture["nodes"] else []})["capture"]


def matching_ids(records, search, filters):
    return [
        {item["id"] for item in records.list(**filters)["items"]},
        {item["source"]["capture_id"] for item in search.search({"query": "학습", **filters})["items"]},
        {item["id"] for item in search.home_graph(filters)["nodes"] if item["kind"] == "capture"},
    ]


def test_topic_filters_include_current_node_only_topics_and_keep_kind_intersection(services):
    records, search, _ = services
    topic = records.concept_create({"request_id": str(uuid4()), "name": "학습"})
    other = records.concept_create({"request_id": str(uuid4()), "name": "일상"})
    node_only = assign(records, create(records, "학습의 단계", kinds=["procedure"],
        nodes=[{"kind": "action", "body_start": 0, "body_end": 2}]), node=[topic["id"]])
    parent = assign(records, create(records, "학습의 경험", kinds=["episode"]), parent=[topic["id"]])
    unrelated = assign(records, create(records, "학습 후의 일상", kinds=["procedure"]), parent=[other["id"]])
    search.prepare()
    search.process_jobs()
    assert all(ids == {node_only["id"], parent["id"]}
        for ids in matching_ids(records, search, {"concept_ids": [topic["id"]]}))
    assert all(ids == {node_only["id"]}
        for ids in matching_ids(records, search, {"concept_ids": [topic["id"]], "kinds": ["procedure"]}))
    assert all(ids == {node_only["id"], unrelated["id"]}
        for ids in matching_ids(records, search, {"concept_ids": [topic["id"], other["id"]], "kinds": ["procedure"]}))
    assert records.get(node_only["id"])["concepts"] == []


def test_old_node_topics_do_not_survive_body_edit_as_current_filters(services):
    records, search, _ = services
    topic = records.concept_create({"request_id": str(uuid4()), "name": "학습"})
    capture = assign(records, create(records, "학습 단계", nodes=[
        {"kind": "action", "body_start": 0, "body_end": 2}]), node=[topic["id"]])
    search.prepare()
    search.process_jobs()
    updated = edit(records, capture, "학습에 관해 새로 쓴 본문")
    search.process_jobs()
    assert updated["node_status"] == "stale"
    assert all(ids == set() for ids in matching_ids(records, search, {"concept_ids": [topic["id"]]}))
    historical = records.get(capture["id"], capture["revision_id"])
    assert historical["nodes"][0]["concepts"][0]["id"] == topic["id"]


@pytest.mark.parametrize("value", ["20261102", "2026-W45-1", "2026-11-2", "2026-02-30"])
def test_search_day_filter_rejects_noncanonical_or_invalid_dates(value):
    with pytest.raises(ValidationError):
        EventFilter(start=value)
    with pytest.raises(ValidationError):
        EventFilter(end=value)


@pytest.mark.parametrize("value", ["20261102T12:00:00+09:00", "2026-W45-1T12:00:00+09:00"])
def test_event_instant_requires_calendar_date_prefix(value):
    with pytest.raises(ValidationError):
        EventTime(precision="instant", value=value)


def test_calendar_dates_keep_inclusive_boundaries_and_offset_instant():
    assert EventFilter(start="2026-11-02", end="2026-11-02").end == "2026-11-02"
    assert EventTime(precision="instant", value="2026-11-02T12:00:00+09:00").value.endswith("+09:00")
