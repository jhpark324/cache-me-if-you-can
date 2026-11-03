from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import select

from second_brain.chunking import MarkdownChunker
from second_brain.db import Database
from second_brain.embedding import EmbeddingError
from second_brain.models import CaptureIndexState, IndexJob, KnowledgeNode
from second_brain.records import DomainError, RecordService
from second_brain.search import SearchService


class TestEmbedding:
    """Deterministic test seam only; the product default always uses real KURE."""
    __test__ = False
    def __init__(self):
        self.ready = False
        self.on_encode = None
        self.fail = False

    def prepare(self):
        self.ready = True

    def configuration(self):
        return {"test_only": True, "token_dimension": 128}

    def count_tokens(self, text, kind="document"):
        return len(text) + 4

    def vector(self, text):
        array = np.zeros((1, 128), dtype=np.float32)
        for character in text:
            array[0, int(hashlib.sha256(character.encode()).hexdigest()[:6], 16) % 128] += 1
        norm = np.linalg.norm(array)
        return array / norm if norm else np.ones((1, 128), dtype=np.float32) / np.sqrt(128)

    def encode_query(self, text):
        if self.count_tokens(text) > 64:
            raise EmbeddingError("QUERY_TOO_LONG", "질의 초과", {"token_count": self.count_tokens(text), "token_budget": 64})
        return self.vector(text)

    def encode_documents(self, texts):
        if self.on_encode:
            callback, self.on_encode = self.on_encode, None
            callback()
        if self.fail:
            raise RuntimeError("injected failure")
        assert all(self.count_tokens(text) <= 512 for text in texts)
        return [self.vector(text) for text in texts]


@pytest.fixture
def services(tmp_path):
    db = Database(tmp_path / "canonical.sqlite3")
    records = RecordService(db)
    embedding = TestEmbedding()
    search = SearchService(records, tmp_path / "lance", embedding=embedding)
    yield records, search, embedding
    db.close()


def create(records, body="한국어 기록입니다.", **values):
    return records.create({"request_id": str(uuid4()), "body_markdown": body, **values})["capture"]


def edit(records, capture, body):
    return records.update({"request_id": str(uuid4()), "capture_id": capture["id"],
        "expected_revision_id": capture["revision_id"], "expected_state_version": capture["state_version"],
        "changes": {"body_markdown": body}})["capture"]


def delete(records, capture):
    expected = {"capture_id": capture["id"], "expected_revision_id": capture["revision_id"],
                "expected_state_version": capture["state_version"]}
    prepared = records.prepare_delete(expected)
    token = prepared["confirmation_token"]
    return records.delete({**expected, "request_id": str(uuid4()), "confirmation_token": token},
                          confirmation=records.confirm_deletion(token))


@pytest.mark.parametrize("body", [
    "# 제목\r\n\r\n본문 👩🏽‍💻 e\u0301\r\n" * 60,
    "# 상위\n## 하위\n" + "첫 문장입니다. " * 230 + "\n## 마지막\n이 마지막 내용도 보존합니다.",
    "서문\n\n```python\n" + "# 코드 속 제목 아님\n" * 100 + "```\n\n끝",
    "> # 인용 제목\n> 본문\n\n- # 목록 제목\n\n" + "x" * 2000,
    "Setext\n======\n\n| 열 | 값 |\n| --- | --- |\n" + "| 행 | 값 |\n" * 150,
    ("Unicode 구분자\u2028본문\r\r# 실제 헤더\r\n본문\r\n" * 80),
])
def test_chunks_preserve_every_codepoint_and_budget(body):
    chunker = MarkdownChunker(TestEmbedding())
    chunks = chunker.split(body, "아주 긴 제목 " * 30)
    covered = set()
    previous_end = 0
    for chunk in chunks:
        assert chunk.text == body[chunk.body_start:chunk.body_end]
        assert chunk.body_start <= previous_end < chunk.body_end
        assert chunker.counter.count_tokens(chunk.embedding_text) <= 512
        if chunk.body_start < previous_end:
            assert chunker.counter.count_tokens(body[chunk.body_start:previous_end]) <= 64
        covered.update(range(chunk.body_start, chunk.body_end))
        previous_end = chunk.body_end
    assert covered == set(range(len(body)))
    assert chunks == chunker.split(body, "아주 긴 제목 " * 30)
    if "코드 속" in body:
        assert all("코드 속 제목 아님" not in str(c.section_refs) for c in chunks)


