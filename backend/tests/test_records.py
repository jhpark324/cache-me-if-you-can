from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from cache_me.api import install_error_handlers, router
from cache_me.db import Database
from cache_me.models import (Capture, CaptureRevision, Concept, ConceptEnrichmentJob,
                                 IndexJob, KnowledgeNode, MutationReceipt, ProvenanceLink)
from cache_me.records import DomainError, RecordService
from cache_me.schemas import (CreateCaptureInput, CreateConceptInput, DeleteCaptureInput,
                                 MergeCapturesInput, PrepareDeletionInput, RelationInput, RetractRelationInput,
                                 ReviewSourcesInput, RetryConceptsInput, SetConceptsInput, SourceRef, UpdateCaptureInput)


@pytest.fixture
def records(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    yield RecordService(db)
    db.close()


def create(records, body="원본 지식", **kwargs):
    return records.create(CreateCaptureInput(request_id=uuid4(), body_markdown=body, **kwargs))["capture"]


def expected(capture):
    return {"capture_id": capture["id"], "expected_revision_id": capture["revision_id"], "expected_state_version": capture["state_version"]}


def ref(capture, **kwargs):
    return SourceRef(capture_id=capture["id"], revision_id=capture["revision_id"], **kwargs)


def update(records, capture, **changes):
    return records.update(UpdateCaptureInput(request_id=uuid4(), **expected(capture), changes=changes))["capture"]


def deletion(records, capture):
    preview = records.prepare_delete(PrepareDeletionInput(**expected(capture)))
    data = DeleteCaptureInput(request_id=uuid4(), **expected(capture), confirmation_token=preview["confirmation_token"])
    return data, records.confirm_deletion(preview["confirmation_token"])


def assert_error(code, operation):
    with pytest.raises(DomainError) as error:
        operation()
    assert error.value.code == code


def test_minimal_create_is_atomic_and_returns_persisted_body(records):
    body = "# 지식\r\n한글 🧠 e\u0301\n  "
    capture = create(records, body)
    assert capture["body_markdown"] == body
    assert capture["kinds"] == []
    assert capture["visibility"] == "public"
    assert capture["completion_state"] is None
    assert capture["concept_state"]["status"] == "pending"
    assert capture["index_state"]["status"] == "pending"
    with records.db.read() as session:
        for model in (Capture, CaptureRevision, MutationReceipt, IndexJob, ConceptEnrichmentJob):
            assert session.scalar(select(func.count()).select_from(model)) == 1


def test_idempotency_replay_and_fingerprint_conflict(records):
    data = CreateCaptureInput(request_id=uuid4(), body_markdown="저장본")
    first = records.create(data)
    again = records.create(data)
    assert again["replayed"] is True
    assert first["capture"]["id"] == again["capture"]["id"]
    assert_error("IDEMPOTENCY_CONFLICT", lambda: records.create(data.model_copy(update={"body_markdown": "다른 본문"})))
    distinct = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="저장본"))
    assert distinct["capture"]["id"] != first["capture"]["id"]


def test_patch_omission_null_and_visibility_only(records):
    capture = create(records, title="제목", visibility="private", kinds=["knowledge"])
    current = update(records, capture, title=None, kinds=[])
    assert current["title"] is None and current["kinds"] == [] and current["visibility"] == "private"
    public = update(records, current, visibility="public")
    assert public["revision_id"] == current["revision_id"]
    assert public["state_version"] == current["state_version"] + 1
    assert records.get(capture["id"], capture["revision_id"])["title"] == "제목"
    assert_error("VERSION_CONFLICT", lambda: update(records, capture, title="오래된 변경"))


def test_unicode_codepoint_node_source_and_stale_transition(records):
    capture = create(records, "가🧠나 e\u0301", nodes=[{"kind": "explanation", "body_start": 1, "body_end": 2}])
    node = capture["nodes"][0]
    assert node["text"] == "🧠"
    assert records.source_get(node["source"])["text"] == "🧠"
    changed = update(records, capture, body_markdown="새로운 본문")
    assert changed["nodes"] == [] and changed["node_status"] == "stale"
    assert_error("NOT_FOUND", lambda: records.node_get(node["id"]))
    assert records.source_get(node["source"])["text"] == "🧠"
    assert not records.source_get(node["source"])["is_current"]
    metadata = update(records, changed, title="제목")
    assert metadata["node_status"] == "stale"
    cleared = update(records, metadata, nodes=[])
    assert cleared["node_status"] == "absent"


