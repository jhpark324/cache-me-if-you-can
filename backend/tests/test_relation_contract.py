"""Keep web relationship choices aligned with the HTTP and storage contracts."""
from pathlib import Path
import re
from typing import get_args
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from cache_me.api import install_error_handlers, router
from cache_me.db import Database
from cache_me.models import Relation
from cache_me.records import RecordService
from cache_me.schemas import RelationInput, RelationType


def frontend_relation_types(source):
    # Read only the exported choices, not unrelated object keys in types.ts.
    block = re.search(r"^export const RELATION_LABELS = \{(.*?)^\} as const;",
                      source, re.MULTILINE | re.DOTALL)
    assert block is not None, "RELATION_LABELS declaration was not found"
    choices = re.findall(r'^\s*(\w+):\s*"[^"\n]+",?\s*$', block[1], re.MULTILINE)
    assert choices and len(choices) == len(set(choices))
    return tuple(choices)


WEB_RELATION_TYPES = frontend_relation_types(
    (Path(__file__).resolve().parents[2] / "frontend/src/types.ts").read_text(encoding="utf-8"))


@pytest.fixture
def relation_api(tmp_path):
    db = Database(tmp_path / "relations.sqlite3")
    app = FastAPI()
    app.state.records = RecordService(db)
    app.include_router(router)
    install_error_handlers(app)
    try:
        with TestClient(app) as client:
            yield client, db
    finally:
        db.close()


def test_web_relation_choices_match_input_and_published_http_contract(relation_api):
    client, _ = relation_api
    expected = set(get_args(RelationType))
    assert set(WEB_RELATION_TYPES) == expected
    assert set(RelationInput.model_json_schema()["properties"]["relation_type"]["enum"]) == expected
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["RelationInput"]
    assert set(schema["properties"]["relation_type"]["enum"]) == expected


@pytest.mark.parametrize("relation_type", WEB_RELATION_TYPES)
def test_every_web_relation_choice_can_be_created_persisted_and_read(relation_api, relation_type):
    client, db = relation_api

    def create_source(body):
        response = client.post("/api/v1/captures", json={
            "request_id": str(uuid4()), "body_markdown": body})
        assert response.status_code == 200, response.json()
        capture = response.json()["data"]["capture"]
        return {"capture_id": capture["id"], "revision_id": capture["revision_id"],
                "body_start": 0, "body_end": len(body)}

    source = create_source("새 조건을 설명하는 합성 근거")
    target = create_source("이전에 저장한 합성 조건")
    payload = {"request_id": str(uuid4()), "relation_type": relation_type,
               "source": source, "target": target, "evidence": source,
               "scope_note": "합성 예제의 작업 조건", "evidence_note": "본문에 명시한 조건 변경"}
    response = client.post("/api/v1/relations", json=payload)
    assert response.status_code == 200, response.json()
    relation = response.json()["data"]
    assert relation["relation_type"] == relation_type

    with db.read() as session:
        stored = session.get(Relation, relation["id"])
        assert stored is not None and stored.relation_type == relation_type
        for prefix in ("source", "target", "evidence"):
            for field, value in payload[prefix].items():
                assert getattr(stored, f"{prefix}_{field}") == value
        assert stored.scope_note == payload["scope_note"]
        assert stored.evidence_note == payload["evidence_note"]

    listed = client.get("/api/v1/relations", params={
        "capture_id": source["capture_id"], "relation_type": relation_type})
    assert listed.status_code == 200, listed.json()
    items = listed.json()["data"]["items"]
    assert [(item["id"], item["relation_type"]) for item in items] == [(relation["id"], relation_type)]
