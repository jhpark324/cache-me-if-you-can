"""Topic candidates inform the classifier without deciding record membership."""
import asyncio
import json
from uuid import UUID

import pytest

from cache_me.enrichment import ConceptEnrichment
from cache_me.models import Concept
from cache_me.topic_candidates import TopicCandidateSearch
from test_operations import create, records
from test_search import services


class ScriptedModel:
    def __init__(self, respond):
        self.respond, self.inputs = respond, []

    def status(self):
        return {'connected': True, 'plan_enabled': True, 'selected_model': 'offline-test'}

    async def generate(self, prompt, instructions):
        value = json.loads(prompt)
        self.inputs.append(value)
        return json.dumps(self.respond(value))


class TopicRanker:
    def __init__(self, respond):
        self.respond, self.inputs = respond, []

    def rank(self, catalog, text, limit=30):
        self.inputs.append(text)
        return self.respond(text)


def catalog_items(count):
    return {str(UUID(int=index + 1)): {
        'id': str(UUID(int=index + 1)), 'name': f'분류 주제 {index:03d}',
        'description': f'주제 {index:03d}의 적용 범위', 'aliases': [], 'state_version': 1,
        'created_at': f'2026-01-01T00:00:00.{index:03d}Z',
        'updated_at': f'2026-01-01T00:00:00.{index:03d}Z',
    } for index in range(count)}


def store_catalog(records, count):
    catalog = catalog_items(count)
    with records.db.write() as session:
        session.add_all(Concept(brain_id=records.brain_id,
            **{key: value for key, value in item.items() if key != 'aliases'})
            for item in catalog.values())
    return catalog


def test_small_catalog_sends_every_topic_without_semantic_lookup(records):
    catalog = store_catalog(records, 100)
    body = '# 원문\r\n\r\n가까운 주제가 있어도 자동 연결하지 않습니다. 👩🏽‍💻'
    capture = create(records, body)
    ranker = TopicRanker(lambda text: list(catalog))
    model = ScriptedModel(lambda value: {})

    asyncio.run(ConceptEnrichment(records, model, topic_search=ranker).process_one())

    assert len(model.inputs) == 1
    assert {item['id'] for item in model.inputs[0]['candidate_concepts']} == set(catalog)
    assert ranker.inputs == []
    current = records.get(capture['id'])
    assert current['body_markdown'] == body and current['concepts'] == []
    assert current['revision_id'] == capture['revision_id']
    assert current['concept_state']['status'] == 'ready'


def test_semantic_candidate_recovers_old_topic_beside_current_and_lexical(records):
    catalog = catalog_items(105)
    semantic, current, lexical = list(catalog.values())[:3]
    lexical['aliases'] = ['캐시 만료']
    capture = create(records, '캐시 만료를 처리하는 방법을 정리했습니다.')
    capture['concepts'] = [current]
    ranker = TopicRanker(lambda text: [semantic['id']])
    worker = ConceptEnrichment(records, None, topic_search=ranker)
    segment = worker.segment_capture(capture, 0, len(capture['body_markdown']))
    baseline = ConceptEnrichment(records, None).ranked_candidates(catalog, capture, segment)

    candidates = worker.ranked_candidates(catalog, capture, segment)

    assert semantic['id'] not in {item['id'] for item in baseline}
    ids = [item['id'] for item in candidates]
    assert {semantic['id'], current['id'], lexical['id']}.issubset(ids)
    assert len(ids) == len(set(ids)) <= 100
    assert ranker.inputs


def test_optional_semantic_failure_keeps_classification_and_original_body(records):
    store_catalog(records, 101)
    body = '이미 저장된 내용의 분류는 의미 검색 장애와 관계없이 계속합니다.'
    capture = create(records, body)
    def unavailable(text):
        raise RuntimeError('optional topic index is unavailable')
    ranker = TopicRanker(unavailable)
    model = ScriptedModel(lambda value: {})
    baseline_worker = ConceptEnrichment(records, None)
    catalog = baseline_worker.candidate_catalog(capture)
    baseline = baseline_worker.ranked_candidates(catalog, capture,
        baseline_worker.segment_capture(capture, 0, len(body)))

    asyncio.run(ConceptEnrichment(records, model, topic_search=ranker).process_one())

    assert ranker.inputs
    assert model.inputs[0]['candidate_concepts'] == baseline
    assert len(model.inputs) == 1
    current = records.get(capture['id'])
    assert current['concept_state']['status'] == 'ready'
    assert current['body_markdown'] == body and current['concepts'] == []
    assert current['revision_id'] == capture['revision_id']


