import asyncio
import json
from uuid import uuid4

import pytest

from second_brain.auth import AuthError
from second_brain.db import Database
from second_brain.questions import QuestionInput, QuestionService, split_question
from second_brain.records import RecordService
from second_brain.token_budget import ModelBudget
from agent_fakes import OfflineModel, request_value, search_call, tool_values


class Counter:
    def count_tokens(self, text, kind='query'):
        return len(text) + 4


@pytest.fixture
def records(tmp_path):
    db = Database(tmp_path / 'quality.sqlite3')
    yield RecordService(db)
    db.close()


def make_item(records, text):
    capture = records.create({'request_id': str(uuid4()), 'body_markdown': text})['capture']
    return {'source': {'capture_id': capture['id'], 'revision_id': capture['revision_id'], 'body_start': 0, 'body_end': len(text)}, 'text': text}


class Search:
    embedding = Counter()
    def __init__(self, items=()):
        self.items = list(items)
        self.queries = []
    def context(self, request):
        self.queries.append(request['query'])
        return {'items': self.items, 'limitations': []}


def test_long_question_keeps_negation_dates_names_and_entire_suffix():
    question = ('2026년 11월 자료에서 민수의 선호와 내 선호를 구분해 줘. '
                'GPU가 필수라는 설명은 제외하고 CPU만 사용한 결정을 찾아줘. '
                '마지막으로 발표는 짧게 하되 학습 예제와 반례는 생략하지 말아줘.')
    units = split_question(question, Counter().count_tokens)
    assert len(units) > 1
    assert ''.join(question[u['start']:u['end']] for u in units) == question
    assert all(u['token_count'] <= 64 for u in units)
    assert '생략하지 말아줘' in units[-1]['query']
    assert any('민수' in u['query'] for u in units)
    assert any('2026' in u['query'] for u in units)
    assert any('제외' in u['query'] for u in units)


def test_query_budget_accounts_for_unprocessed_original_ranges(records):
    question = ' '.join(f'{i}번 조건에서는 해당 프로젝트만 확인하고 다른 대상은 제외해 주세요.' for i in range(20))
    model, search = OfflineModel(), Search()
    result = asyncio.run(QuestionService(search, records, model).run(QuestionInput(request_id=uuid4(), question=question)))
    coverage = result['_query_coverage']
    assert len(search.queries) == 8
    assert coverage[0]['start'] == 0 and coverage[-1]['end'] == len(question)
    assert all(a['end'] == b['start'] for a, b in zip(coverage, coverage[1:]))
    assert {u['status'] for u in coverage} == {'searched', 'omitted'}
    assert coverage[-1]['status'] == 'searched'
    assert any('처리하지 못했' in text for text in result['limitations'])
    assert request_value(model.agent_calls[0]['messages'])['question'] == question
    assert model.calls[-1][0]['question_coverage'] == coverage


def test_rewritten_query_cannot_mark_original_conditions_searched(records):
    question = '민수가 아니라 내 CPU 전용 결정을 찾아줘.'
    model = OfflineModel(first_calls=[search_call('GPU 필수', ['u1'])])
    search = Search()
    result = asyncio.run(QuestionService(search, records, model).run(QuestionInput(request_id=uuid4(), question=question)))
    assert search.queries == ['GPU 필수']
    assert result['_query_coverage'][0]['status'] == 'omitted'
    assert result['limitations']


def test_model_budget_counts_serialized_utf8_and_uses_catalog_limit():
    budget = ModelBudget.from_metadata({'model': 'selected', 'context_window': 2000, 'max_input_tokens': 1800, 'max_output_tokens': 500})
    assert budget.input_limit == 1500
    assert budget.measure('한글' * 100, '지침') > len('한글' * 100)
    assert budget.describe()['limit_source'] == 'catalog_with_client_cap'
    assert budget.describe()['counter'] == 'utf8_bytes_conservative'
    unknown = ModelBudget.from_metadata({'model': 'unknown'})
    assert unknown.input_limit == 32768
    assert unknown.source == 'conservative_client_cap'


