"""Topic links can recover evidence outside the ordinary text candidate budget."""
from uuid import uuid4

from test_record_filter_contract import assign
from test_search import create, delete, services


def test_alias_recovers_node_evidence_outside_text_candidates(services):
    records, search, _ = services
    topic = records.concept_create({"request_id": str(uuid4()), "name": "캐시 만료", "aliases": ["TTL"]})
    for _ in range(41):
        create(records, "TTL", kinds=["episode"])
    intro = "서론에는 다른 기록의 배경을 적었습니다. " * 35 + "\n\n"
    evidence = "만료된 항목은 읽기 시점에 버린다."
    capture = create(records, intro + evidence, kinds=["procedure"], nodes=[{
        "kind": "action", "body_start": len(intro), "body_end": len(intro + evidence),
    }, {"kind": "explanation", "body_start": 0, "body_end": len(intro + evidence)}])
    search.prepare()
    assert search.process_jobs(limit=100)["failed"] == 0
    assert capture["id"] not in {
        hit["source"]["capture_id"] for hit in search.search({"query": "ttl", "limit": 10})["items"]
    }

    capture = assign(records, capture, node=[topic["id"]])
    assert search.process_jobs()["failed"] == 0
    hits = search.search({"query": "ttl", "limit": 10})["items"]
    recovered = [hit for hit in hits if hit["source"]["capture_id"] == capture["id"]]
    assert len(recovered) == 1
    assert recovered[0]["excerpt"] == evidence
    assert recovered[0]["matched_spans"] == [{"body_start": len(intro), "body_end": len(intro + evidence)}]
    assert capture["nodes"][0]["id"] in recovered[0]["matched_node_ids"]
    context = search.context({"query": "ttl"})
    assert any(item["source"]["capture_id"] == capture["id"] and item["text"] == evidence
               for item in context["items"])
    assert all(item["text"] == evidence for item in context["items"]
               if item["source"]["capture_id"] == capture["id"])

    assert capture["id"] not in {
        hit["source"]["capture_id"] for hit in search.search({"query": "ttl", "kinds": ["episode"]})["items"]
    }
    delete(records, capture)
    assert capture["id"] not in {
        hit["source"]["capture_id"] for hit in search.search({"query": "ttl"})["items"]
    }


def test_embedded_or_ambiguous_alias_keeps_original_search(services):
    records, search, _ = services
    topic = records.concept_create({"request_id": str(uuid4()), "name": "인공지능"})
    assign(records, create(records, "모델 활용 기록"), parent=[topic["id"]])
    create(records, "retail 산업의 기록")
    search.prepare()
    assert search.process_jobs()["failed"] == 0
    retail_before = search.search({"query": "retail"})
    ai_before = search.search({"query": "AI"})

    records.concept_update({"request_id": str(uuid4()), "concept_id": topic["id"],
        "expected_state_version": topic["state_version"], "changes": {"aliases": ["AI"]}})
    assert search.search({"query": "retail"}) == retail_before
    records.concept_create({"request_id": str(uuid4()), "name": "Adobe Illustrator", "aliases": ["AI"]})
    assert search.search({"query": "AI"}) == ai_before
