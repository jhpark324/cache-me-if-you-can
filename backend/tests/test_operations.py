import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from cache_me.api import install_error_handlers, router
from cache_me.db import Database
from cache_me.enrichment import ConceptEnrichment, body_segments
from cache_me.models import CaptureRevision, Concept, ConceptEnrichmentJob, MutationReceipt
from cache_me.records import DomainError, RecordService
from cache_me.schemas import CreateCaptureInput, RetryConceptsInput, UpdateCaptureInput


@pytest.fixture
def records(tmp_path):
    database = Database(tmp_path / 'operations.sqlite3')
    yield RecordService(database)
    database.close()


def create(records, body, **kwargs):
    return records.create(CreateCaptureInput(request_id=uuid4(), body_markdown=body, **kwargs))['capture']


def expected(capture):
    return {'capture_id': capture['id'], 'expected_revision_id': capture['revision_id'], 'expected_state_version': capture['state_version']}


class PartitionModel:
    """Returns a topic only after actually receiving the final segment marker."""
    def __init__(self, *, fail_segment=None, omit_last_review=False, during_segment=None):
        self.inputs = []
        self.fail_segment = fail_segment
        self.omit_last_review = omit_last_review
        self.during_segment = during_segment

    def status(self):
        return {'connected': True, 'plan_enabled': True, 'selected_model': 'offline-test'}

    async def generate(self, prompt, instructions):
        value = json.loads(prompt)
        self.inputs.append(value)
        if 'segment_proposals' in value:
            topics = [topic for part in value['segment_proposals'] for topic in part['proposal']['new_concepts']]
            reviewed = list(range(value['segment_count']))
            if self.omit_last_review:
                reviewed.pop()
            return json.dumps({'reviewed_segments': reviewed, 'concept_ids': [], 'node_concepts': {}, 'new_concepts': topics})
        index = value['segment_index']
        if self.during_segment:
            self.during_segment(index)
        if index == self.fail_segment:
            raise RuntimeError('simulated provider interruption; must not commit partial topics')
        topics = []
        if '후반부전용주제' in value['capture']['body_markdown']:
            topics.append({'name': '후반부전용주제', 'description': '마지막 구간에만 등장하는 실제 테스트 주제', 'aliases': [], 'attach_to_capture': True, 'node_ids': []})
        return json.dumps({'concept_ids': [], 'node_concepts': {}, 'new_concepts': topics})


@pytest.mark.parametrize('body', [
    ('한글🧠 e\u0301\r\n\r\n' * 10000)[:100000],
    '가' * 100000,
    '# 제목\r\n' + ('내용\n' * 8000) + '마지막',
])
def test_classification_segments_cover_entire_unicode_body_exactly(body):
    spans = body_segments(body)
    assert ''.join(body[start:end] for start, end in spans) == body
    assert spans[0][0] == 0 and spans[-1][1] == len(body)
    assert all(0 < end - start <= 12000 for start, end in spans)
    assert all(spans[i][1] == spans[i + 1][0] for i in range(len(spans) - 1))
    assert len(spans) <= 20


@pytest.mark.parametrize('length', [20001, 100000])
def test_long_body_classifies_last_segment_and_commits_once(records, length):
    marker = '후반부전용주제'
    body = '가' * (length - len(marker)) + marker
    capture = create(records, body)
    model = PartitionModel()
    asyncio.run(ConceptEnrichment(records, model).process_one())
    current = records.get(capture['id'])
    assert current['body_markdown'] == body
    assert current['revision_no'] == 2
    assert current['concepts'][0]['name'] == marker
    assert current['concept_state']['status'] == 'ready'
    segments = [value['capture']['body_markdown'] for value in model.inputs if 'capture' in value]
    assert ''.join(segments) == body
    assert len(model.inputs) == len(segments) + 1
    with records.db.read() as session:
        assert session.scalar(select(func.count()).select_from(CaptureRevision)) == 2
        assert session.scalar(select(func.count()).select_from(Concept)) == 1
    # A completed job is not reclassified by the next worker iteration.
    asyncio.run(ConceptEnrichment(records, model).process_one())
    assert records.get(capture['id'])['revision_no'] == 2


