"""Bounded, ephemeral graph evidence from the server-owned read ledger."""
from __future__ import annotations

from .auth import AuthError
from .privacy import sanitize_text
from .records import DomainError
from .schemas import SourceRef


MAX_ITEMS = 20
MAX_CAPTURES = 10
MAX_LABEL_LENGTH = 60


def source_key(source):
    """Compare every coordinate; omitted optional fields mean explicit null."""
    ref = SourceRef.model_validate(source)
    return (ref.capture_id, ref.revision_id, ref.node_id, ref.body_start, ref.body_end)


def retrieval_sources(context):
    """Copy references only, never model-supplied labels or canonical bodies."""
    return [SourceRef.model_validate(item['source']).model_dump(mode='json') for item in context]


def _label(text, fallback):
    # Redact the complete value before clipping; a cut email/card/IP may evade
    # detection. Python slicing counts Unicode code points, not UTF-8 bytes.
    return ' '.join(sanitize_text(text or '').split())[:MAX_LABEL_LENGTH] or fallback


def refresh_retrieval(records, result):
    """Recheck graph evidence at each existing answer/SSE validation boundary.

    A changed unused span only disappears from the graph. A cited span still
    invalidates the answer. Keep the original version snapshots untouched.
    Legacy service doubles without this private ledger retain their contract.
    """
    if '_retrieval_sources' not in result:
        return
    cited = {source_key(source) for source in result['sources']}
    versions = result.get('_versions', {})
    truncated = result.get('retrieval', {}).get('truncated', False)
    seen, captures, items = set(), set(), []
    for source in result['_retrieval_sources']:
        key = source_key(source)
        if key in seen:
            continue
        seen.add(key)
        is_cited = key in cited
        try:
            detail = records.source_get(source)
        except DomainError:
            detail = None
        capture = detail['capture'] if detail else None
        expected = versions.get(source['capture_id'])
        valid = (detail is not None and detail.get('is_current')
                 and detail.get('review_state') == 'valid' and expected is not None
                 and expected == [capture['revision_id'], capture['state_version'],
                                  capture['index_state']['index_generation']])
        if not valid:
            if is_cited:
                raise AuthError('ANSWER_INVALIDATED', '답변의 근거가 변경되었습니다. 다시 검색해 주세요.')
            truncated = True
            continue
        capture_id = source['capture_id']
        if len(items) >= MAX_ITEMS or (capture_id not in captures and len(captures) >= MAX_CAPTURES):
            truncated = True
            continue
        captures.add(capture_id)
        items.append({'source': source, 'label': _label(detail['text'], '읽은 구간'),
                      'capture_label': _label(capture.get('title'), '기록'), 'cited': is_cited})
    result['retrieval'] = {'items': items, 'truncated': truncated}