def test_invalid_span_rolls_back_everything(records):
    capture = create(records, "123", nodes=[{"kind": "explanation", "body_start": 0, "body_end": 3}])
    with records.db.read() as session:
        count = session.scalar(select(func.count()).select_from(CaptureRevision))
    assert_error("VALIDATION_ERROR", lambda: update(records, capture, nodes=[{"kind": "question", "body_start": 0, "body_end": 4}]))
    with records.db.read() as session:
        assert session.scalar(select(func.count()).select_from(CaptureRevision)) == count
    assert records.get(capture["id"])["state_version"] == capture["state_version"]


def test_immutable_revisions_and_node_bounds_are_database_guards(records):
    capture = create(records)
    with pytest.raises(IntegrityError):
        with records.db.write() as session:
            session.execute(text("UPDATE capture_revisions SET body_markdown='altered' WHERE id=:id"), {"id": capture["revision_id"]})
    assert records.get(capture["id"])["body_markdown"] == "원본 지식"


def test_concurrent_writes_do_not_overwrite(records):
    capture = create(records)
    def write(title):
        try:
            return update(records, capture, title=title)["title"]
        except DomainError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(write, ["first", "second"]))
    assert results.count("VERSION_CONFLICT") == 1
    assert records.get(capture["id"])["revision_no"] == 2


def test_metadata_equivalence_remaps_node_without_changing_stored_ref(records):
    source = create(records, "근거 본문", nodes=[{"kind": "explanation", "body_start": 0, "body_end": 2}])
    stored = source["nodes"][0]["source"]
    derived = create(records, "파생", sources=[stored])
    changed = update(records, source, kinds=["knowledge"])
    status = records.get(derived["id"])["sources"][0]
    assert status["source"] == stored
    assert status["resolved_source"]["revision_id"] == changed["revision_id"]
    assert status["resolved_source"]["node_id"] == changed["nodes"][0]["id"]
    assert status["review_state"] == "valid"
    assert_error("NOT_FOUND", lambda: records.node_get(stored["node_id"]))


def test_upstream_change_and_patch_cannot_clear_dependencies(records):
    source = create(records)
    derived = create(records, "파생", sources=[ref(source)])
    grandchild = create(records, "파생의 파생", sources=[ref(derived)])
    update(records, source, body_markdown="변경된 근거")
    assert records.get(derived["id"])["sources"][0]["reason"] == "source_changed"
    assert records.get(grandchild["id"])["sources"][0]["reason"] == "upstream_invalid"
    modified = update(records, derived, title="다시 정리", sources=[])
    assert len(modified["sources"]) == 1
    assert modified["review_state"] == "needs_review"
    assert_error("SOURCE_REVIEW_REQUIRED", lambda: records.eligible_capture(derived["id"]))


def test_source_review_rewrite_and_history(records):
    source = create(records)
    derived = create(records, "파생", sources=[ref(source)])
    bad = ReviewSourcesInput(request_id=uuid4(), **expected(derived), replacement_sources=[], review_reason="출처 제거")
    assert_error("SOURCE_REVIEW_REQUIRED", lambda: records.review_sources(bad))
    good = bad.model_copy(update={"request_id": uuid4(), "body_markdown": "새로 확인한 독립 내용"})
    revised = records.review_sources(good)["capture"]
    assert revised["review_state"] == "valid" and revised["sources"] == []
    assert len(records.get(derived["id"], derived["revision_id"])["sources"]) == 1
    assert records.get(derived["id"], derived["revision_id"])["body_markdown"] == "파생"


def test_provenance_cycle_and_cross_brain_are_rejected(records, tmp_path):
    original = create(records)
    derived = create(records, "파생", sources=[ref(original)])
    assert_error("SOURCE_CYCLE", lambda: update(records, original, sources=[ref(derived).model_dump(mode="json")]))
    another = RecordService(Database(records.db.path, brain_id=str(uuid4())))
    try:
        assert_error("NOT_FOUND", lambda: another.get(original["id"]))
        assert_error("INVALID_SOURCE_REF", lambda: create(another, sources=[ref(original)]))
    finally:
        another.db.close()