@pytest.mark.parametrize('action', ['reuse', 'keep', 'defer'])
def test_unseen_topic_gets_one_review_without_forcing_membership(records, action):
    catalog = store_catalog(records, 101)
    old_topic, existing = list(catalog.values())[0], list(catalog.values())[-1]
    body = '# 기록\r\n\r\n본문과 Node의 원래 위치를 그대로 유지합니다. e\u0301'
    capture = create(records, body, nodes=[{'kind': 'explanation', 'body_start': 9, 'body_end': len(body)}])
    node_id = capture['nodes'][0]['id']
    proposal = {'name': '원인 추적', 'description': '재검토전용설명: 원인을 되짚는 분석 절차',
                'attach_to_capture': False, 'node_ids': [node_id]}
    ranker = TopicRanker(lambda text: [old_topic['id']] if '재검토전용설명' in text else [])
    def respond(value):
        if value.get('task') == 'review_new_topics':
            assert old_topic['id'] in {item['id'] for item in value['candidate_concepts']}
            decision = {'proposal_index': 0, 'action': action}
            if action == 'reuse':
                decision['concept_id'] = old_topic['id']
            return {'decisions': [decision]}
        return {'concept_ids': [existing['id']], 'new_concepts': [proposal]}
    model = ScriptedModel(respond)

    asyncio.run(ConceptEnrichment(records, model, topic_search=ranker).process_one())

    assert len(model.inputs) == 2
    assert old_topic['id'] not in {item['id'] for item in model.inputs[0]['candidate_concepts']}
    assert model.inputs[1]['task'] == 'review_new_topics'
    current = records.get(capture['id'])
    assert current['body_markdown'] == body
    assert [item['id'] for item in current['concepts']] == [existing['id']]
    assert current['nodes'][0]['text'] == body[9:]
    topics = current['nodes'][0]['concepts']
    if action == 'reuse':
        assert [item['id'] for item in topics] == [old_topic['id']]
    elif action == 'keep':
        assert [item['name'] for item in topics] == [proposal['name']]
        assert topics[0]['id'] != old_topic['id']
    else:
        assert topics == []
        assert proposal['name'] in current['concept_state']['unresolved_hints']
    assert current['concept_state']['status'] == ('needs_review' if action == 'defer' else 'ready')


def test_already_seen_candidate_does_not_trigger_new_topic_review(records):
    catalog = store_catalog(records, 101)
    seen = list(catalog.values())[-1]
    body = '기존 후보를 검토해도 별개의 새 주제가 적절할 수 있습니다.'
    capture = create(records, body)
    ranker = TopicRanker(lambda text: [seen['id']])
    model = ScriptedModel(lambda value: {'new_concepts': [{
        'name': '독립적인 관점', 'description': '기존 주제와 구별되는 적용 범위',
    }]})

    asyncio.run(ConceptEnrichment(records, model, topic_search=ranker).process_one())

    assert len(model.inputs) == 1
    assert seen['id'] in {item['id'] for item in model.inputs[0]['candidate_concepts']}
    current = records.get(capture['id'])
    assert current['body_markdown'] == body
    assert [item['name'] for item in current['concepts']] == ['독립적인 관점']
    assert seen['id'] not in {item['id'] for item in current['concepts']}
    assert current['concept_state']['status'] == 'ready'


def test_topic_cache_warms_bounded_current_rows_and_reuses_storage(services, monkeypatch):
    records, search, embedding = services
    catalog = store_catalog(records, 101)
    first_id = next(iter(catalog))
    catalog[first_id] = records.concept_update({'request_id': str(UUID(int=1001)),
        'concept_id': first_id, 'expected_state_version': 1,
        'changes': {'description': '아주 긴 적용 범위 설명입니다. ' * 40, 'aliases': ['TTL']}})
    documents, queries = [], []
    original_documents, original_query = embedding.encode_documents, embedding.encode_query
    def encode_documents(texts):
        documents.extend(texts)
        return original_documents(texts)
    def encode_query(text):
        queries.append(text)
        return original_query(text)
    monkeypatch.setattr(embedding, 'encode_documents', encode_documents)
    monkeypatch.setattr(embedding, 'encode_query', encode_query)
    monkeypatch.setattr(embedding, 'offsets', lambda text: [(i, i + 1) for i in range(len(text))], raising=False)
    topics = TopicCandidateSearch(search)

    topics.refresh()
    assert not embedding.ready and documents == []
    search.prepare()
    assert topics.rank(catalog, 'TTL') == [] and documents == []
    topics.refresh()
    assert len(documents) == 8
    assert all(embedding.count_tokens(text) <= 128 for text in documents)
    warmed = set(topics.rank(catalog, '시작 ' + '내용 ' * 70 + '마지막'))
    assert warmed == set(list(catalog)[:8])
    assert 1 <= len(queries) <= 3
    assert all(embedding.count_tokens(text, 'query') <= 64 for text in queries)
    assert len(documents) == 8  # Lookups never encode missing topic documents.

    catalog[first_id] = records.concept_update({'request_id': str(UUID(int=1002)),
        'concept_id': first_id, 'expected_state_version': 2,
        'changes': {'description': '수정된 주제 정의'}})
    assert first_id not in topics.rank(catalog, 'TTL')
    previous = documents.copy()
    restarted = TopicCandidateSearch(search)
    restarted.refresh()
    assert len(documents) == 16
    assert set(previous[1:]).isdisjoint(documents[8:])
    assert first_id in restarted.rank(catalog, 'TTL')
