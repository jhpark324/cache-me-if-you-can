"""Validate and import synthetic conversation scenarios through the real MCP API."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / 'docs/examples/conversations/dataset.json'
BATCH = 'codex-conversations-2026-11-02-v1'
KINDS = {'knowledge', 'episode', 'context', 'idea', 'decision', 'artifact'}
NODE_KINDS = {'explanation', 'interpretation', 'hypothesis', 'question', 'event', 'emotion', 'proposal', 'decision', 'action', 'result'}
ORIGINS = {'user_report', 'user_interpretation', 'ai_explanation', 'unspecified'}
RECORD_FIELDS = {'title', 'body_markdown', 'kinds', 'concept_hints', 'source_keys', 'nodes_spec', 'event_time', 'completion_state', 'visibility'}


class SeedError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise SeedError(message)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def request_id(batch, key):
    return str(uuid5(NAMESPACE_URL, f'cache-me-if-you-can:{batch}:{key}'))


def node_inputs(record):
    body = record['body_markdown']
    result = []
    for spec in record.get('nodes_spec', []):
        text = spec.get('text')
        require(isinstance(text, str) and bool(text) and body.count(text) == 1,
                'Node text는 본문에 정확히 한 번 등장해야 합니다.')
        require(spec.get('kind') in NODE_KINDS, '알 수 없는 Node kind입니다.')
        require(spec.get('origin') in ORIGINS, 'Node origin을 명시해 주세요.')
        require(spec.get('verification_state') in {'unknown', 'unverified', 'verified'}, 'Node verification_state가 올바르지 않습니다.')
        require(set(spec) <= {'text', 'kind', 'origin', 'verification_state', 'verification_note', 'label'}, '지원하지 않는 Node 필드입니다.')
        if spec['verification_state'] == 'verified':
            require(bool((spec.get('verification_note') or '').strip()), '검증된 Node에는 검증 근거가 필요합니다.')
        start = body.index(text)
        result.append({key: value for key, value in spec.items() if key != 'text'} |
                      {'body_start': start, 'body_end': start + len(text)})
    return result


def validate_dataset(dataset, *, expected_count=40):
    require(isinstance(dataset, dict) and dataset.get('batch') == BATCH, '지원하지 않는 배치입니다.')
    require(dataset.get('synthetic') is True, '합성 자료임을 명시해야 합니다.')
    cases = dataset.get('cases')
    require(isinstance(cases, list) and bool(cases), 'cases가 비어 있습니다.')
    if expected_count is not None:
        require(len(cases) == expected_count, f'{expected_count}개 시나리오가 필요합니다.')
    seen, counts, checks = set(), Counter(), 0
    for case in cases:
        key = case.get('key')
        require(isinstance(key, str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]*', key) and key not in seen, '중복 또는 잘못된 case key입니다.')
        record = case.get('record')
        require(isinstance(record, dict) and set(record) <= RECORD_FIELDS, f'{key}: record 필드를 확인해 주세요.')
        title, body, kinds = record.get('title'), record.get('body_markdown'), record.get('kinds')
        require(isinstance(title, str) and title.startswith('[테스트]') and title == case.get('title'), f'{key}: [테스트] 제목이 일치해야 합니다.')
        require(isinstance(body, str) and body.strip() and len(body) <= 100_000 and len(body.encode()) <= 1_048_576, f'{key}: 본문 길이가 올바르지 않습니다.')
        require('가상' in body or '합성' in body, f'{key}: 본문에 합성 범위를 명시해 주세요.')
        require(isinstance(kinds, list) and all(isinstance(kind, str) and kind in KINDS for kind in kinds) and len(kinds) == len(set(kinds)), f'{key}: 여섯 유형 또는 미분류 []만 사용할 수 있습니다.')
        counts.update(kinds or ['unclassified'])
        hints = record.get('concept_hints', [])
        require(isinstance(hints, list) and len(hints) <= 20 and all(isinstance(hint, str) and 0 < len(hint.strip()) <= 100 for hint in hints), f'{key}: 주제 힌트가 올바르지 않습니다.')
        require(record.get('visibility', 'public') in {'public', 'private'}, f'{key}: visibility가 올바르지 않습니다.')
        require(record.get('completion_state') in {None, 'incomplete', 'completed'}, f'{key}: completion_state가 올바르지 않습니다.')
        sources = record.get('source_keys', [])
        require(isinstance(sources, list) and all(isinstance(source, str) and source in seen for source in sources) and len(sources) == len(set(sources)), f'{key}: source_keys는 앞서 저장하는 사례를 가리켜야 합니다.')
        require(isinstance(record.get('nodes_spec', []), list) and len(record.get('nodes_spec', [])) <= 200, f'{key}: Node 목록을 확인해 주세요.')
        node_inputs(record)
        conversation = case.get('conversation')
        require(isinstance(conversation, list) and len(conversation) >= 2 and all(isinstance(turn, dict) and turn.get('role') in {'user', 'assistant'} and isinstance(turn.get('text'), str) and turn['text'].strip() for turn in conversation), f'{key}: 대화 발췌가 필요합니다.')
        save = case.get('explicit_save_request')
        require(conversation[-1]['role'] == 'user' and conversation[-1]['text'] == save and any(word in save for word in ('저장', '넣어', '기록해', '남겨', '기억해', '보관해')), f'{key}: 마지막 사용자 발화는 명시적인 저장 요청이어야 합니다.')
        retrieval = case.get('retrieval_checks')
        require(isinstance(retrieval, list) and bool(retrieval), f'{key}: 검색 검증 항목이 필요합니다.')
        for check in retrieval:
            require(isinstance(check.get('query'), str) and check['query'].strip(), f'{key}: 검색 질문이 비어 있습니다.')
            require(isinstance(check.get('expected_text'), str) and bool(check['expected_text']) and check['expected_text'] in body, f'{key}: 기대 근거는 실제 본문 구간이어야 합니다.')
            require(isinstance(check.get('avoid_claims', []), list) and all(isinstance(value, str) for value in check.get('avoid_claims', [])), f'{key}: avoid_claims를 확인해 주세요.')
        checks += len(retrieval)
        seen.add(key)
    return {'batch': dataset['batch'], 'cases': len(cases), 'kinds': dict(sorted(counts.items())), 'retrieval_checks': checks}


def record_plan_fingerprint(dataset):
    # Editorial conversation/query corrections do not change a committed request.
    return fingerprint({'batch': dataset['batch'], 'records': [{'key': case['key'], 'record': case['record']} for case in dataset['cases']]})


def build_payload(dataset, case, entries):
    record = case['record']
    payload = {key: value for key, value in record.items() if key not in {'source_keys', 'nodes_spec'}}
    payload['request_id'] = request_id(dataset['batch'], case['key'])
    payload['nodes'] = node_inputs(record)
    payload['sources'] = []
    for key in record.get('source_keys', []):
        previous = entries.get(key)
        require(previous is not None and previous.get('state') == 'committed', f'{case["key"]}: 출처 {key}의 커밋이 먼저 필요합니다.')
        payload['sources'].append({'capture_id': previous['capture_id'], 'revision_id': previous['revision_id']})
    return payload


async def call(client, name, arguments):
    result = await client.call_tool(name, arguments)
    envelope = result.structured_content
    require(isinstance(envelope, dict), f'{name}: 구조화 응답이 없습니다.')
    if result.is_error or not envelope.get('ok'):
        code = envelope.get('error', {}).get('code', 'MCP_ERROR')
        raise SeedError(f'{name}: {code}')
    return envelope['data']


def record_snapshot(capture):
    # Do not persist existing users' titles, text, sources, or account information.
    return {'revision_id': capture['revision_id'], 'state_version': capture['state_version'],
            'body_sha256': fingerprint(capture['body_markdown']), 'title_sha256': fingerprint(capture.get('title')),
            'visibility': capture.get('visibility'), 'completion_state': capture.get('completion_state')}


async def snapshot_existing(client):
    result, cursor, seen = {}, None, set()
    while True:
        page = await call(client, 'capture_list', {'limit': 100, 'cursor': cursor})
        for item in page['items']:
            capture = await call(client, 'capture_get', {'capture_id': item['id']})
            result[capture['id']] = record_snapshot(capture)
        cursor = page.get('next_cursor')
        if cursor is None:
            return result
        require(cursor not in seen, '목록 cursor가 반복됩니다.')
        seen.add(cursor)


def check_manifest(manifest, dataset, endpoint):
    require(manifest.get('schema_version') == 1 and manifest.get('batch') == dataset['batch'], 'manifest 배치가 일치하지 않습니다.')
    require(manifest.get('endpoint') == endpoint, 'manifest와 서버 주소가 다릅니다. 별도 manifest를 사용하세요.')
    require(manifest.get('record_plan_sha256') == record_plan_fingerprint(dataset), '저장 계획이 변경되었습니다. 같은 배치의 요청을 바꾸지 마세요.')
    require(set(manifest['entries']) <= {case['key'] for case in dataset['cases']}, 'manifest에 알 수 없는 사례가 있습니다.')
    for case in dataset['cases']:
        entry = manifest['entries'].get(case['key'])
        if entry is None:
            continue
        payload = build_payload(dataset, case, manifest['entries'])
        require(entry['request_id'] == payload['request_id'] and entry['payload'] == payload and entry['payload_sha256'] == fingerprint(payload), f'{case["key"]}: 고정 요청 payload 또는 hash가 변경되었습니다.')


def check_capture_payload(capture, payload):
    require(capture['body_markdown'] == payload['body_markdown'] and capture.get('title') == payload.get('title') and set(capture['kinds']) == set(payload['kinds']), '커밋된 본문·제목·유형이 저장 요청과 다릅니다.')
    defaults = {'visibility': 'public', 'completion_state': None, 'concept_hints': []}
    require(all(capture.get(field) == payload.get(field, default) for field, default in defaults.items()), '저장된 공개 범위·완료 상태·주제 힌트가 요청과 다릅니다.')
    expected_event = payload.get('event_time')
    if expected_event is not None:
        expected_event = {'expression': None, 'value': None, 'timezone': None} | expected_event
    require(capture.get('event_time') == expected_event, '저장된 사건 시점이 요청과 다릅니다.')
    nodes = capture.get('nodes', [])
    requested_nodes = payload.get('nodes', [])
    require(len(nodes) == len(requested_nodes), '저장된 Node 수가 요청과 다릅니다.')
    for node, requested in zip(nodes, requested_nodes):
        expected_node = {'label': None, 'origin': 'unspecified', 'verification_state': 'unknown',
                         'verification_note': None, 'concept_hints': []} | requested
        require(all(node.get(field) == value for field, value in expected_node.items()), '저장된 Node의 의미 필드가 요청과 다릅니다.')
        require(node['text'] == capture['body_markdown'][node['body_start']:node['body_end']], 'Node 본문과 구간이 일치하지 않습니다.')
    def source_identity(source):
        return fingerprint({field: source.get(field) for field in ('capture_id', 'revision_id', 'node_id', 'body_start', 'body_end')})
    require(sorted(source_identity(view['source']) for view in capture.get('sources', [])) ==
            sorted(source_identity(source) for source in payload.get('sources', [])), '저장된 원래 출처가 요청과 다릅니다.')


async def check_commit(client, entry):
    capture = await call(client, 'capture_get', {'capture_id': entry['capture_id'], 'revision_id': entry['revision_id']})
    check_capture_payload(capture, entry['payload'])
    require(capture['revision_id'] == entry['revision_id'], '커밋된 revision이 일치하지 않습니다.')
    return capture


async def import_records(dataset, manifest_path, client, endpoint):
    validate_dataset(dataset, expected_count=None)
    manifest_path = Path(manifest_path)
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        check_manifest(manifest, dataset, endpoint)
    else:
        manifest = {'schema_version': 1, 'batch': dataset['batch'], 'endpoint': endpoint,
                    'created_at': now(), 'dataset_sha256': fingerprint(dataset),
                    'record_plan_sha256': record_plan_fingerprint(dataset),
                    'existing_before': await snapshot_existing(client), 'entries': {}}
        atomic_json(manifest_path, manifest)
    created, resumed = 0, 0
    for case in dataset['cases']:
        key = case['key']
        payload = build_payload(dataset, case, manifest['entries'])
        entry = manifest['entries'].get(key)
        if entry is None:
            entry = {'request_id': payload['request_id'], 'payload': payload,
                     'payload_sha256': fingerprint(payload), 'state': 'pending'}
            manifest['entries'][key] = entry
            # Must complete before the tool call, including on the first attempt.
            atomic_json(manifest_path, manifest)
        if entry['state'] != 'committed':
            result = await call(client, 'capture_create', {'input': entry['payload']})
            capture = result.get('capture')
            require(capture is not None, f'{key}: 커밋 결과를 읽을 수 없습니다.')
            entry.update({'state': 'committed', 'capture_id': capture['id'], 'revision_id': capture['revision_id'],
                          'state_version': capture['state_version'], 'replayed': result.get('replayed', False), 'committed_at': now()})
            atomic_json(manifest_path, manifest)
            created += not entry['replayed']
            resumed += bool(entry['replayed'])
        else:
            resumed += 1
        await check_commit(client, entry)
        entry['body_verified_at'] = now()
        atomic_json(manifest_path, manifest)
    return {'batch': dataset['batch'], 'committed': len(manifest['entries']), 'created': created, 'resumed': resumed,
            'existing_before': len(manifest['existing_before']), 'manifest': str(manifest_path)}


async def verify_records(dataset, manifest_path, client, endpoint):
    validate_dataset(dataset, expected_count=None)
    manifest = read_json(manifest_path)
    check_manifest(manifest, dataset, endpoint)
    require(all(manifest['entries'].get(case['key'], {}).get('state') == 'committed' for case in dataset['cases']), '아직 커밋되지 않은 사례가 있습니다.')
    report = {'batch': dataset['batch'], 'checked_at': now(), 'answer_quality': 'not_evaluated',
              'synthetic_conversations': True, 'index_states': {}, 'concept_states': {}, 'checks': [],
              'current_records_checked': 0, 'nodes_roundtripped': 0}
    index_states, concept_states = Counter(), Counter()
    for case in dataset['cases']:
        entry = manifest['entries'][case['key']]
        await check_commit(client, entry)
        current = await call(client, 'capture_get', {'capture_id': entry['capture_id']})
        check_capture_payload(current, entry['payload'])
        report['current_records_checked'] += 1
        for node in current['nodes']:
            detail = await call(client, 'source_get', {'source': node['source']})
            require(detail['text'] == node['text'] and (detail.get('node') or {}).get('id') == node['id'], 'Node 출처 왕복 결과가 현재 기록과 다릅니다.')
            report['nodes_roundtripped'] += 1
        index_states.update([current.get('index_state', {}).get('status', 'unknown')])
        concept_states.update([current.get('concept_state', {}).get('status', 'unknown')])
        for expectation in case['retrieval_checks']:
            query, expected_text = expectation['query'], expectation['expected_text']
            check = {'case': case['key'], 'query': query, 'search_found': False, 'search_evidence': False,
                     'context_evidence': False, 'source_roundtrip': True, 'avoid_claims': expectation.get('avoid_claims', [])}
            try:
                hits = (await call(client, 'knowledge_search', {'query': query, 'limit': 5}))['items']
                check['search_capture_ids'] = [hit['source']['capture_id'] for hit in hits]
                for rank, hit in enumerate(hits, 1):
                    if hit['source']['capture_id'] != entry['capture_id']:
                        continue
                    check.update({'search_found': True, 'rank': rank})
                    for span in hit['matched_spans']:
                        source = dict(hit['source'], **span)
                        detail = await call(client, 'source_get', {'source': source})
                        check['search_evidence'] |= expected_text in detail['text']
                        body = detail['capture']['body_markdown']
                        check['source_roundtrip'] &= detail['text'] == body[span['body_start']:span['body_end']]
                context = await call(client, 'knowledge_context', {'query': query, 'limit': 10})
                check['context_status'] = context.get('evidence_status')
                for item in context['items']:
                    if item['source']['capture_id'] != entry['capture_id']:
                        continue
                    detail = await call(client, 'source_get', {'source': item['source']})
                    check['context_evidence'] |= expected_text in item['text'] and expected_text in detail['text']
                    check['source_roundtrip'] &= detail['text'] == item['text']
            except SeedError as error:
                check['error'] = str(error)
            check['passed'] = all(check[key] for key in ('search_found', 'search_evidence', 'context_evidence', 'source_roundtrip')) and 'error' not in check
            report['checks'].append(check)
    after, changed, missing = await snapshot_existing(client), [], []
    for capture_id, before in manifest['existing_before'].items():
        if capture_id not in after:
            missing.append(capture_id)
        elif before != after[capture_id]:
            changed.append(capture_id)
    report.update({'index_states': dict(index_states), 'concept_states': dict(concept_states),
                   'preservation': {'before_count': len(manifest['existing_before']), 'changed_ids': changed,
                                    'missing_ids': missing, 'passed': not changed and not missing},
                   'total_records_after': len(after), 'passed_checks': sum(check['passed'] for check in report['checks']),
                   'total_checks': len(report['checks'])})
    report['index_ready'] = index_states.get('ready', 0) == len(dataset['cases'])
    report['passed'] = report['passed_checks'] == report['total_checks'] and report['preservation']['passed'] and report['index_ready']
    manifest['last_verification'] = report
    atomic_json(manifest_path, manifest)
    return report


async def connected_action(args, dataset):
    sys.path.insert(0, str(ROOT / 'backend' / 'src'))
    import httpx2
    from filelock import FileLock
    from mcp.client import Client
    from mcp.client.streamable_http import streamable_http_client
    from second_brain.codex_integration import header_value
    from second_brain.config import Settings
    from second_brain.schemas import CreateCaptureInput

    settings = Settings.load()
    data_dir = Path(args.data_dir) if args.data_dir else settings.data_dir
    endpoint = args.url or settings.origin + '/mcp/'
    parsed = urlparse(endpoint)
    require(parsed.scheme in {'http', 'https'} and parsed.hostname in {'127.0.0.1', 'localhost', '::1'} and not parsed.username and not parsed.password and not parsed.query, '로컬 MCP 주소를 사용해 주세요.')
    manifest_path = Path(args.manifest) if args.manifest else data_dir / 'conversation-imports' / (BATCH + '.json')
    # Validate every field against the product model before connecting or writing.
    for case in dataset['cases']:
        placeholder_entries = {key: {'state': 'committed', 'capture_id': str(uuid5(NAMESPACE_URL, key)), 'revision_id': str(uuid5(NAMESPACE_URL, key + ':revision'))} for key in case['record'].get('source_keys', [])}
        CreateCaptureInput.model_validate(build_payload(dataset, case, placeholder_entries))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(manifest_path) + '.lock', timeout=0):
        async with httpx2.AsyncClient(headers=header_value(data_dir)) as http:
            async with Client(streamable_http_client(endpoint, http_client=http), read_timeout_seconds=120) as client:
                if args.action == 'import':
                    return await import_records(dataset, manifest_path, client, endpoint)
                report = await verify_records(dataset, manifest_path, client, endpoint)
                report_path = Path(args.report) if args.report else manifest_path.with_name(manifest_path.stem + '-verification.json')
                atomic_json(report_path, report)
                return {'passed': report['passed'], 'passed_checks': report['passed_checks'], 'total_checks': report['total_checks'],
                        'preservation': report['preservation'], 'index_states': report['index_states'],
                        'concept_states': report['concept_states'], 'report': str(report_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='합성 대화 시나리오 검증·MCP 저장·검색 확인')
    parser.add_argument('action', nargs='?', default='validate', choices=['validate', 'import', 'verify'])
    parser.add_argument('--dataset', type=Path, default=DATASET)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--url')
    args = parser.parse_args(argv)
    try:
        dataset = read_json(args.dataset)
        summary = validate_dataset(dataset)
        result = summary if args.action == 'validate' else asyncio.run(connected_action(args, dataset))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('passed') is False else 0
    except SeedError as error:
        print(str(error), file=sys.stderr)
    except Exception as error:
        # A transport exception may embed request headers. Do not echo it.
        print(f'작업을 완료하지 못했습니다: {type(error).__name__}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
