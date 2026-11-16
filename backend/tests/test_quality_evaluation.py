"""The offline evaluation uses current read tools without a model or embedding download."""
import asyncio
import importlib.util
from pathlib import Path
from uuid import uuid4

from cache_me.db import Database
from cache_me.records import RecordService


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_quality.py'
spec = importlib.util.spec_from_file_location('evaluate_quality_script', SCRIPT)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_offline_baseline_uses_eight_actual_read_tools_and_canonical_evidence(tmp_path):
    db = Database(tmp_path / 'quality-script.sqlite3')
    records = RecordService(db)
    body = '실제로 저장된 평가용 근거'
    capture = records.create({'request_id': str(uuid4()), 'body_markdown': body})['capture']
    source = {'capture_id': capture['id'], 'revision_id': capture['revision_id'],
              'body_start': 0, 'body_end': len(body)}
    class Embedding:
        def count_tokens(self, text, kind='query'):
            return len(text) + 4
    class Search:
        embedding = Embedding()
        def __init__(self):
            self.queries = []
        def context(self, request):
            self.queries.append(request['query'])
            return {'items': [{'source': source, 'text': '신뢰할 수 없는 검색 사본'}], 'relations': [], 'limitations': []}
    search = Search()
    question = ' '.join(f'{i}번째 조건에서는 해당 프로젝트만 확인하고 다른 대상은 제외해 주세요.' for i in range(12))
    try:
        result = asyncio.run(evaluation.evaluate_retrieval_context(question, search, records))
        assert len(search.queries) == result['tool_calls'] == 8
        assert result['context'] == [{'source': source, 'text': body}]
        coverage = result['query_coverage']
        assert len(coverage) > 8
        assert coverage[0]['status'] == coverage[-1]['status'] == 'searched'
        assert {unit['status'] for unit in coverage} == {'searched', 'omitted'}
        assert ''.join(question[unit['start']:unit['end']] for unit in coverage) == question
        assert search.queries == result['queries']
        assert result['model_budget']['model'] is None
        assert result['model_budget']['limit_source'] == 'conservative_client_cap'
        assert len(records.list()['items']) == 1
    finally:
        db.close()
