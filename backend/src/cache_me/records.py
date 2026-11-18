"""Shared transactional record domain; HTTP and MCP use these same operations."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select

from .db import Database, new_id, utcnow
from .concept_labels import concept_label_key
from .record_filters import record_filter_predicates
from .record_kinds import normalize_record_kinds
from .model_errors import ACTION_REQUIRED_MODEL_ERRORS, CONCEPT_MODEL_ERRORS
from .models import (Capture, CaptureIndexState, CaptureRevision, Concept, ConceptAlias,
                     ConceptEnrichmentJob, DeletionConfirmation, IndexBuild, IndexJob,
                     KnowledgeNode, LocalBrain, MutationReceipt, NodeConcept,
                     ProvenanceLink, Relation, RevisionConcept, RevisionKind)
from .schemas import (CreateCaptureInput, CreateConceptInput, DeleteCaptureInput,
                      MergeCapturesInput, PrepareDeletionInput, RelationInput,
                      RetractRelationInput, ReviewSourcesInput, SetConceptsInput,
                      RetryConceptsInput, SourceRef, UpdateCaptureInput, UpdateConceptInput)


class DomainError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.retryable, self.details = code, message, retryable, details

    def as_dict(self):
        return {"code": self.code, "message": self.message, "retryable": self.retryable, "details": self.details}


def fail(code: str, message: str, **kwargs):
    raise DomainError(code, message, **kwargs)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def source_dict(value):
    return SourceRef.model_validate(value).model_dump(mode="json")


def created_boundary(value, name):
    if value is None:
        return None
    # Require a calendar date, a time and an explicit offset. fromisoformat on
    # its own also accepts naive, basic and week-date forms.
    pattern = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
               r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")
    try:
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise ValueError()
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        fail("VALIDATION_ERROR", f"{name}은 시간대가 포함된 ISO 날짜시각이어야 합니다.")


@dataclass(frozen=True)
class HumanConfirmation:
    """In-process capability, issued only by the trusted human interaction adapter."""
    token_hash: str
    principal_scope: str
    session_scope: str
    proof: str


class SourceValidationLimit(Exception):
    """A bounded read must omit unverified data when its work budget runs out."""


@dataclass
class SourceValidationBudget:
    remaining: int = 512
    max_depth: int = 32
    cache: dict = field(default_factory=dict)

    def spend(self, count=1):
        if count > self.remaining:
            self.remaining = 0
            raise SourceValidationLimit()
        self.remaining -= count


class RecordService:
    def __init__(self, db: Database, *, principal_scope: str = "local", session_scope: str = "local", created_via: str = "web"):
        self.db = db
        self.brain_id = db.brain_id
        self.principal_scope = f"{self.brain_id}:{principal_scope}"
        self.session_scope = session_scope
        self.created_via = created_via
        self._confirmation_secret = secrets.token_hex(32)

    def scoped(self, *, principal_scope: str, session_scope: str, created_via: str = "web"):
        service = RecordService(self.db, principal_scope=principal_scope, session_scope=session_scope, created_via=created_via)
        service._confirmation_secret = self._confirmation_secret
        return service

    def _capture(self, session, capture_id):
        capture = session.get(Capture, str(capture_id))
        if capture is None or capture.brain_id != self.brain_id or capture.deleted_at is not None:
            fail("NOT_FOUND", "기록을 찾을 수 없습니다.")
        return capture

    def _revision(self, session, capture, revision_id=None):
        revision = session.get(CaptureRevision, str(revision_id or capture.current_revision_id))
        if revision is None or revision.capture_id != capture.id or revision.brain_id != self.brain_id:
            fail("NOT_FOUND", "저장본을 찾을 수 없습니다.")
        return revision

    def _expected(self, capture, data):
        if capture.current_revision_id != str(data.expected_revision_id) or capture.state_version != data.expected_state_version:
            fail("VERSION_CONFLICT", "기록이 변경되었습니다. 다시 조회한 뒤 수정해 주세요.", details={"revision_id": capture.current_revision_id, "state_version": capture.state_version})

    def _nodes(self, session, revision_id):
        return list(session.scalars(select(KnowledgeNode).where(KnowledgeNode.revision_id == revision_id).order_by(KnowledgeNode.ordinal)))

    def _kinds(self, session, revision_id):
        return sorted(normalize_record_kinds(list(session.scalars(select(RevisionKind.kind).where(RevisionKind.revision_id == revision_id)))))

    def _concept_ids(self, session, revision_id):
        return list(session.scalars(select(RevisionConcept.concept_id).where(RevisionConcept.revision_id == revision_id).order_by(RevisionConcept.concept_id)))

    def _node_concept_ids(self, session, node_id):
        return list(session.scalars(select(NodeConcept.concept_id).where(NodeConcept.node_id == node_id).order_by(NodeConcept.concept_id)))

    def _sources(self, session, revision_id, *, validation=None):
        query = select(ProvenanceLink).where(ProvenanceLink.derived_revision_id == revision_id).order_by(ProvenanceLink.id)
        if validation is not None:
            query = query.limit(validation.remaining + 1)
        links = list(session.scalars(query))
        if validation is not None:
            validation.spend(len(links))
        return [{"capture_id": link.source_capture_id, "revision_id": link.source_revision_id, "node_id": link.source_node_id, "body_start": link.source_body_start, "body_end": link.source_body_end}
                for link in links]

    def _source_parts(self, session, source):
        source = source_dict(source)
        capture = self._capture(session, source["capture_id"])
        revision = self._revision(session, capture, source["revision_id"])
        node = None
        start, end = 0, len(revision.body_markdown)
        if source["node_id"]:
            node = session.get(KnowledgeNode, source["node_id"])
            if node is None or node.revision_id != revision.id or node.brain_id != self.brain_id:
                fail("INVALID_SOURCE_REF", "출처 Node의 소속이 올바르지 않습니다.")
            start, end = node.body_start, node.body_end
        if source["body_start"] is not None:
            if source["body_start"] < start or source["body_end"] > end:
                fail("INVALID_SOURCE_REF", "출처 범위가 저장본 또는 Node를 벗어납니다.")
            start, end = source["body_start"], source["body_end"]
        return source, capture, revision, node, start, end

    def _equivalent(self, session, old, current, *, validation=None):
        if old.id == current.id:
            return True
        # Explicit source review must not be accepted through metadata equivalence.
        lo, hi = sorted((old.revision_no, current.revision_no))
        review = session.scalar(select(CaptureRevision.id).where(CaptureRevision.capture_id == old.capture_id, CaptureRevision.revision_no > lo, CaptureRevision.revision_no <= hi, CaptureRevision.change_kind == "source_review").limit(1))
        if review:
            return False
        if any(getattr(old, field) != getattr(current, field) for field in ("title", "body_markdown", "completion_state", "event_time", "node_status")):
            return False
        fields = ("ordinal", "kind", "body_start", "body_end", "label", "origin", "verification_state", "verification_note")
        if [tuple(getattr(n, field) for field in fields) for n in self._nodes(session, old.id)] != [tuple(getattr(n, field) for field in fields) for n in self._nodes(session, current.id)]:
            return False
        return {canonical(s) for s in self._sources(session, old.id, validation=validation)} == {canonical(s) for s in self._sources(session, current.id, validation=validation)}

    def _source_status(self, session, source, visiting=None, *, validation=None, _memo=None):
        source = source_dict(source)
        # Reuse repeated upstream evidence during this read only. A new read gets
        # a new cache, so edits/deletions are never hidden by cross-request state.
        memo = validation.cache if validation is not None else ({} if _memo is None else _memo)
        key = canonical(source)
        if key in memo:
            return memo[key]
        if validation is not None:
            if len(visiting or ()) >= validation.max_depth:
                raise SourceValidationLimit()
            validation.spend()
        result = self._resolve_source_status(session, source, visiting, validation=validation, _memo=memo)
        memo[key] = result
        return result

    def _resolve_source_status(self, session, source, visiting=None, *, validation=None, _memo=None):
        visiting = set() if visiting is None else set(visiting)
        try:
            _, capture, revision, node, _, _ = self._source_parts(session, source)
        except DomainError as error:
            if error.code in ("NOT_FOUND", "INVALID_SOURCE_REF"):
                return {"source": source, "resolved_source": None, "availability": "unavailable", "review_state": "needs_review", "reason": "source_deleted"}
            raise
        if capture.id in visiting:
            return {"source": source, "resolved_source": None, "availability": "available", "review_state": "needs_review", "reason": "upstream_invalid"}
        current = self._revision(session, capture)
        if not self._equivalent(session, revision, current, validation=validation):
            return {"source": source, "resolved_source": None, "availability": "available", "review_state": "needs_review", "reason": "source_changed"}
        visiting.add(capture.id)
        for upstream in self._sources(session, current.id, validation=validation):
            if self._source_status(session, upstream, visiting, validation=validation, _memo=_memo)["review_state"] != "valid":
                return {"source": source, "resolved_source": None, "availability": "available", "review_state": "needs_review", "reason": "upstream_invalid"}
        resolved = dict(source, revision_id=current.id)
        if node and revision.id != current.id:
            equivalent_node = next((n for n in self._nodes(session, current.id) if n.ordinal == node.ordinal), None)
            if equivalent_node is None:
                fail("INVALID_SOURCE_REF", "대응하는 현재 Node가 없습니다.")
            resolved["node_id"] = equivalent_node.id
        return {"source": source, "resolved_source": resolved, "availability": "available", "review_state": "valid", "reason": None}

    def _validate_sources(self, session, sources, target_id=None):
        result, seen = [], set()
        memo = {}
        def check_cycle(capture_id, visited):
            if capture_id == target_id:
                fail("SOURCE_CYCLE", "자기 참조 또는 순환 출처를 만들 수 없습니다.")
            if capture_id in visited:
                return
            visited.add(capture_id)
            capture = self._capture(session, capture_id)
            for upstream in self._sources(session, capture.current_revision_id):
                check_cycle(upstream["capture_id"], visited)
        for value in sources:
            source = source_dict(value)
            try:
                self._source_parts(session, source)
            except DomainError:
                fail("INVALID_SOURCE_REF", "현재 조회할 수 없는 출처입니다.")
            if self._source_status(session, source, _memo=memo)["review_state"] != "valid":
                fail("INVALID_SOURCE_REF", "출처가 변경되었거나 재검토가 필요합니다.")
            check_cycle(source["capture_id"], set())
            key = canonical(source)
            if key not in seen:
                result.append(source)
                seen.add(key)
        return result

    def _concept(self, session, concept_id):
        concept = session.get(Concept, str(concept_id))
        if concept is None or concept.brain_id != self.brain_id:
            fail("NOT_FOUND", "주제를 찾을 수 없습니다.")
        return concept

    def _concept_view(self, session, concept):
        return {"id": concept.id, "name": concept.name, "description": concept.description,
                "aliases": list(session.scalars(select(ConceptAlias.alias).where(ConceptAlias.concept_id == concept.id).order_by(ConceptAlias.alias))),
                "state_version": concept.state_version, "created_at": concept.created_at, "updated_at": concept.updated_at}

    def _node_view(self, session, node, capture, revision, review_state):
        return {"id": node.id, "revision_id": revision.id, "ordinal": node.ordinal,
                **{field: getattr(node, field) for field in ("kind", "body_start", "body_end", "label", "origin", "verification_state", "verification_note", "concept_hints")},
                "text": revision.body_markdown[node.body_start:node.body_end],
                "concepts": [self._concept_view(session, self._concept(session, id)) for id in self._node_concept_ids(session, node.id)],
                "source": {"capture_id": capture.id, "revision_id": revision.id, "node_id": node.id, "body_start": node.body_start, "body_end": node.body_end}, "review_state": review_state}

    def _concept_state(self, session, capture, revision):
        job = session.scalar(select(ConceptEnrichmentJob).where(ConceptEnrichmentJob.capture_id == capture.id,
            ConceptEnrichmentJob.status != "superseded",
            or_(ConceptEnrichmentJob.requested_revision_id == revision.id, ConceptEnrichmentJob.applied_revision_id == revision.id))
            .order_by(ConceptEnrichmentJob.created_at.desc(), ConceptEnrichmentJob.expected_state_version.desc(), ConceptEnrichmentJob.id.desc()).limit(1))
        if not job:
            return {"status": "ready", "job_id": None, "requested_revision_id": None, "applied_revision_id": None, "unresolved_hints": [], "error_code": None}
        status = self._concept_job_status(job.status)
        # Deferred candidates remain diagnostic job history, not user review work.
        return {"status": status, "job_id": job.id, "requested_revision_id": job.requested_revision_id, "applied_revision_id": job.applied_revision_id, "unresolved_hints": [], "error_code": job.error_code}

    @staticmethod
    def _concept_job_status(status):
        # Older databases keep their original job rows without a data migration.
        return "ready" if status in ("completed", "needs_review") else status

    def _index_state(self, session, capture):
        brain = session.get(LocalBrain, self.brain_id)
        build = session.get(IndexBuild, brain.active_index_build_id) if brain.active_index_build_id else None
        state = session.get(CaptureIndexState, (capture.id, build.id)) if build else None
        return {"status": state.status if state else "pending", "profile_id": build.profile_id if build else None, "build_id": build.id if build else None, "index_generation": capture.index_generation, "error_code": state.error_code if state else None}

    def _view(self, session, capture, revision=None):
        revision = revision or self._revision(session, capture)
        memo = {}
        sources = [self._source_status(session, source, {capture.id}, _memo=memo) for source in self._sources(session, revision.id)]
        review = "needs_review" if any(source["review_state"] != "valid" for source in sources) else "valid"
        return {"id": capture.id, "revision_id": revision.id, "revision_no": revision.revision_no, "is_current": revision.id == capture.current_revision_id,
                "state_version": capture.state_version, "title": revision.title, "body_markdown": revision.body_markdown, "kinds": self._kinds(session, revision.id), "visibility": capture.visibility,
                "completion_state": revision.completion_state, "event_time": revision.event_time, "deleted_at": None,
                "created_at": capture.created_at, "updated_at": capture.updated_at, "revision_created_at": revision.created_at,
                "index_state": self._index_state(session, capture), "node_status": revision.node_status,
                "nodes": [self._node_view(session, node, capture, revision, review) for node in self._nodes(session, revision.id)],
                "concept_hints": revision.concept_hints, "concept_state": self._concept_state(session, capture, revision),
                "concepts": [self._concept_view(session, self._concept(session, id)) for id in self._concept_ids(session, revision.id)],
                "sources": sources, "review_state": review, "review_reason": revision.review_reason}

    def get(self, capture_id, revision_id=None):
        with self.db.read() as session:
            capture = self._capture(session, capture_id)
            return self._view(session, capture, self._revision(session, capture, revision_id))

    def node_get(self, node_id):
        with self.db.read() as session:
            node = session.get(KnowledgeNode, str(node_id))
            if not node or node.brain_id != self.brain_id:
                fail("NOT_FOUND", "Node를 찾을 수 없습니다.")
            revision = session.get(CaptureRevision, node.revision_id)
            capture = self._capture(session, revision.capture_id)
            if capture.current_revision_id != revision.id:
                fail("NOT_FOUND", "현재 저장본의 Node가 아닙니다.")
            review = self._view(session, capture, revision)["review_state"]
            return self._node_view(session, node, capture, revision, review)

    def source_get(self, source):
        with self.db.read() as session:
            source, capture, revision, node, start, end = self._source_parts(session, source)
            view = self._view(session, capture, revision)
            return {"source": source, "is_current": revision.id == capture.current_revision_id, "current_revision_id": capture.current_revision_id,
                    "text": revision.body_markdown[start:end], "capture": view, "node": self._node_view(session, node, capture, revision, view["review_state"]) if node else None, "review_state": view["review_state"]}

    def source_status(self, source):
        """Validate current/equivalent evidence without exposing unavailable text."""
        with self.db.read() as session:
            return self._source_status(session, source)

    def source_statuses(self, session, sources):
        """Resolve pinned record references within the caller's transaction."""
        memo = {}
        return [self._source_status(session, source, _memo=memo) for source in sources]

    def eligible_capture(self, capture_id):
        view = self.get(capture_id)
        if view["review_state"] != "valid":
            fail("SOURCE_REVIEW_REQUIRED", "출처를 재검토해야 현재 근거로 사용할 수 있습니다.")
        return view

    def claim_concept_job(self, *, lease_seconds=120, max_attempts=3):
        """Claim one bounded job. The caller performs model inference after commit."""
        if not 1 <= lease_seconds <= 600 or not 1 <= max_attempts <= 10:
            fail("VALIDATION_ERROR", "주제 작업 lease 또는 재시도 한도가 올바르지 않습니다.")
        with self.db.write() as session:
            now = utcnow()
            for exhausted in session.scalars(select(ConceptEnrichmentJob).where(
                ConceptEnrichmentJob.brain_id == self.brain_id, ConceptEnrichmentJob.status == "running",
                ConceptEnrichmentJob.attempt_count >= max_attempts, ConceptEnrichmentJob.lease_until < now,
            )):
                exhausted.status, exhausted.error_code, exhausted.completed_at = "failed", "MODEL_TIMEOUT", now
            jobs = session.scalars(select(ConceptEnrichmentJob).where(
                ConceptEnrichmentJob.brain_id == self.brain_id,
                ConceptEnrichmentJob.attempt_count < max_attempts,
                ConceptEnrichmentJob.available_at <= now,
                or_(ConceptEnrichmentJob.status != "failed", ConceptEnrichmentJob.error_code.is_(None),
                    ConceptEnrichmentJob.error_code.not_in(ACTION_REQUIRED_MODEL_ERRORS)),
                or_(ConceptEnrichmentJob.status.in_(["pending", "failed"]), (ConceptEnrichmentJob.status == "running") & (ConceptEnrichmentJob.lease_until < now)),
            ).order_by(ConceptEnrichmentJob.created_at, ConceptEnrichmentJob.id))
            for job in jobs:
                capture = session.get(Capture, job.capture_id)
                if capture.deleted_at or capture.current_revision_id != job.requested_revision_id or capture.state_version != job.expected_state_version:
                    job.status, job.completed_at = "superseded", now
                    continue
                job.status, job.lease_token = "running", secrets.token_urlsafe(24)
                job.lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                job.attempt_count += 1
                session.flush()
                return {"job_id": job.id, "lease_token": job.lease_token, "lease_until": job.lease_until,
                        "capture": self._view(session, capture), "attempt_count": job.attempt_count}
            return None

    def renew_concept_job(self, job_id, lease_token, *, lease_seconds=120):
        """Renew a live worker's lease between bounded model calls."""
        if not 1 <= lease_seconds <= 600:
            fail("VALIDATION_ERROR", "주제 작업 lease가 올바르지 않습니다.")
        with self.db.write() as session:
            job = session.get(ConceptEnrichmentJob, str(job_id))
            if not job or job.brain_id != self.brain_id:
                fail("NOT_FOUND", "주제 작업을 찾을 수 없습니다.")
            if job.status != "running" or job.lease_token != lease_token or not job.lease_until or job.lease_until <= utcnow():
                return False
            capture = session.get(Capture, job.capture_id)
            if capture.deleted_at or capture.current_revision_id != job.requested_revision_id or capture.state_version != job.expected_state_version:
                job.status, job.completed_at = "superseded", utcnow()
                return False
            job.lease_until = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            return True

    def retry_concepts(self, data: RetryConceptsInput):
        data = RetryConceptsInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "capture_retry_concepts", data)
            if receipt:
                return self._mutation_result(session, receipt, True)
            capture = self._capture(session, data.capture_id)
            self._expected(capture, data)
            job = session.get(ConceptEnrichmentJob, str(data.job_id))
            if not job or job.brain_id != self.brain_id or job.capture_id != capture.id:
                fail("NOT_FOUND", "주제 작업을 찾을 수 없습니다.")
            if job.requested_revision_id != capture.current_revision_id or job.expected_state_version != capture.state_version:
                fail("VERSION_CONFLICT", "현재 저장본의 주제 작업을 다시 조회해 주세요.")
            if job.status != "failed":
                fail("JOB_NOT_RETRYABLE", "실패한 주제 작업만 다시 시도할 수 있습니다.")
            job.status, job.attempt_count, job.available_at = "pending", 0, utcnow()
            job.error_code = job.lease_token = job.lease_until = job.completed_at = None
            job.unresolved_hints = []
            receipt = self._remember(session, "capture_retry_concepts", data, fingerprint, capture=capture)
            return self._mutation_result(session, receipt)

    def fail_concept_job(self, job_id, lease_token, *, error_code="MODEL_UNAVAILABLE"):
        # Error codes only: provider exception strings may contain secrets/content.
        allowed = CONCEPT_MODEL_ERRORS | {"CLASSIFICATION_FAILED", "VERSION_CONFLICT"}
        if error_code not in allowed:
            error_code = "CLASSIFICATION_FAILED"
        with self.db.write() as session:
            job = session.get(ConceptEnrichmentJob, str(job_id))
            if not job or job.brain_id != self.brain_id:
                fail("NOT_FOUND", "주제 작업을 찾을 수 없습니다.")
            if job.status != "running" or job.lease_token != lease_token or not job.lease_until or job.lease_until <= utcnow():
                return {"status": job.status, "applied": False}
            capture = session.get(Capture, job.capture_id)
            if capture.deleted_at or capture.current_revision_id != job.requested_revision_id or capture.state_version != job.expected_state_version:
                job.status = "superseded"
            else:
                job.status, job.error_code = "failed", error_code
                job.available_at = (datetime.now(timezone.utc) + timedelta(seconds=30 * job.attempt_count)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            job.completed_at = utcnow()
            return {"status": job.status, "applied": False}

    def apply_concept_job(self, job_id, lease_token, *, concept_ids, node_concepts=None, candidate_versions=None, unresolved_hints=None, new_concepts=None):
        """Apply only a classification proposal under the original revision lease.

        Existing IDs require their observed state versions. New concepts are
        objects {name, description?, aliases?, attach_to_capture?, node_ids?};
        a matching name/alias now present invalidates that proposal, rather than
        silently merging identities. All concept creations and assignments commit
        atomically with the new revision.
        """
        candidate_versions = candidate_versions or {}
        unresolved_hints = unresolved_hints or []
        new_concepts = new_concepts or []
        if len(set(map(str, concept_ids))) != len(concept_ids):
            fail("VALIDATION_ERROR", "주제 ID가 중복되었습니다.")
        if not all(isinstance(value, str) and value.strip() and len(value) <= 100 for value in unresolved_hints) or len(unresolved_hints) > 20:
            fail("VALIDATION_ERROR", "미해결 주제 힌트가 올바르지 않습니다.")
        with self.db.write() as session:
            job = session.get(ConceptEnrichmentJob, str(job_id))
            if not job or job.brain_id != self.brain_id:
                fail("NOT_FOUND", "주제 작업을 찾을 수 없습니다.")
            if job.status in ("completed", "needs_review"):
                return {"status": "completed", "applied": True, "applied_revision_id": job.applied_revision_id}
            capture = session.get(Capture, job.capture_id)
            if job.status != "running" or job.lease_token != lease_token or not job.lease_until or job.lease_until <= utcnow():
                return {"status": job.status, "applied": False}
            if capture.deleted_at or capture.current_revision_id != job.requested_revision_id or capture.state_version != job.expected_state_version:
                job.status, job.completed_at = "superseded", utcnow()
                return {"status": "superseded", "applied": False}
            old = self._revision(session, capture)
            nodes = {node.id: node for node in self._nodes(session, old.id)}
            ids = list(map(str, concept_ids))
            assignments = {node.ordinal: self._node_concept_ids(session, node.id) for node in nodes.values()}
            if node_concepts is not None:
                assignments = {}
                for node_id, values in node_concepts.items():
                    node_id = str(node_id)
                    if node_id not in nodes or len(values) != len(set(map(str, values))):
                        fail("VALIDATION_ERROR", "현재 Node의 중복 없는 주제 연결이 필요합니다.")
                    assignments[nodes[node_id].ordinal] = list(map(str, values))
            all_ids = set(ids).union(*(set(values) for values in assignments.values()))
            for id in all_ids:
                concept = self._concept(session, id)
                if candidate_versions.get(id) != concept.state_version:
                    fail("VERSION_CONFLICT", "주제 후보가 변경되었습니다. 다시 조회해 주세요.")
            for proposal in new_concepts:
                if set(proposal) - {"name", "description", "aliases", "attach_to_capture", "node_ids"}:
                    fail("VALIDATION_ERROR", "새 주제 제안에 알 수 없는 필드가 있습니다.")
                validated = CreateConceptInput(request_id=new_id(), name=proposal["name"], description=proposal.get("description"), aliases=proposal.get("aliases", []))
                requested_names = {concept_label_key(name) for name in [validated.name, *validated.aliases]}
                existing = list(session.scalars(select(Concept).where(Concept.brain_id == self.brain_id)))
                for candidate in existing:
                    names = {concept_label_key(candidate.name), *(concept_label_key(alias) for alias in session.scalars(select(ConceptAlias.alias).where(ConceptAlias.concept_id == candidate.id)))}
                    if requested_names.intersection(names):
                        fail("VERSION_CONFLICT", "같은 이름의 주제 후보를 다시 검토해야 합니다.")
                now = utcnow()
                concept = Concept(id=new_id(), brain_id=self.brain_id, name=validated.name, description=validated.description, state_version=1, created_at=now, updated_at=now)
                session.add(concept)
                session.flush()
                for alias in validated.aliases:
                    session.add(ConceptAlias(concept_id=concept.id, alias=alias))
                self._queue_topic_backfill(session, concept)
                if proposal.get("attach_to_capture", True):
                    ids.append(concept.id)
                for node_id in proposal.get("node_ids", []):
                    if str(node_id) not in nodes:
                        fail("VALIDATION_ERROR", "새 주제에 연결할 Node가 현재 저장본에 없습니다.")
                    assignments.setdefault(nodes[str(node_id)].ordinal, []).append(concept.id)
            existing_assignments = {node.ordinal: set(self._node_concept_ids(session, node.id)) for node in nodes.values()}
            desired_assignments = {node.ordinal: set(assignments.get(node.ordinal, [])) for node in nodes.values()}
            changed = set(ids) != set(self._concept_ids(session, old.id)) or desired_assignments != existing_assignments
            if changed:
                self._apply_update(session, capture, {}, change_kind="concept_enrichment", concept_ids=ids, node_concepts=assignments, reclassify=False, created_via="system")
            job.status = "completed"
            job.applied_revision_id = capture.current_revision_id
            job.unresolved_hints, job.error_code, job.completed_at = list(unresolved_hints), None, utcnow()
            return {"status": job.status, "applied": True, "applied_revision_id": job.applied_revision_id, "changed": changed}

    def _page(self, items, limit, cursor, filters, snapshot, key):
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            fail("VALIDATION_ERROR", "limit은 1부터 100까지입니다.")
        filter_hash = digest(filters)
        offset = 0
        if cursor:
            try:
                parsed = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if set(parsed) != {"filter", "snapshot", "offset"} or parsed["filter"] != filter_hash or parsed["snapshot"] != snapshot:
                    raise ValueError()
                offset = parsed["offset"]
                if not isinstance(offset, int) or offset < 0:
                    raise ValueError()
            except Exception:
                fail("CURSOR_STALE", "목록 기준이 변경되었습니다. 처음부터 다시 조회해 주세요.")
        selected = items[offset:offset + limit]
        next_cursor = None
        if offset + limit < len(items):
            next_cursor = base64.urlsafe_b64encode(canonical({"filter": filter_hash, "snapshot": snapshot, "offset": offset + limit}).encode()).decode()
        return {"items": [key(item) for item in selected], "next_cursor": next_cursor}

    def list(self, *, query=None, kinds=None, concept_ids=None, limit=20, cursor=None,
             created_from=None, created_before=None, sort="created_desc"):
        start, end = created_boundary(created_from, "created_from"), created_boundary(created_before, "created_before")
        if start is not None and end is not None and start >= end:
            fail("VALIDATION_ERROR", "저장일 범위의 시작은 끝보다 앞서야 합니다.")
        if sort not in ("created_desc", "title_asc"):
            fail("VALIDATION_ERROR", "지원하지 않는 기록 정렬입니다.")
        filters = {"query": query, "kinds": sorted(normalize_record_kinds(kinds or [])), "concept_ids": sorted(map(str, concept_ids or []))}
        # Keep existing default cursors valid; canonicalize new boundaries so
        # equivalent offsets refer to the same result set.
        if start is not None:
            filters["created_from"] = start.isoformat()
        if end is not None:
            filters["created_before"] = end.isoformat()
        if sort != "created_desc":
            filters["sort"] = sort
        with self.db.read() as session:
            captures = list(session.scalars(select(Capture).where(Capture.brain_id == self.brain_id, Capture.deleted_at.is_(None)).order_by(Capture.created_at.desc(), Capture.id.desc())))
            snapshot = digest([(c.id, c.state_version) for c in captures])
            predicates = record_filter_predicates(kinds=kinds, concept_ids=concept_ids)
            matching_revisions = set(session.scalars(select(CaptureRevision.id).join(
                Capture, Capture.current_revision_id == CaptureRevision.id).where(
                Capture.brain_id == self.brain_id, Capture.deleted_at.is_(None), *predicates))) if predicates else None
            values = []
            for capture in captures:
                if start is not None or end is not None:
                    created_at = datetime.fromisoformat(capture.created_at.replace("Z", "+00:00"))
                    if (start is not None and created_at < start) or (end is not None and created_at >= end):
                        continue
                if matching_revisions is not None and capture.current_revision_id not in matching_revisions:
                    continue
                revision = self._revision(session, capture)
                if query and query.casefold() not in ((revision.title or "") + "\n" + revision.body_markdown).casefold():
                    continue
                values.append((capture, revision))
            if sort == "title_asc":
                values.sort(key=lambda item: ((item[1].title or "").strip().casefold() or "제목 없는 기록", item[0].id))
            def summary(item):
                capture, revision = item
                view = self._view(session, capture, revision)
                return {field: view[field] for field in ("id", "revision_id", "revision_no", "state_version", "title", "kinds", "visibility", "completion_state", "event_time", "created_at", "updated_at", "index_state", "node_status", "concept_state", "review_state")} | {"excerpt": revision.body_markdown[:240]}
            return self._page(values, limit, cursor, filters, snapshot, summary)

    def _receipt(self, session, operation, data):
        receipt = session.get(MutationReceipt, (self.principal_scope, str(data.request_id)))
        fingerprint = digest(data.model_dump(mode="json", exclude_unset=True))
        matches = receipt is None or receipt.request_fingerprint == fingerprint
        if receipt and not matches:
            matches = receipt.request_fingerprint == digest(data.legacy_request_payload())
        if receipt and (receipt.operation != operation or not matches):
            fail("IDEMPOTENCY_CONFLICT", "같은 request_id에 다른 요청을 사용할 수 없습니다.")
        return receipt, fingerprint

    def _remember(self, session, operation, data, fingerprint, *, capture=None, concept=None, relation=None):
        receipt = MutationReceipt(principal_scope=self.principal_scope, request_id=str(data.request_id), operation=operation, request_fingerprint=fingerprint,
                                  capture_id=capture.id if capture else None, concept_id=concept.id if concept else None, relation_id=relation.id if relation else None,
                                  committed_revision_id=capture.current_revision_id if capture else None, committed_state_version=capture.state_version if capture else concept.state_version if concept else None,
                                  committed_deleted_at=capture.deleted_at if capture else None, outcome="committed", created_at=utcnow())
        session.add(receipt)
        session.flush()
        return receipt

    def _mutation_result(self, session, receipt, replayed=False, warnings=None):
        try:
            capture = self._capture(session, receipt.capture_id)
        except DomainError:
            return {"capture": None, "committed_ref": None, "request_id": receipt.request_id, "replayed": replayed, "result_state": "unavailable", "warnings": ["RESULT_UNAVAILABLE"]}
        revision = self._revision(session, capture, receipt.committed_revision_id)
        return {"capture": self._view(session, capture, revision), "committed_ref": {"capture_id": capture.id, "revision_id": revision.id, "node_id": None, "body_start": None, "body_end": None},
                "request_id": receipt.request_id, "replayed": replayed, "result_state": "available", "warnings": warnings or (["NODES_STALE"] if revision.node_status == "stale" else [])}

    def _outbox(self, session, capture, operation="upsert"):
        now = utcnow()
        session.flush()
        for build in session.scalars(select(IndexBuild).where(IndexBuild.brain_id == self.brain_id, IndexBuild.status.in_(["building", "active"]))):
            state = session.get(CaptureIndexState, (capture.id, build.id))
            values = {"revision_id": capture.current_revision_id, "index_generation": capture.index_generation, "status": "excluded" if operation == "remove" else "pending", "error_code": None, "updated_at": now}
            if state:
                for name, value in values.items():
                    setattr(state, name, value)
            else:
                session.add(CaptureIndexState(capture_id=capture.id, build_id=build.id, **values))
            session.add(IndexJob(id=new_id(), capture_id=capture.id, revision_id=capture.current_revision_id, profile_id=build.profile_id, build_id=build.id, index_generation=capture.index_generation, operation=operation, status="pending", attempt_count=0, available_at=now))

    def _queue_concepts(self, session, capture):
        for old in session.scalars(select(ConceptEnrichmentJob).where(ConceptEnrichmentJob.capture_id == capture.id, ConceptEnrichmentJob.status.in_(["pending", "running"]))):
            old.status, old.completed_at = "superseded", utcnow()
        now = utcnow()
        session.add(ConceptEnrichmentJob(id=new_id(), brain_id=self.brain_id, capture_id=capture.id, requested_revision_id=capture.current_revision_id, expected_state_version=capture.state_version, policy_version="concept-v2", status="pending", unresolved_hints=[], attempt_count=0, available_at=now, created_at=now))

    def _queue_topic_backfill(self, session, concept):
        from .topic_backfill_jobs import enqueue_topic
        enqueue_topic(self, session, concept)

    def _insert_revision(self, session, capture, *, title, body_markdown, kinds, completion_state, event_time, concept_hints, nodes, sources, node_status, change_kind, revision_no, review_reason=None, concept_ids=None, node_concepts=None, created_via=None):
        for node in nodes:
            if node["body_start"] < 0 or node["body_end"] > len(body_markdown) or node["body_end"] <= node["body_start"]:
                fail("VALIDATION_ERROR", "Node 범위가 본문을 벗어납니다.")
        revision = CaptureRevision(id=capture.current_revision_id, brain_id=self.brain_id, capture_id=capture.id, revision_no=revision_no, title=title, body_markdown=body_markdown,
                                   concept_hints=concept_hints, completion_state=completion_state, event_time=event_time, node_status=node_status, change_kind=change_kind, review_reason=review_reason, created_via=created_via or self.created_via, created_at=utcnow())
        session.add(revision)
        session.flush()
        for kind in normalize_record_kinds(kinds):
            session.add(RevisionKind(revision_id=revision.id, kind=kind))
        for concept_id in concept_ids or []:
            self._concept(session, concept_id)
            session.add(RevisionConcept(revision_id=revision.id, concept_id=concept_id, brain_id=self.brain_id))
        for ordinal, data in enumerate(nodes):
            node = KnowledgeNode(id=new_id(), revision_id=revision.id, brain_id=self.brain_id, ordinal=ordinal, **data)
            session.add(node)
            session.flush()
            for concept_id in (node_concepts or {}).get(ordinal, []):
                self._concept(session, concept_id)
                session.add(NodeConcept(node_id=node.id, concept_id=concept_id, brain_id=self.brain_id))
        for source in sources:
            session.add(ProvenanceLink(id=new_id(), brain_id=self.brain_id, derived_revision_id=revision.id, **{"source_" + key: value for key, value in source.items()}))
        session.flush()
        return revision

    def create(self, data: CreateCaptureInput):
        data = CreateCaptureInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "capture_create", data)
            if receipt:
                return self._mutation_result(session, receipt, True)
            sources = self._validate_sources(session, data.sources)
            now = utcnow()
            capture = Capture(id=new_id(), brain_id=self.brain_id, current_revision_id=new_id(), visibility=data.visibility, state_version=1, index_generation=1, created_at=now, updated_at=now)
            session.add(capture)
            session.flush()
            values = data.model_dump(mode="json")
            self._insert_revision(session, capture, **{key: values[key] for key in ("title", "body_markdown", "kinds", "completion_state", "event_time", "concept_hints", "nodes")}, sources=sources, node_status="current" if data.nodes else "absent", change_kind="create", revision_no=1)
            self._outbox(session, capture)
            self._queue_concepts(session, capture)
            receipt = self._remember(session, "capture_create", data, fingerprint, capture=capture)
            return self._mutation_result(session, receipt)

    def _copy_node_data(self, nodes):
        return [{field: getattr(node, field) for field in ("kind", "body_start", "body_end", "label", "origin", "verification_state", "verification_note", "concept_hints")} for node in nodes]

    def _apply_update(self, session, capture, changes, *, change_kind=None, replacement_sources=None, review_reason=None, concept_ids=None, node_concepts=None, reclassify=None, created_via=None):
        old = self._revision(session, capture)
        old_nodes = self._nodes(session, old.id)
        body = changes.get("body_markdown", old.body_markdown)
        body_changed = body != old.body_markdown
        sources = self._sources(session, old.id)
        if replacement_sources is not None:
            sources = replacement_sources
        elif "sources" in changes:
            supplied = self._validate_sources(session, changes["sources"], capture.id)
            sources = list({canonical(s): s for s in sources + supplied}.values())
        if "nodes" in changes:
            nodes = changes["nodes"]
            node_status = "current" if nodes else "absent"
            carried_node_concepts = {}
        elif body_changed:
            nodes = []
            node_status = "absent" if old.node_status == "absent" else "stale"
            carried_node_concepts = {}
        else:
            nodes = self._copy_node_data(old_nodes)
            node_status = old.node_status
            carried_node_concepts = {n.ordinal: self._node_concept_ids(session, n.id) for n in old_nodes}
        values = {field: changes.get(field, getattr(old, field)) for field in ("title", "completion_state", "event_time", "concept_hints")}
        kinds = changes.get("kinds", self._kinds(session, old.id))
        capture.visibility = changes.get("visibility", capture.visibility)
        previous_state_version = capture.state_version
        capture.state_version += 1
        capture.index_generation += 1
        capture.updated_at = utcnow()
        # Visibility-only changes retain immutable revision identity.
        if set(changes) != {"visibility"} or change_kind or concept_ids is not None:
            capture.current_revision_id = new_id()
            selected_kind = change_kind or ("completion_change" if set(changes) <= {"completion_state", "visibility"} else "edit")
            self._insert_revision(session, capture, **values, body_markdown=body, kinds=kinds, nodes=nodes, sources=sources, node_status=node_status, change_kind=selected_kind, revision_no=old.revision_no + 1,
                                  review_reason=review_reason, concept_ids=self._concept_ids(session, old.id) if concept_ids is None else concept_ids,
                                  node_concepts=carried_node_concepts if node_concepts is None else node_concepts, created_via=created_via)
        self._outbox(session, capture)
        should_classify = bool(set(changes).intersection({"body_markdown", "concept_hints", "nodes"})) if reclassify is None else reclassify
        old_pending = list(session.scalars(select(ConceptEnrichmentJob).where(ConceptEnrichmentJob.capture_id == capture.id, ConceptEnrichmentJob.status.in_(["pending", "running"]))))
        if should_classify or (reclassify is None and old_pending):
            self._queue_concepts(session, capture)
        else:
            for job in old_pending:
                job.status, job.completed_at = "superseded", utcnow()
            if capture.current_revision_id == old.id:
                # A visibility-only edit leaves the classified content intact.
                # Keep failures retryable without resetting their error/backoff.
                for job in session.scalars(select(ConceptEnrichmentJob).where(
                    ConceptEnrichmentJob.capture_id == capture.id,
                    ConceptEnrichmentJob.requested_revision_id == old.id,
                    ConceptEnrichmentJob.expected_state_version == previous_state_version,
                    ConceptEnrichmentJob.status == "failed",
                )):
                    job.expected_state_version = capture.state_version
        session.flush()
        return capture

    def update(self, data: UpdateCaptureInput):
        data = UpdateCaptureInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "capture_update", data)
            if receipt:
                return self._mutation_result(session, receipt, True)
            capture = self._capture(session, data.capture_id)
            self._expected(capture, data)
            self._apply_update(session, capture, data.changes.model_dump(mode="json", exclude_unset=True))
            return self._mutation_result(session, self._remember(session, "capture_update", data, fingerprint, capture=capture))

    def merge(self, data: MergeCapturesInput):
        data = MergeCapturesInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "capture_merge", data)
            if receipt:
                return self._mutation_result(session, receipt, True)
            capture = self._capture(session, data.target_capture_id)
            self._expected(capture, data)
            changes = {"body_markdown": data.merged_body_markdown, "sources": [source.model_dump(mode="json") for source in data.sources]}
            for key in ("nodes", "concept_hints", "kinds"):
                if key in data.model_fields_set and getattr(data, key) is not None:
                    changes[key] = data.model_dump(mode="json")[key]
            self._apply_update(session, capture, changes, change_kind="merge")
            return self._mutation_result(session, self._remember(session, "capture_merge", data, fingerprint, capture=capture))

    def review_sources(self, data: ReviewSourcesInput):
        data = ReviewSourcesInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "capture_review_sources", data)
            if receipt:
                return self._mutation_result(session, receipt, True)
            capture = self._capture(session, data.capture_id)
            self._expected(capture, data)
            old = self._revision(session, capture)
            old_sources = self._sources(session, old.id)
            replacement = self._validate_sources(session, data.replacement_sources, capture.id)
            # Removing an entire known dependency requires a rewritten body, even
            # when other unrelated sources are retained.
            removed_captures = {s["capture_id"] for s in old_sources} - {s["capture_id"] for s in replacement}
            if removed_captures and (data.body_markdown is None or data.body_markdown == old.body_markdown):
                fail("SOURCE_REVIEW_REQUIRED", "알려진 출처 의존성을 제거하려면 본문을 재작성해야 합니다.")
            changes = {key: value for key, value in data.model_dump(mode="json", exclude_unset=True).items() if key in ("body_markdown", "nodes") and value is not None}
            self._apply_update(session, capture, changes, change_kind="source_review", replacement_sources=replacement, review_reason=data.review_reason)
            return self._mutation_result(session, self._remember(session, "capture_review_sources", data, fingerprint, capture=capture))

    def set_concepts(self, data: SetConceptsInput):
        data = SetConceptsInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "capture_set_concepts", data)
            if receipt:
                return self._mutation_result(session, receipt, True)
            capture = self._capture(session, data.capture_id)
            self._expected(capture, data)
            ids = [str(id) for id in data.concept_ids]
            for id in ids:
                self._concept(session, id)
            node_concepts = None
            if data.node_concepts is not None:
                nodes = {n.id: n for n in self._nodes(session, capture.current_revision_id)}
                node_concepts, seen = {}, set()
                for assignment in data.node_concepts:
                    node_id = str(assignment.node_id)
                    if node_id not in nodes or node_id in seen:
                        fail("VALIDATION_ERROR", "Node 주제 정정은 현재 저장본의 중복 없는 Node를 사용해야 합니다.")
                    seen.add(node_id)
                    node_concepts[nodes[node_id].ordinal] = [str(id) for id in assignment.concept_ids]
            self._apply_update(session, capture, {}, change_kind="edit", concept_ids=ids, node_concepts=node_concepts, reclassify=False)
            return self._mutation_result(session, self._remember(session, "capture_set_concepts", data, fingerprint, capture=capture))

    def prepare_delete(self, data: PrepareDeletionInput):
        data = PrepareDeletionInput.model_validate(data)
        with self.db.write() as session:
            capture = self._capture(session, data.capture_id)
            self._expected(capture, data)
            revision = self._revision(session, capture)
            token = secrets.token_urlsafe(40)
            expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            session.add(DeletionConfirmation(token_hash=hashlib.sha256(token.encode()).hexdigest(), brain_id=self.brain_id, principal_scope=self.principal_scope, session_scope=self.session_scope, capture_id=capture.id, expected_revision_id=capture.current_revision_id, expected_state_version=capture.state_version, expires_at=expires_at))
            return {"confirmation_token": token, "capture_id": capture.id, "expected_revision_id": capture.current_revision_id, "expected_state_version": capture.state_version, "title": revision.title, "excerpt": revision.body_markdown[:240], "expires_at": expires_at}

    def confirm_deletion(self, token: str) -> HumanConfirmation:
        """Call ONLY after a trusted UI action/actual MCP elicitation acceptance.

        This is deliberately not a Pydantic input or an exposed HTTP/MCP method.
        A model-supplied boolean/token is not a human confirmation.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        proof = hashlib.sha256((self._confirmation_secret + token_hash + self.principal_scope + self.session_scope).encode()).hexdigest()
        return HumanConfirmation(token_hash, self.principal_scope, self.session_scope, proof)

    def _delete_result(self, receipt, replayed):
        return {"request_id": receipt.request_id, "capture_id": receipt.capture_id, "revision_id": receipt.committed_revision_id, "state_version": receipt.committed_state_version,
                "deleted_at": receipt.committed_deleted_at, "index_state": {"status": "excluded"}, "replayed": replayed}

    def delete(self, data: DeleteCaptureInput, *, confirmation: HumanConfirmation | None = None):
        data = DeleteCaptureInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "capture_delete", data)
            if receipt:
                return self._delete_result(receipt, True)
            expected_proof = self.confirm_deletion(data.confirmation_token)
            if not isinstance(confirmation, HumanConfirmation) or confirmation != expected_proof:
                fail("CONFIRMATION_REQUIRED", "사용자의 명시적인 삭제 확인이 필요합니다.")
            capture = self._capture(session, data.capture_id)
            self._expected(capture, data)
            token = session.get(DeletionConfirmation, expected_proof.token_hash)
            if token is None or token.brain_id != self.brain_id or token.principal_scope != self.principal_scope or token.session_scope != self.session_scope or token.capture_id != capture.id or token.expected_revision_id != capture.current_revision_id or token.expected_state_version != capture.state_version or token.used_at:
                fail("CONFIRMATION_REQUIRED", "이 대상과 버전에 유효한 삭제 확인이 필요합니다.")
            if token.expires_at <= utcnow():
                fail("CONFIRMATION_EXPIRED", "삭제 확인이 만료되었습니다. 다시 확인해 주세요.")
            now = utcnow()
            capture.deleted_at = capture.updated_at = token.used_at = now
            capture.state_version += 1
            capture.index_generation += 1
            for job in session.scalars(select(ConceptEnrichmentJob).where(ConceptEnrichmentJob.capture_id == capture.id, ConceptEnrichmentJob.status.in_(["pending", "running"]))):
                job.status, job.completed_at = "superseded", now
            self._outbox(session, capture, "remove")
            return self._delete_result(self._remember(session, "capture_delete", data, fingerprint, capture=capture), False)

    def concept_create(self, data: CreateConceptInput):
        data = CreateConceptInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "concept_create", data)
            if receipt:
                return self._concept_view(session, self._concept(session, receipt.concept_id)) | {"request_id": receipt.request_id, "replayed": True}
            now = utcnow()
            concept = Concept(id=new_id(), brain_id=self.brain_id, name=data.name, description=data.description, state_version=1, created_at=now, updated_at=now)
            session.add(concept)
            session.flush()
            for alias in data.aliases:
                session.add(ConceptAlias(concept_id=concept.id, alias=alias))
            self._queue_topic_backfill(session, concept)
            self._remember(session, "concept_create", data, fingerprint, concept=concept)
            return self._concept_view(session, concept) | {"request_id": str(data.request_id), "replayed": False}

    def concept_get(self, concept_id):
        with self.db.read() as session:
            return self._concept_view(session, self._concept(session, concept_id))

    def concept_list(self, *, query=None, limit=20, cursor=None):
        with self.db.read() as session:
            concepts = list(session.scalars(select(Concept).where(Concept.brain_id == self.brain_id).order_by(Concept.created_at.desc(), Concept.id.desc())))
            snapshot = digest([(c.id, c.state_version) for c in concepts])
            views = [self._concept_view(session, c) for c in concepts]
            if query:
                lookup = concept_label_key(query)
                views = [view for view in views if any(lookup in concept_label_key(name) for name in [view["name"], *view["aliases"]])]
            return self._page(views, limit, cursor, {"query": query}, snapshot, lambda view: view)

    def concept_update(self, data: UpdateConceptInput):
        from .topic_backfill_jobs import definition_hash
        data = UpdateConceptInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "concept_update", data)
            if receipt:
                return self._concept_view(session, self._concept(session, receipt.concept_id)) | {"request_id": receipt.request_id, "replayed": True}
            concept = self._concept(session, data.concept_id)
            if concept.state_version != data.expected_state_version:
                fail("VERSION_CONFLICT", "주제가 변경되었습니다.")
            previous_definition = definition_hash(self._concept_view(session, concept))
            for key, value in data.changes.model_dump(exclude_unset=True).items():
                if key == "aliases":
                    for alias in session.scalars(select(ConceptAlias).where(ConceptAlias.concept_id == concept.id)):
                        session.delete(alias)
                    session.flush()
                    for alias in value:
                        session.add(ConceptAlias(concept_id=concept.id, alias=alias))
                else:
                    setattr(concept, key, value)
            concept.state_version += 1
            concept.updated_at = utcnow()
            session.flush()
            if definition_hash(self._concept_view(session, concept)) != previous_definition:
                self._queue_topic_backfill(session, concept)
            self._remember(session, "concept_update", data, fingerprint, concept=concept)
            return self._concept_view(session, concept) | {"request_id": str(data.request_id), "replayed": False}

    def _relation_ref(self, relation, prefix):
        return {key: getattr(relation, prefix + "_" + key) for key in ("capture_id", "revision_id", "node_id", "body_start", "body_end")}

    def _relation_view(self, session, relation, *, require_valid=True):
        refs = {prefix: self._relation_ref(relation, prefix) for prefix in ("source", "target", "evidence")}
        memo = {}
        for source in refs.values():
            self._source_parts(session, source)
            if require_valid and self._source_status(session, source, _memo=memo)["review_state"] != "valid":
                fail("NOT_FOUND", "현재 유효한 관계를 찾을 수 없습니다.")
        return {"id": relation.id, "relation_type": relation.relation_type, **refs, "scope_note": relation.scope_note, "evidence_note": relation.evidence_note,
                "created_at": relation.created_at, "withdrawn_at": relation.withdrawn_at, "withdrawal_reason": relation.withdrawal_reason}

    def current_relation(self, relation_id):
        """Read a currently usable relation with resolved evidence references.

        This internal service boundary is also used immediately before answering:
        retracting a relation does not change its endpoint Capture versions.
        """
        with self.db.read() as session:
            relation = session.get(Relation, str(relation_id))
            if relation is None or relation.brain_id != self.brain_id or relation.withdrawn_at is not None:
                fail("NOT_FOUND", "현재 유효한 관계를 찾을 수 없습니다.")
            view = self._relation_view(session, relation)
            for field in ("source", "target", "evidence"):
                view[field] = self._source_status(session, view[field])["resolved_source"]
            return view

    def relation_create(self, data: RelationInput):
        data = RelationInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "relation_create", data)
            if receipt:
                relation = session.get(Relation, receipt.relation_id)
                return self._relation_view(session, relation) | {"request_id": receipt.request_id, "replayed": True}
            refs = {prefix: getattr(data, prefix).model_dump(mode="json") for prefix in ("source", "target", "evidence")}
            for source in refs.values():
                self._validate_sources(session, [source])
            if data.relation_type == "supersedes":
                if not (data.scope_note or "").strip() or not (data.evidence_note or "").strip() or any(not ref["node_id"] and ref["body_start"] is None for ref in refs.values()):
                    fail("INVALID_RELATION_SCOPE", "대체 관계는 양쪽 구간과 근거 구간, 적용 범위 설명이 필요합니다.")
                # Conservative cycle guard at Capture level, preserving direction.
                adjacency = {}
                for edge in session.scalars(select(Relation).where(Relation.brain_id == self.brain_id, Relation.relation_type == "supersedes", Relation.withdrawn_at.is_(None))):
                    try:
                        self._relation_view(session, edge)
                    except DomainError:
                        continue
                    adjacency.setdefault(edge.source_capture_id, set()).add(edge.target_capture_id)
                pending, visited = [refs["target"]["capture_id"]], set()
                while pending:
                    current = pending.pop()
                    if current == refs["source"]["capture_id"]:
                        fail("SOURCE_CYCLE", "대체 관계가 순환할 수 없습니다.")
                    if current not in visited:
                        visited.add(current)
                        pending.extend(adjacency.get(current, []))
            values = {prefix + "_" + key: value for prefix, ref in refs.items() for key, value in ref.items()}
            relation = Relation(id=new_id(), brain_id=self.brain_id, relation_type=data.relation_type, **values, scope_note=data.scope_note, evidence_note=data.evidence_note, created_at=utcnow())
            session.add(relation)
            session.flush()
            self._remember(session, "relation_create", data, fingerprint, relation=relation)
            return self._relation_view(session, relation) | {"request_id": str(data.request_id), "replayed": False}

    def relation_list(self, *, capture_id=None, node_id=None, relation_type=None, direction="both", limit=20, cursor=None):
        if not capture_id and not node_id:
            fail("VALIDATION_ERROR", "capture_id 또는 node_id가 필요합니다.")
        if direction not in ("incoming", "outgoing", "both"):
            fail("VALIDATION_ERROR", "관계 방향이 올바르지 않습니다.")
        with self.db.read() as session:
            if capture_id:
                self._capture(session, capture_id)
            if node_id:
                node = session.get(KnowledgeNode, str(node_id))
                if node is None:
                    fail("NOT_FOUND", "Node를 찾을 수 없습니다.")
                capture = self._capture(session, session.get(CaptureRevision, node.revision_id).capture_id)
                if capture.current_revision_id != node.revision_id:
                    fail("NOT_FOUND", "현재 Node가 아닙니다.")
            relations = list(session.scalars(select(Relation).where(Relation.brain_id == self.brain_id, Relation.withdrawn_at.is_(None)).order_by(Relation.created_at.desc(), Relation.id.desc())))
            views = []
            for relation in relations:
                if relation_type and relation.relation_type != relation_type:
                    continue
                try:
                    view = self._relation_view(session, relation)
                except DomainError:
                    continue
                prefixes = ("source", "target") if direction == "both" else ("source",) if direction == "outgoing" else ("target",)
                matches = False
                for prefix in prefixes:
                    resolved = self._source_status(session, view[prefix])["resolved_source"]
                    if (not capture_id or resolved["capture_id"] == str(capture_id)) and (not node_id or resolved["node_id"] == str(node_id)):
                        matches = True
                if matches:
                    views.append(view)
            return self._page(views, limit, cursor, {"capture_id": str(capture_id), "node_id": str(node_id), "relation_type": relation_type, "direction": direction}, digest(views), lambda view: view)

    def relation_retract(self, data: RetractRelationInput):
        data = RetractRelationInput.model_validate(data)
        with self.db.write() as session:
            receipt, fingerprint = self._receipt(session, "relation_retract", data)
            relation = session.get(Relation, receipt.relation_id if receipt else str(data.relation_id))
            if not relation or relation.brain_id != self.brain_id:
                fail("NOT_FOUND", "관계를 찾을 수 없습니다.")
            # Retraction corrects an explicit stored relationship. Changed source
            # contents may make it unusable for retrieval but do not remove the
            # owner's right to withdraw it. Still enforce access to all parents.
            view = self._relation_view(session, relation, require_valid=False)
            if receipt:
                return view | {"request_id": receipt.request_id, "replayed": True}
            if relation.withdrawn_at:
                fail("RELATION_ALREADY_WITHDRAWN", "이미 철회한 관계입니다.")
            relation.withdrawn_at, relation.withdrawal_reason = utcnow(), data.withdrawal_reason
            self._remember(session, "relation_retract", data, fingerprint, relation=relation)
            return self._relation_view(session, relation, require_valid=False) | {"request_id": str(data.request_id), "replayed": False}
