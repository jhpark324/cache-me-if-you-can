"""Importer transaction boundaries; no server, model, account, or network access."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from uuid import NAMESPACE_URL, uuid5

spec = importlib.util.spec_from_file_location('seed_conversations', Path(__file__).parents[1] / 'seed_conversations.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def fixture():
    def case(key, body, kinds, sources=()):
        save = '이 내용을 세컨드브레인에 저장해 줘.'
        return {'key': key, 'group': '학습', 'title': '[테스트] ' + key,
                'conversation': [{'role': 'assistant', 'text': body}, {'role': 'user', 'text': save}],
                'explicit_save_request': save,
                'record': {'title': '[테스트] ' + key, 'body_markdown': body, 'kinds': kinds,
                           'concept_hints': ['학습'], 'source_keys': list(sources)},
                'retrieval_checks': [{'query': key, 'expected_text': body, 'avoid_claims': ['실제 사용자 정보']} ]}
    first = case('learn', '가상 학습자 🧠 e\u0301\n부분 근거를 저장한다.', ['knowledge'])
    first['record']['nodes_spec'] = [{'kind': 'explanation', 'origin': 'ai_explanation',
                                    'verification_state': 'unverified', 'label': '근거', 'text': '🧠 e\u0301'}]
    return {'batch': seed.BATCH, 'synthetic': True, 'cases': [first, case('apply', '가상 프로젝트의 적용 제안', ['idea'], ['learn'])]}


class FakeClient:
    def __init__(self, manifest):
        self.manifest, self.calls, self.receipts, self.revisions = manifest, [], {}, {}
        self.lose_response_once = False
        self.records = {'existing': {'id': 'existing', 'revision_id': 'existing-revision', 'state_version': 1,
            'title': '사용자의 기존 제목', 'body_markdown': '사용자의 기존 메모', 'kinds': [],
            'visibility': 'private', 'completion_state': None}}

    async def call_tool(self, name, arguments):
        self.calls.append((name, deepcopy(arguments)))
        if name == 'capture_list':
            value = {'items': list(self.records.values()), 'next_cursor': None}
        elif name == 'capture_create':
            payload = arguments['input']
            manifest = seed.read_json(self.manifest)
            entry = next(item for item in manifest['entries'].values() if item['request_id'] == payload['request_id'])
            assert entry['state'] == 'pending'
            assert entry['payload'] == payload
            assert entry['payload_sha256'] == seed.fingerprint(payload)
            replayed = payload['request_id'] in self.receipts
            if replayed:
                capture = self.receipts[payload['request_id']]
            else:
                capture_id = str(uuid5(NAMESPACE_URL, payload['request_id']))
                capture = {'id': capture_id, 'revision_id': str(uuid5(NAMESPACE_URL, capture_id)),
                    'state_version': 1, 'title': payload['title'], 'body_markdown': payload['body_markdown'],
                    'kinds': payload['kinds'], 'visibility': payload.get('visibility', 'public'),
                    'completion_state': payload.get('completion_state'), 'event_time': payload.get('event_time'),
                    'concept_hints': payload.get('concept_hints', []), 'nodes': [],
                    'sources': [{'source': source} for source in payload['sources']],
                    'index_state': {'status': 'ready'}, 'concept_state': {'status': 'ready'}}
                for ordinal, requested in enumerate(payload['nodes']):
                    node_id = str(uuid5(NAMESPACE_URL, capture_id + ':node:' + str(ordinal)))
                    node = {'label': None, 'origin': 'unspecified', 'verification_state': 'unknown',
                            'verification_note': None, 'concept_hints': [], **requested, 'id': node_id}
                    node['text'] = capture['body_markdown'][node['body_start']:node['body_end']]
                    node['source'] = {'capture_id': capture_id, 'revision_id': capture['revision_id'],
                                      'node_id': node_id, 'body_start': node['body_start'], 'body_end': node['body_end']}
                    capture['nodes'].append(node)
                self.records[capture_id] = capture
                self.revisions[capture['revision_id']] = deepcopy(capture)
                self.receipts[payload['request_id']] = capture
            if self.lose_response_once:
                self.lose_response_once = False
                raise ConnectionError('response lost after commit')
            value = {'capture': capture, 'replayed': replayed}
        elif name == 'capture_get':
            value = self.revisions[arguments['revision_id']] if arguments.get('revision_id') else self.records[arguments['capture_id']]
        elif name in {'knowledge_search', 'knowledge_context'}:
            captures = [capture for capture in self.records.values() if capture['title'] == '[테스트] ' + arguments['query']]
            items = []
            for capture in captures:
                body = capture['body_markdown']
                source = {'capture_id': capture['id'], 'revision_id': capture['revision_id'], 'body_start': 0, 'body_end': len(body)}
                items.append({'source': source, 'matched_spans': [{'body_start': 0, 'body_end': len(body)}], 'text': body})
            value = {'items': items, 'evidence_status': 'found'}
        elif name == 'source_get':
            source = arguments['source']
            capture = self.records[source['capture_id']]
            node = next((node for node in capture.get('nodes', []) if node['id'] == source.get('node_id')), None)
            value = {'text': capture['body_markdown'][source['body_start']:source['body_end']], 'capture': capture, 'node': node}
        else:
            raise AssertionError('Unexpected or destructive tool: ' + name)
        return SimpleNamespace(is_error=False, structured_content={'ok': True, 'data': value})


class SeedValidationTests(unittest.TestCase):
    def test_exact_unicode_offsets_and_resolved_source_ids(self):
        dataset = fixture()
        self.assertEqual(seed.validate_dataset(dataset, expected_count=2)['cases'], 2)
        first = seed.build_payload(dataset, dataset['cases'][0], {})
        node = first['nodes'][0]
        self.assertEqual(first['body_markdown'][node['body_start']:node['body_end']], '🧠 e\u0301')
        self.assertEqual(node['body_end'] - node['body_start'], 4)
        self.assertNotIn('nodes_spec', first)
        self.assertNotIn('text', node)
        entries = {'learn': {'state': 'committed', 'capture_id': 'actual-id', 'revision_id': 'actual-revision'}}
        second = seed.build_payload(dataset, dataset['cases'][1], entries)
        self.assertEqual(second['sources'], [{'capture_id': 'actual-id', 'revision_id': 'actual-revision'}])
        self.assertEqual(first['request_id'], seed.build_payload(dataset, dataset['cases'][0], {})['request_id'])

    def test_rejects_unsafe_or_ambiguous_scenarios_before_import(self):
        changes = [
            lambda data: data.update(synthetic=False),
            lambda data: data['cases'][0]['record'].update(kinds=['procedure']),
            lambda data: data['cases'][0]['record'].update(source_keys=['apply']),
            lambda data: data['cases'][0]['record'].update(nodes_spec=[{'text': '없는 문장'}]),
            lambda data: data['cases'][0]['record'].update(body_markdown='가상 🧠 e\u0301 와 🧠 e\u0301'),
            lambda data: data['cases'][0].update(explicit_save_request='그냥 대화'),
            lambda data: data['cases'][1].update(key='learn'),
            lambda data: data['cases'][0]['retrieval_checks'][0].update(expected_text='본문에 없는 근거'),
        ]
        for change in changes:
            with self.subTest(change=change):
                data = fixture()
                change(data)
                with self.assertRaises(seed.SeedError):
                    seed.validate_dataset(data, expected_count=2)

    def test_atomic_manifest_replaces_json_without_partial_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            seed.atomic_json(path, {'한글': '처음'})
            seed.atomic_json(path, {'한글': '다음'})
            self.assertEqual(seed.read_json(path), {'한글': '다음'})
            self.assertEqual(list(Path(directory).iterdir()), [path])


class SeedImportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.manifest = Path(self.temporary.name) / 'manifest.json'
        self.dataset = fixture()
        self.client = FakeClient(self.manifest)
        self.endpoint = 'http://127.0.0.1:8000/mcp/'

    async def test_lost_response_reuses_pending_payload_and_creates_no_duplicates(self):
        self.client.lose_response_once = True
        with self.assertRaises(ConnectionError):
            await seed.import_records(self.dataset, self.manifest, self.client, self.endpoint)
        pending = seed.read_json(self.manifest)['entries']['learn']
        self.assertEqual(pending['state'], 'pending')
        first_payload = deepcopy(pending['payload'])
        result = await seed.import_records(self.dataset, self.manifest, self.client, self.endpoint)
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['resumed'], 1)
        self.assertEqual(len(self.client.records), 3)
        committed = seed.read_json(self.manifest)
        self.assertEqual(committed['entries']['learn']['payload'], first_payload)
        self.assertTrue(committed['entries']['learn']['replayed'])
        self.assertEqual(committed['entries']['apply']['payload']['sources'][0]['capture_id'], committed['entries']['learn']['capture_id'])
        calls_before = len([name for name, _ in self.client.calls if name == 'capture_create'])
        repeated = await seed.import_records(self.dataset, self.manifest, self.client, self.endpoint)
        self.assertEqual(repeated['created'], 0)
        self.assertEqual(calls_before, len([name for name, _ in self.client.calls if name == 'capture_create']))
        serialized = self.manifest.read_text()
        self.assertNotIn('사용자의 기존 메모', serialized)
        self.assertNotIn('사용자의 기존 제목', serialized)
        self.assertNotIn('Authorization', serialized)

    async def test_changed_record_or_manifest_payload_cannot_reuse_batch(self):
        await seed.import_records(self.dataset, self.manifest, self.client, self.endpoint)
        changed = deepcopy(self.dataset)
        changed['cases'][0]['record']['body_markdown'] += '\n추가 내용'
        before = len(self.client.calls)
        with self.assertRaises(seed.SeedError):
            await seed.import_records(changed, self.manifest, self.client, self.endpoint)
        self.assertEqual(before, len(self.client.calls))
        manifest = seed.read_json(self.manifest)
        manifest['entries']['learn']['payload']['title'] = '[테스트] 변경'
        seed.atomic_json(self.manifest, manifest)
        with self.assertRaises(seed.SeedError):
            await seed.import_records(self.dataset, self.manifest, self.client, self.endpoint)
        self.assertEqual(before, len(self.client.calls))

    async def test_verify_checks_real_spans_and_existing_record_preservation(self):
        await seed.import_records(self.dataset, self.manifest, self.client, self.endpoint)
        report = await seed.verify_records(self.dataset, self.manifest, self.client, self.endpoint)
        self.assertTrue(report['passed'])
        self.assertEqual(report['passed_checks'], 2)
        self.assertEqual(report['answer_quality'], 'not_evaluated')
        self.assertTrue(report['index_ready'])
        self.assertEqual(report['current_records_checked'], 2)
        self.assertEqual(report['nodes_roundtripped'], 1)
        self.assertEqual(report['preservation']['before_count'], 1)
        self.assertTrue(any(name == 'source_get' for name, _ in self.client.calls))
        self.client.records['existing']['body_markdown'] = '외부 변경'
        changed = await seed.verify_records(self.dataset, self.manifest, self.client, self.endpoint)
        self.assertFalse(changed['passed'])
        self.assertEqual(changed['preservation']['changed_ids'], ['existing'])

    async def test_current_body_change_cannot_pass_through_old_committed_snapshot(self):
        await seed.import_records(self.dataset, self.manifest, self.client, self.endpoint)
        capture_id = seed.read_json(self.manifest)['entries']['learn']['capture_id']
        self.client.records[capture_id]['body_markdown'] += '\n현재 본문이 수정됨'
        with self.assertRaises(seed.SeedError):
            await seed.verify_records(self.dataset, self.manifest, self.client, self.endpoint)

    async def test_matching_record_without_expected_span_is_not_retrieval_success(self):
        await seed.import_records(self.dataset, self.manifest, self.client, self.endpoint)
        original = self.client.call_tool

        async def wrong_span(name, arguments):
            result = await original(name, arguments)
            if name == 'knowledge_search':
                for item in result.structured_content['data']['items']:
                    item['matched_spans'] = [{'body_start': 0, 'body_end': 2}]
            return result

        self.client.call_tool = wrong_span
        report = await seed.verify_records(self.dataset, self.manifest, self.client, self.endpoint)
        self.assertFalse(report['passed'])
        self.assertTrue(all(check['search_found'] for check in report['checks']))
        self.assertTrue(all(not check['search_evidence'] for check in report['checks']))


if __name__ == '__main__':
    unittest.main()
