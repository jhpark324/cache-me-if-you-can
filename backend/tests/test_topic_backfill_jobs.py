from uuid import uuid4

import pytest
from sqlalchemy import func, select

from cache_me.db import Database
from cache_me.models import (CaptureRevision, ConceptEnrichmentJob, IndexJob,
                             TopicBackfillDecision, TopicBackfillJob)
from cache_me.records import RecordService
from cache_me.schemas import (CreateCaptureInput, CreateConceptInput, DeleteCaptureInput,
                             PrepareDeletionInput, SetConceptsInput, UpdateCaptureInput,
                             UpdateConceptInput)
from cache_me.topic_backfill_jobs import TopicBackfillJobs


@pytest.fixture
def records(tmp_path):
    db = Database(tmp_path / "backfill.sqlite3")
    yield RecordService(db)
    db.close()


def expected(capture):
    return {"capture_id": capture["id"], "expected_revision_id": capture["revision_id"],
            "expected_state_version": capture["state_version"]}


def topic(records, name="주제", **kwargs):
    return records.concept_create(CreateConceptInput(request_id=uuid4(), name=name, **kwargs))


def settle(records, *, concept_ids=(), node_concepts=None, versions=None):
    while job := records.claim_concept_job():
        records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=list(concept_ids),
            node_concepts=node_concepts, candidate_versions=versions or {})


def record(records, body="주제에 대한 원본", **kwargs):
    capture = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown=body, **kwargs))["capture"]
    settle(records)
    return records.get(capture["id"])


def claim(jobs, concept):
    while job := jobs.claim():
        if job["concept"]["id"] == concept["id"]:
            return job
        jobs.finish(job)
    raise AssertionError("expected topic job")


def hits(*captures):
    return [{"source": {"capture_id": c["id"], "revision_id": c["revision_id"],
                        "body_start": 0, "body_end": len(c["body_markdown"])}} for c in captures]


def test_topic_creation_and_actual_definition_changes_enqueue_atomically(records):
    request = CreateConceptInput(request_id=uuid4(), name="초기", aliases=["A", "B"])
    original = records.concept_create(request)
    records.concept_create(request)
    jobs = TopicBackfillJobs(records)
    first = claim(jobs, original)
    assert jobs.reserve_call(first)
    unchanged = records.concept_update(UpdateConceptInput(request_id=uuid4(), concept_id=original["id"],
        expected_state_version=original["state_version"], changes={"name": "초기", "aliases": ["B", "A"]}))
    assert jobs.renew(first)  # Alias order/state_version alone does not change the definition.
    changed = records.concept_update(UpdateConceptInput(request_id=uuid4(), concept_id=original["id"],
        expected_state_version=unchanged["state_version"], changes={"description": "새 범위"}))
    assert not jobs.reserve_call(first)
    current = claim(jobs, changed)
    assert current["definition_hash"] != first["definition_hash"]
    with records.db.read() as session:
        assert session.scalar(select(func.count()).select_from(TopicBackfillJob)) == 2
        assert session.get(TopicBackfillJob, first["job_id"]).status == "superseded"
    capture = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="새 자동 주제"))["capture"]
    normal = records.claim_concept_job()
    records.apply_concept_job(normal["job_id"], normal["lease_token"], concept_ids=[],
        new_concepts=[{"name": "자동 주제", "description": "자동으로 발견한 범위"}])
    automatic = records.get(capture["id"])["concepts"][0]
    assert claim(jobs, automatic)["concept"]["id"] == automatic["id"]


