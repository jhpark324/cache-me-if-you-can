"""Dedicated article HTTP/MCP contracts on disposable local databases."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from mcp.client import Client
from sqlalchemy import func, select

from agent_fakes import OfflineModel
from cache_me.db import Database
from cache_me.mcp_server import create_mcp
from cache_me.models import (Capture, CaptureIndexState, CaptureRevision, Concept,
                             ConceptEnrichmentJob, IndexJob, KnowledgeNode, ProvenanceLink)
from cache_me.questions import QuestionInput, QuestionService
from cache_me.records import RecordService
from cache_me.search import SearchService
from test_capture_browsing import client
from test_records import create, deletion, expected, records, ref, update
from test_search import TestEmbedding


ARTICLES = "/api/v1/articles"
CAPTURES = "/api/v1/captures"
EXTERNAL = {"kind": "external", "title": "참고 논문", "url": "https://example.org/paper", "note": "논문의 실험 조건"}


def local(capture):
    return {"kind": "record", "source": ref(capture, body_start=0, body_end=2).model_dump(mode="json")}


def payload(**fields):
    return {"request_id": str(uuid4()), "title": "복습 노트", "summary": "발견한 규칙 한 줄",
            "body_markdown": "규칙을 사용해 본 예시", "citations": [], **fields}


def success_data(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def patch_payload(article, **fields):
    content = {key: article[key] for key in ("title", "summary", "body_markdown", "citations", "topics")}
    return payload(article_id=article["id"], expected_revision_id=article["revision_id"], **(content | fields))


def record_rows(records):
    with records.db.read() as session:
        return {model.__tablename__: session.scalar(select(func.count()).select_from(model))
                for model in (Capture, CaptureRevision, CaptureIndexState, IndexJob, KnowledgeNode,
                              Concept, ConceptEnrichmentJob, ProvenanceLink)}


def test_create_and_edit_have_no_record_index_graph_or_question_evidence(records, client, tmp_path):
    source = create(records, "복습에 쓰는 원자료", visibility="private")
    search = SearchService(records, tmp_path / "lance", embedding=TestEmbedding())
    search.prepare()
    assert search.process_jobs()["processed"] == 1
    before = record_rows(records)

    request = payload(body_markdown="원문 [1](#cite-1), 노트 [2](#cite-2)와 코드 예시 `[3](#cite-3)`",
                      citations=[EXTERNAL, local(source)], topics=["복습"])
    result = success_data(client.post(ARTICLES, json=request))
    article = result["article"]
    assert result["replayed"] is False and result["request_id"] == request["request_id"]
    assert article["citations"] == request["citations"] and article["topics"] == ["복습"]
    assert [item["source"] for item in article["sources"]] == [local(source)["source"]]
    edited = success_data(client.patch(f"{ARTICLES}/{article['id']}", json=patch_payload(
        article, title="복습한 규칙", body_markdown="원자료 [1](#cite-1)", citations=[local(source)])))["article"]
    assert edited["revision_no"] == article["revision_no"] + 1

    shelf = client.get(ARTICLES).json()["data"]["items"]
    assert [(item["id"], item["title"], item["summary"]) for item in shelf] == [
        (article["id"], "복습한 규칙", edited["summary"])]
    assert "body_markdown" not in shelf[0]
    assert [r["id"] for r in client.get(CAPTURES).json()["data"]["items"]] == [source["id"]]
    assert client.get(f"{CAPTURES}/{article['id']}").status_code == 404
    assert client.get(f"{ARTICLES}/{source['id']}").status_code == 404
    assert client.patch(f"{CAPTURES}/{article['id']}", json={
        "capture_id": article["id"], "expected_revision_id": edited["revision_id"], "expected_state_version": 1,
        "request_id": str(uuid4()), "changes": {"title": "기록 수정 시도"}}).status_code == 404
    assert client.post("/api/v1/sources/resolve", json={
        "capture_id": article["id"], "revision_id": edited["revision_id"]}).status_code == 404
    legacy_metadata = {"summary": article["summary"], "citations": article["citations"]}
    assert client.post(CAPTURES, json={"request_id": str(uuid4()), "body_markdown": "저장",
                                      "article": legacy_metadata}).status_code == 422
    assert client.patch(f"{CAPTURES}/{source['id']}", json={
        **expected(source), "request_id": str(uuid4()), "changes": {"article": legacy_metadata}}).status_code == 422
    assert "article" not in client.get(f"{CAPTURES}/{source['id']}").json()["data"]
    assert record_rows(records) == before
    assert search.process_jobs()["processed"] == 0
    assert {node["id"] for node in search.home_graph()["nodes"] if node["kind"] == "capture"} == {source["id"]}
    for result in (search.search({"query": "복습"}), search.context({"query": "복습"})):
        assert {item["source"]["capture_id"] for item in result["items"]} == {source["id"]}
    answer = asyncio.run(QuestionService(search, records, OfflineModel()).run(
        QuestionInput(request_id=uuid4(), question="복습 자료는 무엇인가요?")))
    assert {item["capture_id"] for item in answer["sources"]} == {source["id"]}


def test_pinned_sources_survive_edits_and_report_deletion(records, client):
    old = create(records, "기존 근거")
    original = success_data(client.post(ARTICLES, json=payload(
        body_markdown="근거 [1](#cite-1)", citations=[local(old)])))["article"]
    url = f"{ARTICLES}/{original['id']}"
    newer = update(records, old, body_markdown="수정된 근거")
    stale = client.get(url).json()["data"]
    assert stale["review_state"] == "needs_review" and stale["sources"][0]["reason"] == "source_changed"
    old_ref = stale["citations"][0]["source"]
    assert success_data(client.post("/api/v1/sources/resolve", json=old_ref))["text"] == "기존"
    retitled = success_data(client.patch(url, json=patch_payload(original, title="근거 재검토 중")))["article"]
    assert retitled["review_state"] == "needs_review" and retitled["citations"] == [local(old)]
    corrected = success_data(client.patch(url, json=patch_payload(
        retitled, body_markdown="변경된 근거 [1](#cite-1)", citations=[local(newer)])))["article"]
    assert corrected["review_state"] == "valid"
    assert corrected["citations"] == [local(newer)]
    history = client.get(url, params={"revision_id": original["revision_id"]}).json()["data"]
    assert history["citations"] == [local(old)] and history["body_markdown"] == original["body_markdown"]
    delete, proof = deletion(records, newer)
    records.delete(delete, confirmation=proof)
    detached = client.get(url).json()["data"]
    assert detached["review_state"] == "needs_review"
    assert detached["sources"][0]["availability"] == "unavailable"
    assert detached["body_markdown"] == corrected["body_markdown"]
    assert client.post("/api/v1/sources/resolve", json=old_ref).status_code == 404


def test_create_replay_concurrent_edit_and_replay_original_versions(client):
    creation = payload()
    with ThreadPoolExecutor(max_workers=2) as pool:
        writes = list(pool.map(lambda _: success_data(client.post(ARTICLES, json=creation)), range(2)))
    assert sorted(reply["replayed"] for reply in writes) == [False, True]
    assert writes[0]["article"] == writes[1]["article"]
    first = writes[0]["article"]
    url = f"{ARTICLES}/{first['id']}"
    changes = [patch_payload(first, title="개정 A"), patch_payload(first, title="개정 B")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda change: client.patch(url, json=change), changes))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner, loser = (0, 1) if responses[0].status_code == 200 else (1, 0)
    assert responses[loser].json()["error"]["code"] == "VERSION_CONFLICT"
    second = success_data(responses[winner])["article"]
    success_data(client.patch(url, json=patch_payload(second, title="최종 버전")))
    assert success_data(client.post(ARTICLES, json=creation))["article"] == first
    replay = success_data(client.patch(url, json=changes[winner]))
    assert replay["replayed"] and replay["article"] == second
    conflict = client.post(ARTICLES, json={**creation, "summary": "다른 요청"})
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert client.get(url).json()["data"]["revision_no"] == 3
    assert len(client.get(ARTICLES).json()["data"]["items"]) == 1


@pytest.mark.parametrize("fields", [
    {"body_markdown": "[1](#cite-1)"},
    {"body_markdown": "[2](#cite-1)", "citations": [EXTERNAL]},
    {"title": "   "},
    {"summary": "두\n줄"},
    {"citations": [{**EXTERNAL, "url": "javascript:alert(1)"}]},
    {"citations": [{"kind": "record", "source": {"capture_id": str(uuid4()), "revision_id": str(uuid4())}}]},
])
def test_invalid_article_neither_creates_nor_revises(client, fields):
    bad = payload(**fields)
    assert client.post(ARTICLES, json=bad).status_code == 422
    assert client.get(ARTICLES).json()["data"]["items"] == []
    first = success_data(client.post(ARTICLES, json=payload()))["article"]
    url = f"{ARTICLES}/{first['id']}"
    assert client.patch(url, json=patch_payload(first, **fields)).status_code == 422
    assert client.get(url).json()["data"] == first


def test_article_catalog_separates_brains_and_paginates(records, client):
    source = create(records, "개인 자료", visibility="private")
    first = success_data(client.post(ARTICLES, json=payload(title="첫 글", topics=["운영체제"])))["article"]
    second = success_data(client.post(ARTICLES, json=payload(title="둘째 글")))["article"]
    matching = client.get(ARTICLES, params={"query": "운영체제"}).json()["data"]["items"]
    assert [item["id"] for item in matching] == [first["id"]]
    page = client.get(ARTICLES, params={"limit": 1}).json()["data"]
    next_page = client.get(ARTICLES, params={"limit": 1, "cursor": page["next_cursor"]}).json()["data"]
    assert {page["items"][0]["id"], next_page["items"][0]["id"]} == {first["id"], second["id"]}
    assert next_page["next_cursor"] is None
    assert client.get(f"{ARTICLES}/{first['id']}", params={"revision_id": second["revision_id"]}).status_code == 404

    other = Database(records.db.path, brain_id=str(uuid4()))
    try:
        client.app.state.records = RecordService(other)
        assert client.get(ARTICLES).json()["data"]["items"] == []
        assert client.get(f"{ARTICLES}/{first['id']}").status_code == 404
        assert client.patch(f"{ARTICLES}/{first['id']}", json=patch_payload(first)).status_code == 404
        assert client.post(ARTICLES, json=payload(body_markdown="[1](#cite-1)", citations=[local(source)])).status_code == 422
    finally:
        client.app.state.records = records
        other.close()


def test_only_dedicated_mcp_tools_publish_read_and_update_articles(records):
    async def run():
        async with Client(create_mcp(records, None)) as mcp:
            tools = {tool.name: tool for tool in (await mcp.list_tools()).tools}
            assert "articles_only" not in tools["capture_list"].input_schema["properties"]
            request = payload()
            result = await mcp.call_tool("article_create", {"input": request})
            article = result.structured_content["data"]["article"]
            listed = await mcp.call_tool("article_list", {})
            assert [item["id"] for item in listed.structured_content["data"]["items"]] == [article["id"]]
            changed = await mcp.call_tool("article_update", {"input": patch_payload(article, title="다시 쓴 글")})
            assert changed.structured_content["data"]["article"]["title"] == "다시 쓴 글"
            historical = await mcp.call_tool("article_get", {"article_id": article["id"], "revision_id": article["revision_id"]})
            assert historical.structured_content["data"] == article
            record_list = await mcp.call_tool("capture_list", {})
            assert record_list.structured_content["data"]["items"] == []
            hidden = await mcp.call_tool("capture_get", {"capture_id": article["id"]})
            assert hidden.is_error and hidden.structured_content["error"]["code"] == "NOT_FOUND"
            rejected = await mcp.call_tool("capture_create", {"input": request})
            assert rejected.is_error

    asyncio.run(run())
