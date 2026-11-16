"""Opt-in integration test: KURE_TEST_MODEL_PATH points to the pinned local snapshot."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from cache_me.chunking import MarkdownChunker
from cache_me.db import Database
from cache_me.embedding import KureEmbedding
from cache_me.records import DomainError, RecordService
from cache_me.search import SearchService


@pytest.mark.skipif(not os.environ.get("KURE_TEST_MODEL_PATH"), reason="explicit pinned KURE-v2 model path required")
def test_real_cpu_embeddings_full_body_hybrid_and_current_generation(tmp_path):
    db = Database(tmp_path / "canonical.sqlite3")
    records = RecordService(db)
    search = SearchService(records, tmp_path / "lance", model_path=os.environ["KURE_TEST_MODEL_PATH"])
    body = "# 분산 시스템\n" + ("데이터베이스 트랜잭션은 여러 변경의 원자성을 보장합니다.\n\n" * 100) + "# 동물 지식\n오리너구리는 알을 낳는 포유류이며 호주에 살고 있습니다."
    capture = records.create({"request_id": str(uuid4()), "title": "학습 노트", "body_markdown": body})["capture"]
    assert search.prepare()["ready"]
    assert search.embedding.model.device.type == "cpu"
    chunks = MarkdownChunker(search.embedding).split(body, "학습 노트")
    assert len(chunks) > 1
    assert chunks[-1].body_end == len(body)
    assert all(search.embedding.count_tokens(c.embedding_text) <= 512 for c in chunks)
    assert search.process_jobs()["failed"] == 0
    hit = search.search({"query": "알을 낳는 포유류가 있나요?"})["items"][0]
    assert hit["source"]["capture_id"] == capture["id"]
    assert "오리너구리" in hit["excerpt"]
    context = search.context({"query": "오리너구리는 어디에 사나요?"})
    assert any("호주" in item["text"] for item in context["items"])
    with pytest.raises(DomainError) as error:
        search.search({"query": "부정 조건과 제외 조건을 잃어버리면 안 됩니다. " * 30})
    assert error.value.code == "QUERY_TOO_LONG"
    assert error.value.details["token_count"] > 64
    changed = records.update({"request_id": str(uuid4()), "capture_id": capture["id"],
        "expected_revision_id": capture["revision_id"], "expected_state_version": capture["state_version"],
        "changes": {"body_markdown": "새 기록은 바다거북에 관한 내용입니다."}})["capture"]
    assert search.search({"query": "오리너구리"})["items"] == []
    search.process_jobs()
    hits = search.search({"query": "바다거북"})["items"]
    assert hits[0]["source"]["revision_id"] == changed["revision_id"]
    assert "오리너구리" not in hits[0]["excerpt"]
    db.close()