def test_intermediate_model_failure_does_not_commit_partial_classification(records):
    body = '후반부전용주제' + '가' * 30000
    capture = create(records, body)
    asyncio.run(ConceptEnrichment(records, PartitionModel(fail_segment=1)).process_one())
    current = records.get(capture['id'])
    assert current['body_markdown'] == body and current['revision_no'] == 1
    assert current['concepts'] == []
    assert current['concept_state']['status'] == 'failed'
    with records.db.read() as session:
        assert session.scalar(select(func.count()).select_from(Concept)) == 0


def test_long_body_node_topics_are_not_copied_to_capture_topics(records):
    body = '가' * 30000 + '후반부전용주제'
    capture = create(records, body, nodes=[{'kind': 'explanation', 'body_start': 28000, 'body_end': len(body)}])
    class NodeTopicModel(PartitionModel):
        async def generate(self, prompt, instructions):
            value = json.loads(prompt)
            if 'capture' in value and '후반부전용주제' in value['capture']['body_markdown']:
                return json.dumps({'concept_ids': [], 'node_concepts': {}, 'new_concepts': [{'name': '후반부전용주제', 'description': '마지막 구간의 Node에만 해당하는 주제', 'attach_to_capture': False, 'node_ids': [capture['nodes'][0]['id']]}]})
            return await super().generate(prompt, instructions)
    asyncio.run(ConceptEnrichment(records, NodeTopicModel()).process_one())
    current = records.get(capture['id'])
    assert current['body_markdown'] == body and current['concepts'] == []
    assert current['nodes'][0]['text'] == body[28000:]
    assert current['nodes'][0]['concepts'][0]['name'] == '후반부전용주제'


def test_incomplete_reduce_cannot_skip_last_segment(records):
    capture = create(records, '가' * 30000 + '후반부전용주제')
    asyncio.run(ConceptEnrichment(records, PartitionModel(omit_last_review=True)).process_one())
    current = records.get(capture['id'])
    assert current['revision_id'] == capture['revision_id']
    assert current['concept_state']['status'] == 'failed'


def test_reducer_omitted_topics_complete_with_internal_diagnostics(records):
    capture = create(records, '가' * 30000 + '후반부전용주제')
    class OmittingReducer(PartitionModel):
        async def generate(self, prompt, instructions):
            value = json.loads(prompt)
            if 'segment_proposals' in value:
                return json.dumps({'reviewed_segments': list(range(value['segment_count'])), 'concept_ids': [], 'new_concepts': []})
            return await super().generate(prompt, instructions)
    asyncio.run(ConceptEnrichment(records, OmittingReducer()).process_one())
    current = records.get(capture['id'])
    assert current['revision_id'] == capture['revision_id']
    assert current['concept_state']['status'] == 'ready'
    assert current['concept_state']['unresolved_hints'] == []
    with records.db.read() as session:
        job = session.get(ConceptEnrichmentJob, current['concept_state']['job_id'])
        assert job.status == 'completed'
        assert '후반부전용주제' in job.unresolved_hints


def test_edit_during_long_classification_supersedes_old_lease(records):
    capture = create(records, '가' * 30000 + '후반부전용주제')
    def edit(index):
        if index == 0:
            records.update(UpdateCaptureInput(request_id=uuid4(), **expected(capture), changes={'body_markdown': '사용자가 정정한 새 본문'}))
    model = PartitionModel(during_segment=edit)
    asyncio.run(ConceptEnrichment(records, model).process_one())
    current = records.get(capture['id'])
    assert current['body_markdown'] == '사용자가 정정한 새 본문'
    assert current['concepts'] == [] and current['revision_no'] == 2
    assert len(model.inputs) == 1
    with records.db.read() as session:
        old = session.get(ConceptEnrichmentJob, capture['concept_state']['job_id'])
        assert old.status == 'superseded'


def failed_job(records):
    capture = create(records, '실패해도 저장되는 본문')
    job = records.claim_concept_job()
    records.fail_concept_job(job['job_id'], job['lease_token'], error_code='CLASSIFICATION_FAILED')
    return capture, job