def test_delete_requires_internal_confirmation_and_bound_session(records):
    capture = create(records)
    data, confirmation = deletion(records, capture)
    assert_error("CONFIRMATION_REQUIRED", lambda: records.delete(data))
    foreign = records.scoped(principal_scope="local", session_scope="other")
    assert_error("CONFIRMATION_REQUIRED", lambda: foreign.delete(data, confirmation=confirmation))
    assert records.get(capture["id"])["deleted_at"] is None
    result = records.delete(data, confirmation=confirmation)
    assert result["deleted_at"] and result["index_state"]["status"] == "excluded"
    assert records.delete(data)["replayed"] is True


def test_delete_hides_body_history_nodes_sources_and_receipt(records):
    request = CreateCaptureInput(request_id=uuid4(), body_markdown="민감한 비밀", nodes=[{"kind": "event", "body_start": 0, "body_end": 3}])
    capture = records.create(request)["capture"]
    source = capture["nodes"][0]["source"]
    derived = create(records, "파생 기록", sources=[source])
    data, confirmation = deletion(records, capture)
    records.delete(data, confirmation=confirmation)
    for operation in (lambda: records.get(capture["id"]), lambda: records.get(capture["id"], capture["revision_id"]), lambda: records.node_get(source["node_id"]), lambda: records.source_get(source), lambda: update(records, capture, title="다시")):
        assert_error("NOT_FOUND", operation)
    assert [item["id"] for item in records.list()["items"]] == [derived["id"]]
    replay = records.create(request)
    assert replay["result_state"] == "unavailable" and replay["capture"] is None
    dependent = records.get(derived["id"])
    assert dependent["sources"][0]["availability"] == "unavailable"
    assert "민감한 비밀" not in str(dependent)
    with records.db.read() as session:
        assert session.get(CaptureRevision, capture["revision_id"]).body_markdown == "민감한 비밀"
        assert session.scalar(select(func.count()).select_from(KnowledgeNode)) == 1
        assert session.scalar(select(func.count()).select_from(ProvenanceLink)) == 1


def test_delete_stale_token_and_expiry_do_not_mutate(records):
    capture = create(records)
    data, confirmation = deletion(records, capture)
    update(records, capture, title="새 제목")
    assert_error("VERSION_CONFLICT", lambda: records.delete(data, confirmation=confirmation))
    assert records.get(capture["id"])["deleted_at"] is None


def test_concepts_same_names_remain_distinct_and_manual_assignment(records):
    a = records.concept_create(CreateConceptInput(request_id=uuid4(), name="시스템", aliases=["system"]))
    b = records.concept_create(CreateConceptInput(request_id=uuid4(), name="시스템"))
    assert a["id"] != b["id"]
    assert len(records.concept_list(query="시스템")["items"]) == 2
    capture = create(records, nodes=[{"kind": "explanation", "body_start": 0, "body_end": 2}])
    corrected = records.set_concepts(SetConceptsInput(request_id=uuid4(), **expected(capture), concept_ids=[a["id"]], node_concepts=[{"node_id": capture["nodes"][0]["id"], "concept_ids": [b["id"]]}]))["capture"]
    assert corrected["concepts"][0]["id"] == a["id"]
    assert corrected["nodes"][0]["concepts"][0]["id"] == b["id"]
    assert corrected["concept_state"]["status"] == "ready"


def test_concept_worker_applies_atomically_no_recursion(records):
    capture = create(records, concept_hints=["트랜잭션"])
    job = records.claim_concept_job()
    result = records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[],
        new_concepts=[{"name": "트랜잭션"}], unresolved_hints=["불확실한 후보"])
    current = records.get(capture["id"])
    assert result["changed"] and current["revision_no"] == 2
    assert current["body_markdown"] == capture["body_markdown"]
    assert current["concept_state"]["status"] == "ready"
    assert current["concept_state"]["unresolved_hints"] == []
    assert result["status"] == "completed"
    with records.db.read() as session:
        saved_job = session.get(ConceptEnrichmentJob, job["job_id"])
        assert saved_job.status == "completed"
        assert saved_job.unresolved_hints == ["불확실한 후보"]
    assert current["concepts"][0]["name"] == "트랜잭션"
    assert records.claim_concept_job() is None
    again = records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[])
    assert again["applied_revision_id"] == current["revision_id"]
    assert records.get(capture["id"])["revision_no"] == 2


