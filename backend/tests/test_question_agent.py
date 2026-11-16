"""ReAct limits and evidence boundaries through the real LangChain runtime."""
import asyncio
import json
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agent_fakes import OfflineModel, final_message, search_call, tool_values
from cache_me.auth import AuthError
from cache_me.db import Database
from cache_me.questions import QuestionInput, QuestionService
from cache_me.records import RecordService


@pytest.fixture
def records(tmp_path):
    db = Database(tmp_path / 'agent.sqlite3')
    yield RecordService(db)
    db.close()


class Counter:
    def count_tokens(self, text, kind='query'):
        return len(text) + 4


class Search:
    embedding = Counter()

    def __init__(self, items=()):
        self.items = list(items)
        self.requests = []

    def context(self, request):
        self.requests.append(request)
        return {'items': self.items, 'relations': [], 'limitations': []}


def question(**kwargs):
    return QuestionInput(request_id=uuid4(), question='내 기록을 찾아줘.', **kwargs)


def test_parallel_batch_executes_at_most_eight_calls(records):
    search = Search()
    model = OfflineModel(first_calls=[search_call(f'질의 {i}') for i in range(10)])
    result = asyncio.run(QuestionService(search, records, model).run(question()))
    assert len(search.requests) == 8
    assert result['_agent_usage']['tool_calls'] == 8
    assert result['_agent_usage']['tool_limit'] == 8
    assert result['_agent_usage']['model_calls'] == 3
    assert result['limitations']
    assert any('limit' in json.dumps(value).lower() or '한도' in json.dumps(value, ensure_ascii=False)
               for value in tool_values(model.agent_calls[-1]['messages']))


def test_sequential_search_stops_at_eight_and_finishes_on_ninth_model_turn(records):
    class RepeatedSearch(OfflineModel):
        async def generate_message(self, messages, instructions, *, tools=None, expected_model=None):
            self.agent_calls.append({'messages': messages, 'tools': tools})
            if not tools:
                return final_message(messages)
            return AIMessage(content='', tool_calls=[search_call(f'검색 {len(self.agent_calls)}')])
    search, model = Search(), RepeatedSearch()
    result = asyncio.run(QuestionService(search, records, model).run(question()))
    assert len(search.requests) == 8
    assert len(model.agent_calls) == 9
    assert len(model.calls) == 1
    assert result['_agent_usage']['model_calls'] == 10
    assert not model.agent_calls[-1]['tools']


def test_request_counters_and_evidence_do_not_survive_the_next_request(records):
    capture = records.create({'request_id': str(uuid4()), 'body_markdown': '첫 요청에서만 검색한 기록'})['capture']
    source = {'capture_id': capture['id'], 'revision_id': capture['revision_id'],
              'body_start': 0, 'body_end': len(capture['body_markdown'])}
    search = Search([{'source': source, 'text': capture['body_markdown']}])
    model = OfflineModel(first_calls=[search_call(f'질의 {i}') for i in range(10)])
    service = QuestionService(search, records, model)
    async def scenario():
        first = await service.run(question())
        search.items.clear()
        return first, await service.run(question())
    first, second = asyncio.run(scenario())
    assert len(search.requests) == 16
    assert first['_agent_usage'] == second['_agent_usage']
    assert first['answer_id'] != second['answer_id']
    assert first['sources'] == [source]
    assert second['sources'] == []
    assert not any(isinstance(message, ToolMessage) for message in model.agent_calls[2]['messages'])


def test_simultaneous_requests_keep_counters_and_evidence_separate(records):
    from threading import Barrier
    captures = [records.create({'request_id': str(uuid4()), 'body_markdown': body})['capture']
                for body in ('첫 요청의 독립 근거', '둘째 요청의 독립 근거')]
    sources = [{'capture_id': capture['id'], 'revision_id': capture['revision_id'],
                'body_start': 0, 'body_end': len(capture['body_markdown'])} for capture in captures]
    barrier = Barrier(2)
    class ConcurrentSearch(Search):
        def context(self, request):
            self.requests.append(request)
            barrier.wait(timeout=5)
            index = 0 if request['query'] == '첫 질의' else 1
            return {'items': [{'source': sources[index], 'text': captures[index]['body_markdown']}],
                    'relations': [], 'limitations': []}
    search, model = ConcurrentSearch(), OfflineModel()
    service = QuestionService(search, records, model)
    async def scenario():
        return await asyncio.gather(*[service.run(QuestionInput(request_id=uuid4(), question=text))
                                      for text in ('첫 질의', '둘째 질의')])
    first, second = asyncio.run(scenario())
    assert first['sources'] == [sources[0]]
    assert second['sources'] == [sources[1]]
    assert first['_agent_usage'] == second['_agent_usage'] == {'tool_calls': 1, 'model_calls': 3, 'tool_limit': 8}
    assert len(search.requests) == 2


