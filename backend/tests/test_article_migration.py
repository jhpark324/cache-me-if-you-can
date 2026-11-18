"""Exercise upgrades from frozen 0003 data without relying on its retired ORM."""
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from cache_me.articles import ArticleService
from cache_me.db import Database, migrate_database
from cache_me.records import RecordService
from cache_me.search import SearchService
from test_records import assert_error, create
from test_search import TestEmbedding


CREATED = "2026-01-01T00:00:00.000Z"
EDITED = "2026-01-02T00:00:00.000Z"
UPDATED = "2026-01-03T00:00:00.000Z"
EXTERNAL = {"kind": "external", "title": "공식 문서", "url": "https://example.org/docs", "note": "예시"}


def legacy_database(tmp_path):
    path = tmp_path / "v3.sqlite3"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", "sqlite:///" + str(path))
    command.upgrade(config, "0003")
    return path


def add_legacy_article(connection, brain_id, editions, deleted_at=None):
    article_id = str(uuid4())
    revision_ids = [str(uuid4()) for _ in editions]
    connection.execute("""INSERT INTO captures
        (id, brain_id, current_revision_id, visibility, state_version, index_generation, created_at, updated_at, deleted_at)
        VALUES (?, ?, ?, 'public', 3, 3, ?, ?, ?)""",
        (article_id, brain_id, revision_ids[-1], CREATED, UPDATED, deleted_at))
    for number, (revision_id, metadata) in enumerate(zip(revision_ids, editions), start=1):
        connection.execute("""INSERT INTO capture_revisions
            (id, brain_id, capture_id, revision_no, title, body_markdown, article, concept_hints,
             node_status, change_kind, created_via, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '[]', 'absent', ?, 'mcp', ?)""",
            (revision_id, brain_id, article_id, number, f"제목 {number}", f"본문 {number} [1](#cite-1)",
             json.dumps(metadata, ensure_ascii=False) if metadata is not None else None, "create" if number == 1 else "edit",
             CREATED if number == 1 else EDITED))
    return article_id, revision_ids


def test_upgrade_preserves_articles_and_hides_retired_record_sources(tmp_path):
    path = legacy_database(tmp_path)
    db = Database(path, initialize=False)
    records = RecordService(db)
    source = create(records, "복습할 근거")
    downstream = create(records, "종전 글을 인용한 기록")
    pinned = {"kind": "record", "source": {"capture_id": source["id"], "revision_id": source["revision_id"],
                                          "node_id": None, "body_start": 0, "body_end": 3}}
    initial = {"summary": "첫 요약", "citations": [EXTERNAL]}
    latest = {"summary": "다음 요약", "citations": [pinned, EXTERNAL]}
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        article_id, (first, second) = add_legacy_article(connection, db.brain_id, [initial, latest])
        deleted_id, _ = add_legacy_article(connection, db.brain_id, [initial], deleted_at=UPDATED)
        topic = str(uuid4())
        connection.execute("""INSERT INTO concepts (id, brain_id, name, state_version, created_at, updated_at)
                              VALUES (?, ?, '자료 구조', 1, ?, ?)""", (topic, db.brain_id, CREATED, EDITED))
        connection.execute("INSERT INTO revision_concepts VALUES (?, ?, ?)", (second, topic, db.brain_id))
        connection.execute("""INSERT INTO provenance_links (id, brain_id, derived_revision_id, source_capture_id,
            source_revision_id) VALUES (?, ?, ?, ?, ?)""",
            (str(uuid4()), db.brain_id, downstream["revision_id"], article_id, first))
        build, profile = connection.execute("SELECT id, profile_id FROM index_builds").fetchone()
        connection.execute("""INSERT INTO capture_index_states
            (capture_id, build_id, revision_id, index_generation, status, updated_at)
            VALUES (?, ?, ?, 3, 'ready', ?)""", (article_id, build, second, EDITED))
        connection.execute("""INSERT INTO index_jobs
            (id, capture_id, build_id, profile_id, revision_id, index_generation, operation, status, attempt_count,
             available_at, lease_token) VALUES (?, ?, ?, ?, ?, 3, 'upsert', 'running', 1, ?, 'old-lease')""",
            (str(uuid4()), article_id, build, profile, second, EDITED))
        connection.execute("""INSERT INTO concept_enrichment_jobs
            (id, brain_id, capture_id, requested_revision_id, expected_state_version, policy_version, status,
             unresolved_hints, attempt_count, available_at, created_at)
            VALUES (?, ?, ?, ?, 3, 'concept-v2', 'pending', '[]', 0, ?, ?)""",
            (str(uuid4()), db.brain_id, article_id, second, EDITED, EDITED))

    try:
        migrate_database(path)
        migrate_database(path)
        articles = ArticleService(records)
        assert [row["id"] for row in articles.list()["items"]] == [article_id]
        current = articles.get(article_id)
        assert (current["revision_id"], current["revision_no"], current["created_at"], current["updated_at"]) == (
            second, 2, CREATED, UPDATED)
        assert (current["title"], current["body_markdown"], current["summary"], current["topics"], current["citations"]) == (
            "제목 2", "본문 2 [1](#cite-1)", latest["summary"], ["자료 구조"], [pinned, EXTERNAL])
        assert records.source_get(current["citations"][0]["source"])["text"] == "복습할"
        original = articles.get(article_id, first)
        assert (original["revision_no"], original["citations"], original["updated_at"]) == (1, [EXTERNAL], CREATED)
        assert_error("NOT_FOUND", lambda: articles.get(deleted_id))
        assert_error("NOT_FOUND", lambda: records.get(article_id))
        assert_error("NOT_FOUND", lambda: records.get(article_id, first))
        assert_error("NOT_FOUND", lambda: records.source_get({"capture_id": article_id, "revision_id": first}))
        assert records.get(downstream["id"])["sources"][0]["availability"] == "unavailable"
        assert {row["id"] for row in records.list()["items"]} == {source["id"], downstream["id"]}
        assert records.get(source["id"]) == source
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT deleted_at FROM articles WHERE id=?", (deleted_id,)).fetchone() == (UPDATED,)
            assert connection.execute("SELECT status,index_generation FROM capture_index_states WHERE capture_id=?",
                                      (article_id,)).fetchone() == ("excluded", 4)
            jobs = connection.execute("""SELECT operation, status, lease_token, index_generation FROM index_jobs
                                         WHERE capture_id=? ORDER BY operation""", (article_id,)).fetchall()
            assert jobs == [("remove", "pending", None, 4), ("upsert", "superseded", None, 3)]
            assert connection.execute("SELECT status FROM concept_enrichment_jobs WHERE capture_id=?",
                                      (article_id,)).fetchone() == ("superseded",)
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute("UPDATE article_revisions SET title='다른 제목' WHERE id=?", (first,))
    finally:
        db.close()