def test_question_too_large_rejected_before_any_model_call(records):
    model = OfflineModel(window=2000, max_output=500)
    service = QuestionService(Search(), records, model)
    with pytest.raises(AuthError) as error:
        asyncio.run(service.run(QuestionInput(request_id=uuid4(), question='원문을 자르지 않아야 합니다. ' * 80)))
    assert error.value.code == 'MODEL_INPUT_BUDGET_EXCEEDED'
    assert model.calls == []
    assert model.agent_calls == []
    assert '원문을 자르지' not in json.dumps(error.value.as_dict(), ensure_ascii=False)


def test_context_budget_preserves_whole_source_spans(records):
    items = [make_item(records, f'근거 {i}의 시작. ' + '문장을 자르지 않고 보존한다. ' * 35 + f' 근거 {i}의 끝.') for i in range(8)]
    model = OfflineModel(window=16000, max_output=1024)
    result = asyncio.run(QuestionService(Search(items), records, model).run(QuestionInput(request_id=uuid4(), question='보존된 근거를 찾아줘.')))
    evidence = [item for value in tool_values(model.agent_calls[-1]['messages']) for item in value.get('evidence', [])]
    assert 0 < len(evidence) < len(items)
    originals = {item['text'] for item in items}
    assert all(item['text'] in originals for item in evidence)
    assert result['limitations']
    assert all(row['input_tokens'] <= row['input_limit'] for row in result['_input_estimates'])


def test_user_model_change_does_not_silently_switch_during_answer(records):
    model = OfflineModel()
    model.switch_during_answer = True
    service = QuestionService(Search([make_item(records, '확인한 기록입니다.')]), records, model)
    with pytest.raises(AuthError) as error:
        asyncio.run(service.run(QuestionInput(request_id=uuid4(), question='기록은?')))
    assert error.value.code == 'MODEL_CHANGED'
    assert model.model == 'new-user-selection'


def test_separate_searches_can_collect_different_question_facets(records):
    first = [make_item(records, f'첫 번째 주제의 근거 {index}.') for index in range(10)]
    second = make_item(records, '두 번째 주제에서만 찾은 중요한 근거.')
    class FacetedSearch(Search):
        def context(self, request):
            return {'items': [second] if '두번째' in request['query'] else first, 'limitations': []}
    model = OfflineModel(first_calls=[search_call('첫번째'), search_call('두번째')])
    asyncio.run(QuestionService(FacetedSearch(), records, model).run(QuestionInput(request_id=uuid4(), question='두 주제를 비교해줘.')))
    evidence = [item for value in tool_values(model.agent_calls[-1]['messages']) for item in value.get('evidence', [])]
    evidence_ids = {item['source']['capture_id'] for item in evidence}
    assert second['source']['capture_id'] in evidence_ids
    assert first[0]['source']['capture_id'] in evidence_ids
    assert len(evidence_ids) <= 10


def test_budget_model_is_forwarded_to_every_generation(records):
    model = OfflineModel()
    result = asyncio.run(QuestionService(Search(), records, model).run(QuestionInput(request_id=uuid4(), question='기록은?')))
    assert model.expected_models == ['selected-test-model'] * (len(model.agent_calls) + len(model.calls))
    assert all(row['input_tokens'] <= row['input_limit'] for row in result['_input_estimates'])


def test_cancelled_search_does_not_start_a_later_agent_turn(records):
    from threading import Event
    entered, release = Event(), Event()
    class BlockingSearch(Search):
        def context(self, request):
            self.queries.append(request['query'])
            entered.set()
            assert release.wait(5)
            return {'items': [], 'limitations': []}
    search, model = BlockingSearch(), OfflineModel()
    service = QuestionService(search, records, model)
    async def scenario():
        task = asyncio.create_task(service.run(QuestionInput(request_id=uuid4(), question='질의 하나')))
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
    asyncio.run(scenario())
    assert search.queries == ['질의 하나']
    assert len(model.agent_calls) == 1
    assert model.calls == []