def test_concept_worker_noop_and_model_failure_preserve_body(records):
    capture = create(records)
    job = records.claim_concept_job()
    result = records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[])
    assert not result["changed"] and records.get(capture["id"])["revision_no"] == 1
    updated = update(records, capture, body_markdown="변경 본문")
    job = records.claim_concept_job()
    records.fail_concept_job(job["job_id"], job["lease_token"], error_code="AUTH_REQUIRED")
    current = records.get(capture["id"])
    assert current["body_markdown"] == "변경 본문" and current["concept_state"]["status"] == "failed"
    assert records.claim_concept_job() is None


@pytest.mark.parametrize("error_code", ["MODEL_TIMEOUT", "AUTH_REQUIRED"])
def test_visibility_change_keeps_failed_classification_retryable(records, error_code):
    capture = create(records)
    job = records.claim_concept_job()
    records.fail_concept_job(job["job_id"], job["lease_token"], error_code=error_code)

    changed = update(records, capture, visibility="private")
    assert changed["revision_id"] == capture["revision_id"]
    assert changed["concept_state"]["status"] == "failed"
    assert changed["concept_state"]["error_code"] == error_code
    assert changed["concept_state"]["job_id"] == job["job_id"]
    with records.db.write() as session:
        failed = session.get(ConceptEnrichmentJob, job["job_id"])
        assert failed.expected_state_version == changed["state_version"]
        assert failed.attempt_count == 1 and failed.status == "failed"
        failed.available_at = "2000-01-01T00:00:00.000Z"

    if error_code == "AUTH_REQUIRED":
        assert records.claim_concept_job() is None
        assert records.get(capture["id"])["concept_state"]["status"] == "failed"
        retried = records.retry_concepts(RetryConceptsInput(request_id=uuid4(),
            **expected(changed), job_id=job["job_id"]))["capture"]
        assert retried["concept_state"]["status"] == "pending"
    attempt = records.claim_concept_job()
    assert attempt["job_id"] == job["job_id"]
    assert attempt["attempt_count"] == (1 if error_code == "AUTH_REQUIRED" else 2)
    applied = records.apply_concept_job(attempt["job_id"], attempt["lease_token"], concept_ids=[])
    assert applied["applied"] is True
    current = records.get(capture["id"])
    assert current["concept_state"]["status"] == "ready"
    assert current["revision_id"] == capture["revision_id"]
    assert current["body_markdown"] == capture["body_markdown"]


def test_late_concept_worker_does_not_overwrite_manual_assignment_or_delete(records):
    capture = create(records)
    job = records.claim_concept_job()
    corrected = records.set_concepts(SetConceptsInput(request_id=uuid4(), **expected(capture), concept_ids=[]))["capture"]
    assert records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[], new_concepts=[{"name": "늦은 주제"}])["applied"] is False
    assert records.concept_list()["items"] == []
    assert records.get(capture["id"])["revision_id"] == corrected["revision_id"]
    later = update(records, corrected, body_markdown="다시 수정")
    job = records.claim_concept_job()
    data, confirmation = deletion(records, later)
    records.delete(data, confirmation=confirmation)
    assert records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[], new_concepts=[{"name": "삭제 뒤 주제"}])["applied"] is False
    assert records.concept_list()["items"] == []


def test_ambiguous_concept_is_not_automatically_merged(records):
    records.concept_create(CreateConceptInput(request_id=uuid4(), name="동일"))
    capture = create(records, concept_hints=["동일"])
    job = records.claim_concept_job()
    assert_error("VERSION_CONFLICT", lambda: records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[], new_concepts=[{"name": "동일"}]))
    records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[], unresolved_hints=["동일"])
    current = records.get(capture["id"])
    assert current["concept_state"]["status"] == "ready"
    assert current["concept_state"]["unresolved_hints"] == []
    assert current["revision_id"] == capture["revision_id"]
    assert records.claim_concept_job() is None
    with records.db.read() as session:
        assert session.get(ConceptEnrichmentJob, job["job_id"]).unresolved_hints == ["동일"]
    assert len(records.concept_list()["items"]) == 1


