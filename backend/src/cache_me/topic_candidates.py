"""Optional, derived topic candidates; SQLite and the classifier stay authoritative."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json

from filelock import FileLock

from .embedding import QUERY_TOKENS, TOKEN_DIMENSION


TABLE_NAME = "topic_candidates_v1"
WARM_BATCH = 8
DOCUMENT_TOKENS = 128
MAX_CANDIDATES = 30


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _fingerprint(concept: dict) -> str:
    value = [TABLE_NAME, DOCUMENT_TOKENS, concept["name"], concept.get("description"), concept.get("aliases", [])]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class TopicCandidateSearch:
    """Warm a bounded batch separately from lookup; never prepare/download a model.

    A cold or partially warmed table is only an incomplete candidate aid. Neither
    an empty result nor a low similarity score establishes that a topic is new.
    """

    def __init__(self, search):
        self.search = search

    def _ready(self):
        return (self.search.embedding.ready and self.search._model_state == "ready"
                and self.search.profile_id is not None and self.search._connection is not None)

    @contextmanager
    def _available(self):
        # Match SearchService's lock order and do not queue behind record indexing
        # or an interactive query. KURE methods reenter their model RLock.
        search_lock = self.search._lock
        if not search_lock.acquire(blocking=False):
            yield False
            return
        model_lock = getattr(self.search.embedding, "_lock", None)
        acquired = False
        try:
            acquired = model_lock is None or model_lock.acquire(blocking=False)
            yield acquired and self._ready()
        finally:
            if model_lock is not None and acquired:
                model_lock.release()
            search_lock.release()

    def _metadata(self, table):
        return {row["id"]: row for row in table.search()
                .where("brain_id = " + _quote(self.search.brain_id))
                .select(["id", "profile_id", "state_version", "content_hash"]).limit(None).to_list()}

    def _matches(self, row, concept):
        return (row is not None and row["profile_id"] == self.search.profile_id
                and row["state_version"] == concept["state_version"]
                and row["content_hash"] == _fingerprint(concept))

    def _fit(self, text, budget, *, kind="document", suffix=False):
        """Use source character boundaries and verify the actual prompted budget."""
        embedding = self.search.embedding
        text = text.strip()
        if embedding.count_tokens(text, kind) <= budget:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            piece = text[-middle:] if suffix else text[:middle]
            if embedding.count_tokens(piece, kind) <= budget:
                low = middle
            else:
                high = middle - 1
        fitted = (text[-low:] if suffix and low else text[:low]).strip()
        # Boundary whitespace can change tokenization; check the final string too.
        while fitted and embedding.count_tokens(fitted, kind) > budget:
            fitted = fitted[1:] if suffix else fitted[:-1]
        return fitted

    def _document(self, concept):
        parts = [concept["name"], concept.get("description") or "", "\n".join(concept.get("aliases", []))]
        parts = [part.strip() for part in parts if part.strip()]
        embedding = self.search.embedding
        combined = "\n".join(parts)
        if embedding.count_tokens(combined) <= DOCUMENT_TOKENS:
            return combined
        # Reserve space for each field instead of letting a long description
        # remove all aliases. This is a bounded representation, not source text.
        overhead = embedding.count_tokens("")
        remaining, fragments = DOCUMENT_TOKENS - overhead, []
        for index, part in enumerate(parts):
            quota = max(1, remaining // (len(parts) - index))
            fragment = self._fit(part, overhead + quota)
            fragments.append(fragment)
            remaining -= max(0, embedding.count_tokens(fragment) - overhead) + 1
        return self._fit("\n".join(fragments), DOCUMENT_TOKENS)

    def _queries(self, text):
        embedding = self.search.embedding
        text = text.strip()
        if not text:
            return []
        if embedding.count_tokens(text, "query") <= QUERY_TOKENS:
            return [text]
        offsets = [(start, end) for start, end in embedding.offsets(text) if end > start]
        if not offsets:
            return []
        width = min(QUERY_TOKENS, len(offsets))
        starts = (0, (len(offsets) - width) // 2, len(offsets) - width)
        queries = []
        for ordinal, start in enumerate(starts):
            window = text[offsets[start][0]:offsets[start + width - 1][1]]
            query = self._fit(window, QUERY_TOKENS, kind="query", suffix=ordinal == 2)
            if query and query not in queries:
                queries.append(query)
        # These windows sample the beginning, middle and end. The LLM still reads
        # every classification segment; vector lookup does not cover every token.
        return queries

    def refresh(self) -> None:
        """Warm at most eight current topics; failures never block classification."""
        try:
            if not self._ready():
                return
            with self._available() as available:
                if not available:
                    return
                catalog, cursor = {}, None
                while True:
                    page = self.search.records.concept_list(limit=100, cursor=cursor)
                    catalog.update({item["id"]: item for item in page["items"]})
                    cursor = page["next_cursor"]
                    if not cursor:
                        break
                if len(catalog) <= 100:
                    return
                import pyarrow as pa

                schema = pa.schema([
                    ("id", pa.string()), ("brain_id", pa.string()), ("profile_id", pa.string()),
                    ("state_version", pa.int64()), ("content_hash", pa.string()),
                    ("vector", pa.list_(pa.list_(pa.float32(), TOKEN_DIMENSION))),
                ])
                with FileLock(str(self.search.index_path / ".writer.lock"), timeout=0):
                    table = self.search._connection.create_table(TABLE_NAME, schema=schema, exist_ok=True)
                    if not table.schema.equals(schema):
                        return
                    stored = self._metadata(table)
                    pending = [catalog[id] for id in sorted(catalog)
                               if not self._matches(stored.get(id), catalog[id])][:WARM_BATCH]
                    if not pending:
                        return
                    vectors = self.search.embedding.encode_documents([self._document(concept) for concept in pending])
                    rows = [{"id": concept["id"], "brain_id": self.search.brain_id,
                             "profile_id": self.search.profile_id, "state_version": concept["state_version"],
                             "content_hash": _fingerprint(concept), "vector": vector.tolist()}
                            for concept, vector in zip(pending, vectors, strict=True)]
                    table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(rows)
        except Exception:
            # This table is disposable; keep canonical saving/classification and
            # the ordinary record index independent of optional candidate work.
            return

    def rank(self, catalog: dict[str, dict], text: str, limit: int = 30) -> list[str]:
        """Return only current catalog IDs; do not warm documents on this path."""
        try:
            limit = min(limit, MAX_CANDIDATES)
            if limit <= 0 or not catalog or not text.strip() or not self._ready():
                return []
            with self._available() as available:
                if not available:
                    return []
                table = self.search._connection.open_table(TABLE_NAME)
                stored = self._metadata(table)
                valid = sorted(id for id, concept in catalog.items() if self._matches(stored.get(id), concept))
                if not valid:
                    return []
                filters = ("brain_id = " + _quote(self.search.brain_id)
                           + " AND profile_id = " + _quote(self.search.profile_id)
                           + " AND id IN (" + ",".join(map(_quote, valid)) + ")")
                scores = {}
                for query_text in self._queries(text):
                    query = self.search.embedding.encode_query(query_text)
                    rows = (table.search(query, query_type="vector", vector_column_name="vector")
                            .metric("cosine").bypass_vector_index().where(filters, prefilter=True)
                            .select(["id", "_distance"]).limit(limit).to_list())
                    for rank, row in enumerate(sorted(rows, key=lambda row: (row["_distance"], row["id"])), 1):
                        scores[row["id"]] = scores.get(row["id"], 0.0) + 1.0 / (60 + rank)
                return sorted(scores, key=lambda id: (-scores[id], id))[:limit]
        except Exception:
            return []
