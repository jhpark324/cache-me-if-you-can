from uuid import uuid4

import pytest

from cache_me.schemas import CreateCaptureInput
from test_capture_browsing import client
from test_records import assert_error, create, deletion, expected, records, ref, update


EXTERNAL = {"kind": "external", "title": "원문", "url": "https://example.org/paper", "note": "논문에서 확인한 조건"}


def local(source):
    return {"kind": "record", "source": ref(source, body_start=0, body_end=2).model_dump(mode="json")}


def article(*citations):
    return {"summary": "한 줄 정리", "citations": list(citations)}


def test_register_article_through_api_preserves_citation_identity_and_filters(records, client):
    source = create(records, "저장한 원문", kinds=["artifact"])
    metadata = article(EXTERNAL, local(source))
    body = "| 근거 | 참고 |\n|---|---|\n| 기록 | [2](#cite-2) |\n\n외부 [1](#cite-1)\n\n예시 `[3](#cite-3)`"
    payload = {"request_id": str(uuid4()), "body_markdown": body, "title": "학습 글", "article": metadata}
    saved = client.post("/api/v1/captures", json=payload).json()["data"]["capture"]
    assert saved["article"] == metadata
    assert [s["source"] for s in saved["sources"]] == [local(source)["source"]]
    assert client.post("/api/v1/captures", json=payload).json()["data"]["replayed"]
    assert client.get(f"/api/v1/captures/{saved['id']}").json()["data"]["article"] == metadata
    shelf = client.get("/api/v1/captures", params={"articles_only": True}).json()["data"]
    assert [(r["id"], r["article_summary"]) for r in shelf["items"]] == [(saved["id"], "한 줄 정리")]
    assert {r["id"] for r in records.list()["items"]} == {source["id"], saved["id"]}

    current = update(records, saved, title="수정된 제목")
    assert current["article"] == metadata
    changed = update(records, current, article=article(local(source), EXTERNAL), body_markdown="기록 [1](#cite-1)과 원문 [2](#cite-2)")
    assert changed["article"]["citations"][0] == local(source)
    assert records.get(saved["id"], saved["revision_id"])["article"] == metadata
    assert client.post("/api/v1/captures", json=payload).json()["data"]["capture"]["article"] == metadata
    delete, proof = deletion(records, changed)
    records.delete(delete, confirmation=proof)
    assert records.list(articles_only=True)["items"] == []
    assert client.post("/api/v1/captures", json=payload).json()["data"]["result_state"] == "unavailable"


def test_source_changes_and_review_require_numbered_reference_to_match_new_version(records):
    old = create(records, "기존 근거")
    saved = create(records, "기록 [1](#cite-1)", title="원인", article=article(local(old)))
    newer = update(records, old, body_markdown="정정한 근거")
    stale = records.get(saved["id"])
    assert stale["review_state"] == "needs_review" and stale["sources"][0]["reason"] == "source_changed"
    assert records.source_get(stale["article"]["citations"][0]["source"])["text"] == "기존"
    review = {**expected(saved), "request_id": uuid4(), "replacement_sources": [local(newer)["source"]],
              "review_reason": "새 원문을 확인함"}
    assert_error("INVALID_SOURCE_REF", lambda: records.review_sources(review))
    corrected = records.review_sources({**review, "article": article(local(newer))})["capture"]
    assert corrected["review_state"] == "valid" and corrected["article"]["citations"] == [local(newer)]
    assert records.get(saved["id"], saved["revision_id"])["article"]["citations"] == [local(old)]
    delete, proof = deletion(records, newer)
    records.delete(delete, confirmation=proof)
    detached = records.get(saved["id"])
    assert detached["sources"][0]["availability"] == "unavailable"
    assert_error("NOT_FOUND", lambda: records.source_get(detached["article"]["citations"][0]["source"]))


def test_topic_metadata_preserves_citation_order_and_external_change_invalidates_derivation(records):
    source = create(records, "근거")
    original = create(records, "원문 [1](#cite-1), 기록 [2](#cite-2)", title="개념 글", article=article(EXTERNAL, local(source)))
    derived = create(records, "후속 글", sources=[ref(original)])
    current = records.set_concepts({**expected(original), "request_id": uuid4(), "concept_ids": []})["capture"]
    assert current["article"] == original["article"]
    assert records.get(derived["id"])["review_state"] == "valid"
    update(records, current, article=article({**EXTERNAL, "url": "https://example.org/correction"}, local(source)))
    assert records.get(derived["id"])["review_state"] == "needs_review"


@pytest.mark.parametrize("body,metadata,title", [
    ("[1](#cite-1)", article(), "제목"),
    ("[2](#cite-1)", article(EXTERNAL), "제목"),
    ("ok", article(), "   "),
    ("ok", {**article(), "summary": "두\n줄"}, "제목"),
    ("ok", article({**EXTERNAL, "url": "javascript:alert(1)"}), "제목"),
    ("ok", article({"kind": "record", "source": {"capture_id": str(uuid4()), "revision_id": str(uuid4())}}), "제목"),
])
def test_invalid_registration_is_atomic(records, client, body, metadata, title):
    response = client.post("/api/v1/captures", json={
        "request_id": str(uuid4()), "body_markdown": body, "title": title, "article": metadata})
    assert response.status_code == 422
    assert records.list()["items"] == []


def test_article_filters_have_distinct_cursor_and_old_requests_keep_their_receipt(records):
    legacy = {"request_id": str(uuid4()), "body_markdown": "기존 기록"}
    created = records.create(CreateCaptureInput(**legacy))
    from cache_me.records import digest
    from cache_me.models import MutationReceipt
    with records.db.read() as session:
        assert session.get(MutationReceipt, (records.principal_scope, legacy["request_id"])).request_fingerprint == digest(legacy)
    for title in ("첫 글", "둘째 글"):
        create(records, "배운 내용", title=title, article=article())
    assert records.create(legacy)["capture"]["id"] == created["capture"]["id"]
    cursor = records.list(articles_only=True, limit=1)["next_cursor"]
    assert len(records.list(articles_only=True, limit=1, cursor=cursor)["items"]) == 1
    assert_error("CURSOR_STALE", lambda: records.list(limit=1, cursor=cursor))
