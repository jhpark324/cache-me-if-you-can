"""OAuth Responses tool turns and LangChain binding, using an offline transport."""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from cache_me.auth import AuthError, ModelAuth
from cache_me.chat_model import OAuthChatModel, message_from_output, serialize_model_input
from test_auth_contract import install_model_stream, prepare_expired_account


def account(tmp_path):
    auth = ModelAuth(tmp_path, 'http://127.0.0.1:8000')
    prepare_expired_account(auth, expires_at=time.time() + 3600)
    return auth


def function_call(call_id='call_1', arguments='{"query":"검색어"}', name='search_knowledge'):
    return {'type': 'function_call', 'id': 'fc_1', 'call_id': call_id,
            'name': name, 'arguments': arguments, 'status': 'completed'}


def text_item(text):
    return {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}


def completed(output):
    return {'type': 'response.completed', 'response': SimpleNamespace(output=output)}


def test_oauth_converts_completed_tool_turn_and_replays_result_without_duplicates(tmp_path, monkeypatch):
    auth = account(tmp_path)
    recorded = install_model_stream(monkeypatch, [
        {'type': 'response.output_text.delta', 'delta': '자료를 찾아볼게요.'},
        {'type': 'response.function_call_arguments.delta', 'delta': '{"query":'},
        {'type': 'response.function_call_arguments.delta', 'delta': '"검색어"}'},
        {'type': 'response.output_item.done', 'output_index': 1, 'item': function_call()},
        completed([text_item('자료를 찾아볼게요.'), function_call()]),
    ])
    functions = [{'type': 'function', 'function': {'name': 'search_knowledge', 'description': '지식 검색',
        'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}}}]
    result = asyncio.run(auth.generate_message([SystemMessage(content='지침'), HumanMessage(content='기록을 찾아줘')], '',
        tools=functions, expected_model='catalog-model'))
    assert result.content == '자료를 찾아볼게요.'
    assert result.tool_calls == [{'id': 'call_1', 'name': 'search_knowledge', 'args': {'query': '검색어'}, 'type': 'tool_call'}]
    assert recorded['request']['instructions'] == '지침'
    assert recorded['request']['tools'][0]['name'] == 'search_knowledge'
    assert 'function' not in recorded['request']['tools'][0]
    assert recorded['request']['store'] is False
    assert 'previous_response_id' not in recorded['request']
    replay = serialize_model_input([HumanMessage(content='기록을 찾아줘'), result,
        ToolMessage(content='{"items":[]}', tool_call_id='call_1')], '지침', functions)
    assert [entry.get('type') for entry in replay['input']] == [None, None, 'function_call', 'function_call_output']
    assert json.loads(replay['input'][2]['arguments']) == {'query': '검색어'}
    assert replay['input'][3] == {'type': 'function_call_output', 'call_id': 'call_1', 'output': '{"items":[]}'}


def test_completed_output_is_authoritative_and_raw_reasoning_is_not_exposed(tmp_path, monkeypatch):
    auth = account(tmp_path)
    opaque = 'opaque-encrypted-state'
    output = [{'type': 'reasoning', 'id': 'rs_1', 'summary': [{'type': 'summary_text', 'text': 'private thoughts'}],
               'encrypted_content': opaque}, function_call()]
    install_model_stream(monkeypatch, [completed(output)])
    result = asyncio.run(auth.generate_message([HumanMessage(content='검색')], '', expected_model='catalog-model'))
    assert result.content == ''
    assert 'private thoughts' not in result.model_dump_json()
    replay = serialize_model_input([result, ToolMessage(content='결과', tool_call_id='call_1')], '')
    assert replay['input'][0] == {'type': 'reasoning', 'id': 'rs_1', 'summary': [], 'encrypted_content': opaque}
    assert replay['input'][1]['type'] == 'function_call'


@pytest.mark.parametrize('output', [
    [function_call(arguments='not-json')],
    [function_call(arguments='[]')],
    [function_call(arguments='{"value":NaN}')],
    [function_call(call_id='')],
    [function_call(), function_call()],
])
def test_malformed_or_duplicate_tool_calls_fail_before_execution(tmp_path, monkeypatch, output):
    auth = account(tmp_path)
    install_model_stream(monkeypatch, [completed(output)])
    with pytest.raises(AuthError) as error:
        asyncio.run(auth.generate_message([HumanMessage(content='질문')], ''))
    assert error.value.code == 'MODEL_FORMAT_ERROR'
    assert 'not-json' not in str(error.value)


def test_incomplete_stream_does_not_return_completed_tool_items(tmp_path, monkeypatch):
    auth = account(tmp_path)
    install_model_stream(monkeypatch, [{'type': 'response.output_item.done', 'output_index': 0, 'item': function_call()}])
    with pytest.raises(AuthError) as error:
        asyncio.run(auth.generate_message([HumanMessage(content='질문')], ''))
    assert error.value.code == 'MODEL_INTERRUPTED'


@pytest.mark.parametrize('events', [
    [{'type': 'response.function_call_arguments.delta', 'delta': 'x' * 32001}],
    [completed([function_call(arguments=json.dumps({'query': 'x' * 32001}))])],
])
def test_tool_arguments_share_output_size_bound(tmp_path, monkeypatch, events):
    auth = account(tmp_path)
    install_model_stream(monkeypatch, events)
    with pytest.raises(AuthError) as error:
        asyncio.run(auth.generate_message([HumanMessage(content='질문')], ''))
    assert error.value.code == 'MODEL_OUTPUT_LIMIT'


def test_boundary_redacts_all_turns_and_generated_tool_arguments(tmp_path, monkeypatch):
    auth = account(tmp_path)
    secret = 'learner@example.com'
    recorded = install_model_stream(monkeypatch, [completed([
        text_item(f'주소 {secret}'), function_call(arguments=json.dumps({'query': secret}))])])
    messages = [SystemMessage(content=f'지침 {secret}'), HumanMessage(content=f'질문 {secret}'),
        AIMessage(content=f'이전 응답 {secret}', tool_calls=[{'id': 'old_call', 'name': 'search_knowledge', 'args': {'query': secret}}]),
        ToolMessage(content=json.dumps({'text': secret}), tool_call_id='old_call')]
    result = asyncio.run(auth.generate_message(messages, f'정책 {secret}'))
    assert secret not in json.dumps(recorded['request'], ensure_ascii=False)
    assert secret not in result.model_dump_json()
    assert messages[1].content == f'질문 {secret}'
    assert messages[2].tool_calls[0]['args']['query'] == secret
    assert result.tool_calls[0]['id'] == 'call_1'
    assert '[REDACTED_EMAIL]' in result.content


def test_langchain_bind_tools_uses_selected_model_and_async_oauth_boundary():
    seen = []
    class Auth:
        async def generate_message(self, messages, instructions, **kwargs):
            seen.append((messages, instructions, kwargs))
            return AIMessage(content='', tool_calls=[{'id': 'call_1', 'name': 'lookup', 'args': {'query': '검색'}}])

    @tool
    def lookup(query: str) -> str:
        """Read matching local knowledge."""
        return query

    model = OAuthChatModel(auth=Auth(), expected_model='selected-model')
    bound = model.bind_tools([lookup])
    result = asyncio.run(bound.ainvoke([HumanMessage(content='검색')]))
    assert result.tool_calls[0]['name'] == 'lookup'
    assert seen[0][2]['expected_model'] == 'selected-model'
    assert seen[0][2]['tools'][0]['name'] == 'lookup'
    assert 'auth' not in model.model_dump()
    assert model._identifying_params == {'model': 'selected-model'}


def test_batch_of_nine_calls_is_visible_to_agent_execution_budget():
    result = message_from_output([function_call(call_id=f'call_{i}') for i in range(9)])
    assert len(result.tool_calls) == 9  # The agent reserves/denies individual execution slots.


def test_chat_adapter_privacy_boundary_also_covers_explicit_provider_doubles():
    secret = 'learner@example.com'
    class Auth:
        async def generate_message(self, messages, instructions, *, tools=None, expected_model=None):
            assert secret not in ''.join(message.text for message in messages)
            return AIMessage(content=secret, tool_calls=[{'id': 'safe_id', 'name': 'lookup', 'args': {'query': secret}}])
    model = OAuthChatModel(auth=Auth(), expected_model='selected-model')
    response = asyncio.run(model.ainvoke([HumanMessage(content=secret)]))
    assert secret not in response.model_dump_json()
    assert response.tool_calls[0]['id'] == 'safe_id'