def test_apply_is_additive_preserves_history_nodes_and_source_equivalence(records):
    existing = topic(records, "기존")
    capture = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="원본 내용 보존",
        nodes=[{"kind": "explanation", "body_start": 0, "body_end": 5}]))["capture"]
    settle(records, concept_ids=[existing["id"]],
        node_concepts={capture["nodes"][0]["id"]: [existing["id"]]}, versions={existing["id"]: existing["state_version"]})
    capture = records.get(capture["id"])
    new = topic(records, "추가")
    jobs, job = TopicBackfillJobs(records), None
    job = claim(jobs, new)
    candidates = jobs.prepare_candidates(job, hits(capture, capture))
    assert len(candidates) == 1
    with records.db.read() as session:
        revisions = session.scalar(select(func.count()).select_from(CaptureRevision))
        outbox = session.scalar(select(func.count()).select_from(IndexJob))
        normal_jobs = session.scalar(select(func.count()).select_from(ConceptEnrichmentJob))
        backfill_jobs = session.scalar(select(func.count()).select_from(TopicBackfillJob))
    decision = [{"capture_id": capture["id"], "action": "attach"}]
    assert jobs.apply_decisions(job, candidates, decision)["applied"] == 1
    assert jobs.apply_decisions(job, candidates, decision)["applied"] == 0
    current = records.get(capture["id"])
    assert current["body_markdown"] == capture["body_markdown"]
    assert {c["id"] for c in current["concepts"]} == {existing["id"], new["id"]}
    for key in ("kind", "body_start", "body_end", "text", "concepts"):
        assert current["nodes"][0][key] == capture["nodes"][0][key]
    assert [c["id"] for c in records.get(capture["id"], capture["revision_id"])["concepts"]] == [existing["id"]]
    assert records.source_status(hits(capture)[0]["source"])["review_state"] == "valid"
    assert jobs.finish(job)
    with records.db.read() as session:
        assert session.get(TopicBackfillJob, job["job_id"]).status == "completed"
        assert session.scalar(select(func.count()).select_from(CaptureRevision)) == revisions + 1
        assert session.scalar(select(func.count()).select_from(IndexJob)) == outbox + 1
        assert session.scalar(select(func.count()).select_from(ConceptEnrichmentJob)) == normal_jobs
        assert session.scalar(select(func.count()).select_from(TopicBackfillJob)) == backfill_jobs
        revision = session.get(CaptureRevision, current["revision_id"])
        assert revision.created_via == "system" and revision.change_kind == "concept_enrichment"


def test_prepare_excludes_manual_edits_unfinished_classification_and_invalid_sources(records):
    manual = record(records)
    records.set_concepts(SetConceptsInput(request_id=uuid4(), **expected(manual), concept_ids=[]))
    manual = records.get(manual["id"])
    source = record(records, "출처 원본")
    derived = record(records, sources=[hits(source)[0]["source"]])
    records.update(UpdateCaptureInput(request_id=uuid4(), **expected(source), changes={"body_markdown": "변경된 출처"}))
    settle(records)
    valid = record(records)
    review = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="판단이 모호함"))["capture"]
    normal = records.claim_concept_job()
    records.apply_concept_job(normal["job_id"], normal["lease_token"], concept_ids=[], unresolved_hints=["모호한 주제"])
    failed = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="실패 후 재시도 필요"))["capture"]
    normal = records.claim_concept_job()
    records.fail_concept_job(normal["job_id"], normal["lease_token"], error_code="MODEL_TIMEOUT")
    pending = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="아직 분류 중"))["capture"]
    concept = topic(records)
    jobs = TopicBackfillJobs(records)
    job = claim(jobs, concept)
    selected = jobs.prepare_candidates(job, hits(manual, pending, review, failed, derived, valid))
    assert [item["capture_id"] for item in selected] == [valid["id"]]
    assert records.get(review["id"])["concept_state"]["unresolved_hints"] == ["모호한 주제"]
    assert records.get(failed["id"])["concept_state"]["status"] == "failed"


