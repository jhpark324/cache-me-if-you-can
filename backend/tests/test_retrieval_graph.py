"""Graph metadata uses accepted evidence and survives unused-source races."""
import asyncio
from copy import deepcopy
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import ToolMessage

from agent_fakes import OfflineModel
from cache_me.auth import AuthError
from cache_me.config import Settings
from cache_me.db import Database
from cache_me.main import create_app
from cache_me.models import Capture
from cache_me.questions import QuestionInput, QuestionService
from cache_me.records import DomainError, RecordService
from cache_me.retrieval_view import retrieval_sources, source_key
from cache_me.schemas import SourceRef


@pytest.fixture
def records(tmp_path):
    db = Database(tmp_path / 'retrieval.sqlite3')
    yield RecordService(db)
    db.close()


def create(records, body='서버가 읽은 근거', **kwargs):
    return records.create({'request_id': str(uuid4()), 'body_markdown': body, **kwargs})['capture']


def source(capture, **span):
    return {'capture_id': capture['id'], 'revision_id': capture['revision_id'], **span}


def expected(capture):
    return {'capture_id': capture['id'], 'expected_revision_id': capture['revision_id'],
            'expected_state_version': capture['state_version']}


def update(records, capture, **changes):
    return records.update({'request_id': str(uuid4()), **expected(capture), 'changes': changes})['capture']


class Search:
    def __init__(self, sources):
        # The ledger must replace a search adapter's text with canonical text.
        self.items = [{'source': ref, 'text': '검색기가 만든 잘못된 문장'} for ref in sources]

    def context(self, _request):
        return {'items': self.items, 'limitations': []}


def run(records, sources, model=None):
    service = QuestionService(Search(sources), records, model or OfflineModel())
    return service, asyncio.run(service.run(QuestionInput(request_id=uuid4(), question='기록은?')))


def result_for(records, sources, cited=()):
    versions = {}
    for ref in sources:
        capture = records.get(ref['capture_id'])
        versions[capture['id']] = [capture['revision_id'], capture['state_version'],
                                   capture['index_state']['index_generation']]
    return {'sources': list(cited), '_versions': versions,
            '_retrieval_sources': retrieval_sources([{'source': ref} for ref in sources])}


def test_graph_uses_accepted_spans_distinguishes_nodes_and_ignores_model_metadata(records):
    capture = create(records, '첫 번째 근거.\n두 번째 근거.', title='학습 메모',
                     nodes=[{'kind': 'explanation', 'body_start': 0, 'body_end': 8}])
    first = source(capture, body_start=0, body_end=8)
    second = source(capture, body_start=9, body_end=len(capture['body_markdown']))
    node = {**first, 'node_id': capture['nodes'][0]['id']}
    duplicate = dict(reversed(list({**first, 'node_id': None}.items())))
    forged = source(create(records, '에이전트가 읽지 않은 기록'))

    class ForgedGraphModel(OfflineModel):
        async def generate_message(self, messages, instructions, **kwargs):
            message = await super().generate_message(messages, instructions, **kwargs)
            if any(isinstance(item, ToolMessage) for item in messages):
                value = json.loads(message.content)
                value['retrieval'] = {'items': [{'source': forged, 'label': '위조 그래프', 'cited': True}]}
                value['sources'] = [forged]
                message.content = json.dumps(value)
            return message

    _, result = run(records, [first, duplicate, second, node], ForgedGraphModel())
    items = result['retrieval']['items']
    assert [source_key(item['source']) for item in items] == [source_key(ref) for ref in (first, second, node)]
    assert [item['cited'] for item in items] == [True, False, False]
    assert [item['label'] for item in items] == [records.source_get(ref)['text'] for ref in (first, second, node)]
    assert all(item['capture_label'] == '학습 메모' for item in items)
    assert all(item['source'] == SourceRef.model_validate(ref).model_dump(mode='json')
               for item, ref in zip(items, (first, second, node)))
    assert all(set(item) == {'source', 'label', 'capture_label', 'cited'} for item in items)
    assert result['retrieval']['truncated'] is False
    assert forged['capture_id'] not in json.dumps(result['retrieval'])


def test_reviewer_rejected_citations_are_read_but_not_cited(records):
    class RejectingReviewer(OfflineModel):
        async def generate(self, prompt, instructions):
            return json.dumps({'supported_part_ids': []})

    _, result = run(records, [source(create(records))], RejectingReviewer())
    assert result['sources'] == []
    assert result['retrieval']['items'][0]['cited'] is False
    assert result['evidence_status'] == 'none'


def test_no_read_evidence_returns_empty_graph_and_legacy_result_remains_supported(records):
    service, result = run(records, [])
    assert result['retrieval'] == {'items': [], 'truncated': False}
    legacy = {'sources': []}
    service.revalidate(legacy)
    assert legacy == {'sources': []}


@pytest.mark.parametrize('pii', ['learner@example.com', '4111 1111 1111 1111', '203.0.113.7'])
def test_graph_redacts_complete_text_and_title_before_codepoint_clipping(records, pii):
    prefix = '🧠' * 52 + ' '
    body = prefix + pii + ' 뒤에 있는 문장은 그래프에 포함하지 않는다.'
    capture = create(records, body, title=body)
    _, result = run(records, [source(capture)])
    item = result['retrieval']['items'][0]
    for field in ('label', 'capture_label'):
        assert len(item[field]) == 60
        assert item[field].startswith(prefix + '[REDACT')
        assert pii[:6] not in item[field]
    # Graph redaction never changes the original or the source panel's text.
    assert records.source_get(item['source'])['text'] == body
    assert records.get(capture['id'])['title'] == body


