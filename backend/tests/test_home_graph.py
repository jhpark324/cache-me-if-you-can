"""Canonical home graph: real SQLite, no embedding/model or user account."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from second_brain.brand import PRODUCT_NAME
from second_brain.config import Settings
from second_brain.db import Database, new_id
from second_brain.main import create_app
from second_brain.models import ProvenanceLink
from second_brain.records import DomainError, RecordService
from second_brain.search import SearchService


@pytest.fixture
def graph(tmp_path):
    db = Database(tmp_path / "canonical.sqlite3")
    records = RecordService(db)
    search = SearchService(records, tmp_path / "unused-index")
    yield records, search
    db.close()


def create(records, body="현재 지식입니다.", **values):
    return records.create({"request_id": str(uuid4()), "body_markdown": body, **values})["capture"]


def expected(capture):
    return {"capture_id": capture["id"], "expected_revision_id": capture["revision_id"],
            "expected_state_version": capture["state_version"]}


def ref(capture, node=False):
    result = {"capture_id": capture["id"], "revision_id": capture["revision_id"]}
    if node:
        result["node_id"] = capture["nodes"][0]["id"]
    return result


def update(records, capture, **changes):
    return records.update({"request_id": str(uuid4()), **expected(capture), "changes": changes})["capture"]


def delete(records, capture):
    preview = records.prepare_delete(expected(capture))
    token = preview["confirmation_token"]
    return records.delete({"request_id": str(uuid4()), **expected(capture), "confirmation_token": token},
                          confirmation=records.confirm_deletion(token))


def concept(records, name):
    return records.concept_create({"request_id": str(uuid4()), "name": name})


def assign(records, capture, concepts=(), node_concepts=()):
    return records.set_concepts({"request_id": str(uuid4()), **expected(capture),
        "concept_ids": list(concepts), "node_concepts": list(node_concepts)})["capture"]


def relate(records, left, right, evidence=None, *, node=False):
    return records.relation_create({"request_id": str(uuid4()), "relation_type": "supports",
        "source": ref(left, node), "target": ref(right, node), "evidence": ref(evidence or left, node)})


def ids(result, kind="capture"):
    return {node["id"] for node in result["nodes"] if node["kind"] == kind}


def test_empty_and_owner_private_records_work_without_embeddings(graph):
    records, search = graph
    assert search.home_graph() == {"nodes": [], "edges": [], "truncated": False}
    private = create(records, visibility="private", kinds=["reflection"])
    result = search.home_graph()
    assert ids(result) == {private["id"]}
    assert result["nodes"][0]["kinds"] == ["episode"]
    assert result["nodes"][0]["source"]["revision_id"] == private["revision_id"]
    assert search.status()["status"] == "not_prepared"
    assert not search.index_path.exists()


def test_graph_labels_are_bounded_but_canonical_text_is_preserved(graph):
    records, search = graph
    long_label = "이름" * 50_000
    topic = concept(records, long_label)
    capture = create(records, title=long_label, nodes=[{"kind": "explanation", "body_start": 0, "body_end": 2, "label": long_label}])
    capture = assign(records, capture, [topic["id"]])
    for result in (search.home_graph(), search.neighbors(capture["id"])):
        assert {n["kind"] for n in result["nodes"]} == {"capture", "concept", "node"}
        assert all(len(n["label"]) == 60 for n in result["nodes"])
    assert records.get(capture["id"])["title"] == long_label


def test_only_explicit_current_topics_nodes_and_relations_are_drawn(graph):
    records, search = graph
    topic = concept(records, "학습")
    node_topic = concept(records, "부분 주제")
    left = create(records, "👩🏽‍💻 첫 설명", nodes=[{"kind": "explanation", "body_start": 0, "body_end": 4}])
    left = assign(records, left, [topic["id"]], [{"node_id": left["nodes"][0]["id"], "concept_ids": [node_topic["id"]]}])
    right = create(records, "두번째 설명", nodes=[{"kind": "explanation", "body_start": 0, "body_end": 3}])
    relation = relate(records, left, right, node=True)
    result = search.home_graph()
    assert ids(result) == {left["id"], right["id"]}
    assert ids(result, "concept") == {topic["id"], node_topic["id"]}
    assert ids(result, "node") == {left["nodes"][0]["id"], right["nodes"][0]["id"]}
    edge = next(e for e in result["edges"] if e["id"] == relation["id"])
    assert edge["source"] == left["nodes"][0]["id"]
    assert edge["target"] == right["nodes"][0]["id"]
    assert {e["kind"] for e in result["edges"]} == {"contains", "has_topic", "supports"}
    assert any(e["source"] == left["nodes"][0]["id"] and e["target"] == node_topic["id"] for e in result["edges"])
    detail = records.source_get(next(n["source"] for n in result["nodes"] if n["id"] == left["nodes"][0]["id"]))
    assert detail["text"] == "👩🏽‍💻"


def test_filters_match_capture_and_node_topics_and_do_not_expand_other_records(graph):
    records, search = graph
    topic = concept(records, "필터")
    left = assign(records, create(records, kinds=["knowledge"]), [topic["id"]])
    right = create(records, kinds=["episode"], nodes=[{"kind": "event", "body_start": 0, "body_end": 2}])
    right = assign(records, right, node_concepts=[{"node_id": right["nodes"][0]["id"], "concept_ids": [topic["id"]]}])
    other = create(records, kinds=["plan"])
    relate(records, left, other)
    assert ids(search.home_graph({"concept_ids": [topic["id"]]})) == {left["id"], right["id"]}
    result = search.home_graph({"concept_ids": [topic["id"]], "kinds": ["knowledge", "decision"]})
    assert ids(result) == {left["id"]}
    assert all(e["kind"] != "supports" for e in result["edges"])
    assert search.home_graph({"concept_ids": [str(uuid4())]})["nodes"] == []


def test_delete_hides_derived_records_topics_nodes_and_relation_evidence(graph):
    records, search = graph
    upstream = create(records, title="삭제될 민감 원문")
    topic = concept(records, "파생 비밀 주제")
    derived = create(records, "파생 비밀", title="파생 비밀 제목", sources=[ref(upstream)],
                     nodes=[{"kind": "explanation", "body_start": 0, "body_end": 2}])
    derived = assign(records, derived, [topic["id"]])
    left, right = create(records, "유효한 왼쪽"), create(records, "유효한 오른쪽")
    relation = relate(records, left, right, upstream)
    assert relation["id"] in {e["id"] for e in search.home_graph()["edges"]}
    delete(records, upstream)
    result = search.home_graph()
    assert ids(result) == {left["id"], right["id"]}
    assert result["edges"] == []
    assert "비밀" not in str(result) and "민감" not in str(result)
    with pytest.raises(DomainError) as rejected:
        search.neighbors(derived["id"])
    assert rejected.value.code == "SOURCE_REVIEW_REQUIRED"


def test_other_brain_is_excluded_even_for_public_and_concept_filter(graph):
    records, search = graph
    ours = create(records)
    other_db = Database(records.db.path, brain_id=str(uuid4()))
    try:
        other = RecordService(other_db)
        topic = concept(other, "다른 저장소 주제")
        assign(other, create(other, "다른 저장소 비밀", visibility="public"), [topic["id"]])
        result = search.home_graph()
        assert ids(result) == {ours["id"]}
        assert "다른 저장소" not in str(result)
        assert search.home_graph({"concept_ids": [topic["id"]]})["nodes"] == []
    finally:
        other_db.close()


def test_revisions_resolve_metadata_equivalence_but_body_edits_invalidate_relations(graph):
    records, search = graph
    left, right = create(records, "왼쪽 원문"), create(records, "오른쪽 원문")
    relation = relate(records, left, right)
    topic = concept(records, "새 주제")
    left = assign(records, left, [topic["id"]])
    result = search.home_graph()
    edge = next(e for e in result["edges"] if e["id"] == relation["id"])
    assert edge["evidence"]["revision_id"] == left["revision_id"]
    edge = next(e for e in search.neighbors(right["id"])["edges"] if e["id"] == relation["id"])
    assert edge["evidence"]["revision_id"] == left["revision_id"]
    left = update(records, left, body_markdown="수정한 내용", title="현재 제목")
    result = search.home_graph()
    assert relation["id"] not in {e["id"] for e in result["edges"]}
    node = next(n for n in result["nodes"] if n["id"] == left["id"])
    assert node["label"] == "현재 제목" and node["source"]["revision_id"] == left["revision_id"]


def test_withdrawal_hides_relation_without_removing_current_endpoints(graph):
    records, search = graph
    left, right = create(records), create(records)
    relation = relate(records, left, right)
    records.relation_retract({"request_id": str(uuid4()), "relation_id": relation["id"], "withdrawal_reason": "관계 정정"})
    result = search.home_graph()
    assert ids(result) == {left["id"], right["id"]} and result["edges"] == []


def test_record_window_is_bounded_and_deterministic(graph, monkeypatch):
    records, search = graph
    for i in range(80):
        create(records, title=f"기록 {i}")
    validations = []
    validate = records._source_status
    def counted(session, source, visiting=None, **kwargs):
        validations.append(source["capture_id"])
        return validate(session, source, visiting, **kwargs)
    monkeypatch.setattr(records, "_source_status", counted)
    statements = []
    def track(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)
    event.listen(records.db.engine, "before_cursor_execute", track)
    try:
        result = search.home_graph()
    finally:
        event.remove(records.db.engine, "before_cursor_execute", track)
    assert len(result["nodes"]) == 50 and result["truncated"]
    assert len(validations) == 50
    # One bounded validation per candidate plus batch metadata/expansion reads.
    assert len(statements) <= 59
    assert result == search.home_graph()


def test_nodes_and_edges_have_independent_bounds_without_dangling_endpoints(graph):
    records, search = graph
    capture = create(records, "범위 원문", nodes=[{"kind": "explanation", "body_start": 0, "body_end": 2} for _ in range(200)])
    result = search.home_graph()
    assert len(result["nodes"]) == 50 and result["truncated"]
    assert len(result["edges"]) == 49
    delete(records, capture)
    left, right = create(records), create(records)
    for _ in range(105):
        relate(records, left, right)
    result = search.home_graph()
    assert len(result["nodes"]) == 2 and len(result["edges"]) == 100 and result["truncated"]
    all_ids = {n["id"] for n in result["nodes"]}
    assert all({e["source"], e["target"]} <= all_ids for e in result["edges"])


def test_node_only_topics_are_preserved_in_neighbors_with_current_evidence(graph):
    records, search = graph
    topic = concept(records, "세부 항목에만 지정한 주제")
    capture = create(records, "주제와 연결할 본문", nodes=[
        {"kind": "explanation", "body_start": 0, "body_end": 2},
    ])
    capture = assign(records, capture, node_concepts=[
        {"node_id": capture["nodes"][0]["id"], "concept_ids": [topic["id"]]},
    ])
    part = capture["nodes"][0]
    home, neighbors = search.home_graph(), search.neighbors(capture["id"])
    expected_edge = next(edge for edge in home["edges"] if edge["kind"] == "has_topic")
    assert expected_edge in neighbors["edges"]
    assert expected_edge["source"] == part["id"]
    assert expected_edge["target"] == topic["id"]
    assert expected_edge["evidence"]["revision_id"] == capture["revision_id"]
    assert expected_edge["evidence"]["body_start"] == part["body_start"]
    assert topic["id"] in ids(neighbors, "concept")

    # A subsequent semantic edit must not expose the old Node's topic edge.
    changed = update(records, capture, body_markdown="의미를 바꾼 새로운 본문")
    result = search.neighbors(changed["id"])
    assert expected_edge["id"] not in {edge["id"] for edge in result["edges"]}
    assert topic["id"] not in ids(result, "concept")


def test_node_topic_expansion_obeys_graph_limits_without_dangling_edges(graph):
    records, search = graph
    topics = [concept(records, f"주제 {index}")["id"] for index in range(20)]
    capture = create(records, "범위 원문", nodes=[
        {"kind": "explanation", "body_start": 0, "body_end": 2} for _ in range(8)
    ])
    capture = assign(records, capture, node_concepts=[
        {"node_id": part["id"], "concept_ids": topics} for part in capture["nodes"]
    ])
    result = search.neighbors(capture["id"])
    assert result["truncated"]
    assert len(result["nodes"]) <= 50 and len(result["edges"]) == 100
    all_ids = {node["id"] for node in result["nodes"]}
    assert all({edge["source"], edge["target"]} <= all_ids for edge in result["edges"])


def test_home_graph_reports_current_classification_state_without_job_secrets(graph):
    records, search = graph
    capture = create(records, "합성 분류 상태 확인")
    def node_state():
        node = next(node for node in search.home_graph()["nodes"] if node["id"] == capture["id"])
        return node["concept_state"]
    assert node_state() == {"status": "pending", "error_code": None}
    job = records.claim_concept_job()
    assert node_state() == {"status": "running", "error_code": None}
    records.fail_concept_job(job["job_id"], job["lease_token"], error_code="CLASSIFICATION_FAILED")
    assert node_state() == {"status": "failed", "error_code": "CLASSIFICATION_FAILED"}

    # Current metadata must not inherit the failure of an older version.
    capture = update(records, capture, body_markdown="새 버전의 합성 분류 상태")
    assert node_state() == {"status": "pending", "error_code": None}
    job = records.claim_concept_job()
    records.apply_concept_job(job["job_id"], job["lease_token"], concept_ids=[], new_concepts=[
        {"name": "합성 주제", "attach_to_capture": True, "node_ids": []},
    ])
    assert node_state() == {"status": "ready", "error_code": None}
    result = search.home_graph()
    assert any(edge["kind"] == "has_topic" for edge in result["edges"])
    assert all("lease_token" not in node and "job_id" not in node for node in result["nodes"])


def test_http_contract_session_filters_validation_and_brand(tmp_path):
    settings = Settings(tmp_path, background_jobs=False)
    app = create_app(settings)
    with TestClient(app, base_url=settings.origin) as client:
        assert client.get("/api/v1/graph").status_code == 401
        client.get("/api/v1/session")
        assert client.get("/api/v1/graph").json()["data"] == {"nodes": [], "edges": [], "truncated": False}
        capture = create(app.state.records, kinds=["knowledge"])
        response = client.get("/api/v1/graph", params=[("kinds", "knowledge"), ("kinds", "reflection")])
        assert response.status_code == 200 and ids(response.json()["data"]) == {capture["id"]}
        assert client.get("/api/v1/graph?kinds=invalid").status_code == 422
        assert client.get("/api/v1/graph?concept_ids=not-a-uuid").status_code == 422
        assert client.get("/api/v1/graph?unknown=yes").status_code == 422
        assert app.title == PRODUCT_NAME == "Cache Me If You Can"


def connect_sources(records, capture, sources):
    """Build a canonical DAG without making fixture setup itself recurse."""
    with records.db.write() as session:
        for source in sources:
            session.add(ProvenanceLink(id=new_id(), brain_id=records.brain_id,
                derived_revision_id=capture["revision_id"], source_capture_id=source["id"],
                source_revision_id=source["revision_id"], source_node_id=None,
                source_body_start=None, source_body_end=None))


def test_shared_provenance_dag_is_memoized_not_exponential(graph, monkeypatch):
    records, search = graph
    previous = [create(records), create(records)]
    all_records = list(previous)
    for _ in range(12):
        current = [create(records), create(records)]
        for capture in current:
            connect_sources(records, capture, previous)
        all_records.extend(current)
        previous = current
    resolutions = []
    resolve = records._resolve_source_status
    def counted(session, source, visiting=None, **kwargs):
        resolutions.append(source["capture_id"])
        return resolve(session, source, visiting, **kwargs)
    monkeypatch.setattr(records, "_resolve_source_status", counted)
    result = search.home_graph()
    assert ids(result) == {r["id"] for r in all_records}
    assert not result["truncated"]
    assert len(resolutions) == len(all_records) == 26


def test_provenance_depth_and_work_budget_fail_closed_with_truncation(graph, monkeypatch):
    records, search = graph
    chain = [create(records)]
    for _ in range(35):
        current = create(records)
        connect_sources(records, current, [chain[-1]])
        chain.append(current)
    result = search.home_graph()
    assert result["truncated"] and chain[-1]["id"] not in ids(result)
    assert search.neighbors(chain[-1]["id"]) == {"nodes": [], "edges": [], "truncated": True}
    # A tiny deterministic test budget proves partial source arrays are never
    # mistaken for completely validated provenance.
    from second_brain.records import SourceValidationBudget
    import second_brain.search as search_module
    monkeypatch.setattr(search_module, "SourceValidationBudget", lambda: SourceValidationBudget(remaining=1))
    limited = search.home_graph()
    assert limited == {"nodes": [], "edges": [], "truncated": True}


def test_record_detail_memoizes_shared_sources_only_within_one_read(graph, monkeypatch):
    records, _ = graph
    previous = [create(records), create(records)]
    roots = list(previous)
    for _ in range(10):
        current = [create(records), create(records)]
        for capture in current:
            connect_sources(records, capture, previous)
        previous = current
    resolutions = []
    resolve = records._resolve_source_status
    def counted(session, source, visiting=None, **kwargs):
        resolutions.append(source["capture_id"])
        return resolve(session, source, visiting, **kwargs)
    monkeypatch.setattr(records, "_resolve_source_status", counted)
    assert records.get(previous[0]["id"])["review_state"] == "valid"
    # 20 unique upstream records; recursive branch traversal formerly revisited
    # the same parents exponentially despite the small canonical graph.
    assert len(resolutions) == len(set(resolutions)) == 20
    update(records, roots[0], body_markdown="출처가 달라졌습니다.")
    resolutions.clear()
    assert records.get(previous[0]["id"])["review_state"] == "needs_review"
    assert roots[0]["id"] in resolutions