def test_commit_rechecks_manual_edits_revision_deletion_and_source_validity(records):
    manual, edited, deleted = record(records), record(records), record(records)
    source = record(records, "출처 원본")
    derived = record(records, sources=[hits(source)[0]["source"]])
    concept = topic(records)
    jobs = TopicBackfillJobs(records)
    job = claim(jobs, concept)
    candidates = jobs.prepare_candidates(job, hits(manual, edited, deleted, derived))
    # A different entry point/principal also protects a manual correction.
    scoped = records.scoped(principal_scope="other", session_scope="other", created_via="mcp")
    scoped.set_concepts(SetConceptsInput(request_id=uuid4(), **expected(manual), concept_ids=[]))
    records.update(UpdateCaptureInput(request_id=uuid4(), **expected(edited), changes={"title": "수정"}))
    preview = records.prepare_delete(PrepareDeletionInput(**expected(deleted)))
    records.delete(DeleteCaptureInput(request_id=uuid4(), **expected(deleted), confirmation_token=preview["confirmation_token"]),
                   confirmation=records.confirm_deletion(preview["confirmation_token"]))
    records.update(UpdateCaptureInput(request_id=uuid4(), **expected(source), changes={"body_markdown": "다른 출처"}))
    result = jobs.apply_decisions(job, candidates, [{"capture_id": c["capture_id"], "action": "attach"} for c in candidates])
    assert result["applied"] == 0 and result["skipped"] == 4
    with records.db.read() as session:
        assert session.scalar(select(func.count()).select_from(TopicBackfillDecision)) == 0


def test_rejection_cache_uses_content_not_metadata_revision(records):
    capture = record(records)
    unresolved = record(records, "이번에는 판단을 보류할 후보")
    concept = topic(records)
    jobs = TopicBackfillJobs(records)
    job = claim(jobs, concept)
    candidates = jobs.prepare_candidates(job, hits(capture, unresolved))
    assert jobs.apply_decisions(job, candidates, [{"capture_id": capture["id"], "action": "reject"}])["rejected"] == 1
    changed = records.update(UpdateCaptureInput(request_id=uuid4(), **expected(capture), changes={"visibility": "private"}))["capture"]
    assert jobs.prepare_candidates(job, hits(changed)) == []
    changed = records.update(UpdateCaptureInput(request_id=uuid4(), **expected(changed), changes={"body_markdown": "주제와 관련된 새 내용"}))["capture"]
    settle(records)
    changed = records.get(changed["id"])
    candidates = jobs.prepare_candidates(job, hits(changed))
    assert len(candidates) == 1
    jobs.apply_decisions(job, candidates, [{"capture_id": changed["id"], "action": "reject"}])
    assert jobs.defer(job, error_code="CANDIDATES_NOT_READY", delay_seconds=0)
    retried = claim(jobs, concept)
    # The fresh search no longer returns the unresolved record from attempt one.
    assert jobs.prepare_candidates(retried, hits(changed)) == []
    assert jobs.finish(retried, status="completed")
    with records.db.read() as session:
        stored = session.get(TopicBackfillJob, job["job_id"])
        assert stored.status == "partial" and stored.error_code == "INCOMPLETE_DECISIONS"


def test_restart_lease_and_call_budget_are_durable_and_candidates_stay_bounded(records):
    captures = [record(records, f"기록 {i}") for i in range(21)]
    concept = topic(records)
    jobs = TopicBackfillJobs(records)
    first = claim(jobs, concept)
    candidates = jobs.prepare_candidates(first, hits(*captures))
    assert len(candidates) == 20
    assert jobs.reserve_call(first)
    with records.db.write() as session:
        session.get(TopicBackfillJob, first["job_id"]).lease_until = "2000-01-01T00:00:00.000Z"
    restarted = TopicBackfillJobs(RecordService(records.db))
    second = claim(restarted, concept)
    assert second["attempt_count"] == 2 and second["call_count"] == 1
    assert not jobs.reserve_call(first)
    assert restarted.prepare_candidates(second, hits(captures[-1])) == []
    assert all(restarted.reserve_call(second) for _ in range(3))
    assert not restarted.reserve_call(second)
    assert restarted.defer(second, error_code="MODEL_TIMEOUT", delay_seconds=0)
    assert restarted.claim() is None
    with records.db.read() as session:
        stored = session.get(TopicBackfillJob, second["job_id"])
        assert stored.call_count == 4 and stored.status == "partial"