def test_preparation_is_explicit_and_query_is_not_truncated(services):
    records, search, _ = services
    capture = create(records)
    assert search.status()["status"] == "not_prepared"
    assert records.get(capture["id"])["index_state"]["status"] == "pending"
    with pytest.raises(DomainError, match="준비") as error:
        search.search({"query": "기록"})
    assert error.value.code == "INDEX_NOT_READY"
    search.prepare()
    with pytest.raises(DomainError) as error:
        search.search({"query": "긴질의" * 100})
    assert error.value.code == "QUERY_TOO_LONG"
    assert error.value.details["token_budget"] == 64


def test_full_body_index_edit_delete_and_reopen(services):
    records, search, embedding = services
    capture = create(records, "# 앞부분\n" + "앞쪽 문장입니다. " * 140 + "\n# 뒷부분\n오리너구리는 알을 낳는 포유류입니다.")
    search.prepare()
    assert search.process_jobs()["processed"] == 1
    hit = search.search({"query": "오리너구리"})["items"][0]
    assert hit["source"]["capture_id"] == capture["id"]
    assert any(span["body_end"] == len(capture["body_markdown"]) for span in hit["matched_spans"])
    count = search._table.count_rows()
    # Retrying an already-written generation cannot duplicate rows.
    with records.db.write() as session:
        job = session.scalar(select(IndexJob))
        job.status = "pending"
    assert search.process_jobs()["processed"] == 1
    assert search._table.count_rows() == count
    changed = edit(records, capture, "현재 기록에는 바다거북만 있습니다.")
    assert search.search({"query": "오리너구리"})["items"] == []
    search.process_jobs()
    assert all("바다거북" in h["excerpt"] for h in search.search({"query": "바다거북"})["items"])
    reopened = SearchService(records, search.index_path, embedding=TestEmbedding())
    reopened.prepare()
    assert reopened.search({"query": "바다거북"})["items"][0]["source"]["revision_id"] == changed["revision_id"]
    delete(records, changed)
    assert reopened.search({"query": "바다거북"})["items"] == []
    assert reopened.context({"query": "바다거북"})["items"] == []
    with pytest.raises(DomainError):
        reopened.neighbors(changed["id"])
    reopened.process_jobs()
    assert reopened._table.count_rows() == 0


def test_stale_job_cannot_publish_after_concurrent_edit(services):
    records, search, embedding = services
    old = create(records, "변경 전 근거입니다.")
    search.prepare()
    embedding.on_encode = lambda: edit(records, old, "변경 후 근거입니다.")
    search.process_jobs(limit=1)
    assert records.get(old["id"])["index_state"]["status"] == "pending"
    assert search.search({"query": "근거"})["items"] == []
    search.process_jobs()
    assert search.search({"query": "근거"})["items"][0]["excerpt"] == "변경 후 근거입니다."
    with records.db.read() as session:
        assert "superseded" in list(session.scalars(select(IndexJob.status)))


def test_failure_retry_and_expired_lease_recovery(services):
    records, search, embedding = services
    capture = create(records)
    search.prepare()
    embedding.fail = True
    assert search.process_jobs()["failed"] == 1
    assert records.get(capture["id"])["index_state"]["status"] == "failed"
    assert search.search({"query": "기록"})["items"] == []
    embedding.fail = False
    assert search.retry(capture["id"])["retried"] == 1
    with records.db.write() as session:
        job = session.scalar(select(IndexJob))
        job.status, job.lease_until, job.lease_token = "running", "2000-01-01T00:00:00.000Z", "lost-process"
    assert search.process_jobs()["processed"] == 1
    assert search.status()["index_counts"]["ready"] == 1


def test_deleted_parent_invalidates_derived_search_without_reindex(services):
    records, search, _ = services
    source = create(records, "원본 근거입니다.")
    derived = create(records, "원본에서 정리한 파생 내용입니다.", sources=[{"capture_id": source["id"], "revision_id": source["revision_id"]}])
    search.prepare()
    search.process_jobs()
    assert len(search.search({"query": "근거 내용"})["items"]) == 2
    delete(records, source)
    assert search.search({"query": "내용"})["items"] == []
    assert records.get(derived["id"])["review_state"] == "needs_review"