def test_legacy_deferred_classification_is_ready_without_rewriting_history(records):
    capture = create(records)
    job = records.claim_concept_job()
    records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[],
        new_concepts=[{"name": "확정한 주제"}], unresolved_hints=["이전 보류 후보"])
    current = records.get(capture["id"])
    with records.db.write() as session:
        session.get(ConceptEnrichmentJob, job["job_id"]).status = "needs_review"
    with records.db.read() as session:
        revision_count = session.scalar(select(func.count()).select_from(CaptureRevision))
        index_count = session.scalar(select(func.count()).select_from(IndexJob))

    view = records.get(capture["id"])
    listed = records.list()["items"][0]
    assert view["concept_state"]["status"] == listed["concept_state"]["status"] == "ready"
    assert view["concept_state"]["unresolved_hints"] == listed["concept_state"]["unresolved_hints"] == []
    assert view["revision_id"] == current["revision_id"]
    assert view["state_version"] == current["state_version"]
    assert view["body_markdown"] == capture["body_markdown"]
    assert view["concepts"] == current["concepts"]
    replayed = records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[])
    assert replayed["status"] == "completed"
    with records.db.read() as session:
        saved_job = session.get(ConceptEnrichmentJob, job["job_id"])
        assert saved_job.status == "needs_review"
        assert saved_job.unresolved_hints == ["이전 보류 후보"]
        assert session.scalar(select(func.count()).select_from(CaptureRevision)) == revision_count
        assert session.scalar(select(func.count()).select_from(IndexJob)) == index_count


@pytest.mark.parametrize("stored, proposed", [
    (" Cache   Me ", "cache me"),
    ("학습", "학습"),
    ("Café", "Cafe\u0301"),
])
def test_concept_lookup_normalizes_comparison_without_rewriting_or_merging(records, stored, proposed):
    existing = records.concept_create(CreateConceptInput(request_id=uuid4(), name=stored))
    assert records.concept_list(query=proposed)["items"][0]["id"] == existing["id"]
    assert records.concept_get(existing["id"])["name"] == stored
    capture = create(records, concept_hints=[proposed])
    job = records.claim_concept_job()
    assert_error("VERSION_CONFLICT", lambda: records.apply_concept_job(job["job_id"], job["lease_token"],
        concept_ids=[], new_concepts=[{"name": proposed}]))
    assert records.get(capture["id"])["revision_no"] == 1
    assert len(records.concept_list()["items"]) == 1
    # Explicit distinct senses remain allowed; comparison normalization is not
    # an identity constraint or permission to merge user-created concepts.
    separate = records.concept_create(CreateConceptInput(request_id=uuid4(), name=proposed, description="다른 의미"))
    assert separate["id"] != existing["id"]
    assert len(records.concept_list(query=proposed)["items"]) == 2


def test_concept_aliases_share_normalized_lookup_and_auto_collision_check(records):
    existing = records.concept_create(CreateConceptInput(request_id=uuid4(), name="능동 회상", aliases=["Active  Recall"]))
    assert records.concept_list(query=" active recall ")["items"][0]["id"] == existing["id"]
    create(records)
    job = records.claim_concept_job()
    assert_error("VERSION_CONFLICT", lambda: records.apply_concept_job(job["job_id"], job["lease_token"],
        concept_ids=[], new_concepts=[{"name": "기억 연습", "aliases": ["active recall"]}]))
    assert records.concept_get(existing["id"])["aliases"] == ["Active  Recall"]


@pytest.mark.parametrize("changed_endpoint", ["source", "target", "evidence"])
def test_stale_but_accessible_relation_can_be_explicitly_retracted(records, changed_endpoint):
    captures = {field: create(records, field + " 근거") for field in ("source", "target", "evidence")}
    relation = records.relation_create(RelationInput(request_id=uuid4(), relation_type="supports",
        **{field: ref(capture) for field, capture in captures.items()}))
    update(records, captures[changed_endpoint], body_markdown="다시 확인한 내용")
    assert records.relation_list(capture_id=captures["source"]["id"])["items"] == []
    assert_error("NOT_FOUND", lambda: records.current_relation(relation["id"]))
    command = RetractRelationInput(request_id=uuid4(), relation_id=relation["id"], withdrawal_reason="기존 근거가 변경됨")
    result = records.relation_retract(command)
    assert result["withdrawn_at"] and result["withdrawal_reason"] == "기존 근거가 변경됨"
    assert records.relation_retract(command)["replayed"] is True
    # Retraction does not turn the old relation into usable current evidence.
    assert_error("NOT_FOUND", lambda: records.current_relation(relation["id"]))