def test_explicit_retry_reuses_job_without_content_change_and_is_idempotent(records):
    capture, job = failed_job(records)
    data = RetryConceptsInput(request_id=uuid4(), **expected(capture), job_id=job['job_id'])
    result = records.retry_concepts(data)
    assert result['capture']['concept_state']['status'] == 'pending'
    assert result['capture']['revision_id'] == capture['revision_id']
    assert result['capture']['state_version'] == capture['state_version']
    assert result['capture']['concept_state']['job_id'] == job['job_id']
    attempt = records.claim_concept_job()
    assert attempt['attempt_count'] == 1 and attempt['job_id'] == job['job_id']
    assert records.retry_concepts(data)['replayed'] is True
    with records.db.read() as session:
        assert session.get(ConceptEnrichmentJob, job['job_id']).status == 'running'
        assert session.get(ConceptEnrichmentJob, job['job_id']).attempt_count == 1
        assert session.scalar(select(func.count()).select_from(CaptureRevision)) == 1
    records.apply_concept_job(attempt['job_id'], attempt['lease_token'], concept_ids=[])
    assert records.get(capture['id'])['concept_state']['status'] == 'ready'


def test_retry_rejects_running_and_old_revision_jobs(records):
    capture = create(records, '원래 본문')
    job = records.claim_concept_job()
    data = RetryConceptsInput(request_id=uuid4(), **expected(capture), job_id=job['job_id'])
    with pytest.raises(DomainError) as error:
        records.retry_concepts(data)
    assert error.value.code == 'JOB_NOT_RETRYABLE'
    records.update(UpdateCaptureInput(request_id=uuid4(), **expected(capture), changes={'body_markdown': '새 본문'}))
    with pytest.raises(DomainError) as error:
        records.retry_concepts(data)
    assert error.value.code == 'VERSION_CONFLICT'


def test_exhausted_expired_lease_becomes_failed_and_explicitly_retryable(records):
    capture = create(records, '작업자가 종료된 본문')
    job = records.claim_concept_job()
    with records.db.write() as session:
        row = session.get(ConceptEnrichmentJob, job['job_id'])
        row.attempt_count = 3
        row.lease_until = '2000-01-01T00:00:00.000Z'
    assert records.claim_concept_job() is None
    assert records.get(capture['id'])['concept_state']['status'] == 'failed'
    records.retry_concepts(RetryConceptsInput(request_id=uuid4(), **expected(capture), job_id=job['job_id']))
    assert records.claim_concept_job()['attempt_count'] == 1


def test_retry_http_contract_and_version_conflict(records):
    app = FastAPI()
    app.state.records = records
    app.include_router(router)
    install_error_handlers(app)
    capture, job = failed_job(records)
    payload = {'request_id': str(uuid4()), **expected(capture), 'job_id': job['job_id']}
    with TestClient(app) as client:
        response = client.post(f"/api/v1/captures/{capture['id']}/concept-retry", json=payload)
        assert response.status_code == 200
        assert response.json()['data']['capture']['concept_state']['status'] == 'pending'
        other = client.post(f"/api/v1/captures/{capture['id']}/concept-retry", json=payload | {'request_id': str(uuid4())})
        assert other.status_code == 409 and other.json()['error']['code'] == 'JOB_NOT_RETRYABLE'


def test_web_login_cancellation_uses_current_session_and_csrf(tmp_path):
    from cache_me.config import Settings
    from cache_me.main import create_app
    settings = Settings(tmp_path / 'web-state', background_jobs=False)
    app = create_app(settings)
    with TestClient(app, base_url=settings.origin) as client:
        csrf = client.get('/api/v1/session').json()['data']['csrf_token']
        client.headers['x-csrf-token'] = csrf
        assert not client.get('/api/v1/settings').json()['data']['auth']['pending_login']
        assert client.post('/api/v1/auth/login', json={}).status_code == 200
        assert client.get('/api/v1/settings').json()['data']['auth']['pending_login']
        assert client.post('/api/v1/auth/cancel', headers={'x-csrf-token': 'wrong'}).status_code == 403
        assert client.post('/api/v1/auth/cancel').json()['data']['cancelled']
        assert not client.get('/api/v1/settings').json()['data']['auth']['pending_login']
        assert not client.post('/api/v1/auth/cancel').json()['data']['cancelled']