def test_node_only_concepts_and_private_records_are_searchable(services):
    records, search, _ = services
    concept = records.concept_create({"request_id": str(uuid4()), "name": "동물"})
    concept_id = concept["id"]
    capture = create(records, "돌고래는 포유류입니다.", visibility="private", kinds=["knowledge"],
                     nodes=[{"kind": "explanation", "body_start": 0, "body_end": len("돌고래는 포유류입니다."), "origin": "ai_explanation", "verification_state": "unverified"}])
    node = capture["nodes"][0]
    capture = records.set_concepts({"request_id": str(uuid4()), "capture_id": capture["id"],
        "expected_revision_id": capture["revision_id"], "expected_state_version": capture["state_version"],
        "concept_ids": [], "node_concepts": [{"node_id": node["id"], "concept_ids": [concept_id]}]})["capture"]
    search.prepare()
    search.process_jobs()
    results = search.search({"query": "돌고래", "concept_ids": [concept_id], "kinds": ["knowledge"]})
    assert results["items"][0]["matched_node_ids"] == [capture["nodes"][0]["id"]]
    assert search.search({"query": "돌고래", "kinds": ["plan"]})["items"] == []
    context = search.context({"query": "돌고래"})
    assert context["items"][0]["verification_state"] == "unverified"
    assert context["items"][0]["applicability"] == "uncertain"


