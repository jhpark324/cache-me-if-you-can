"""Real SQLite relation races with a deterministic, offline answer model."""
import asyncio
import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agent_fakes import request_value, search_call, tool_values

from cache_me.auth import AuthError
from cache_me.db import Database
from cache_me.questions import QuestionInput, QuestionService
from cache_me.records import DomainError, RecordService
from cache_me.schemas import CreateCaptureInput, RelationInput, RetractRelationInput, SourceRef, UpdateCaptureInput


@pytest.fixture
def knowledge(tmp_path):
    db = Database(tmp_path / "relations.sqlite3")
    records = RecordService(db)
    first = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="이전에는 작업 알림을 선호했다."))["capture"]
    second = records.create(CreateCaptureInput(request_id=uuid4(), body_markdown="현재는 집중을 위해 작업 알림을 끄기로 했다."))["capture"]
    def source(capture):
        return SourceRef(capture_id=capture["id"], revision_id=capture["revision_id"], body_start=0, body_end=len(capture["body_markdown"]))
    relation = records.relation_create(RelationInput(request_id=uuid4(), relation_type="supersedes", source=source(second), target=source(first),
        evidence=source(second), scope_note="사용자의 작업 중 알림 선호", evidence_note="작업 알림을 끄기로 명시적으로 변경했다."))
    yield records, first, second, relation
    db.close()


def service_for(records, first, second, relation, *, during_answer=None):
    class Search:
        def context(self, request):
            view = records.current_relation(relation["id"])
            return {"items": [
                {"source": view["source"], "text": second["body_markdown"]},
                {"source": view["target"], "text": first["body_markdown"]},
            ], "relations": [view], "limitations": []}

    class OfflineModel:
        def __init__(self):
            self.used_relations = None

        async def generate_message(self, messages, instructions, *, tools=None, expected_model=None):
            if not any(isinstance(message, ToolMessage) for message in messages):
                units = request_value(messages)['source_units']
                return AIMessage(content='', tool_calls=[search_call(unit['query'], [unit['unit_id']]) for unit in units])
            self.used_relations = [relation for value in tool_values(messages) for relation in value.get('relations', [])]
            if during_answer:
                during_answer()
            return AIMessage(content=json.dumps({'parts': [{'kind': 'stored_knowledge',
                'text': '명시적 대체 관계에 따라 현재는 작업 알림을 끄는 쪽입니다.', 'evidence_ids': [0, 1]}], 'evidence_status': 'found'}))

        async def generate(self, prompt, instructions):
            return json.dumps({"supported_part_ids": [part["part_id"] for part in json.loads(prompt)["parts"]]})
    model = OfflineModel()
    return QuestionService(Search(), records, model), model


def retract(records, relation):
    return records.relation_retract(RetractRelationInput(request_id=uuid4(), relation_id=relation["id"], withdrawal_reason="기록 사이의 대체 관계를 잘못 연결했다."))


def question():
    return QuestionInput(request_id=uuid4(), question="현재 작업 중 알림을 어떻게 설정하기로 했어?")


def test_retraction_during_answer_invalidates_even_when_capture_versions_are_unchanged(knowledge):
    records, first, second, relation = knowledge
    service, model = service_for(*knowledge, during_answer=lambda: retract(records, relation))
    with pytest.raises(AuthError) as caught:
        asyncio.run(service.run(question()))
    assert caught.value.code == "ANSWER_INVALIDATED"
    assert model.used_relations[0]["id"] == relation["id"]
    for original in (first, second):
        current = records.get(original["id"])
        assert current["revision_id"] == original["revision_id"]
        assert current["state_version"] == original["state_version"]


def test_relationship_snapshot_is_rechecked_after_answer_generation(knowledge):
    records, first, second, relation = knowledge
    service, _ = service_for(*knowledge)
    result = asyncio.run(service.run(question()))
    assert result["_relations"][0]["id"] == relation["id"]
    service.revalidate(result)
    retract(records, relation)
    with pytest.raises(AuthError) as caught:
        service.revalidate(result)
    assert caught.value.code == "ANSWER_INVALIDATED"


def test_current_relation_uses_equivalent_current_references(knowledge):
    records, first, second, relation = knowledge
    amended = records.update(UpdateCaptureInput(request_id=uuid4(), capture_id=second["id"], expected_revision_id=second["revision_id"], expected_state_version=second["state_version"], changes={"kinds": ["context"]}))["capture"]
    current = records.current_relation(relation["id"])
    assert current["source"]["revision_id"] == amended["revision_id"]
    assert current["evidence"]["revision_id"] == amended["revision_id"]
    assert current["target"]["revision_id"] == first["revision_id"]
    records.update(UpdateCaptureInput(request_id=uuid4(), capture_id=second["id"], expected_revision_id=amended["revision_id"], expected_state_version=amended["state_version"], changes={"body_markdown": "새로운 조건"}))
    with pytest.raises(DomainError) as caught:
        records.current_relation(relation["id"])
    assert caught.value.code == "NOT_FOUND"
