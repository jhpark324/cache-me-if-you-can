"""Six public types, immutable historical values, and exact legacy request replay."""
import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.client import Client
from pydantic import ValidationError
from sqlalchemy import select

from second_brain.api import install_error_handlers, router
from second_brain.db import utcnow
from second_brain.mcp_server import create_mcp
from second_brain.models import MutationReceipt, RevisionKind
from second_brain.questions import QuestionInput
from second_brain.record_kinds import RECORD_KINDS
from second_brain.records import DomainError, digest
from second_brain.schemas import CaptureChanges, CreateCaptureInput, MergeCapturesInput, UpdateCaptureInput
from second_brain.search import ContextInput, GraphInput, SearchInput
from test_search import create, services


def raw_kinds(records, revision_id):
    with records.db.read() as session:
        return set(session.scalars(select(RevisionKind.kind).where(RevisionKind.revision_id == revision_id)))


def historical_kinds(records, capture, kinds):
    # Fixture for an old database. Only INSERT previously absent rows; never
    # disable immutability triggers or update a historical revision.
    with records.db.write() as session:
        session.add_all(RevisionKind(revision_id=capture["revision_id"], kind=kind) for kind in kinds)
    return capture


def historical_receipt(records, operation, payload, capture):
    with records.db.write() as session:
        session.add(MutationReceipt(principal_scope=records.principal_scope,
            request_id=payload["request_id"], operation=operation,
            request_fingerprint=digest(payload), capture_id=capture["id"],
            committed_revision_id=capture["revision_id"], committed_state_version=capture["state_version"],
            outcome="committed", created_at=utcnow()))


def expected(capture):
    return {"capture_id": capture["id"], "expected_revision_id": capture["revision_id"],
            "expected_state_version": capture["state_version"]}


@pytest.mark.parametrize("alias,kind", [("procedure", "knowledge"), ("reflection", "episode"), ("plan", "idea")])
def test_alias_write_normalizes_and_collapses_public_and_storage(services, alias, kind):
    records, _, _ = services
    payload = {"request_id": str(uuid4()), "body_markdown": "직접 요청한 기록", "kinds": [alias, kind]}
    result = records.create(payload)
    assert result["capture"]["kinds"] == [kind]
    assert raw_kinds(records, result["capture"]["revision_id"]) == {kind}
    assert records.create(payload | {"kinds": [kind]})["replayed"]
    assert records.create(payload)["replayed"]


@pytest.mark.parametrize("alias,kind", [("procedure", "knowledge"), ("reflection", "episode"), ("plan", "idea")])
def test_historical_reads_filters_context_and_graph_use_current_labels(services, alias, kind):
    records, search, _ = services
    capture = historical_kinds(records, create(records, "학습 단계와 회고"), [alias, kind])
    source = {"capture_id": capture["id"], "revision_id": capture["revision_id"]}
    search.prepare()
    search.process_jobs()
    assert records.get(capture["id"])["kinds"] == [kind]
    assert records.source_get(source)["capture"]["kinds"] == [kind]
    for filter_kind in (alias, kind):
        assert [item["kinds"] for item in records.list(kinds=[filter_kind])["items"]] == [[kind]]
        hits = search.search({"query": "학습", "kinds": [filter_kind]})["items"]
        assert {item["source"]["capture_id"] for item in hits} == {capture["id"]}
        context = search.context({"query": "학습", "kinds": [filter_kind]})
        assert context["items"] and all(item["record_kinds"] == [kind] for item in context["items"])
        graph = search.home_graph({"kinds": [filter_kind]})
        assert [node["kinds"] for node in graph["nodes"] if node["kind"] == "capture"] == [[kind]]
    neighbors = search.neighbors(capture["id"])
    assert [node["kinds"] for node in neighbors["nodes"] if node["kind"] == "capture"] == [[kind]]
    assert raw_kinds(records, capture["revision_id"]) == {alias, kind}


def test_unrelated_edit_copies_canonical_kinds_and_preserves_historical_evidence(services):
    records, _, _ = services
    old = historical_kinds(records, create(records, "원문 🧠 그대로", nodes=[
        {"kind": "action", "body_start": 0, "body_end": 2, "origin": "user_report"}]),
        ["procedure", "knowledge", "reflection", "plan"])
    source = old["nodes"][0]["source"]
    derived = create(records, "위 기록에 근거한 설명", sources=[source])
    # Metadata-only edit creates a new revision and retains source equivalence.
    changed = records.update({"request_id": str(uuid4()), **expected(old),
        "changes": {"concept_hints": ["개발"]}})["capture"]
    assert changed["kinds"] == ["episode", "idea", "knowledge"]
    assert raw_kinds(records, changed["revision_id"]) == {"episode", "idea", "knowledge"}
    assert raw_kinds(records, old["revision_id"]) == {"procedure", "knowledge", "reflection", "plan"}
    assert changed["body_markdown"] == old["body_markdown"]
    assert records.source_get(source)["text"] == "원문"
    assert records.source_get(source)["capture"]["kinds"] == changed["kinds"]
    assert records.source_status(source)["review_state"] == "valid"
    assert records.get(derived["id"])["review_state"] == "valid"
    records.update({"request_id": str(uuid4()), **expected(changed), "changes": {"body_markdown": "사실 변경"}})
    assert records.source_status(source)["reason"] == "source_changed"