def test_search_revalidates_after_candidate_collection(services, monkeypatch):
    records, search, _ = services
    capture = create(records, "삭제 직전 기록입니다.")
    search.prepare()
    search.process_jobs()
    original = search._eligible
    calls = 0
    def eligible(session, current, state=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            delete(records, capture)
            session.expire_all()
        return original(session, current, state)
    monkeypatch.setattr(search, "_eligible", eligible)
    assert search.search({"query": "기록"})["items"] == []


def test_missing_derived_directory_requeues_canonical_records(services, tmp_path):
    records, search, _ = services
    capture = create(records, "색인은 삭제되어도 정본은 남습니다.")
    search.prepare()
    search.process_jobs()
    fresh = SearchService(records, tmp_path / "new-derived-location", embedding=TestEmbedding())
    fresh.prepare()
    assert records.get(capture["id"])["index_state"]["status"] == "pending"
    assert fresh.search({"query": "정본"})["items"] == []
    fresh.process_jobs()
    assert fresh.search({"query": "정본"})["items"][0]["source"]["capture_id"] == capture["id"]


def test_context_reads_incoming_replacement_and_evidence_in_shared_budget(services):
    records, search, _ = services
    old = create(records, "내 프로젝트는 Windows만 지원할 계획이었다.", kinds=["plan"])
    search.prepare()
    search.process_jobs()
    new = create(records, "내 프로젝트는 이제 Windows와 macOS와 Linux를 모두 지원한다.", kinds=["decision"])
    evidence = create(records, "11월 회의에서 운영체제 지원 범위를 세 종류로 바꾸기로 결정했다.", kinds=["episode"])
    def ref(capture):
        return {"capture_id": capture["id"], "revision_id": capture["revision_id"], "body_start": 0, "body_end": len(capture["body_markdown"])}
    records.relation_create({"request_id": str(uuid4()), "relation_type": "supersedes",
        "source": ref(new), "target": ref(old), "evidence": ref(evidence),
        "scope_note": "이 프로젝트의 지원 운영체제", "evidence_note": "회의 결정에 따라 세 종류로 확대"})
    result = search.context({"query": "운영체제 계획", "kinds": ["plan"]})
    assert {item["source"]["capture_id"] for item in result["items"]} == {old["id"], new["id"], evidence["id"]}
    assert result["relations"][0]["source"]["capture_id"] == new["id"]
    assert result["relations"][0]["target"]["capture_id"] == old["id"]
    assert result["relations"][0]["scope_note"] == "이 프로젝트의 지원 운영체제"
    assert all(item["applicability"] == "uncertain" for item in result["items"])
    limited = search.context({"query": "운영체제 계획", "kinds": ["plan"], "limit": 2})
    assert len({item["source"]["capture_id"] for item in limited["items"]}) == 2
    assert limited["evidence_status"] == "insufficient" and limited["truncated"]
    assert any("일부 본문을 확인하지 못했" in value for value in limited["limitations"])
    delete(records, new)
    after = search.context({"query": "운영체제 계획", "kinds": ["plan"]})
    assert after["relations"] == []
    assert all(item["source"]["capture_id"] != new["id"] for item in after["items"])


def test_context_marks_pending_and_failed_records_as_incomplete(services):
    records, search, _ = services
    create(records)
    search.prepare()
    result = search.context({"query": "기록"})
    assert result["items"] == []
    assert result["evidence_status"] == "insufficient"
    assert any("색인" in text for text in result["limitations"])


def test_invalid_search_inputs_are_safe_domain_errors(services):
    _, search, _ = services
    with pytest.raises(DomainError) as error:
        search.search({"query": "민감한 검색 문장", "arbitrary": "비밀 데이터"})
    assert error.value.code == "VALIDATION_ERROR"
    assert "비밀" not in str(error.value.as_dict())
    assert "민감" not in str(error.value.as_dict())


def test_graph_is_bounded_and_deleted_neighbors_do_not_leak(services):
    records, search, _ = services
    body = "지식 구조 원문입니다."
    capture = create(records, body, nodes=[{"kind": "explanation", "body_start": 0, "body_end": len(body),
                      "origin": "unspecified", "verification_state": "unknown"} for _ in range(60)])
    graph = search.neighbors(capture["id"])
    assert len(graph["nodes"]) == 50
    assert len(graph["edges"]) <= 100
    assert graph["truncated"]
    parent = create(records, "연결 출발 기록")
    neighbor = create(records, "노출되면 안 되는 삭제 대상 제목", title="사라져야 할 제목")
    records.relation_create({"request_id": str(uuid4()), "relation_type": "related_to",
        "source": {"capture_id": parent["id"], "revision_id": parent["revision_id"]},
        "target": {"capture_id": neighbor["id"], "revision_id": neighbor["revision_id"]},
        "evidence": {"capture_id": parent["id"], "revision_id": parent["revision_id"]}})
    assert len(search.neighbors(parent["id"])["nodes"]) == 2
    delete(records, neighbor)
    after = search.neighbors(parent["id"])
    assert len(after["nodes"]) == 1 and after["edges"] == []
    assert "사라져야" not in str(after)


def test_date_filter_excludes_unknown_dates_and_supports_inclusive_days(services):
    records, search, _ = services
    wanted = create(records, "지정일의 회고 기록", event_time={"precision": "day", "value": "2026-11-02"})
    create(records, "날짜가 없는 회고 기록")
    create(records, "이전 날짜의 회고 기록", event_time={"precision": "day", "value": "2026-10-01"})
    search.prepare()
    search.process_jobs()
    result = search.search({"query": "회고", "event_time": {"start": "2026-11-02", "end": "2026-11-02"}})
    assert [hit["source"]["capture_id"] for hit in result["items"]] == [wanted["id"]]


def test_ready_search_does_not_wait_for_entire_writer_batch(services):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    records, search, embedding = services
    existing = create(records, "이미 검색 가능한 기록입니다.")
    search.prepare()
    search.process_jobs()
    create(records, "새로운 색인 작업입니다.")
    entered, release = Event(), Event()
    def pause_writer():
        entered.set()
        assert release.wait(5)
    embedding.on_encode = pause_writer
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(search.process_jobs)
        assert entered.wait(3)
        reader = pool.submit(search.search, {"query": "검색 가능한 기록"})
        try:
            result = reader.result(timeout=3)
            assert result["items"][0]["source"]["capture_id"] == existing["id"]
        finally:
            release.set()
        assert writer.result(timeout=5)["failed"] == 0


def test_graph_relation_retains_exact_node_endpoints(services):
    records, search, _ = services
    def record_with_node(body):
        return create(records, body, nodes=[{"kind": "explanation", "body_start": 0,
                      "body_end": len(body), "origin": "unspecified", "verification_state": "unknown"}])
    left = record_with_node("첫 번째 설명")
    right = record_with_node("두 번째 설명")
    def ref(capture):
        return {"capture_id": capture["id"], "revision_id": capture["revision_id"], "node_id": capture["nodes"][0]["id"]}
    relation = records.relation_create({"request_id": str(uuid4()), "relation_type": "supports",
        "source": ref(left), "target": ref(right), "evidence": ref(left)})
    graph = search.neighbors(left["id"])
    edge = next(edge for edge in graph["edges"] if edge["id"] == relation["id"])
    assert edge["source"] == left["nodes"][0]["id"]
    assert edge["target"] == right["nodes"][0]["id"]
    assert {edge["source"], edge["target"]} <= {node["id"] for node in graph["nodes"]}
