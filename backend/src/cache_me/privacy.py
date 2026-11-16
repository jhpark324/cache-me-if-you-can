"""Built-in PII redaction at ephemeral model boundaries, never canonical storage.

The agent uses the actual LangChain middleware. The boundary helpers also cover
older model-only callers and tool-call arguments, which PIIMiddleware's state
hooks do not inspect. No additional detector or semantic classification runs.
"""
from __future__ import annotations

import json
from typing import Any

from langchain.agents.middleware import PIIMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.runtime import Runtime


PII_TYPES = ("email", "credit_card", "ip")


def pii_middleware() -> list[PIIMiddleware]:
    """Give each agent fresh middleware and stream-transformer factories."""
    return [
        PIIMiddleware(
            kind,
            strategy="redact",
            apply_to_input=True,
            apply_to_output=True,
            apply_to_tool_results=True,
        )
        for kind in PII_TYPES
    ]


# These hooks have no per-invocation state. Agent instances use the factory above
# instead so a future stream consumer never shares a transformer buffer.
_TEXT_RULES = tuple(pii_middleware())


def _redact_text(text: str) -> str:
    state = {"messages": [HumanMessage(content=text)]}
    for middleware in _TEXT_RULES:
        update = middleware.before_model(state, Runtime())
        if update is not None:
            state = update
    return state["messages"][0].content


def _sanitize_value(value: Any) -> Any:
    """Redact text values and object keys; preserve numbers and structure."""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            clean_key = sanitize_text(key) if isinstance(key, str) else key
            # Distinct emails can redact to the same key. Keep both values in
            # the transient model payload instead of silently overwriting one.
            if clean_key in clean:
                base, occurrence = clean_key, 2
                while clean_key in clean:
                    clean_key = f"{base}#{occurrence}"
                    occurrence += 1
            clean[clean_key] = _sanitize_value(item)
        return clean
    return value


def sanitize_text(text: str) -> str:
    """Apply the same built-in rules to a text or JSON model payload.

    Decoding JSON text, including object keys, prevents escaped ``@`` or
    punctuation from skipping detection. Numeric source offsets and evidence
    IDs are preserved. Colliding redacted object keys receive numeric suffixes.
    Plain/malformed JSON is handled as text rather than trusted as a structure.
    """
    if text.lstrip().startswith(("{", "[", '"')):
        try:
            value = json.loads(text)
        except (ValueError, RecursionError):
            pass
        else:
            clean = _sanitize_value(value)
            if clean != value:
                return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
            return text
    return _redact_text(text)


def sanitize_ai_message(message: AIMessage) -> AIMessage:
    """Clean AI text and decoded/raw tool arguments before tool execution.

    Protocol IDs, names and metadata remain intact. This app's adapter serializes
    only content and these explicit tool-call fields, not arbitrary metadata.
    """
    calls = [
        {**call, "args": _sanitize_value(call["args"])}
        for call in message.tool_calls
    ]
    invalid = [
        {**call, "args": sanitize_text(call["args"]) if isinstance(call.get("args"), str) else call.get("args")}
        for call in message.invalid_tool_calls
    ]
    return message.model_copy(update={
        "content": _sanitize_value(message.content),
        "tool_calls": calls,
        "invalid_tool_calls": invalid,
    })


def sanitize_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Copy and clean every model-bound message, including older tool results.

    PIIMiddleware's before_model checks the last human message and latest batch of
    tool results. This adapter additionally covers replayed message history without
    mutating the original request or any stored body/SourceRef.
    """
    return [
        sanitize_ai_message(message) if isinstance(message, AIMessage)
        else message.model_copy(update={"content": _sanitize_value(message.content)})
        for message in messages
    ]