def test_invalid_arguments_still_consume_a_tool_slot(records):
    invalid = {'id': 'invalid_query', 'name': 'search_knowledge',
               'args': {'unit_ids': ['u1']}, 'type': 'tool_call'}
    search = Search()
    model = OfflineModel(first_calls=[invalid, *[search_call(f'질의 {i}') for i in range(8)]])
    result = asyncio.run(QuestionService(search, records, model).run(question()))
    assert len(search.requests) == 7
    assert result['_agent_usage']['tool_calls'] == 8


def test_unknown_tool_name_does_not_expand_the_search_budget(records):
    unknown = {'id': 'unknown_tool', 'name': 'capture_delete',
               'args': {}, 'type': 'tool_call'}
    search = Search()
    model = OfflineModel(first_calls=[unknown, *[search_call(f'질의 {i}') for i in range(8)]])
    result = asyncio.run(QuestionService(search, records, model).run(question()))
    assert len(search.requests) == 7
    assert result['_agent_usage']['tool_calls'] <= 8
    assert result['sources'] == []


def test_model_cannot_continue_tool_loop_after_final_turn(records):
    class UncooperativeModel(OfflineModel):
        async def generate_message(self, messages, instructions, *, tools=None, expected_model=None):
            self.agent_calls.append({'messages': messages, 'tools': tools})
            return AIMessage(content='', tool_calls=[search_call('계속 검색')])
    search, model = Search(), UncooperativeModel()
    with pytest.raises(AuthError):
        asyncio.run(QuestionService(search, records, model).run(question()))
    assert len(search.requests) == 8
    assert len(model.agent_calls) <= 9
    assert not model.calls


def test_server_filters_are_forced_and_only_read_tools_are_bound(records):
    concept = uuid4()
    search, model = Search(), OfflineModel()
    asyncio.run(QuestionService(search, records, model).run(question(kinds=['knowledge'], concept_ids=[concept])))
    assert search.requests
    assert all(request['kinds'] == ['knowledge'] and request['concept_ids'] == [str(concept)] for request in search.requests)
    tools = model.agent_calls[0]['tools']
    names = {tool.get('name', tool.get('function', {}).get('name')) for tool in tools}
    assert names == {'search_knowledge', 'read_evidence'}
    for tool in tools:
        schema = tool.get('parameters', tool.get('function', {}).get('parameters', {}))
        assert not {'kinds', 'concept_ids', 'event_time'} & schema.get('properties', {}).keys()


def test_model_supplied_filter_cannot_replace_user_filter(records):
    search = Search()
    model = OfflineModel(first_calls=[search_call('기록', kinds=['episode'])])
    asyncio.run(QuestionService(search, records, model).run(question(kinds=['knowledge'])))
    # The runtime may reject unknown args or ignore them; it must never apply them.
    assert all(request['kinds'] == ['knowledge'] for request in search.requests)


def test_read_tool_cannot_read_an_unseen_record(records):
    capture = records.create({'request_id': str(uuid4()), 'body_markdown': '검색하지 않은 별도 기록'})['capture']
    call = {'id': 'unseen', 'name': 'read_evidence', 'args': {'evidence_id': 999}, 'type': 'tool_call'}
    model = OfflineModel(first_calls=[call])
    result = asyncio.run(QuestionService(Search(), records, model).run(question()))
    assert result['sources'] == []
    assert result['_agent_usage']['tool_calls'] == 1
    assert capture['body_markdown'] not in json.dumps(tool_values(model.agent_calls[-1]['messages']), ensure_ascii=False)


