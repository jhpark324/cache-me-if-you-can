"""An ordinary record promoted in 0.9 must retain both independent histories."""
import json
import sqlite3
from uuid import uuid4

from cache_me.articles import ArticleService
from cache_me.db import Database, migrate_database
from cache_me.records import RecordService, digest
from cache_me.search import SearchService
from test_article_migration import EDITED, EXTERNAL, legacy_database
from test_records import assert_error, create, deletion, ref, update
from test_search import TestEmbedding


def promote(path, records, raw):
    # Version 0.9 copied article metadata onto every later Capture revision,
    # including ordinary capture_update and capture_review_sources writes.
    first, second, node_id = [str(uuid4()) for _ in range(3)]
    metadata = json.dumps({"summary": "출판된 요약", "citations": [EXTERNAL]})
    request = {"request_id": str(uuid4()), "capture_id": raw["id"], "expected_revision_id": first,
               "expected_state_version": raw["state_version"] + 1, "changes": {"title": "발행 후 수정"}}
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for ordinal, revision_id, title, change_kind in (
            (raw["revision_no"] + 1, first, raw["title"], "source_review"),
            (raw["revision_no"] + 2, second, "발행 후 수정", "edit"),
        ):
            connection.execute("""INSERT INTO capture_revisions (id, brain_id, capture_id, revision_no,
                title, body_markdown, article, concept_hints, node_status, change_kind, review_reason, created_via, created_at)
                VALUES (?, ?, ?, ?, ?, '아티클 전용 본문 [1](#cite-1)', ?, '[]', 'current', ?, ?, 'mcp', ?)""",
                (revision_id, records.brain_id, raw["id"], ordinal, title, metadata, change_kind,
                 "출처 확인" if change_kind == "source_review" else None, EDITED))
            connection.execute("""INSERT INTO knowledge_nodes (id, brain_id, revision_id, ordinal, kind, body_start,
                body_end, label, origin, verification_state, concept_hints)
                VALUES (?, ?, ?, 0, 'explanation', 0, 3, '아티클 전용 노드', 'user_report', 'unknown', '[]')""",
                (node_id if revision_id == second else str(uuid4()), records.brain_id, revision_id))
        connection.execute("""UPDATE captures SET current_revision_id=?, state_version=state_version+2,
            index_generation=index_generation+2, updated_at=? WHERE id=?""", (second, EDITED, raw["id"]))
        connection.execute("""INSERT INTO mutation_receipts (principal_scope, request_id, operation, request_fingerprint,
            capture_id, committed_revision_id, committed_state_version, outcome, created_at)
            VALUES (?, ?, 'capture_update', ?, ?, ?, ?, 'committed', ?)""",
            (records.principal_scope, request["request_id"], digest(request), raw["id"], second, raw["state_version"] + 2, EDITED))
    return first, second, node_id, request


def test_migrated_raw_record_and_published_article_remain_independently_editable(tmp_path):
    path = legacy_database(tmp_path)
    db = Database(path, initialize=False)
    try:
        records = RecordService(db)
        original_request = {"request_id": str(uuid4()), "title": "공부 기록", "body_markdown": "원자료에서 남긴 문장"}
        original = records.create(original_request)["capture"]
        original_ref = ref(original, body_start=0, body_end=3).model_dump(mode="json")
        derived_raw = create(records, "원자료에 근거한 기록", sources=[original_ref])
        raw = update(records, original, kinds=["knowledge"])
        first, second, node_id, old_request = promote(path, records, raw)
        published_ref = {"capture_id": raw["id"], "revision_id": second, "node_id": node_id}
        derived_published = create(records, "출판본을 인용한 옛 기록", sources=[published_ref])
        search = SearchService(records, tmp_path / "index", embedding=TestEmbedding())
        search.prepare()
        search.process_jobs()
        assert any(hit["source"]["revision_id"] == second for hit in search.search({"query": "아티클 전용"})["items"])

        migrate_database(path)
        articles = ArticleService(records)
        restored = records.get(raw["id"])
        assert restored["revision_id"] == raw["revision_id"] and restored["body_markdown"] == raw["body_markdown"]
        assert records.get(derived_raw["id"])["review_state"] == "valid"
        assert records.source_get(original_ref)["text"] == "원자료"
        assert records.create(original_request)["capture"]["revision_id"] == original["revision_id"]
        for revision_id in first, second:
            assert_error("NOT_FOUND", lambda: records.get(raw["id"], revision_id))
        assert_error("NOT_FOUND", lambda: records.source_get(published_ref))
        assert_error("NOT_FOUND", lambda: records.node_get(node_id))
        assert records.get(derived_published["id"])["sources"][0]["availability"] == "unavailable"
        replay = records.update(old_request)
        assert replay["replayed"] and replay["result_state"] == "unavailable" and replay["capture"] is None

        current_article = articles.get(raw["id"])
        assert current_article["revision_id"] == second and current_article["revision_no"] == raw["revision_no"] + 2
        assert articles.get(raw["id"], first)["title"] == raw["title"]
        assert_error("NOT_FOUND", lambda: articles.get(raw["id"], raw["revision_id"]))
        assert all("아티클 전용" not in item["excerpt"] for item in records.list()["items"])
        for query in search.search, search.context:
            assert "아티클 전용" not in str(query({"query": "아티클 전용"}))
        search.process_jobs()
        assert any(item["source"]["revision_id"] == raw["revision_id"] for item in search.search({"query": "원자료"})["items"])
        assert "아티클 전용" not in str(search.home_graph())

        edit = update(records, restored, kinds=["episode"])
        assert edit["is_current"] and edit["revision_no"] > raw["revision_no"]
        assert records.get(derived_raw["id"])["review_state"] == "valid"
        assert records.get(derived_published["id"])["sources"][0]["availability"] == "unavailable"
        assert_error("NOT_FOUND", lambda: records.get(raw["id"], second))
        assert articles.get(raw["id"]) == current_article
        changed = articles.update({"article_id": raw["id"], "expected_revision_id": second, "request_id": str(uuid4()),
            "title": "독립 개정판", "body_markdown": "새로 쓴 글", "summary": "새 요약", "topics": [], "citations": []})["article"]
        assert changed["revision_no"] == current_article["revision_no"] + 1 and records.get(raw["id"]) == edit
        delete_request, proof = deletion(records, edit)
        records.delete(delete_request, confirmation=proof)
        assert articles.get(raw["id"]) == changed
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()
