"""LangChain chat adapter for the existing, user-selected ChatGPT OAuth model."""
from __future__ import annotations

import json
import re
from typing import Any, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from .auth import AuthError
from .privacy import sanitize_ai_message, sanitize_messages, sanitize_text


def check_output_size(text: str) -> None:
    if len(text) > 32_000 or len(text.encode('utf-8')) > 131_072:
        raise AuthError('MODEL_OUTPUT_LIMIT', '모델 응답이 처리 한도를 넘었습니다. 질문을 나누어 주세요.')


def _field(value: Any, key: str, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def message_from_output(output: list | None, fallback_text: str = '') -> AIMessage:
    """Parse only a completed Responses output; partial tool arguments never run."""
    if output is None:
        check_output_size(fallback_text)
        return AIMessage(content=fallback_text)
    text, calls, reasoning, seen, output_parts = [], [], [], set(), []
    for item in output:
        kind = _field(item, 'type')
        if kind == 'message':
            for block in _field(item, 'content', []):
                if _field(block, 'type') != 'output_text' or not isinstance(_field(block, 'text'), str):
                    raise AuthError('MODEL_FORMAT_ERROR', '모델 답변 형식을 검증하지 못했습니다.')
                text.append(_field(block, 'text'))
                output_parts.append(_field(block, 'text'))
        elif kind == 'function_call':
            name, call_id, arguments = (_field(item, key) for key in ('name', 'call_id', 'arguments'))
            if (not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', name) or
                    not isinstance(call_id, str) or not call_id or len(call_id) > 200 or call_id in seen or
                    not isinstance(arguments, str)):
                raise AuthError('MODEL_FORMAT_ERROR', '모델의 도구 호출 형식을 검증하지 못했습니다.')
            output_parts.extend((name, call_id, arguments))
            check_output_size(''.join(output_parts))
            try:
                args = json.loads(arguments)
                if not isinstance(args, dict):
                    raise ValueError()
                json.dumps(args, allow_nan=False)
            except (ValueError, TypeError, RecursionError):
                raise AuthError('MODEL_FORMAT_ERROR', '모델의 도구 인수를 검증하지 못했습니다.') from None
            seen.add(call_id)
            calls.append({'name': name, 'args': args, 'id': call_id, 'type': 'tool_call'})
        elif kind == 'reasoning':
            encrypted = _field(item, 'encrypted_content')
            item_id = _field(item, 'id')
            if encrypted is not None and not isinstance(encrypted, str):
                raise AuthError('MODEL_FORMAT_ERROR', '모델의 이어쓰기 정보를 검증하지 못했습니다.')
            if encrypted and isinstance(item_id, str):
                # Plaintext reasoning summaries are unnecessary for a tool turn.
                reasoning.append({'id': item_id, 'type': 'reasoning', 'summary': [], 'encrypted_content': encrypted})
                output_parts.append(encrypted)
        else:
            raise AuthError('MODEL_FORMAT_ERROR', '지원하지 않는 모델 출력 형식입니다.')
        check_output_size(''.join(output_parts))
    return AIMessage(content=''.join(text), tool_calls=calls,
                     additional_kwargs={'response_reasoning': reasoning} if reasoning else {})


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get('type') in ('text', 'input_text', 'output_text') and isinstance(block.get('text'), str):
                parts.append(block['text'])
            else:
                raise AuthError('MODEL_REQUEST_INVALID', '지원하지 않는 모델 메시지 형식입니다.')
        return ''.join(parts)
    raise AuthError('MODEL_REQUEST_INVALID', '지원하지 않는 모델 메시지 형식입니다.')


def responses_tools(tools: Sequence[Any] | None) -> list[dict]:
    """Convert LangChain function schemas to the flat Responses API schema."""
    result = []
    for tool in tools or []:
        converted = convert_to_openai_tool(tool)
        if converted.get('type') != 'function':
            raise AuthError('MODEL_REQUEST_INVALID', '로컬 함수 도구만 사용할 수 있습니다.')
        function = converted.get('function', converted)
        result.append({'type': 'function', **{key: function[key] for key in
            ('name', 'description', 'parameters', 'strict') if key in function}})
    return result


def serialize_model_input(messages: list[BaseMessage], instructions: str,
                          tools: Sequence[Any] | None = None, *, tool_choice: Any = None) -> dict:
    """Return the exact sanitized SIWC payload, excluding model/transport flags.

    The agent budget uses the same serializer as the provider boundary. Source
    offsets and tool IDs are protocol fields and are never rewritten here.
    """
    messages = sanitize_messages(messages)
    system = [sanitize_text(instructions)] if instructions else []
    inputs = []
    for message in messages:
        content = _text(message.content)
        if isinstance(message, SystemMessage):
            system.append(content)
        elif isinstance(message, HumanMessage):
            inputs.append({'role': 'user', 'content': content})
        elif isinstance(message, ToolMessage):
            inputs.append({'type': 'function_call_output', 'call_id': message.tool_call_id, 'output': content})
        elif isinstance(message, AIMessage):
            # Stateless Responses calls need the encrypted reasoning items that
            # preceded a function call. Keep them out of user-visible text.
            for reasoning in message.additional_kwargs.get('response_reasoning', []):
                inputs.append({key: reasoning[key] for key in ('id', 'type', 'summary', 'encrypted_content')
                               if key in reasoning})
            if content:
                inputs.append({'role': 'assistant', 'content': content})
            for call in message.tool_calls:
                try:
                    arguments = json.dumps(call['args'], ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                except (ValueError, TypeError):
                    raise AuthError('MODEL_REQUEST_INVALID', '도구 인수를 직렬화하지 못했습니다.') from None
                inputs.append({'type': 'function_call', 'call_id': call['id'], 'name': call['name'], 'arguments': arguments})
        else:
            raise AuthError('MODEL_REQUEST_INVALID', '지원하지 않는 모델 메시지 형식입니다.')
    payload = {'instructions': '\n\n'.join(system), 'input': inputs}
    if tools:
        payload['tools'] = responses_tools(tools)
    if tool_choice is not None:
        if tool_choice in ('auto', 'none', 'required'):
            payload['tool_choice'] = tool_choice
        elif isinstance(tool_choice, str):
            payload['tool_choice'] = {'type': 'function', 'name': tool_choice}
        elif isinstance(tool_choice, dict) and tool_choice.get('type') == 'function':
            payload['tool_choice'] = {'type': 'function', 'name': tool_choice.get('name') or tool_choice.get('function', {}).get('name')}
        else:
            raise AuthError('MODEL_REQUEST_INVALID', '지원하지 않는 도구 선택 형식입니다.')
    return payload


class OAuthChatModel(BaseChatModel):
    """Async-only model; authentication stays in ModelAuth, never in graph state."""

    auth: Any = Field(exclude=True, repr=False)
    expected_model: str | None = None
    cache: bool = False
    disable_streaming: bool = True

    @property
    def _llm_type(self) -> str:
        return 'chatgpt-oauth-responses'

    @property
    def _identifying_params(self) -> dict:
        return {'model': self.expected_model}

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: Any = None, **kwargs: Any):
        return self.bind(tools=responses_tools(tools), tool_choice=tool_choice, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError('OAuthChatModel requires async invocation.')

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if stop:
            raise AuthError('MODEL_REQUEST_INVALID', '이 모델 연결에서는 stop 옵션을 지원하지 않습니다.')
        options = {'tools': kwargs.get('tools'), 'expected_model': self.expected_model}
        if kwargs.get('tool_choice') is not None:
            options['tool_choice'] = kwargs['tool_choice']
        message = await self.auth.generate_message(sanitize_messages(messages), '', **options)
        return ChatResult(generations=[ChatGeneration(message=sanitize_ai_message(message))])