def mutate(records, capture, kind, upstream=None):
    if kind == 'revision':
        update(records, capture, body_markdown='정정한 다른 근거')
    elif kind == 'state':
        update(records, capture, visibility='private')
    elif kind == 'index':
        with records.db.write() as session:
            session.get(Capture, capture['id']).index_generation += 1
    elif kind == 'review':
        update(records, upstream, body_markdown='상위 원문 정정')
    elif kind == 'deleted':
        preview = records.prepare_delete(expected(capture))
        records.delete({'request_id': str(uuid4()), **expected(capture),
                        'confirmation_token': preview['confirmation_token']},
                       confirmation=records.confirm_deletion(preview['confirmation_token']))


@pytest.mark.parametrize('kind', ['revision', 'state', 'index', 'review', 'deleted'])
@pytest.mark.parametrize('cited', [False, True])
def test_changed_evidence_only_invalidates_answer_when_cited(records, kind, cited):
    stable = create(records, '답변에 사용한 유효한 근거')
    upstream = create(records, '다른 기록의 원본')
    changing = create(records, '변경할 근거', sources=[source(upstream)] if kind == 'review' else [])
    service, result = run(records, [source(changing), source(stable)] if cited else [source(stable), source(changing)])
    before_versions, before_parts = deepcopy(result['_versions']), deepcopy(result['parts'])
    mutate(records, changing, kind, upstream)
    if cited:
        with pytest.raises((AuthError, DomainError)):
            service.revalidate(result)
    else:
        service.revalidate(result)
        assert [item['source']['capture_id'] for item in result['retrieval']['items']] == [stable['id']]
        assert result['retrieval']['truncated'] is True
        assert result['parts'] == before_parts
        service.revalidate(result)
        assert result['retrieval']['truncated'] is True
    assert result['_versions'] == before_versions


@pytest.mark.parametrize('limit', ['items', 'captures'])
def test_graph_enforces_bounded_unique_spans_and_capture_anchors(records, limit):
    if limit == 'items':
        capture = create(records, '가' * 21)
        refs = [source(capture, body_start=i, body_end=i + 1) for i in range(21)]
        expected_count = 20
    else:
        refs = [source(create(records, f'{i}번째 기록')) for i in range(11)]
        expected_count = 10
    result = result_for(records, refs)
    QuestionService(None, records, None).revalidate(result)
    assert len(result['retrieval']['items']) == expected_count
    assert len({row['source']['capture_id'] for row in result['retrieval']['items']}) <= 10
    assert result['retrieval']['truncated'] is True


def test_search_candidates_excluded_from_model_budget_do_not_appear_in_graph(records):
    refs = [source(create(records, f'{i}번째 근거. ' + '문장을 통째로 읽어야 한다. ' * 35)) for i in range(8)]
    model = OfflineModel(window=16000, max_output=1024)
    _, result = run(records, refs, model)
    accepted = model.calls[-1][0]['evidence']
    assert 0 < len(accepted) < len(refs)
    assert {source_key(row['source']) for row in result['retrieval']['items']} == {source_key(row['source']) for row in accepted}


@pytest.mark.parametrize('cited', [False, True])
def test_final_completed_boundary_rechecks_graph_without_leaking_stale_labels(tmp_path, monkeypatch, cited):
    settings = Settings(tmp_path, background_jobs=False)
    app = create_app(settings)
    records = app.state.records
    stable = create(records, '살아 있는 답변 근거')
    changing = create(records, '마지막 순간 사라질 구간', title='사라질 제목')
    refs = [source(stable), source(changing)]
    result = result_for(records, refs, [refs[1] if cited else refs[0]])
    result.update({'answer_id': str(uuid4()), 'parts': [{'part_id': 'p1', 'kind': 'stored_knowledge',
                   'text': '검증한 답변', 'sources': result['sources']}], 'evidence_status': 'found', 'limitations': []})
    real_revalidate = QuestionService.revalidate
    calls = 0

    async def answer(_self, _request):
        return result

    def revalidate(self, value):
        nonlocal calls
        calls += 1
        # run returns, then one answer_part, then immediately before completed.
        if calls == 3:
            mutate(records, changing, 'deleted')
        real_revalidate(self, value)

    monkeypatch.setattr(QuestionService, 'run', answer)
    monkeypatch.setattr(QuestionService, 'revalidate', revalidate)
    with TestClient(app, base_url=settings.origin) as client:
        client.headers['x-csrf-token'] = client.get('/api/v1/session').json()['data']['csrf_token']
        response = client.post('/api/v1/questions', json={'request_id': str(uuid4()), 'question': '기록은?'})
    assert '사라질 제목' not in response.text and '마지막 순간' not in response.text
    if cited:
        assert 'event: invalidated' in response.text
        assert 'event: completed' not in response.text
    else:
        completed = next(chunk for chunk in response.text.split('\n\n') if chunk.startswith('event: completed'))
        payload = json.loads(completed.split('\ndata: ', 1)[1])['result']
        assert payload['retrieval']['truncated'] is True
        assert [row['source']['capture_id'] for row in payload['retrieval']['items']] == [stable['id']]
        assert not any(key.startswith('_') for key in payload)
