"""Request-local, read-only tools and the server-owned evidence ledger."""
from __future__ import annotations

import asyncio
import json

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from .auth import AuthError
from .privacy import sanitize_text
from .records import DomainError


class SearchArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=10000)
    unit_ids: list[str] = Field(default_factory=list, max_length=200)


class EvidenceArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_id: int = Field(ge=0, strict=True)


class EvidenceLedger:
    def __init__(self, service, state, instructions):
        self.service, self.state, self.instructions = service, state, instructions
        self.lock = asyncio.Lock()
        self.keys = {}
        self.relations = {}

    def _coverage(self):
        return [{k: unit[k] for k in ('unit_id', 'start', 'end', 'status')}
                for unit in self.state['query_coverage']]

    def _note(self, text):
        if text not in self.state['limitations']:
            self.state['limitations'].append(text)

    def _accept(self, item):
        source = item['source']
        key = json.dumps(source, sort_keys=True)
        if key in self.keys:
            return self.keys[key], False
        try:
            current = self.service.records.eligible_capture(source['capture_id'])
            detail = self.service.records.source_get(source)
        except DomainError:
            self._note('검색 중 변경되거나 조회할 수 없게 된 근거를 제외했습니다.')
            return None, False
        if current['revision_id'] != source['revision_id'] or not detail['is_current'] or detail['review_state'] != 'valid':
            self._note('검색 중 변경된 근거를 제외했습니다.')
            return None, False
        snapshot = [current['revision_id'], current['state_version'], current['index_state']['index_generation']]
        previous = self.state['versions'].get(source['capture_id'])
        if previous is not None and previous != snapshot:
            raise AuthError('ANSWER_INVALIDATED', '검색 중 근거가 변경되었습니다. 다시 검색해 주세요.')
        # Canonical text, not a tool/model-provided quotation, owns the SourceRef.
        item = {**item, 'text': detail['text']}
        context = self.state['context']
        if (len(context) >= 20 or sum(len(x['text']) for x in context) + len(item['text']) > 20000
                or len({x['source']['capture_id'] for x in context} | {source['capture_id']}) > 10):
            self._note('근거량 한도로 일부 구간을 읽지 못했습니다.')
            return None, False
        preview = json.dumps({'question': self.state['request']['question'],
            'evidence': [*context, item]}, ensure_ascii=False)
        budget = self.state['budget']
        # Reserve conversation/tool schema and the later answer-review input.
        if budget.measure(sanitize_text(preview), self.instructions) + 4096 + budget.output_reserve > budget.input_limit:
            self._note('선택 모델의 입력 예산 때문에 일부 근거 구간 전체를 제외했습니다.')
            return None, False
        index = len(context)
        context.append(item)
        self.keys[key] = index
        self.state['versions'][source['capture_id']] = snapshot
        return index, True

    def _result(self, evidence):
        usable = []
        for relation in self.relations.values():
            try:
                if self.service._relation_fits_context(relation, self.state['context']):
                    usable.append(relation)
            except DomainError:
                raise AuthError('ANSWER_INVALIDATED', '관계의 근거가 변경되었습니다. 다시 검색해 주세요.') from None
        self.state['relations'] = usable
        if len(usable) != len(self.relations):
            self._note('변경·상충 관계의 양쪽 또는 근거가 예산에서 빠져 현재 조건을 확정할 수 없습니다.')
        return {'evidence': evidence, 'relations': usable, 'question_coverage': self._coverage(),
                'limitations': list(self.state['limitations'])}

    def tools(self):
        @tool(args_schema=SearchArguments)
        async def search_knowledge(query: str, unit_ids: list[str] | None = None) -> dict:
            """Search stored knowledge. Use short queries (at most 64 embedding tokens).

            Search source_units' exact queries first; rephrase freely when useful.
            Returned evidence_id values may be cited. Repeated evidence IDs have
            already been read; read_evidence can retrieve their exact text again.
            UI filters are always applied by the server and cannot be overridden.
            """
            async with self.lock:
                self.service.check_request(self.state)
                if not query.strip() or self.service._query_count(query) > 64:
                    return {'error': 'QUERY_TOO_LONG', 'message': '64 임베딩 토큰 이내의 짧은 질의로 다시 검색하세요.'}
                filters = {key: value for key, value in self.state['request'].items()
                           if key in ('kinds', 'concept_ids', 'event_time') and value is not None}
                try:
                    result = await asyncio.to_thread(self.service.search.context, {'query': query, **filters, 'limit': 10})
                except DomainError as exc:
                    if exc.code not in ('QUERY_TOO_LONG', 'VALIDATION_ERROR'):
                        raise
                    return {'error': exc.code, 'message': '질의 형식을 확인하고 짧은 질의로 다시 검색하세요.'}
                self.service.check_request(self.state)
                # Model-supplied unit IDs never prove coverage. Exact, PII-redacted
                # text equality is required; paraphrases remain supplementary.
                for unit in self.state['query_coverage']:
                    if query.strip() == sanitize_text(unit['query']).strip():
                        unit['status'] = 'searched'
                for text in result.get('limitations', []):
                    self._note(str(text))
                evidence, repeated = [], []
                captures_before = {item['source']['capture_id'] for item in self.state['context']}
                pending_queries = {unit['query'] for unit in self.state['query_coverage'] if unit['status'] != 'searched'}
                # A broad first query must not consume all ten record slots and
                # make a later question facet impossible to investigate.
                new_capture_limit = max(1, (10 - len(captures_before)) // (len(pending_queries) + 1))
                added_captures = set()
                for item in result.get('items', []):
                    capture_id = item['source']['capture_id']
                    if (pending_queries and capture_id not in captures_before and capture_id not in added_captures
                            and len(added_captures) >= new_capture_limit):
                        self._note('질문의 다른 구간을 확인할 여유를 남기기 위해 이번 검색의 일부 근거를 제외했습니다.')
                        continue
                    index, added = self._accept(item)
                    if index is not None:
                        if added:
                            evidence.append({'evidence_id': index, **self.state['context'][index]})
                            if capture_id not in captures_before:
                                added_captures.add(capture_id)
                        else:
                            repeated.append(index)
                for relation in result.get('relations', []):
                    self.relations[relation['id']] = relation
                return {**self._result(evidence), 'previous_evidence_ids': repeated}

        @tool(args_schema=EvidenceArguments)
        async def read_evidence(evidence_id: int) -> dict:
            """Re-read an already discovered evidence span and check its current source.

            Only IDs returned by search_knowledge are accepted. Returns the exact
            stored span, its citation, and provenance metadata; this never writes.
            """
            async with self.lock:
                self.service.check_request(self.state)
                if evidence_id >= len(self.state['context']):
                    return {'error': 'EVIDENCE_NOT_FOUND', 'message': '먼저 검색에서 받은 근거 ID를 사용하세요.'}
                item = self.state['context'][evidence_id]
                detail = await asyncio.to_thread(self.service.records.source_get, item['source'])
                self.service.check_request(self.state)
                capture = detail['capture']
                actual = [capture['revision_id'], capture['state_version'], capture['index_state']['index_generation']]
                if (not detail['is_current'] or detail['review_state'] != 'valid'
                        or actual != self.state['versions'][item['source']['capture_id']]):
                    raise AuthError('ANSWER_INVALIDATED', '답변의 근거가 변경되었습니다. 다시 검색해 주세요.')
                return self._result([{'evidence_id': evidence_id, **item}])

        return [search_knowledge, read_evidence]