def test_relation_with_deleted_parent_cannot_be_retracted_or_replayed(records):
    a, b = create(records, "A"), create(records, "B")
    relation = records.relation_create(RelationInput(request_id=uuid4(), relation_type="supports",
        source=ref(a), target=ref(b), evidence=ref(a)))
    command = RetractRelationInput(request_id=uuid4(), relation_id=relation["id"], withdrawal_reason="정정")
    records.relation_retract(command)
    data, confirmation = deletion(records, a)
    records.delete(data, confirmation=confirmation)
    assert_error("NOT_FOUND", lambda: records.relation_retract(command))
    assert_error("NOT_FOUND", lambda: records.relation_retract(command.model_copy(update={"request_id": uuid4()})))


def test_relation_retraction_is_idempotent_and_does_not_change_capture(records):
    a, b = create(records, "A 근거"), create(records, "B 근거")
    relation = records.relation_create(RelationInput(request_id=uuid4(), relation_type="supports", source=ref(a), target=ref(b), evidence=ref(a)))
    assert len(records.relation_list(capture_id=a["id"])["items"]) == 1
    data = RetractRelationInput(request_id=uuid4(), relation_id=relation["id"], withdrawal_reason="근거 해석 정정")
    first = records.relation_retract(data)
    assert records.relation_retract(data)["replayed"]
    assert records.relation_list(capture_id=a["id"])["items"] == []
    assert_error("RELATION_ALREADY_WITHDRAWN", lambda: records.relation_retract(data.model_copy(update={"request_id": uuid4(), "withdrawal_reason": "덮어쓰기"})))
    assert first["withdrawal_reason"] == "근거 해석 정정"
    assert records.get(a["id"])["revision_id"] == a["revision_id"]


def test_supersedes_requires_scoped_evidence_and_rejects_cycle(records):
    a, b = create(records, "예전 조건"), create(records, "새 조건")
    assert_error("INVALID_RELATION_SCOPE", lambda: records.relation_create(RelationInput(request_id=uuid4(), relation_type="supersedes", source=ref(b), target=ref(a), evidence=ref(b))))
    args = {"relation_type": "supersedes", "scope_note": "사용자 작업 선호", "evidence_note": "명시적으로 선호를 변경함"}
    records.relation_create(RelationInput(request_id=uuid4(), source=ref(b, body_start=0, body_end=2), target=ref(a, body_start=0, body_end=2), evidence=ref(b, body_start=0, body_end=2), **args))
    assert_error("SOURCE_CYCLE", lambda: records.relation_create(RelationInput(request_id=uuid4(), source=ref(a, body_start=0, body_end=2), target=ref(b, body_start=0, body_end=2), evidence=ref(a, body_start=0, body_end=2), **args)))


def test_list_cursor_binds_filters_and_current_state(records):
    a, b = create(records, "첫 기록"), create(records, "둘째 기록")
    page = records.list(limit=1)
    assert page["next_cursor"]
    assert len(records.list(limit=1, cursor=page["next_cursor"])["items"]) == 1
    assert_error("CURSOR_STALE", lambda: records.list(query="기록", limit=1, cursor=page["next_cursor"]))
    update(records, a, title="변경")
    assert_error("CURSOR_STALE", lambda: records.list(limit=1, cursor=page["next_cursor"]))


@pytest.mark.parametrize("payload", [
    {"body_markdown": "  "}, {"body_markdown": "x" * 100001}, {"body_markdown": "ok", "deleted_at": None},
    {"body_markdown": "ok", "kinds": ["unknown"]}, {"body_markdown": "ok", "concept_hints": [" "]},
    {"body_markdown": "ok", "nodes": [{"kind": "event", "body_start": True, "body_end": 2}]},
    {"body_markdown": "ok", "nodes": [{"kind": "event", "body_start": 0, "body_end": 2, "verification_state": "verified"}]},
])
def test_strict_capture_validation(payload):
    with pytest.raises(ValidationError):
        CreateCaptureInput(request_id=uuid4(), **payload)