def test_legacy_index_hits_are_hidden_before_the_removal_worker_runs(tmp_path):
    path = legacy_database(tmp_path)
    db = Database(path, initialize=False)
    records = RecordService(db)
    search = SearchService(records, tmp_path / "lance", embedding=TestEmbedding())
    try:
        with sqlite3.connect(path) as connection:
            article_id, _ = add_legacy_article(connection, db.brain_id, [{"summary": "첫 요약", "citations": [EXTERNAL]}])
        search.prepare()
        search.process_jobs()
        assert search.search({"query": "본문"})["items"][0]["source"]["capture_id"] == article_id
        assert search.context({"query": "본문"})["items"]
        assert {row["id"] for row in search.home_graph()["nodes"]} == {article_id}

        migrate_database(path)
        assert search._table.count_rows() > 0
        assert search.search({"query": "본문"})["items"] == []
        assert search.context({"query": "본문"})["items"] == []
        assert search.home_graph()["nodes"] == []
        assert_error("NOT_FOUND", lambda: search.neighbors(article_id))
        assert search.process_jobs()["processed"] == 1
        assert search._table.count_rows() == 0
    finally:
        db.close()


def test_split_preserves_relation_endpoints_and_keeps_deleted_mixed_records_hidden(tmp_path):
    path = legacy_database(tmp_path)
    db = Database(path, initialize=False)
    metadata = {"summary": "발행본", "citations": [EXTERNAL]}
    try:
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            owner, (raw, published) = add_legacy_article(connection, db.brain_id, [None, metadata])
            deleted_owner, (deleted_raw, _) = add_legacy_article(connection, db.brain_id, [None, metadata], deleted_at=UPDATED)
            mixed = str(uuid4())
            ordinary = str(uuid4())
            for relation, source, target, evidence in ((mixed, raw, published, published), (ordinary, raw, raw, raw)):
                connection.execute("""INSERT INTO relations (id, brain_id, relation_type, source_capture_id,
                    source_revision_id, target_capture_id, target_revision_id, evidence_capture_id,
                    evidence_revision_id, created_at) VALUES (?, ?, 'related_to', ?, ?, ?, ?, ?, ?, ?)""",
                    (relation, db.brain_id, owner, source, owner, target, owner, evidence, UPDATED))

        migrate_database(path)
        records = RecordService(db)
        articles = ArticleService(records)
        assert records.get(owner)["revision_id"] == raw
        assert articles.get(owner)["revision_id"] == published
        assert_error("NOT_FOUND", lambda: records.get(deleted_owner, deleted_raw))
        assert_error("NOT_FOUND", lambda: articles.get(deleted_owner))
        assert [relation["id"] for relation in records.relation_list(capture_id=owner)["items"]] == [ordinary]
        with sqlite3.connect(path) as connection:
            archive, = connection.execute("SELECT capture_id FROM capture_revisions WHERE id=?", (published,)).fetchone()
            assert archive != owner
            assert connection.execute("SELECT deleted_at FROM captures WHERE id=?", (archive,)).fetchone()[0]
            assert connection.execute("""SELECT source_capture_id, target_capture_id, evidence_capture_id
                                         FROM relations WHERE id=?""", (mixed,)).fetchone() == (owner, archive, archive)
            assert connection.execute("SELECT deleted_at FROM captures WHERE id=?", (deleted_owner,)).fetchone() == (UPDATED,)
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute("UPDATE capture_revisions SET title='변경' WHERE id=?", (raw,))
            assert connection.execute("""SELECT count(*) FROM sqlite_master WHERE type='trigger'
                AND name='immutable_provenance_links_update'""").fetchone() == (1,)
    finally:
        db.close()


def test_failed_article_copy_rolls_back_schema_and_capture_changes(tmp_path):
    path = legacy_database(tmp_path)
    db = Database(path, initialize=False)
    with sqlite3.connect(path) as connection:
        add_legacy_article(connection, db.brain_id, [{"citations": [EXTERNAL]}])
    db.close()
    with pytest.raises(IntegrityError, match="summary"):
        migrate_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0003",)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'article%'").fetchall() == []
        assert connection.execute("SELECT deleted_at, index_generation FROM captures").fetchall() == [(None, 3)]
