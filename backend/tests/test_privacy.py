import json

import pytest
from langchain.agents.middleware import PIIMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from cache_me.privacy import (
    pii_middleware,
    sanitize_ai_message,
    sanitize_messages,
    sanitize_text,
)


@pytest.mark.parametrize(("raw", "replacement"), [
    ("learner@example.com", "[REDACTED_EMAIL]"),
    ("4111 1111 1111 1111", "[REDACTED_CREDIT_CARD]"),
    ("192.0.2.17", "[REDACTED_IP]"),
])
def test_builtin_detectors_preserve_korean_context(raw, replacement):
    assert sanitize_text(f"공부 기록: {raw} 다음 설명") == f"공부 기록: {replacement} 다음 설명"


def test_factory_enables_builtin_input_output_and_tool_result_hooks():
    first, second = pii_middleware(), pii_middleware()
    assert [rule.pii_type for rule in first] == ["email", "credit_card", "ip"]
    assert all(type(rule) is PIIMiddleware for rule in first)
    assert all(a is not b for a, b in zip(first, second))
    for rule in first:
        assert rule.strategy == "redact"
        assert rule.apply_to_input and rule.apply_to_output and rule.apply_to_tool_results


def test_plain_and_json_payloads_keep_source_offsets_and_ids():
    value = {
        "question": "learner@example.com 의 기록은?",
        "evidence": [{"text": "카드 4111 1111 1111 1111", "source": {
            "capture_id": "a012b345-12cd-432a-8f00-0123a456b789",
            "revision_id": "b012b345-12cd-432a-8f00-0123a456b789",
            "body_start": 17, "body_end": 211,
        }}],
    }
    raw = json.dumps(value, ensure_ascii=True).replace("@", "\\u0040")
    clean = json.loads(sanitize_text(raw))
    assert clean["question"] == "[REDACTED_EMAIL] 의 기록은?"
    assert clean["evidence"][0]["text"] == "카드 [REDACTED_CREDIT_CARD]"
    assert clean["evidence"][0]["source"] == value["evidence"][0]["source"]
    assert value["evidence"][0]["text"] == "카드 4111 1111 1111 1111"
    assert sanitize_text('{"malformed":"learner@example.com"') == '{"malformed":"[REDACTED_EMAIL]"'


def test_all_message_turns_cleaned_without_mutating_originals():
    originals = [
        SystemMessage(content="주소 learner@example.com"),
        HumanMessage(content="먼저 learner@example.com"),
        AIMessage(content="이전 답 learner@example.com", tool_calls=[{
            "id": "call_first", "name": "search_knowledge", "args": {"query": "learner@example.com"},
        }]),
        ToolMessage(content='{"text":"learner@example.com"}', tool_call_id="call_first"),
        HumanMessage(content="이제 192.0.2.17"),
        AIMessage(content="", tool_calls=[{
            "id": "call_second", "name": "search_knowledge", "args": {"query": "192.0.2.17"},
        }]),
        ToolMessage(content="새 근거 4111 1111 1111 1111", tool_call_id="call_second"),
    ]
    before = [message.model_dump() for message in originals]
    clean = sanitize_messages(originals)
    serialized = json.dumps([message.model_dump() for message in clean], ensure_ascii=False)
    for pii in ("learner@example.com", "192.0.2.17", "4111 1111 1111 1111"):
        assert pii not in serialized
    assert [message.model_dump() for message in originals] == before
    assert clean[3].tool_call_id == "call_first"
    assert clean[5].tool_calls[0]["id"] == "call_second"


def test_ai_tool_arguments_and_blocks_cleaned_before_execution():
    original = AIMessage(
        content=[{"type": "text", "text": "메일 learner@example.com"}],
        tool_calls=[{
            "id": "call_1", "name": "search_knowledge",
            "args": {"query": "learner@example.com", "nested": ["192.0.2.17"], "evidence_id": 3},
        }],
        invalid_tool_calls=[{
            "id": "call_bad", "name": "search_knowledge", "args": '{"query":"learner@example.com"', "error": None,
        }],
    )
    clean = sanitize_ai_message(original)
    assert clean.content[0]["text"] == "메일 [REDACTED_EMAIL]"
    assert clean.tool_calls[0]["args"] == {"query": "[REDACTED_EMAIL]", "nested": ["[REDACTED_IP]"], "evidence_id": 3}
    assert clean.invalid_tool_calls[0]["args"] == '{"query":"[REDACTED_EMAIL]"'
    assert original.tool_calls[0]["args"]["query"] == "learner@example.com"


def test_actual_middleware_redacts_user_tool_and_output_state():
    state = {"messages": [
        HumanMessage(content="learner@example.com", id="user"),
        AIMessage(content="", id="call", tool_calls=[{"id": "t1", "name": "search", "args": {}}]),
        ToolMessage(content="192.0.2.17", id="result", tool_call_id="t1"),
    ]}
    for rule in pii_middleware():
        state = rule.before_model(state, Runtime()) or state
    assert state["messages"][0].content == "[REDACTED_EMAIL]"
    assert state["messages"][2].content == "[REDACTED_IP]"
    state["messages"].append(AIMessage(content="4111 1111 1111 1111", id="answer"))
    for rule in pii_middleware():
        state = rule.after_model(state, Runtime()) or state
    assert state["messages"][-1].content == "[REDACTED_CREDIT_CARD]"


def test_rule_scope_is_explicit_and_safe_text_is_unchanged():
    text = '민수 010-1234-5678 https://example.com 공부 기록'
    assert sanitize_text(text) == text
    assert sanitize_text('카드 검증 실패 4111 1111 1111 1112') == '카드 검증 실패 4111 1111 1111 1112'
    assert sanitize_text('{ "evidence_id": 2, "text": "기록" }') == '{ "evidence_id": 2, "text": "기록" }'
    assert sanitize_text(sanitize_text('learner@example.com 192.0.2.17')) == '[REDACTED_EMAIL] [REDACTED_IP]'


def test_builtin_email_detector_has_known_korean_particle_limit():
    # Document the upstream detector boundary instead of silently claiming all
    # Korean PII is covered or introducing an unrequested custom detector.
    assert sanitize_text('learner@example.com의 기록') == 'learner@example.com의 기록'


def test_json_keys_and_escaped_nested_json_cannot_bypass_builtin_rules():
    payload = {
        "learner@example.com": "노트",
        "nested": '{"other\\u0040example.com":"192.0.2.17"}',
        "source": {"capture_id": "a012b345-12cd-432a-8f00-0123a456b789", "body_start": 17},
    }
    raw = json.dumps(payload, ensure_ascii=False).replace("learner@", "learner\\u0040")
    clean = json.loads(sanitize_text(raw))
    assert clean["[REDACTED_EMAIL]"] == "노트"
    assert json.loads(clean["nested"]) == {"[REDACTED_EMAIL]": "[REDACTED_IP]"}
    assert clean["source"] == payload["source"]
    assert "learner@example.com" in payload


def test_redacted_key_collisions_keep_every_value_and_are_idempotent():
    payload = {"one@example.com": "첫째", "two@example.com": "둘째", "[REDACTED_EMAIL]": "셋째"}
    clean = sanitize_text(json.dumps(payload, ensure_ascii=False))
    assert json.loads(clean) == {"[REDACTED_EMAIL]": "첫째", "[REDACTED_EMAIL]#2": "둘째", "[REDACTED_EMAIL]#3": "셋째"}
    assert sanitize_text(clean) == clean