def test_http_adapter_envelope_validation_and_no_confirmation_bypass(records):
    app = FastAPI()
    app.state.records = records
    app.include_router(router)
    install_error_handlers(app)
    with TestClient(app) as client:
        response = client.post("/api/v1/captures", json={"request_id": str(uuid4()), "body_markdown": "저장한 내용"})
        assert response.status_code == 200
        envelope = response.json()
        assert envelope["schema_version"] == 1 and envelope["ok"]
        capture = envelope["data"]["capture"]
        malformed = client.post("/api/v1/captures", json={"request_id": str(uuid4()), "body_markdown": "secret", "deleted_at": "secret"})
        assert malformed.status_code == 422 and "secret" not in malformed.text
        preview = client.post(f"/api/v1/captures/{capture['id']}/deletion-preview", json=expected(capture)).json()["data"]
        payload = {"request_id": str(uuid4()), **expected(capture), "confirmation_token": preview["confirmation_token"]}
        result = client.post(f"/api/v1/captures/{capture['id']}/deletion", json=payload)
        assert result.status_code == 403
        bypass = client.post(f"/api/v1/captures/{capture['id']}/deletion", json=payload | {"confirmed": True})
        assert bypass.status_code == 422
        assert records.get(capture["id"])


def test_merge_keeps_sources_and_originals(records):
    a, b = create(records, "원문 A"), create(records, "원문 B")
    merged = records.merge(MergeCapturesInput(request_id=uuid4(), target_capture_id=a["id"], expected_revision_id=a["revision_id"], expected_state_version=a["state_version"], sources=[ref(b)], merged_body_markdown="A와 B의 정리"))["capture"]
    assert merged["id"] == a["id"] and merged["revision_no"] == 2
    assert merged["sources"][0]["source"]["capture_id"] == b["id"]
    assert records.get(b["id"])["revision_id"] == b["revision_id"]
    assert records.get(a["id"], a["revision_id"])["body_markdown"] == "원문 A"


def test_deleted_relation_endpoint_cannot_leak_through_replay(records):
    a, b = create(records, "A"), create(records, "B")
    request = RelationInput(request_id=uuid4(), relation_type="supports", source=ref(a), target=ref(b), evidence=ref(a), evidence_note="비공개 근거 설명")
    records.relation_create(request)
    data, proof = deletion(records, a)
    records.delete(data, confirmation=proof)
    assert records.relation_list(capture_id=b["id"])["items"] == []
    assert_error("NOT_FOUND", lambda: records.relation_create(request))


def test_deletion_token_expiry_is_enforced(records):
    from cache_me.models import DeletionConfirmation
    capture = create(records)
    data, proof = deletion(records, capture)
    with records.db.write() as session:
        session.get(DeletionConfirmation, proof.token_hash).expires_at = "2000-01-01T00:00:00.000Z"
    assert_error("CONFIRMATION_EXPIRED", lambda: records.delete(data, confirmation=proof))
    assert records.get(capture["id"])["deleted_at"] is None


def test_alembic_baseline_applies_idempotently(tmp_path):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    database_path = tmp_path / "migrated.sqlite3"
    config.set_main_option("sqlalchemy.url", "sqlite:///" + str(database_path))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    database = Database(database_path, initialize=False)
    try:
        service = RecordService(database)
        capture = create(service)
        assert service.get(capture["id"])["body_markdown"] == "원본 지식"
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0002"
    finally:
        database.close()


