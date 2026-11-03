"""Synthetic retrieval baseline and optional live ReAct evaluation.

The offline baseline uses deterministic original-unit selection (at most eight),
not an autonomous model. It exercises the current read tools and evidence ledger.
No user data is indexed.

Run with the backend environment. --live-data-dir reads the existing selected model
and credentials, but all records/questions in this evaluation come from the fixture.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from second_brain.auth import ModelAuth
from second_brain.db import Database
from second_brain.embedding import MODEL_REVISION
from second_brain.questions import QuestionInput, QuestionService, split_question
from second_brain.question_agent import INSTRUCTIONS, TOOL_LIMIT
from second_brain.question_tools import EvidenceLedger
from second_brain.privacy import sanitize_text
from second_brain.records import RecordService
from second_brain.search import SearchService
from second_brain.token_budget import ModelBudget
from langsmith import tracing_context

FIXTURE = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'korean_quality.json'


def selected_units(question, search):
    units = split_question(question, lambda text: search.embedding.count_tokens(text, 'query'))
    unique = list(dict.fromkeys(unit['query'] for unit in units))
    selected = unique if len(unique) <= TOOL_LIMIT else unique[:TOOL_LIMIT - 1] + unique[-1:]
    return units, selected


async def evaluate_retrieval_context(question, search, records):
    """Run the real read tool without an LLM; never claim autonomous-agent quality."""
    units, queries = selected_units(question, search)
    service = QuestionService(search, records, None)
    budget = ModelBudget.from_metadata(None)
    state = {'request': {'question': question}, 'calls': 0, 'tool_calls': 0,
             'input_estimates': [], 'context': [], 'relations': [], 'versions': {},
             'limitations': [], 'active': True, 'auth_context': service._auth_context(),
             'budget': budget, 'query_coverage': units}
    ledger = EvidenceLedger(service, state, INSTRUCTIONS)
    search_tool = next(tool for tool in ledger.tools() if tool.name == 'search_knowledge')
    try:
        with tracing_context(enabled=False):
            for query in queries:
                state['tool_calls'] += 1
                await search_tool.ainvoke({'query': sanitize_text(query),
                    'unit_ids': [unit['unit_id'] for unit in units if unit['query'] == query]})
        for unit in units:
            if unit['status'] != 'searched':
                unit['status'] = 'omitted'
        return {'context': state['context'], 'query_coverage': units, 'queries': queries,
                'tool_calls': state['tool_calls'], 'limitations': state['limitations'],
                'model_budget': budget.describe()}
    finally:
        state['active'] = False


async def evaluate(args):
    raw = FIXTURE.read_bytes()
    fixture = json.loads(raw)
    report = {'fixture_version': fixture['version'], 'fixture_sha256': hashlib.sha256(raw).hexdigest(),
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'evaluated_at': datetime.now(timezone.utc).isoformat(),
              'data_kind': 'synthetic', 'platform': platform.platform(), 'python': platform.python_version(),
              'model_revision': MODEL_REVISION,
              'retrieval_evaluation_kind': 'deterministic_retrieval_baseline',
              'retrieval_query_policy': 'unique original units, first seven plus last when over eight',
              'retrieval_tool_limit': TOOL_LIMIT,
              'live_evaluation_kind': 'create_agent_with_selected_oauth_model',
              'retrieval': [], 'live': []}
    with tempfile.TemporaryDirectory(prefix='second-brain-quality-') as directory:
        db = Database(Path(directory) / 'canonical.sqlite3')
        records = RecordService(db)
        search = SearchService(records, Path(directory) / 'lance', model_path=args.model_path)
        ids, keys = {}, {}
        for row in fixture['records']:
            capture = records.create({'request_id': str(uuid4()), **{key: value for key, value in row.items() if key != 'key'}})['capture']
            ids[row['key']], keys[capture['id']] = capture['id'], row['key']
        started = time.perf_counter()
        await asyncio.to_thread(search.prepare)
        jobs = await asyncio.to_thread(search.process_jobs, 100)
        assert jobs['failed'] == 0, jobs
        report['setup_seconds'] = round(time.perf_counter() - started, 3)
        report['record_count'] = len(ids)
        report['runtime_profile'] = search.embedding.configuration()
        if not args.live_only:
            for case in fixture['queries']:
                if case.get('live_only'):
                    continue
                started = time.perf_counter()
                gathered = await evaluate_retrieval_context(case['question'], search, records)
                units, queries = gathered['query_coverage'], gathered['queries']
                scores = {}
                for query in queries:
                    result = search.search({'query': sanitize_text(query), 'limit': 10})
                    for rank, hit in enumerate(result['items'], 1):
                        key = keys[hit['source']['capture_id']]
                        scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
                ranked = sorted(scores, key=lambda key: (-scores[key], key))
                expected = set(case['expected'])
                context_ids = {keys[item['source']['capture_id']] for item in gathered['context']}
                report['retrieval'].append({'case_id': case['id'], 'category': case['category'],
                    'query_count': len(queries), 'source_units': len(units),
                    'all_original_units_searched': all(unit['status'] == 'searched' for unit in units),
                    'query_coverage': [{key: unit[key] for key in ('unit_id', 'start', 'end', 'status')} for unit in units],
                    'tool_calls': gathered['tool_calls'], 'limitations': gathered['limitations'],
                    'model_budget': gathered['model_budget'],
                    'query_tokens_max': max(search.embedding.count_tokens(sanitize_text(query), 'query') for query in queries),
                    'top5': ranked[:5], 'expected': sorted(expected),
                    'hit_at_1': bool(expected.intersection(ranked[:1])),
                    'recall_at_5': len(expected.intersection(ranked[:5])) / len(expected),
                    'context_recall': len(expected.intersection(context_ids)) / len(expected),
                    'seconds': round(time.perf_counter() - started, 3)})
            rows = report['retrieval']
            report['summary'] = {'cases': len(rows), 'hit_at_1': statistics.mean(row['hit_at_1'] for row in rows),
                'macro_recall_at_5': statistics.mean(row['recall_at_5'] for row in rows),
                'macro_context_recall': statistics.mean(row['context_recall'] for row in rows),
                'latency_median_seconds': statistics.median(row['seconds'] for row in rows),
                'all_queries_within_64_tokens': all(row['query_tokens_max'] <= 64 for row in rows),
                'unprocessed_question_cases': [row['case_id'] for row in rows if not row['all_original_units_searched']],
                'ranking': 'RRF over per-source-unit retrieval ranks; top5 distinct captures',
                'scope': 'deterministic retrieval baseline on a small frozen synthetic corpus; no autonomous agent or production quality claim'}
        if args.live_data_dir:
            auth = ModelAuth(Path(args.live_data_dir), args.origin)
            selected_before = (auth.active() or {}).get('model')
            if not selected_before:
                raise RuntimeError('A user-selected model is required; evaluation never selects one.')
            cases = args.live_cases.split(',') if args.live_cases else fixture['live_cases']
            assert 1 <= len(cases) <= 3, 'bounded live evaluation allows at most three cases'
            service = QuestionService(search, records, auth)
            for case in fixture['queries']:
                if case['id'] not in cases:
                    continue
                started = time.perf_counter()
                try:
                    result = await service.run(QuestionInput(request_id=uuid4(), question=case['question']))
                    source_keys = sorted({keys[source['capture_id']] for source in result['sources']})
                    report['live'].append({'case_id': case['id'], 'selected_model': selected_before,
                        'evidence_status': result['evidence_status'], 'source_keys': source_keys,
                        'expected_source_present': all(key in source_keys for key in case['expected']),
                        'answer': '\n'.join(part['text'] for part in result['parts']),
                        'limitations': result['limitations'], 'query_coverage': result['_query_coverage'],
                        'model_budget': result['_model_budget'], 'input_estimates': result['_input_estimates'],
                        'agent_usage': result['_agent_usage'],
                        'seconds': round(time.perf_counter() - started, 3)})
                except Exception as error:
                    # No stack trace, prompt, credential, or network body in the report.
                    report['live'].append({'case_id': case['id'], 'selected_model': selected_before,
                                           'error_code': getattr(error, 'code', type(error).__name__)})
                assert (auth.active() or {}).get('model') == selected_before, 'selected model changed during evaluation'
        db.close()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(output.resolve()), 'summary': report.get('summary'),
                      'live': [{key: row[key] for key in ('case_id', 'evidence_status', 'error_code', 'seconds') if key in row}
                               for row in report['live']]}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-path', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--live-data-dir')
    parser.add_argument('--origin', default='http://127.0.0.1:8000')
    parser.add_argument('--live-cases')
    parser.add_argument('--live-only', action='store_true')
    asyncio.run(evaluate(parser.parse_args()))
