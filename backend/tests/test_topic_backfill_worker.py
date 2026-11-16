"""Offline checks for the incremental worker's cost and retrieval boundaries."""
import asyncio
from uuid import uuid4

from sqlalchemy import select, update

from cache_me.models import ConceptEnrichmentJob, TopicBackfillJob
from cache_me.topic_backfill import TopicBackfill, record_context
from test_operations import create, records
from test_search import services
from test_topic_classification import ScriptedModel


def ready_records(records, count=1, body="캐시 만료와 재시도 정책"):
    captures = [create(records, body, title=f"기록 {index}") for index in range(count)]
    # Simulate previously completed ordinary classification without model calls.
    with records.db.write() as session:
        session.execute(update(ConceptEnrichmentJob).values(status="completed"))
    return captures


def topic(records, **values):
    return records.concept_create({"request_id": str(uuid4()), "name": "캐시 만료",
                                   "description": "캐시 유효기간과 갱신 정책", **values})


class BodySearch:
    ready, complete = True, True

    def __init__(self, captures):
        self.captures = captures

    def status(self):
        return {"ready": self.ready}

    def backfill_candidates(self, concept, limit=20):
        return {"hits": [{"source": {"capture_id": item["id"], "revision_id": item["revision_id"]}}
                         for item in self.captures[:limit]], "complete": self.complete}


def job_state(records):
    with records.db.read() as session:
        job = session.scalar(select(TopicBackfillJob))
        return job.status, job.call_count, job.attempt_count


def test_worker_limits_batches_and_preserves_original_records(records):
    captures = ready_records(records, 23)
    concept = topic(records)
    model = ScriptedModel(lambda value: {"decisions": [
        {"capture_id": item["capture_id"], "action": "attach"} for item in value["records"]]})
    asyncio.run(TopicBackfill(records, model, BodySearch(captures)).process_one())

    assert job_state(records) == ("completed", 4, 1)
    assert [len(item["records"]) for item in model.inputs] == [5, 5, 5, 5]
    for index, original in enumerate(captures):
        current = records.get(original["id"])
        for key in ("body_markdown", "title", "event_time", "kinds", "completion_state", "visibility"):
            assert current[key] == original[key]
        assert [item["id"] for item in current["concepts"]] == ([concept["id"]] if index < 20 else [])


def test_invalid_model_ids_never_apply_and_spent_call_survives_retry(records):
    captures = ready_records(records)
    topic(records)
    model = ScriptedModel(lambda value: {"decisions": [{"capture_id": str(uuid4()), "action": "attach"}]})
    worker = TopicBackfill(records, model, BodySearch(captures))
    asyncio.run(worker.process_one())
    assert job_state(records) == ("pending", 1, 1)
    assert records.get(captures[0]["id"])["concepts"] == []

    with records.db.write() as session:
        session.scalar(select(TopicBackfillJob)).available_at = "2000-01-01T00:00:00.000Z"
    model.respond = lambda value: {"decisions": [
        {"capture_id": item["capture_id"], "action": "reject"} for item in value["records"]]}
    asyncio.run(worker.process_one())
    assert job_state(records) == ("completed", 2, 2)


def test_unready_search_waits_and_uncertainty_finishes_partial(records):
    captures = ready_records(records)
    topic(records)
    search = BodySearch(captures)
    search.ready = False
    model = ScriptedModel(lambda value: {"decisions": [
        {"capture_id": item["capture_id"], "action": "defer"} for item in value["records"]]})
    worker = TopicBackfill(records, model, search)
    asyncio.run(worker.process_one())
    assert job_state(records) == ("pending", 0, 0)
    search.ready = True
    asyncio.run(worker.process_one())
    assert job_state(records) == ("partial", 1, 1)
    assert records.get(captures[0]["id"])["concepts"] == []


def test_body_retrieval_uses_bounded_queries_and_reports_pending_index(services, monkeypatch):
    records, search, embedding = services
    captures = ready_records(records)
    search.prepare()
    search.process_jobs()
    concept = topic(records, description="캐시 갱신 " * 100, aliases=["cache expiration"])
    monkeypatch.setattr(search, "_topic_candidates", lambda *args: (_ for _ in ()).throw(AssertionError("topic path")))
    result = search.backfill_candidates(concept)
    assert result["complete"] is True
    assert result["hits"][0]["source"]["capture_id"] == captures[0]["id"]
    ready_records(records, body="아직 색인 중인 기록")
    assert search.backfill_candidates(concept)["complete"] is False

    context = record_context({"capture_id": "test", "body_markdown": "x" * 20_000,
                              "source": {"body_start": 18_000}})
    assert sum(len(item["text"]) for item in context["excerpts"]) <= 4_000
    assert context["complete_body"] is False
    assert any(item["body_start"] <= 18_000 < item["body_end"] for item in context["excerpts"])