def test_migration_helper_adopts_only_matching_unversioned_schema(tmp_path):
    import runpy
    import sqlite3
    from pathlib import Path
    from cache_me.db import migrate_database
    # Adoption recognizes the frozen historical baseline, never the current ORM.
    original_path = tmp_path / "original.sqlite3"
    baseline = runpy.run_path(str(Path(__file__).parents[1] / "alembic/versions/0001_canonical_records.py"))
    with sqlite3.connect(original_path) as connection:
        for statement in baseline["STATEMENTS"]:
            connection.execute(statement)
    database = Database(original_path, initialize=False)
    records = RecordService(database)
    original = create(records, "마이그레이션 후 보존")
    from cache_me.db import new_id, utcnow
    with database.write() as session:
        session.add(Concept(id=new_id(), brain_id=records.brain_id, name="기존 주제", description=None,
                            state_version=1, created_at=utcnow(), updated_at=utcnow()))
    migrate_database(records.db.path)
    assert records.get(original["id"])["body_markdown"] == "마이그레이션 후 보존"
    with records.db.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0002"
        assert connection.exec_driver_sql("SELECT count(*) FROM concepts").scalar() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM topic_backfill_jobs").scalar() == 0
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    database.close()
    fresh_path = tmp_path / "fresh.sqlite3"
    migrate_database(fresh_path)
    migrated = Database(fresh_path, initialize=False)
    migrated.close()
    mismatched_path = tmp_path / "unrecognized.sqlite3"
    with sqlite3.connect(mismatched_path) as connection:
        connection.execute("CREATE TABLE captures (id TEXT, old_body TEXT)")
        connection.execute("INSERT INTO captures VALUES ('old', 'preserve me')")
    with pytest.raises(RuntimeError, match="explicit migration"):
        migrate_database(mismatched_path)
    with sqlite3.connect(mismatched_path) as connection:
        assert connection.execute("SELECT old_body FROM captures").fetchone()[0] == "preserve me"


def test_output_models_validate_real_nested_domain_results(records):
    from cache_me.outputs import (CaptureSummary, CaptureView, ConceptMutationView, ConceptView,
        DeleteResult, DeletionPreview, MutationResult, NodeView, OutputEnvelope, Page,
        RelationMutationView, RelationView, SourceDetail)
    def validate(model, result):
        envelope = OutputEnvelope[model].model_validate({"schema_version": 1, "ok": True, "data": result})
        serialized = envelope.model_dump(mode="json")
        assert "data" in serialized and "error" not in serialized
        return serialized["data"]
    raw = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="정확한 🧠 근거", nodes=[{"kind": "explanation", "body_start": 4, "body_end": 5}]))
    capture = validate(MutationResult, raw)["capture"]
    assert capture["title"] is None and capture["deleted_at"] is None
    assert capture["nodes"][0]["text"] == "🧠"
    validate(CaptureView, records.get(capture["id"]))
    validate(Page[CaptureSummary], records.list())
    validate(NodeView, records.node_get(capture["nodes"][0]["id"]))
    validate(SourceDetail, records.source_get(capture["nodes"][0]["source"]))
    concept = validate(ConceptMutationView, records.concept_create(CreateConceptInput(request_id=uuid4(), name="근거")))
    validate(ConceptView, records.concept_get(concept["id"]))
    validate(Page[ConceptView], records.concept_list())
    second = create(records, "또 다른 기록")
    relation = records.relation_create(RelationInput(request_id=uuid4(), relation_type="supports", source=ref(capture), target=ref(second), evidence=ref(capture)))
    validate(RelationMutationView, relation)
    validate(Page[RelationView], records.relation_list(capture_id=capture["id"]))
    validate(RelationMutationView, records.relation_retract(RetractRelationInput(request_id=uuid4(), relation_id=relation["id"], withdrawal_reason="명시적 정정")))
    preview = validate(DeletionPreview, records.prepare_delete(PrepareDeletionInput(**expected(capture))))
    deletion = DeleteCaptureInput(request_id=uuid4(), **expected(capture), confirmation_token=preview["confirmation_token"])
    validate(DeleteResult, records.delete(deletion, confirmation=records.confirm_deletion(preview["confirmation_token"])))


def test_output_envelope_enforces_exclusive_success_and_failure_branches():
    from cache_me.outputs import OutputEnvelope
    success = OutputEnvelope[dict].model_validate({"ok": True, "data": {"example": "value"}})
    assert success.model_dump(mode="json") == {"schema_version": 1, "ok": True, "data": {"example": "value"}}
    failure = OutputEnvelope[dict].model_validate({"ok": False, "error": {"code": "NOT_FOUND", "message": "없음", "retryable": False}})
    assert "data" not in failure.model_dump(mode="json")
    for payload in ({"ok": True}, {"ok": False}, {"ok": True, "data": {}, "error": None}, {"ok": False, "data": None, "error": {"code": "X", "message": "x", "retryable": False}}):
        with pytest.raises(ValidationError):
            OutputEnvelope[dict].model_validate(payload)
    schema = OutputEnvelope[dict].model_json_schema()
    assert schema["type"] == "object" and len(schema["oneOf"]) == 2