@pytest.mark.parametrize("operation", ["create", "update", "merge"])
def test_historical_receipt_replays_exact_legacy_payload_and_committed_body(services, operation):
    records, _, _ = services
    old = create(records, "이전 본문")
    kinds = ["procedure", "knowledge", "reflection"]
    if operation == "create":
        committed = historical_kinds(records, create(records, "당시 본문"), kinds)
        payload = {"request_id": str(uuid4()), "body_markdown": "당시 본문", "kinds": kinds}
        model = CreateCaptureInput
    else:
        committed = records.update({"request_id": str(uuid4()), **expected(old),
            "changes": {"body_markdown": "당시 본문"}})["capture"]
        historical_kinds(records, committed, kinds)
        if operation == "update":
            payload = {"request_id": str(uuid4()), **expected(old),
                "changes": {"body_markdown": "당시 본문", "kinds": kinds}}
            model = UpdateCaptureInput
        else:
            source = create(records, "합치기 근거")
            payload = {"request_id": str(uuid4()), "target_capture_id": old["id"],
                "expected_revision_id": old["revision_id"], "expected_state_version": old["state_version"],
                "sources": [{"capture_id": source["id"], "revision_id": source["revision_id"]}],
                "merged_body_markdown": "당시 본문", "kinds": kinds}
            model = MergeCapturesInput
    historical_receipt(records, "capture_" + operation, payload, committed)
    records.update({"request_id": str(uuid4()), **expected(committed), "changes": {"body_markdown": "이후 본문"}})
    request = model.model_validate(payload)
    # Models are revalidated by the service, as when HTTP/MCP has already parsed them.
    result = getattr(records, operation)(request)
    assert result["replayed"]
    assert result["capture"]["body_markdown"] == "당시 본문"
    assert result["capture"]["revision_id"] == committed["revision_id"]
    assert result["capture"]["kinds"] == ["episode", "knowledge"]
    assert raw_kinds(records, committed["revision_id"]) == set(kinds)
    if operation == "update":
        changed = request.model_copy(update={"changes": request.changes.model_copy(update={"body_markdown": "다른 내용"})})
    else:
        field = "body_markdown" if operation == "create" else "merged_body_markdown"
        changed = request.model_copy(update={field: "다른 내용"})
    with pytest.raises(DomainError, match="같은 request_id") as error:
        getattr(records, operation)(changed)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    if operation == "create":
        with pytest.raises(DomainError):
            records.create(request.model_copy(update={"kinds": ["artifact"]}))


@pytest.mark.parametrize("schema,payload", [
    (CreateCaptureInput, {"request_id": str(uuid4()), "body_markdown": "본문"}),
    (CaptureChanges, {}), (SearchInput, {"query": "검색"}),
    (ContextInput, {"query": "검색"}), (GraphInput, {}),
    (QuestionInput, {"request_id": str(uuid4()), "question": "질문"}),
])
def test_input_schemas_accept_aliases_but_reject_unknown_types(schema, payload):
    assert schema.model_validate(payload | {"kinds": ["plan", "idea"]}).kinds == ["idea"]
    with pytest.raises(ValidationError):
        schema.model_validate(payload | {"kinds": ["made_up"]})


def assert_six_kind_enums(schema):
    found = []
    def visit(value):
        if isinstance(value, dict):
            if "enum" in value and "knowledge" in value["enum"]:
                found.append(set(value["enum"]))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(schema)
    assert found and all(kinds == RECORD_KINDS for kinds in found)


def test_http_and_mcp_publish_six_types_and_accept_legacy_requests(services):
    records, search, _ = services
    app = FastAPI()
    app.state.records = records
    app.include_router(router)
    install_error_handlers(app)
    with TestClient(app) as client:
        assert_six_kind_enums(client.get("/openapi.json").json())
        result = client.post("/api/v1/captures", json={"request_id": str(uuid4()),
            "body_markdown": "HTTP 저장", "kinds": ["procedure", "knowledge"]})
        assert result.status_code == 200
        assert result.json()["data"]["capture"]["kinds"] == ["knowledge"]
        listed = client.get("/api/v1/captures", params={"kinds": "procedure"})
        assert listed.status_code == 200 and len(listed.json()["data"]["items"]) == 1
        assert client.get("/api/v1/captures", params={"kinds": "unknown"}).status_code == 422

    async def run():
        async with Client(create_mcp(records, search)) as client:
            tools = (await client.list_tools()).tools
            for name in ("capture_create", "capture_update", "capture_merge", "capture_list", "knowledge_search", "knowledge_context"):
                assert_six_kind_enums(next(tool.input_schema for tool in tools if tool.name == name))
            payload = {"request_id": str(uuid4()), "body_markdown": "MCP 저장", "kinds": ["reflection", "episode"]}
            created = await client.call_tool("capture_create", {"input": payload})
            assert not created.is_error
            assert created.structured_content["data"]["capture"]["kinds"] == ["episode"]
            listed = await client.call_tool("capture_list", {"kinds": ["reflection"]})
            assert not listed.is_error and len(listed.structured_content["data"]["items"]) == 1
    asyncio.run(run())
