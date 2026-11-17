"""LanceDB retrieval with SQLite authority, durable jobs and bounded context."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Annotated
from uuid import UUID

from filelock import FileLock
from pydantic import Field, StrictInt, ValidationError, field_validator, model_validator
from sqlalchemy import func, or_, select

from .chunking import MarkdownChunker
from .db import new_id, utcnow
from .embedding import KureEmbedding, EmbeddingError, MODEL_ID, MODEL_REVISION, QUERY_TOKENS
from .models import (Capture, CaptureIndexState, CaptureRevision, Concept, ConceptAlias, ConceptEnrichmentJob, EmbeddingProfile,
                     IndexBuild, IndexJob, KnowledgeNode, LocalBrain, MutationReceipt, NodeConcept, Relation,
                     RevisionConcept, RevisionKind)
from .records import DomainError, SourceValidationBudget, SourceValidationLimit, digest
from .record_filters import matches_record_filters, record_filter_predicates
from .schemas import InputModel, RecordKinds
from .record_kinds import normalize_record_kinds
from .topic_retrieval import matched_topic_ids, RECORDS_PER_TOPIC


class EventFilter(InputModel):
    """Inclusive ISO day boundaries; imprecise or unknown dates are excluded."""
    start: str | None = None
    end: str | None = None

    @field_validator("start", "end")
    @classmethod
    def iso_day(cls, value):
        if value is not None:
            from datetime import date
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError("event date boundary must be YYYY-MM-DD")
            date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def ordered(self):
        if not self.start and not self.end:
            raise ValueError("an event date boundary is required")
        if self.start and self.end and self.start > self.end:
            raise ValueError("event date boundaries are reversed")
        return self


class SearchInput(InputModel):
    query: Annotated[str, Field(min_length=1, max_length=10_000)]
    kinds: RecordKinds = Field(default_factory=list)
    concept_ids: list[UUID] = Field(default_factory=list)
    event_time: EventFilter | None = None
    limit: Annotated[StrictInt, Field(ge=1, le=100)] = 20
    cursor: str | None = None

    @field_validator("query")
    @classmethod
    def query_limits(cls, value):
        if not value.strip() or len(value.encode("utf-8")) > 65_536:
            raise ValueError("invalid query length")
        return value


class ContextInput(SearchInput):
    limit: Annotated[StrictInt, Field(ge=1, le=10)] = 10
    subject_hint: Annotated[str, Field(max_length=500)] | None = None
    situation_hint: Annotated[str, Field(max_length=500)] | None = None
    as_of: str | None = None


class GraphInput(InputModel):
    kinds: Annotated[RecordKinds, Field(max_length=6)] = Field(default_factory=list)
    concept_ids: Annotated[list[UUID], Field(max_length=100)] = Field(default_factory=list)


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ref(capture, revision=None, start=None, end=None, node=None):
    return {"capture_id": capture.id, "revision_id": revision or capture.current_revision_id,
            "node_id": node, "body_start": start, "body_end": end}


class SearchService:
    def __init__(self, records, index_path: str | Path, model_path: str | Path | None = None, *, embedding=None):
        self.records, self.db = records, records.db
        self.brain_id = self.db.brain_id
        self.index_path = Path(index_path)
        self.embedding = embedding if embedding is not None else KureEmbedding(model_path)
        self._lock = RLock()
        self._table = None
        self._connection = None
        self._model_state = "not_prepared"
        self._error_code = None
        self.build_id = self.profile_id = None

    def _embedding_error(self, error):
        return DomainError(error.code, error.message, details=error.details)

    @staticmethod
    def _input(schema, value):
        try:
            if type(value) is schema:
                return value
            return schema.model_validate(value.model_dump(mode="json") if hasattr(value, "model_dump") else value)
        except ValidationError as exc:
            # Pydantic's default error details can contain the original query.
            fields = [{"field": ".".join(map(str, e["loc"])), "type": e["type"]}
                      for e in exc.errors(include_input=False, include_context=False, include_url=False)]
            raise DomainError("VALIDATION_ERROR", "검색 조건을 확인해 주세요.", details={"fields": fields}) from exc

    def status(self) -> dict:
        with self.db.read() as session:
            brain = session.get(LocalBrain, self.brain_id)
            build = session.get(IndexBuild, brain.active_index_build_id)
            counts = dict(session.execute(select(CaptureIndexState.status, func.count())
                .join(Capture, Capture.id == CaptureIndexState.capture_id)
                .where(Capture.brain_id == self.brain_id, CaptureIndexState.build_id == build.id)
                .group_by(CaptureIndexState.status)).all())
            return {"status": self._model_state, "ready": self._model_state == "ready" and self.embedding.ready and self._table is not None,
                    "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                    "profile_id": build.profile_id, "build_id": build.id,
                    "index_counts": {key: counts.get(key, 0) for key in ("pending", "ready", "failed", "excluded")},
                    "error_code": self._error_code}

    def prepare(self) -> dict:
        """Explicit setup action, safe to call in a worker thread; never at import/startup."""
        with self._lock:
            self._model_state, self._error_code = "preparing", None
            try:
                self.embedding.prepare()
                config = self.embedding.configuration()
                import lancedb
                import pyarrow as pa
                self.index_path.mkdir(parents=True, exist_ok=True)
                with FileLock(str(self.index_path / ".writer.lock")):
                    self._connection = lancedb.connect(str(self.index_path))
                    with self.db.read() as session:
                        brain = session.get(LocalBrain, self.brain_id)
                        build = session.get(IndexBuild, brain.active_index_build_id)
                        profile = session.get(EmbeddingProfile, build.profile_id)
                        build_id, profile_id, table_name = build.id, profile.id, build.table_name
                        if profile.model_revision not in ("unconfigured", MODEL_REVISION):
                            raise DomainError("EMBEDDING_PROFILE_MISMATCH", "현재 색인과 모델이 다릅니다. 별도 재색인이 필요합니다.")
                        if profile.model_revision != "unconfigured" and profile.configuration != config:
                            raise DomainError("EMBEDDING_PROFILE_MISMATCH", "색인 프로필이 실행 환경과 다릅니다. 별도 재색인이 필요합니다.")
                    schema = pa.schema([
                        ("id", pa.string()), ("brain_id", pa.string()), ("capture_id", pa.string()),
                        ("revision_id", pa.string()), ("profile_id", pa.string()), ("index_generation", pa.int64()),
                        ("body_start", pa.int64()), ("body_end", pa.int64()), ("text", pa.string()),
                        ("context_prefix", pa.string()), ("context_truncated", pa.bool_()),
                        ("section_refs", pa.string()), ("split_reason", pa.string()),
                        ("vector", pa.list_(pa.list_(pa.float32(), 128)))])
                    existed = table_name in self._connection.list_tables()
                    self._table = self._connection.create_table(table_name, schema=schema, exist_ok=True)
                    if not self._table.schema.equals(schema):
                        raise DomainError("EMBEDDING_PROFILE_MISMATCH", "색인 테이블의 구조가 현재 프로필과 다릅니다.")
                    if self._table.count_rows():
                        self._fts()
                    with self.db.write() as session:
                        profile = session.get(EmbeddingProfile, profile_id)
                        profile.model_revision, profile.configuration = MODEL_REVISION, config
                        build = session.get(IndexBuild, build_id)
                        build.status, build.activated_at = "active", build.activated_at or utcnow()
                        if not existed:
                            # Backups deliberately omit derived Lance data. Losing that
                            # directory must enqueue a rebuild, never leave false readiness.
                            for capture in session.scalars(select(Capture).where(
                                    Capture.brain_id == self.brain_id, Capture.deleted_at.is_(None))):
                                state = session.get(CaptureIndexState, (capture.id, build_id))
                                if state is None:
                                    state = CaptureIndexState(capture_id=capture.id, build_id=build_id,
                                        revision_id=capture.current_revision_id, index_generation=capture.index_generation,
                                        status="pending", updated_at=utcnow())
                                    session.add(state)
                                else:
                                    state.revision_id, state.index_generation = capture.current_revision_id, capture.index_generation
                                    state.status, state.error_code, state.updated_at = "pending", None, utcnow()
                                job = session.scalar(select(IndexJob).where(IndexJob.capture_id == capture.id,
                                    IndexJob.revision_id == capture.current_revision_id, IndexJob.build_id == build_id,
                                    IndexJob.index_generation == capture.index_generation, IndexJob.operation == "upsert"))
                                if job is None:
                                    job = IndexJob(id=new_id(), capture_id=capture.id, revision_id=capture.current_revision_id,
                                        profile_id=profile_id, build_id=build_id, index_generation=capture.index_generation,
                                        operation="upsert", status="pending", attempt_count=0, available_at=utcnow())
                                    session.add(job)
                                else:
                                    job.status, job.available_at, job.last_error_code = "pending", utcnow(), None
                                    job.lease_token, job.lease_until = None, None
                    self.build_id, self.profile_id = build_id, profile_id
                self._model_state = "ready"
            except EmbeddingError as exc:
                self._model_state, self._error_code = "failed", exc.code
                raise self._embedding_error(exc) from exc
            except DomainError as exc:
                self._table = None
                self._model_state, self._error_code = "failed", exc.code
                raise
            except Exception as exc:
                self._table = None
                self._model_state, self._error_code = "failed", "INDEX_PREPARATION_FAILED"
                raise DomainError(self._error_code, "검색 저장소를 준비하지 못했습니다.", retryable=True) from exc
        return self.status()

    def _require(self):
        if not self.embedding.ready or self._table is None or self._model_state != "ready":
            raise DomainError("INDEX_NOT_READY", "설정에서 검색 기능을 먼저 준비해 주세요.", retryable=True)

    def _fts(self):
        from lancedb.index import FTS
        self._table.create_index("text", replace=True,
            config=FTS(base_tokenizer="icu", stem=False, remove_stop_words=False, ascii_folding=False))

    def _claim(self):
        now = utcnow()
        with self.db.write() as session:
            job = session.scalar(select(IndexJob).join(Capture, Capture.id == IndexJob.capture_id).where(
                Capture.brain_id == self.brain_id, IndexJob.build_id == self.build_id,
                or_((IndexJob.status == "pending") & (IndexJob.available_at <= now),
                    (IndexJob.status == "running") & (IndexJob.lease_until < now)))
                .order_by(IndexJob.available_at, IndexJob.id).limit(1))
            if job is None:
                return None
            job.status, job.lease_token = "running", new_id()
            job.lease_until = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            job.attempt_count += 1
            capture = session.get(Capture, job.capture_id)
            if capture.current_revision_id != job.revision_id or capture.index_generation != job.index_generation or (capture.deleted_at and job.operation != "remove"):
                job.status, job.lease_token, job.lease_until = "superseded", None, None
                return {"skip": True}
            revision = session.get(CaptureRevision, job.revision_id)
            return {"id": job.id, "token": job.lease_token, "capture_id": job.capture_id,
                    "revision_id": job.revision_id, "generation": job.index_generation,
                    "operation": job.operation, "body": revision.body_markdown, "title": revision.title}

    def _finish(self, data, error_code=None):
        with self.db.write() as session:
            job = session.get(IndexJob, data["id"])
            if job.lease_token != data["token"] or job.status != "running":
                return
            capture = session.get(Capture, job.capture_id)
            state = session.get(CaptureIndexState, (capture.id, job.build_id))
            current = (capture.current_revision_id == job.revision_id and capture.index_generation == job.index_generation
                       and state is not None and state.revision_id == job.revision_id and state.index_generation == job.index_generation)
            if not current or (capture.deleted_at and job.operation != "remove"):
                job.status = "superseded"
            elif error_code:
                job.status, job.last_error_code = "failed", error_code
                if not capture.deleted_at:
                    state.status, state.error_code, state.updated_at = "failed", error_code, utcnow()
            else:
                job.status, job.last_error_code = "done", None
                state.status = "excluded" if capture.deleted_at else "ready"
                state.error_code, state.updated_at = None, utcnow()
            job.lease_token, job.lease_until = None, None

    def process_jobs(self, limit: int = 20) -> dict:
        self._require()
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise DomainError("VALIDATION_ERROR", "작업 수는 1부터 100까지입니다.")
        result = {"processed": 0, "failed": 0, "superseded": 0}
        with self._lock, FileLock(str(self.index_path / ".writer.lock")):
            for _ in range(limit):
                job = self._claim()
                if job is None:
                    break
                if job.get("skip"):
                    result["superseded"] += 1
                    continue
                try:
                    if job["operation"] == "remove":
                        self._table.delete("capture_id = " + _quote(job["capture_id"]))
                    else:
                        chunks = MarkdownChunker(self.embedding).split(job["body"], job["title"])
                        # Encode bounded batches; no write transaction spans inference.
                        for offset in range(0, len(chunks), 4):
                            batch = chunks[offset:offset + 4]
                            vectors = self.embedding.encode_documents([c.embedding_text for c in batch])
                            rows = []
                            for chunk, vector in zip(batch, vectors, strict=True):
                                row_id = digest([job["capture_id"], job["revision_id"], chunk.body_start,
                                                 chunk.body_end, self.profile_id, job["generation"]])
                                rows.append({"id": row_id, "brain_id": self.brain_id,
                                    "capture_id": job["capture_id"], "revision_id": job["revision_id"],
                                    "profile_id": self.profile_id, "index_generation": job["generation"],
                                    "body_start": chunk.body_start, "body_end": chunk.body_end,
                                    "text": chunk.embedding_text, "context_prefix": chunk.context_prefix,
                                    "context_truncated": chunk.context_truncated,
                                    "section_refs": json.dumps(chunk.section_refs, ensure_ascii=False),
                                    "split_reason": chunk.split_reason, "vector": vector.tolist()})
                            self._table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(rows)
                        # Derived old generations can be discarded; immutable SQLite
                        # revisions stay intact. A late job never removes a newer one.
                        self._table.delete("capture_id = " + _quote(job["capture_id"]) +
                                           f" AND index_generation < {job['generation']}")
                        self._fts()
                    self._finish(job)
                    result["processed"] += 1
                except Exception as exc:
                    code = exc.code if isinstance(exc, EmbeddingError) else "INDEX_WRITE_FAILED"
                    self._finish(job, code)
                    result["failed"] += 1
        return result

    def retry(self, capture_id: str | None = None) -> dict:
        count = 0
        with self.db.write() as session:
            if capture_id:
                self.records._capture(session, capture_id)
            statement = select(IndexJob).join(Capture, Capture.id == IndexJob.capture_id).where(
                Capture.brain_id == self.brain_id, IndexJob.status == "failed")
            if capture_id:
                statement = statement.where(IndexJob.capture_id == str(capture_id))
            for job in session.scalars(statement):
                capture = session.get(Capture, job.capture_id)
                if capture.current_revision_id != job.revision_id or capture.index_generation != job.index_generation:
                    job.status = "superseded"
                    continue
                job.status, job.last_error_code, job.available_at = "pending", None, utcnow()
                state = session.get(CaptureIndexState, (capture.id, job.build_id))
                if state and not capture.deleted_at:
                    state.status, state.error_code, state.updated_at = "pending", None, utcnow()
                count += 1
        return {"retried": count}

    def _matches(self, session, capture, revision, data):
        if not matches_record_filters(session, revision, kinds=data.kinds, concept_ids=data.concept_ids):
            return False
        if data.event_time:
            event = revision.event_time or {}
            if event.get("precision") not in ("day", "instant") or not event.get("value"):
                return False
            day = event["value"][:10]
            if data.event_time.start and day < data.event_time.start:
                return False
            if data.event_time.end and day > data.event_time.end:
                return False
        return True

    def _eligible(self, session, capture, state=None):
        if capture is None or capture.brain_id != self.brain_id or capture.deleted_at:
            return False
        state = state or session.get(CaptureIndexState, (capture.id, self.build_id))
        if state is None or state.status != "ready" or state.revision_id != capture.current_revision_id or state.index_generation != capture.index_generation:
            return False
        return self.records._source_status(session, _ref(capture))["review_state"] == "valid"

    def _body_candidates(self, data: SearchInput, query, *, excluded_capture_ids=frozenset()) -> list[dict]:
        with self.db.read() as session:
            captures = list(session.scalars(select(Capture).where(Capture.brain_id == self.brain_id, Capture.deleted_at.is_(None))))
            allowed = []
            for capture in captures:
                if capture.id in excluded_capture_ids:
                    continue
                revision = session.get(CaptureRevision, capture.current_revision_id)
                if self._eligible(session, capture) and self._matches(session, capture, revision, data):
                    allowed.append((capture.id, capture.current_revision_id, capture.index_generation))
        if not allowed:
            return []
        filters = "brain_id = " + _quote(self.brain_id) + " AND profile_id = " + _quote(self.profile_id) + " AND (" + " OR ".join(
            "(capture_id = " + _quote(cid) + " AND revision_id = " + _quote(rid) + f" AND index_generation = {generation})"
            for cid, rid, generation in allowed) + ")"
        columns = ["id", "capture_id", "revision_id", "index_generation", "body_start", "body_end"]
        # Fetch up to the fixed candidate budget from each channel, then combine ranks.
        # No ANN or fast_search skipping of new rows is used in this initial implementation.
        try:
            # Lance snapshots support readers during writes. Do not hold the writer
            # lock while reading: a large pending corpus must not monopolize queries.
            table = self._table
            vector_rows = table.search(query, query_type="vector", vector_column_name="vector").metric("cosine").bypass_vector_index().where(filters, prefilter=True).select(columns + ["_distance"]).limit(40).to_list()
            fts_rows = table.search(data.query, query_type="fts", fts_columns="text").where(filters, prefilter=True).select(columns + ["_score"]).limit(40).to_list()
        except Exception as exc:
            raise DomainError("SEARCH_FAILED", "검색을 완료하지 못했습니다. 설정에서 검색 준비 상태를 확인해 주세요.", retryable=True) from exc
        scored = {}
        for rows in (vector_rows, fts_rows):
            for rank, row in enumerate(rows, 1):
                item = scored.setdefault(row["id"], {"row": row, "score": 0.0})
                item["score"] += 1.0 / (60 + rank)
        return sorted(scored.values(), key=lambda x: (-x["score"], x["row"]["id"]))

    def backfill_candidates(self, concept: dict, *, limit: int = 20) -> dict:
        """Bounded body-only retrieval; existing topic links never supply evidence.

        `complete` refers to index availability, not exhaustive semantic coverage.
        The current vector implementation still scans eligible indexed vectors.
        """
        self._require()
        excluded, complete = set(), True
        with self.db.read() as session:
            manual = set(session.scalars(select(MutationReceipt.capture_id).where(
                MutationReceipt.operation == "capture_set_concepts")))
            active = set(session.scalars(select(ConceptEnrichmentJob.capture_id).where(
                ConceptEnrichmentJob.status.in_(("pending", "running")))))
            for capture in session.scalars(select(Capture).where(
                    Capture.brain_id == self.brain_id, Capture.deleted_at.is_(None))):
                if capture.id in manual or concept["id"] in self.records._concept_ids(session, capture.current_revision_id):
                    excluded.add(capture.id)
                    continue
                if self.records._source_status(session, _ref(capture))["review_state"] != "valid":
                    excluded.add(capture.id)
                    continue
                revision = session.get(CaptureRevision, capture.current_revision_id)
                classification = self.records._concept_state(session, capture, revision)["status"]
                if classification != "ready":
                    if classification in ("pending", "running"):
                        complete = False
                    excluded.add(capture.id)
                    continue
                if capture.id in active or not self._eligible(session, capture):
                    complete = False
                    excluded.add(capture.id)

        # Each topic field gets a query window so a long description cannot hide
        # its name/aliases. Verify the real prompted budget before encoding.
        queries = []
        for text in (concept["name"], concept.get("description") or "", " ".join(concept.get("aliases", []))):
            text = text.strip()
            low, high = 0, len(text)
            while low < high:
                middle = (low + high + 1) // 2
                if self.embedding.count_tokens(text[:middle], "query") <= QUERY_TOKENS:
                    low = middle
                else:
                    high = middle - 1
            text = text[:low].strip()
            while text and self.embedding.count_tokens(text, "query") > QUERY_TOKENS:
                text = text[:-1]
            if text and text not in queries:
                queries.append(text)
        if not queries:
            raise DomainError("QUERY_TOO_LONG", "주제 검색 질의를 만들 수 없습니다.")
        combined = {}
        for text in queries:
            data = SearchInput(query=text)
            try:
                query = self.embedding.encode_query(text)
            except EmbeddingError as exc:
                raise self._embedding_error(exc) from exc
            ranked = self._body_candidates(data, query, excluded_capture_ids=excluded)
            with self.db.read() as session:
                hits = self._record_hits(session, ranked, data)
            for rank, hit in enumerate(hits, 1):
                key = hit["source"]["capture_id"]
                item = combined.setdefault(key, {**hit, "score": 0.0})
                item["score"] += 1.0 / (60 + rank)
        hits = sorted(combined.values(), key=lambda hit: (-hit["score"], hit["source"]["capture_id"]))
        return {"hits": hits[:max(0, min(limit, 20))], "complete": complete}

    def _topic_candidates(self, data: SearchInput, query) -> list[dict]:
        candidates = {}
        with self.db.read() as session:
            catalog = {}
            for concept_id, name, alias in session.execute(select(Concept.id, Concept.name, ConceptAlias.alias)
                    .outerjoin(ConceptAlias, ConceptAlias.concept_id == Concept.id)
                    .where(Concept.brain_id == self.brain_id)):
                concept = catalog.setdefault(concept_id, {"id": concept_id, "name": name, "aliases": []})
                if alias is not None:
                    concept["aliases"].append(alias)
            for concept_id in matched_topic_ids(data.query, list(catalog.values())):
                captures = session.scalars(select(Capture).join(CaptureRevision, Capture.current_revision_id == CaptureRevision.id)
                    .where(Capture.brain_id == self.brain_id, Capture.deleted_at.is_(None),
                           *record_filter_predicates(concept_ids=[concept_id]))
                    .order_by(Capture.updated_at.desc(), Capture.id))
                count = 0
                for capture in captures:
                    revision = session.get(CaptureRevision, capture.current_revision_id)
                    if not self._eligible(session, capture) or not self._matches(session, capture, revision, data):
                        continue
                    record_topic = session.scalar(select(RevisionConcept.concept_id).where(
                        RevisionConcept.revision_id == revision.id, RevisionConcept.concept_id == concept_id))
                    spans = None if record_topic else list(session.execute(select(KnowledgeNode.body_start, KnowledgeNode.body_end)
                        .join(NodeConcept, NodeConcept.node_id == KnowledgeNode.id)
                        .where(KnowledgeNode.revision_id == revision.id, NodeConcept.concept_id == concept_id)
                        .order_by(KnowledgeNode.ordinal)))
                    if data.concept_ids:
                        filter_ids = list(map(str, data.concept_ids))
                        record_filter = session.scalar(select(RevisionConcept.concept_id).where(
                            RevisionConcept.revision_id == revision.id, RevisionConcept.concept_id.in_(filter_ids)))
                        if not record_filter:
                            filter_spans = list(session.execute(select(KnowledgeNode.body_start, KnowledgeNode.body_end)
                                .join(NodeConcept, NodeConcept.node_id == KnowledgeNode.id)
                                .where(KnowledgeNode.revision_id == revision.id, NodeConcept.concept_id.in_(filter_ids))))
                            spans = filter_spans if spans is None else [
                                (max(start, left), min(end, right)) for start, end in spans
                                for left, right in filter_spans if start < right and end > left]
                    if spans == []:
                        continue
                    if spans is not None:
                        spans = sorted(set(spans))
                    previous = candidates.get(capture.id)
                    if previous is None:
                        candidates[capture.id] = {"capture_id": capture.id, "revision_id": revision.id,
                            "index_generation": capture.index_generation, "spans": spans}
                    elif previous["spans"] is not None:
                        previous["spans"] = None if spans is None else sorted(set(previous["spans"] + spans))
                    count += 1
                    if count >= RECORDS_PER_TOPIC:
                        break

        ranked = []
        table = self._table
        columns = ["id", "capture_id", "revision_id", "index_generation", "body_start", "body_end", "_distance"]
        for candidate in candidates.values():
            filters = ("brain_id = " + _quote(self.brain_id) + " AND profile_id = " + _quote(self.profile_id)
                + " AND capture_id = " + _quote(candidate["capture_id"])
                + " AND revision_id = " + _quote(candidate["revision_id"])
                + f" AND index_generation = {candidate['index_generation']}")
            if candidate["spans"] is not None:
                filters += " AND (" + " OR ".join(f"(body_start < {end} AND body_end > {start})"
                    for start, end in candidate["spans"]) + ")"
            try:
                rows = table.search(query, query_type="vector", vector_column_name="vector").metric("cosine") \
                    .bypass_vector_index().where(filters, prefilter=True).select(columns).limit(1).to_list()
            except Exception as exc:
                raise DomainError("SEARCH_FAILED", "검색을 완료하지 못했습니다. 설정에서 검색 준비 상태를 확인해 주세요.", retryable=True) from exc
            for row in rows:
                # A chunk crossing a Node boundary must not turn unrelated text
                # into evidence for that Node's topic.
                spans = [(row["body_start"], row["body_end"])] if candidate["spans"] is None else [
                    (max(row["body_start"], start), min(row["body_end"], end))
                    for start, end in candidate["spans"]
                    if row["body_start"] < end and row["body_end"] > start]
                for start, end in sorted(set(spans)):
                    ranked.append({"row": {**row, "body_start": start, "body_end": end},
                        "score": -row["_distance"], "bounded": candidate["spans"] is not None})
        return sorted(ranked, key=lambda item: (-item["score"], item["row"]["capture_id"], item["row"]["body_start"]))

    def _record_hits(self, session, ranked: list[dict], data: SearchInput) -> list[dict]:
        grouped = {}
        for scored_row in ranked:
            row = scored_row["row"]
            capture = session.get(Capture, row["capture_id"])
            if not self._eligible(session, capture) or capture.current_revision_id != row["revision_id"] or capture.index_generation != row["index_generation"]:
                continue
            revision = session.get(CaptureRevision, capture.current_revision_id)
            if not self._matches(session, capture, revision, data):
                continue
            start, end = row["body_start"], row["body_end"]
            if not 0 <= start < end <= len(revision.body_markdown):
                continue
            nodes = self.records._nodes(session, revision.id) if revision.node_status == "current" else []
            matched_nodes = [n.id for n in nodes if n.body_start < end and n.body_end > start]
            span = {"body_start": start, "body_end": end}
            if capture.id in grouped:
                hit = grouped[capture.id]
                if span not in hit["matched_spans"]:
                    hit["matched_spans"].append(span)
                if scored_row.get("bounded") and span not in hit["_bounded_spans"]:
                    hit["_bounded_spans"].append(span)
                hit["matched_node_ids"] = sorted(set(hit["matched_node_ids"] + matched_nodes))
                continue
            grouped[capture.id] = {"source": _ref(capture, start=start, end=end),
                "title": revision.title, "excerpt": revision.body_markdown[start:min(end, start + 480)],
                "matched_spans": [span], "matched_node_ids": matched_nodes,
                "_bounded_spans": [span] if scored_row.get("bounded") else [],
                "score": scored_row["score"], "score_kind": "rrf", "index_profile_id": self.profile_id,
                "index_generation": capture.index_generation}
        return list(grouped.values())

    def search(self, value: dict | SearchInput, *, _for_context: bool = False) -> dict:
        data = self._input(SearchInput, value)
        self._require()
        try:
            query = self.embedding.encode_query(data.query)
        except EmbeddingError as exc:
            raise self._embedding_error(exc) from exc
        # Topic discovery is independent of the body's top-40 candidate lists.
        # Both branches share the one query embedding and own their DB sessions.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache-me-search") as executor:
            body = executor.submit(self._body_candidates, data, query)
            topics = executor.submit(self._topic_candidates, data, query)
            body_candidates, topic_candidates = body.result(), topics.result()
        with self.db.read() as session:
            body_hits = self._record_hits(session, body_candidates, data)
            topic_hits = self._record_hits(session, topic_candidates, data)
        results = body_hits
        if topic_hits:
            combined = {}
            for channel in (body_hits, topic_hits):
                for rank, hit in enumerate(channel, 1):
                    key = (hit["source"]["capture_id"], hit["source"]["revision_id"])
                    if key not in combined:
                        combined[key] = {**hit, "score": 0.0, "matched_spans": [], "matched_node_ids": [], "_bounded_spans": []}
                    result = combined[key]
                    result["score"] += 1.0 / (60 + rank)
                    for span in hit["matched_spans"]:
                        if span not in result["matched_spans"]:
                            result["matched_spans"].append(span)
                            if span in hit["_bounded_spans"]:
                                result["_bounded_spans"].append(span)
                    result["matched_node_ids"] = sorted(set(result["matched_node_ids"] + hit["matched_node_ids"]))
            results = sorted(combined.values(), key=lambda hit: (-hit["score"], hit["source"]["capture_id"]))
        snapshot = digest([[h["source"], h["index_generation"], h["matched_spans"]] for h in results])
        return self.records._page(results, data.limit, data.cursor,
            data.model_dump(mode="json", exclude={"cursor", "limit"}), snapshot,
            lambda hit: hit if _for_context else {key: value for key, value in hit.items() if key != "_bounded_spans"})

    def context(self, value: dict | ContextInput) -> dict:
        data = self._input(ContextInput, value)
        search_data = data.model_dump(mode="json", exclude={"subject_hint", "situation_hint", "as_of"})
        hits = self.search(search_data, _for_context=True)
        items, limitations, conflicts, relation_views = [], [], [], []
        characters = 0
        captured_ids, relation_ids = set(), set()
        truncated = False
        with self.db.read() as session:
            def add_item(source, *, node_hint=None, related=None, expand=False):
                nonlocal characters, truncated
                status = self.records._source_status(session, source)
                if status["review_state"] != "valid" or not status["resolved_source"]:
                    limitations.append("확인 중 변경되거나 무효화된 출처를 제외했습니다.")
                    return None
                resolved, capture, revision, node, start, end = self.records._source_parts(session, status["resolved_source"])
                if expand:
                    # Read a complete surrounding paragraph to keep speaker/conditions.
                    before = revision.body_markdown.rfind("\n\n", 0, start)
                    after = revision.body_markdown.find("\n\n", end)
                    start = before + 2 if before >= 0 else 0
                    end = after if after >= 0 else len(revision.body_markdown)
                for existing in items:
                    ref = existing["source"]
                    if ref["capture_id"] == capture.id and ref["revision_id"] == revision.id and ref["body_start"] <= start and ref["body_end"] >= end:
                        for related_ref in related or []:
                            if related_ref not in existing["related_sources"]:
                                existing["related_sources"].append(related_ref)
                        return existing
                text = revision.body_markdown[start:end]
                if (len(items) >= 20 or characters + len(text) > 20_000 or
                        (capture.id not in captured_ids and len(captured_ids) >= data.limit)):
                    limitations.append("기록·근거 구간·본문의 공유 예산을 넘어 일부 구간을 생략했습니다.")
                    truncated = True
                    return None
                chosen_node = node_hint or node
                ref = _ref(capture, start=start, end=end)
                item = {"source": ref, "text": text, "record_kinds": self.records._kinds(session, revision.id),
                        "node_kind": chosen_node.kind if chosen_node else None,
                        "origin": chosen_node.origin if chosen_node else "unspecified",
                        "verification_state": chosen_node.verification_state if chosen_node else "unknown",
                        "context_notes": {"subject": None, "situation": None, "time": revision.event_time, "adoption": None},
                        "basis_sources": [ref], "applicability": "uncertain", "related_sources": list(related or [])}
                if source["revision_id"] != revision.id:
                    item["stored_source"] = source
                items.append(item)
                characters += len(text)
                captured_ids.add(capture.id)
                return item

            for hit in hits["items"]:
                capture = session.get(Capture, hit["source"]["capture_id"])
                if not self._eligible(session, capture) or capture.current_revision_id != hit["source"]["revision_id"]:
                    limitations.append("검색 후 변경된 기록을 근거에서 제외했습니다.")
                    continue
                revision = session.get(CaptureRevision, capture.current_revision_id)
                nodes = self.records._nodes(session, revision.id) if revision.node_status == "current" else []
                seed_items = []
                for span in hit["matched_spans"]:
                    bounded = span in hit.get("_bounded_spans", [])
                    overlapping = [n for n in nodes if n.body_start < span["body_end"] and n.body_end > span["body_start"]]
                    for node in overlapping or [None]:
                        # Topic-only evidence keeps the exact allowed range even
                        # when an unrelated, broader Node overlaps it. Body hits
                        # retain their existing full-Node context expansion.
                        start = min(span["body_start"], node.body_start) if node and not bounded else span["body_start"]
                        end = max(span["body_end"], node.body_end) if node and not bounded else span["body_end"]
                        item = add_item(_ref(capture, start=start, end=end), node_hint=node)
                        if item is not None and item not in seed_items:
                            seed_items.append(item)
                if not seed_items:
                    continue
                # Both incoming and outgoing relations are followed once. In particular,
                # a hit on an old condition discovers the incoming supersedes source.
                query = select(Relation).where(Relation.brain_id == self.brain_id, Relation.withdrawn_at.is_(None),
                    or_(Relation.source_capture_id == capture.id, Relation.target_capture_id == capture.id))
                for relation in session.scalars(query.order_by(Relation.created_at, Relation.id)):
                    if relation.id in relation_ids:
                        continue
                    if len(relation_ids) >= 20:
                        limitations.append("관계 조회 예산을 넘어 변경·상충 관계 일부를 확인하지 못했습니다.")
                        truncated = True
                        break
                    try:
                        view = self.records._relation_view(session, relation)
                    except DomainError:
                        continue
                    mine = "source" if view["source"]["capture_id"] == capture.id else "target"
                    own_status = self.records._source_status(session, view[mine])
                    _, _, _, _, own_start, own_end = self.records._source_parts(session, own_status["resolved_source"])
                    matched = [item for item in seed_items if item["source"]["body_start"] < own_end and item["source"]["body_end"] > own_start]
                    if not matched:
                        continue
                    relation_ids.add(relation.id)
                    # Preserve direction and scope/evidence notes for the caller's semantic check.
                    for key in ("source", "target", "evidence"):
                        view[key] = self.records._source_status(session, view[key])["resolved_source"]
                    relation_views.append(view)
                    other = view["target" if mine == "source" else "source"]
                    extra_refs = [other, view["evidence"]]
                    for item in matched:
                        for ref in extra_refs:
                            if ref not in item["related_sources"]:
                                item["related_sources"].append(ref)
                    extra_items = [add_item(ref, related=[view[mine]], expand=True) for ref in extra_refs]
                    if view["relation_type"] == "contradicts":
                        conflicts.append({"sources": [view["source"], view["target"], view["evidence"]],
                                          "reason": view["evidence_note"] or "명시적으로 기록된 상충 관계입니다."})
                    if view["relation_type"] == "supersedes":
                        if all(item is not None for item in extra_items):
                            limitations.append("대체 관계의 실제 양쪽 구간과 근거를 읽었으며, 주체·상황·시점 적용 여부는 추가 해석이 필요합니다.")
                        else:
                            limitations.append("대체 관계의 일부 본문을 확인하지 못했으므로 현재 적용 조건을 단정할 수 없습니다.")
                    next_relation = session.scalar(select(Relation.id).where(Relation.brain_id == self.brain_id,
                        Relation.withdrawn_at.is_(None), Relation.id.not_in(relation_ids),
                        Relation.relation_type.in_(["supersedes", "contradicts"]),
                        or_(Relation.source_capture_id == other["capture_id"], Relation.target_capture_id == other["capture_id"])).limit(1))
                    if next_relation:
                        limitations.append("추가 대체·상충 체인은 1홉 조회 범위 밖이므로 최종 조건으로 단정할 수 없습니다.")
                        truncated = True
            pending = session.scalar(select(func.count()).select_from(CaptureIndexState).join(Capture,
                Capture.id == CaptureIndexState.capture_id).where(Capture.brain_id == self.brain_id,
                Capture.deleted_at.is_(None), CaptureIndexState.build_id == self.build_id,
                CaptureIndexState.status.in_(["pending", "failed"])))
            if pending:
                limitations.append("아직 색인되지 않았거나 색인에 실패한 기록은 이번 검색에 포함되지 않았습니다.")
        if data.subject_hint or data.situation_hint or data.as_of:
            limitations.append("주체·상황·기준 시점 힌트는 사실로 확정하지 않았습니다. 근거에서 적용 범위를 확인해야 합니다.")
        if hits["next_cursor"]:
            limitations.append("기록 수 예산으로 검색 결과의 일부만 포함했습니다.")
            truncated = True
        return {"items": items, "conflicts": conflicts, "relations": relation_views,
                "evidence_status": "insufficient" if limitations else ("found" if items else "none"),
                "limitations": list(dict.fromkeys(limitations)), "truncated": truncated}

    def home_graph(self, value: dict | GraphInput | None = None) -> dict:
        """A bounded canonical overview, available before embedding preparation.

        Read at most 50 recent candidate records plus a sentinel. Filters select
        records; relation expansion never brings unrelated records through the
        filter. A fixed candidate window also bounds work when many derived
        records need source review. The regular record list/neighbors are the
        continuation path, rather than scanning until this graph is full.
        """
        data = self._input(GraphInput, {} if value is None else value)
        nodes, edges = {}, {}
        truncated = False

        def add_node(item):
            nonlocal truncated
            if item["id"] in nodes:
                return True
            if len(nodes) >= 50:
                truncated = True
                return False
            nodes[item["id"]] = item
            return True

        def add_edge(item):
            nonlocal truncated
            if item["source"] not in nodes or item["target"] not in nodes:
                truncated = True
            elif item["id"] in edges:
                return
            elif len(edges) >= 100:
                truncated = True
            else:
                edges[item["id"]] = item

        with self.db.read() as session:
            # A single SQLite read snapshot prevents mixing revisions across the
            # batched links/Nodes and their canonical provenance validation.
            session.connection().exec_driver_sql("BEGIN")
            validation = SourceValidationBudget()
            def source_status(source):
                nonlocal truncated
                try:
                    state = self.records._source_status(session, source, validation=validation)
                    resolved = state["resolved_source"]
                    if resolved and resolved["node_id"]:
                        revision = session.get(CaptureRevision, resolved["revision_id"])
                        if revision.node_status != "current":
                            return None
                    return state
                except SourceValidationLimit:
                    truncated = True
                    return None
            query = select(Capture, CaptureRevision).join(
                CaptureRevision, Capture.current_revision_id == CaptureRevision.id
            ).where(Capture.brain_id == self.brain_id, Capture.deleted_at.is_(None))
            query = query.where(*record_filter_predicates(kinds=data.kinds, concept_ids=data.concept_ids))
            candidates = session.execute(query.order_by(Capture.updated_at.desc(), Capture.id.desc()).limit(51)).all()
            truncated = len(candidates) > 50
            captures = {}
            revisions = {}
            for capture, revision in candidates[:50]:
                status = source_status(_ref(capture))
                if status and status["review_state"] == "valid":
                    captures[capture.id] = capture
                    revisions[revision.id] = revision
            if not captures:
                return {"nodes": [], "edges": [], "truncated": truncated}

            # Every expansion query has an independent ceiling. Batch loading
            # avoids a topic/Node query for each record and every graph edge.
            current_jobs = select(
                ConceptEnrichmentJob.capture_id, ConceptEnrichmentJob.status, ConceptEnrichmentJob.error_code,
                func.row_number().over(partition_by=ConceptEnrichmentJob.capture_id, order_by=(
                    ConceptEnrichmentJob.created_at.desc(), ConceptEnrichmentJob.expected_state_version.desc(),
                    ConceptEnrichmentJob.id.desc())).label("position"),
            ).where(ConceptEnrichmentJob.brain_id == self.brain_id,
                    ConceptEnrichmentJob.capture_id.in_(captures),
                    ConceptEnrichmentJob.status != "superseded",
                    or_(ConceptEnrichmentJob.requested_revision_id.in_(revisions),
                        ConceptEnrichmentJob.applied_revision_id.in_(revisions))).subquery()
            concept_states = {
                capture_id: {"status": self.records._concept_job_status(status),
                             "error_code": error_code}
                for capture_id, status, error_code in session.execute(select(
                    current_jobs.c.capture_id, current_jobs.c.status, current_jobs.c.error_code,
                ).where(current_jobs.c.position == 1).limit(50))
            }
            kinds = {revision_id: [] for revision_id in revisions}
            for revision_id, kind in session.execute(select(RevisionKind.revision_id, RevisionKind.kind).where(
                    RevisionKind.revision_id.in_(revisions)).order_by(RevisionKind.kind).limit(450)):
                kinds[revision_id].append(kind)
            kinds = {revision_id: sorted(normalize_record_kinds(values)) for revision_id, values in kinds.items()}
            topic_rows = session.execute(select(RevisionConcept.revision_id, Concept).join(
                Concept, Concept.id == RevisionConcept.concept_id).where(
                RevisionConcept.revision_id.in_(revisions), Concept.brain_id == self.brain_id
            ).order_by(RevisionConcept.revision_id, Concept.id).limit(101)).all()
            current_nodes = list(session.scalars(select(KnowledgeNode).where(
                KnowledgeNode.brain_id == self.brain_id,
                KnowledgeNode.revision_id.in_([id for id, revision in revisions.items() if revision.node_status == "current"])
            ).order_by(KnowledgeNode.revision_id, KnowledgeNode.ordinal, KnowledgeNode.id).limit(101)))
            truncated |= len(topic_rows) > 100 or len(current_nodes) > 100
            topics = {id: [] for id in revisions}
            parts = {id: [] for id in revisions}
            for revision_id, concept in topic_rows[:100]:
                topics[revision_id].append(concept)
            for node in current_nodes[:100]:
                parts[node.revision_id].append(node)

            def add_part(node, capture, revision):
                ref = _ref(capture, start=node.body_start, end=node.body_end, node=node.id)
                if add_node({"id": node.id, "kind": "node", "label": (node.label or revision.body_markdown[node.body_start:node.body_end])[:60], "source": ref}):
                    add_edge({"id": f"part:{capture.id}:{node.id}", "source": capture.id, "target": node.id,
                              "kind": "contains", "directed": True, "evidence": ref})
                    return True
                return False

            def add_topic(owner_id, concept, evidence):
                if add_node({"id": concept.id, "kind": "concept", "label": concept.name[:60]}):
                    add_edge({"id": f"topic:{owner_id}:{concept.id}", "source": owner_id, "target": concept.id,
                              "kind": "has_topic", "directed": True, "evidence": evidence})

            for capture in captures.values():
                revision = revisions[capture.current_revision_id]
                if not add_node({"id": capture.id, "kind": "capture", "label": (revision.title or revision.body_markdown)[:60],
                                 "kinds": kinds[revision.id], "source": _ref(capture),
                                 "concept_state": concept_states.get(capture.id, {"status": "ready", "error_code": None})}):
                    continue
                for concept in topics[revision.id]:
                    add_topic(capture.id, concept, _ref(capture))
                for node in parts[revision.id]:
                    add_part(node, capture, revision)

            shown_nodes = [id for id, node in nodes.items() if node["kind"] == "node"]
            node_topics = session.execute(select(NodeConcept.node_id, Concept).join(
                Concept, Concept.id == NodeConcept.concept_id).where(
                NodeConcept.node_id.in_(shown_nodes), Concept.brain_id == self.brain_id
            ).order_by(NodeConcept.node_id, Concept.id).limit(101)).all()
            truncated |= len(node_topics) > 100
            for node_id, concept in node_topics[:100]:
                add_topic(node_id, concept, nodes[node_id]["source"])

            relations = list(session.scalars(select(Relation).where(
                Relation.brain_id == self.brain_id, Relation.withdrawn_at.is_(None),
                Relation.source_capture_id.in_(captures), Relation.target_capture_id.in_(captures)
            ).order_by(Relation.created_at.desc(), Relation.id.desc()).limit(101)))
            truncated |= len(relations) > 100
            for relation in relations[:100]:
                resolved = {}
                for field in ("source", "target", "evidence"):
                    status = source_status(self.records._relation_ref(relation, field))
                    if not status or status["review_state"] != "valid":
                        break
                    resolved[field] = status["resolved_source"]
                if len(resolved) != 3:
                    continue
                endpoints = []
                for field in ("source", "target"):
                    ref = resolved[field]
                    capture = captures[ref["capture_id"]]
                    if capture.id not in nodes:
                        truncated = True
                        break
                    if ref["node_id"] and ref["node_id"] not in nodes:
                        node = session.get(KnowledgeNode, ref["node_id"])
                        if not add_part(node, capture, revisions[capture.current_revision_id]):
                            break
                    endpoints.append(ref["node_id"] or capture.id)
                if len(endpoints) == 2:
                    add_edge({"id": relation.id, "source": endpoints[0], "target": endpoints[1],
                              "kind": relation.relation_type, "directed": relation.relation_type != "related_to",
                              "evidence": resolved["evidence"]})
        return {"nodes": list(nodes.values()), "edges": list(edges.values()), "truncated": truncated}

    def neighbors(self, capture_id: str) -> dict:
        """One-hop record, explicit topics/Nodes/relations. No semantic edges invented."""
        nodes, edges = {}, []
        truncated = False
        with self.db.read() as session:
            session.connection().exec_driver_sql("BEGIN")
            validation = SourceValidationBudget()
            capture = self.records._capture(session, str(capture_id))
            revision = self.records._revision(session, capture)
            try:
                status = self.records._source_status(session, _ref(capture), validation=validation)
            except SourceValidationLimit:
                return {"nodes": [], "edges": [], "truncated": True}
            if status["review_state"] != "valid":
                raise DomainError("SOURCE_REVIEW_REQUIRED", "출처가 변경되어 재검토가 필요한 기록입니다.")
            def add_node(item):
                nonlocal truncated
                if item["id"] in nodes:
                    return True
                if len(nodes) >= 50:
                    truncated = True
                    return False
                nodes[item["id"]] = item
                return True
            def add_edge(item):
                nonlocal truncated
                if len(edges) >= 100:
                    truncated = True
                elif item["source"] in nodes and item["target"] in nodes:
                    edges.append(item)
            def record_node(cap):
                rev = session.get(CaptureRevision, cap.current_revision_id)
                return {"id": cap.id, "kind": "capture", "label": (rev.title or rev.body_markdown)[:60],
                        "source": _ref(cap), "kinds": self.records._kinds(session, rev.id)}
            add_node(record_node(capture))
            concepts = list(session.scalars(select(Concept).join(RevisionConcept, RevisionConcept.concept_id == Concept.id).where(
                RevisionConcept.revision_id == revision.id, Concept.brain_id == self.brain_id).order_by(Concept.id).limit(51)))
            truncated |= len(concepts) > 50
            for concept in concepts[:50]:
                if add_node({"id": concept.id, "kind": "concept", "label": concept.name[:60]}):
                    add_edge({"id": f"topic:{capture.id}:{concept.id}", "source": capture.id, "target": concept.id,
                              "kind": "has_topic", "directed": True, "evidence": _ref(capture)})
            if revision.node_status == "current":
                parts = list(session.scalars(select(KnowledgeNode).where(KnowledgeNode.revision_id == revision.id).order_by(KnowledgeNode.ordinal).limit(51)))
                truncated |= len(parts) > 50
                for node in parts[:50]:
                    ref = _ref(capture, start=node.body_start, end=node.body_end, node=node.id)
                    if add_node({"id": node.id, "kind": "node", "label": (node.label or revision.body_markdown[node.body_start:node.body_end])[:60], "source": ref}):
                        add_edge({"id": f"part:{capture.id}:{node.id}", "source": capture.id, "target": node.id,
                                  "kind": "contains", "directed": True, "evidence": ref})
                shown_parts = [id for id, item in nodes.items() if item["kind"] == "node"]
                node_topics = session.execute(select(NodeConcept.node_id, Concept).join(
                    Concept, Concept.id == NodeConcept.concept_id).where(
                    NodeConcept.node_id.in_(shown_parts), Concept.brain_id == self.brain_id,
                ).order_by(NodeConcept.node_id, Concept.id).limit(101)).all()
                truncated |= len(node_topics) > 100
                for node_id, concept in node_topics[:100]:
                    if add_node({"id": concept.id, "kind": "concept", "label": concept.name[:60]}):
                        add_edge({"id": f"topic:{node_id}:{concept.id}", "source": node_id, "target": concept.id,
                                  "kind": "has_topic", "directed": True, "evidence": nodes[node_id]["source"]})
            relations = list(session.scalars(select(Relation).where(Relation.brain_id == self.brain_id, Relation.withdrawn_at.is_(None),
                or_(Relation.source_capture_id == capture.id, Relation.target_capture_id == capture.id)).order_by(Relation.created_at, Relation.id).limit(101)))
            truncated |= len(relations) > 100
            for relation in relations[:100]:
                resolved_refs = {}
                for field in ("source", "target", "evidence"):
                    try:
                        status = self.records._source_status(session, self.records._relation_ref(relation, field), validation=validation)
                    except SourceValidationLimit:
                        truncated = True
                        break
                    if status["review_state"] != "valid":
                        break
                    resolved = status["resolved_source"]
                    if resolved["node_id"] and session.get(CaptureRevision, resolved["revision_id"]).node_status != "current":
                        break
                    resolved_refs[field] = resolved
                if len(resolved_refs) != 3:
                    continue
                endpoints = []
                for resolved in (resolved_refs["source"], resolved_refs["target"]):
                    ref, cap, rev, node, start, end = self.records._source_parts(session, resolved)
                    if node:
                        add_node({"id": node.id, "kind": "node", "label": (node.label or rev.body_markdown[start:end])[:60], "source": ref})
                        endpoints.append(node.id)
                    else:
                        add_node(record_node(cap))
                        endpoints.append(cap.id)
                add_edge({"id": relation.id, "source": endpoints[0], "target": endpoints[1],
                          "kind": relation.relation_type, "directed": relation.relation_type != "related_to",
                          "evidence": resolved_refs["evidence"]})
        return {"nodes": list(nodes.values()), "edges": edges, "truncated": truncated}