def test_unknown_evidence_id_cannot_become_a_citation(records):
    class InventedCitation(OfflineModel):
        async def generate_message(self, messages, instructions, *, tools=None, expected_model=None):
            return AIMessage(content=json.dumps({'parts': [{'kind': 'stored_knowledge',
                'text': '없는 개인 기록입니다.', 'evidence_ids': [123]}], 'evidence_status': 'found'}))
    with pytest.raises(AuthError) as error:
        asyncio.run(QuestionService(Search(), records, InventedCitation()).run(question()))
    assert error.value.code == 'MODEL_FORMAT_ERROR'


def test_pii_is_redacted_in_agent_input_tool_results_and_final_output(records):
    raw = '연락 이메일 alice@example.com, 카드 4111 1111 1111 1111, IP 192.0.2.10'
    capture = records.create({'request_id': str(uuid4()), 'body_markdown': raw})['capture']
    source = {'capture_id': capture['id'], 'revision_id': capture['revision_id'],
              'body_start': 0, 'body_end': len(raw)}
    search = Search([{'source': source, 'text': raw}])
    model = OfflineModel(final_text=raw)
    result = asyncio.run(QuestionService(search, records, model).run(
        QuestionInput(request_id=uuid4(), question='alice@example.com 관련 기록은?')))
    provider_inputs = json.dumps([message.model_dump() for call in model.agent_calls for message in call['messages']], ensure_ascii=False)
    output = json.dumps(result['parts'], ensure_ascii=False)
    for private in ['alice@example.com', '4111 1111 1111 1111', '192.0.2.10']:
        assert private not in provider_inputs
        assert private not in output
    assert result['sources'] == [source]
    assert records.get(capture['id'])['body_markdown'] == raw


def test_reread_tool_and_review_never_reintroduce_redacted_pii(records):
    raw = '담당 alice@example.com, 카드 4111 1111 1111 1111, IP 192.0.2.10'
    capture = records.create({'request_id': str(uuid4()), 'body_markdown': raw})['capture']
    source = {'capture_id': capture['id'], 'revision_id': capture['revision_id'],
              'body_start': 0, 'body_end': len(raw)}
    class RereadingModel(OfflineModel):
        async def generate_message(self, messages, instructions, *, tools=None, expected_model=None):
            self.agent_calls.append({'messages': messages, 'instructions': instructions, 'tools': tools})
            previous_tools = [message for message in messages if isinstance(message, ToolMessage)]
            if not previous_tools:
                return AIMessage(content='', tool_calls=[search_call('alice@example.com')])
            if len(previous_tools) == 1:
                evidence_id = tool_values(messages)[0]['evidence'][0]['evidence_id']
                return AIMessage(content='', tool_calls=[{'id': 'read_known_source', 'name': 'read_evidence',
                    'args': {'evidence_id': evidence_id}, 'type': 'tool_call'}])
            return final_message(messages, text=raw)
    search, model = Search([{'source': source, 'text': raw}]), RereadingModel()
    result = asyncio.run(QuestionService(search, records, model).run(question()))
    assert len(search.requests) == 1
    assert result['_agent_usage'] == {'tool_calls': 2, 'model_calls': 4, 'tool_limit': 8}
    reread = tool_values(model.agent_calls[-1]['messages'])[-1]['evidence'][0]
    assert reread['evidence_id'] == 0 and reread['source'] == source
    assert result['sources'] == [source]
    provider_inputs = json.dumps([message.model_dump() for call in model.agent_calls for message in call['messages']], ensure_ascii=False)
    review_inputs = json.dumps(model.calls, ensure_ascii=False)
    for private in ['alice@example.com', '4111 1111 1111 1111', '192.0.2.10']:
        assert private not in provider_inputs
        assert private not in review_inputs
        assert private not in json.dumps(search.requests, ensure_ascii=False)
        assert private not in json.dumps(result['parts'], ensure_ascii=False)
    assert records.get(capture['id'])['body_markdown'] == raw


def test_generation_change_between_tool_and_next_model_aborts(records):
    class SessionModel(OfflineModel):
        auth_generation = 0
        model_generation = 0
        data = {'active': 'test-account'}
    model = SessionModel()
    class LogoutSearch(Search):
        def context(self, request):
            result = super().context(request)
            model.auth_generation += 1
            return result
    with pytest.raises(AuthError) as error:
        asyncio.run(QuestionService(LogoutSearch(), records, model).run(question()))
    assert error.value.code == 'LOGIN_REQUIRED'
    assert len(model.agent_calls) == 1
