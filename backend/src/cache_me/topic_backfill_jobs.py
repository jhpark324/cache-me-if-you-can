"""Durable, bounded work for linking changed topics to existing records."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy import or_, select

from .db import new_id, utcnow
from .model_errors import ACTION_REQUIRED_MODEL_ERRORS, CONCEPT_MODEL_ERRORS
from .models import (Capture, Concept, ConceptEnrichmentJob, MutationReceipt,
                     TopicBackfillDecision, TopicBackfillJob)
from .records import SourceValidationBudget, SourceValidationLimit, digest, fail


POLICY_VERSION = "topic-backfill-v1"
MAX_CALLS = 4
MAX_ATTEMPTS = 3
MAX_CANDIDATES = 20
LEASE_SECONDS = 120


def definition_hash(concept):
    return digest([concept["name"], concept.get("description"), sorted(set(concept.get("aliases", [])))])


def enqueue_topic(records, session, concept):
    """Called only from an actual topic creation/definition change transaction."""
    session.flush()
    fingerprint = definition_hash(records._concept_view(session, concept))
    now = utcnow()
    jobs = list(session.scalars(select(TopicBackfillJob).where(
        TopicBackfillJob.concept_id == concept.id, TopicBackfillJob.policy_version == POLICY_VERSION)))
    matching = None
    for job in jobs:
        if job.definition_hash == fingerprint:
            matching = job
        elif job.status in ("pending", "running"):
            job.status, job.completed_at = "superseded", now
            job.lease_token = job.lease_until = None
    if matching:
        # A quick A -> B -> A edit resumes A's bounded work, never resets its budget.
        if matching.status == "superseded" and matching.call_count < MAX_CALLS and matching.attempt_count < MAX_ATTEMPTS:
            matching.status, matching.available_at, matching.completed_at = "pending", now, None
        return
    session.add(TopicBackfillJob(id=new_id(), brain_id=records.brain_id, concept_id=concept.id,
        definition_hash=fingerprint, policy_version=POLICY_VERSION, status="pending", candidate_ids=[],
        attempt_count=0, call_count=0, available_at=now, created_at=now))


def _later(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _error_code(value):
    allowed = CONCEPT_MODEL_ERRORS | {"CLASSIFICATION_FAILED", "INDEX_NOT_READY", "CANDIDATES_NOT_READY", "INCOMPLETE_DECISIONS", "VERSION_CONFLICT", "CALL_BUDGET_EXHAUSTED"}
    return value if value is None or value in allowed else "CLASSIFICATION_FAILED"


class TopicBackfillJobs:
    def __init__(self, records):
        self.records, self.db, self.brain_id = records, records.db, records.brain_id

    def _current_topic(self, session, job):
        concept = session.get(Concept, job.concept_id)
        if concept is None or concept.brain_id != self.brain_id:
            return None
        view = self.records._concept_view(session, concept)
        return view if definition_hash(view) == job.definition_hash else None

    def _active(self, session, claimed):
        job = session.get(TopicBackfillJob, claimed["job_id"])
        if (not job or job.brain_id != self.brain_id or job.status != "running"
                or job.lease_token != claimed["lease_token"] or not job.lease_until or job.lease_until <= utcnow()):
            return None
        if self._current_topic(session, job) is None:
            job.status, job.completed_at = "superseded", utcnow()
            job.lease_token = job.lease_until = None
            return None
        return job

    def claim(self, *, lease_seconds=LEASE_SECONDS):
        if not 1 <= lease_seconds <= 600:
            fail("VALIDATION_ERROR", "주제 보강 lease가 올바르지 않습니다.")
        with self.db.write() as session:
            now = utcnow()
            jobs = session.scalars(select(TopicBackfillJob).where(
                TopicBackfillJob.brain_id == self.brain_id, TopicBackfillJob.available_at <= now,
                or_(TopicBackfillJob.status == "pending", (TopicBackfillJob.status == "running") & (TopicBackfillJob.lease_until <= now)),
            ).order_by(TopicBackfillJob.created_at, TopicBackfillJob.id))
            for job in jobs:
                concept = self._current_topic(session, job)
                if concept is None:
                    job.status, job.completed_at = "superseded", now
                    continue
                if job.call_count >= MAX_CALLS or job.attempt_count >= MAX_ATTEMPTS:
                    job.status, job.completed_at = "partial", now
                    job.error_code = "CALL_BUDGET_EXHAUSTED" if job.call_count >= MAX_CALLS else "MODEL_TIMEOUT"
                    continue
                job.status, job.lease_token = "running", secrets.token_urlsafe(24)
                job.lease_until = _later(lease_seconds)
                job.attempt_count += 1
                session.flush()
                return {"job_id": job.id, "lease_token": job.lease_token, "lease_until": job.lease_until,
                    "concept": concept, "definition_hash": job.definition_hash, "policy_version": job.policy_version,
                    "call_count": job.call_count, "attempt_count": job.attempt_count}
        return None

    def renew(self, claimed):
        with self.db.write() as session:
            job = self._active(session, claimed)
            if job is None:
                return False
            job.lease_until = _later(LEASE_SECONDS)
            claimed["lease_until"] = job.lease_until
            return True

    def reserve_call(self, claimed):
        with self.db.write() as session:
            job = self._active(session, claimed)
            if job is None or job.call_count >= MAX_CALLS:
                return False
            job.call_count += 1
            job.lease_until = _later(LEASE_SECONDS)
            claimed["call_count"], claimed["lease_until"] = job.call_count, job.lease_until
            return True

    def _eligible(self, session, capture, concept_id):
        if capture is None or capture.brain_id != self.brain_id or capture.deleted_at:
            return False
        # This first version intentionally protects even historical manual edits.
        if session.scalar(select(MutationReceipt.request_id).where(
            MutationReceipt.capture_id == capture.id, MutationReceipt.operation == "capture_set_concepts").limit(1)):
            return False
        if session.scalar(select(ConceptEnrichmentJob.id).where(
            ConceptEnrichmentJob.capture_id == capture.id, ConceptEnrichmentJob.status.in_(["pending", "running"])).limit(1)):
            return False
        # A new metadata revision must not make a failed classification
        # impossible to retry. Deferred candidates are normal completion.
        revision = self.records._revision(session, capture)
        if self.records._concept_state(session, capture, revision)["status"] != "ready":
            return False
        if concept_id in self.records._concept_ids(session, capture.current_revision_id):
            return False
        try:
            source = {"capture_id": capture.id, "revision_id": capture.current_revision_id}
            return self.records._source_status(session, source, validation=SourceValidationBudget())["review_state"] == "valid"
        except SourceValidationLimit:
            return False

    def _snapshot(self, session, capture):
        revision = self.records._revision(session, capture)
        fields = ("ordinal", "kind", "body_start", "body_end", "label", "origin", "verification_state", "verification_note", "concept_hints")
        nodes = [{field: getattr(node, field) for field in fields} for node in self.records._nodes(session, revision.id)]
        content = {"title": revision.title, "body_markdown": revision.body_markdown, "nodes": nodes,
            "kinds": self.records._kinds(session, revision.id), "concept_hints": revision.concept_hints,
            "event_time": revision.event_time, "sources": self.records._sources(session, revision.id)}
        return {**content, "capture_id": capture.id, "revision_id": revision.id,
                "state_version": capture.state_version, "content_hash": digest(content)}

    @staticmethod
    def _decision_key(job, snapshot):
        return (job.concept_id, job.definition_hash, snapshot["capture_id"], snapshot["content_hash"], job.policy_version)

    def prepare_candidates(self, claimed, hits, limit=MAX_CANDIDATES):
        if not isinstance(limit, int) or not 1 <= limit <= MAX_CANDIDATES:
            fail("VALIDATION_ERROR", "주제 보강 후보 한도가 올바르지 않습니다.")
        with self.db.write() as session:
            job = self._active(session, claimed)
            if job is None:
                return []
            admitted, seen, result = list(job.candidate_ids), set(), []
            for hit in hits:
                source = hit.get("source", {})
                id = str(source.get("capture_id", hit.get("capture_id", "")))
                if not id or id in seen:
                    continue
                seen.add(id)
                capture = session.get(Capture, id)
                if not self._eligible(session, capture, job.concept_id):
                    continue
                if source.get("revision_id", hit.get("revision_id")) != capture.current_revision_id:
                    continue
                snapshot = self._snapshot(session, capture)
                if session.get(TopicBackfillDecision, self._decision_key(job, snapshot)):
                    continue
                if id not in admitted:
                    if len(admitted) >= MAX_CANDIDATES:
                        continue
                    admitted.append(id)
                # Reconstruct the retrieved excerpt from canonical text, never a stale hit.
                start, end = source.get("body_start"), source.get("body_end")
                start = 0 if start is None else start
                end = len(snapshot["body_markdown"]) if end is None else end
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(snapshot["body_markdown"]):
                    continue
                snapshot.update(source={"capture_id": id, "revision_id": snapshot["revision_id"],
                    "node_id": None, "body_start": start, "body_end": end}, excerpt=snapshot["body_markdown"][start:end])
                result.append(snapshot)
                if len(result) >= limit:
                    break
            job.candidate_ids = admitted
            return result

    def apply_decisions(self, claimed, candidates, decisions):
        snapshots = {candidate["capture_id"]: candidate for candidate in candidates}
        ids = [item.get("capture_id") for item in decisions]
        if (len(decisions) > 5 or len(ids) != len(set(ids))
                or any(id not in snapshots for id in ids)
                or any(item.get("action") not in ("attach", "reject") for item in decisions)):
            fail("VALIDATION_ERROR", "주제 보강 판단이 후보와 일치하지 않습니다.")
        result = {"applied": 0, "rejected": 0, "skipped": 0, "status": "running"}
        with self.db.write() as session:
            job = self._active(session, claimed)
            if job is None:
                return {**result, "skipped": len(decisions), "status": "superseded"}
            for item in decisions:
                snapshot = snapshots[item["capture_id"]]
                capture = session.get(Capture, snapshot["capture_id"])
                if (snapshot["capture_id"] not in job.candidate_ids
                        or not self._eligible(session, capture, job.concept_id)
                        or capture.current_revision_id != snapshot["revision_id"]
                        or capture.state_version != snapshot["state_version"]
                        or self._snapshot(session, capture)["content_hash"] != snapshot["content_hash"]
                        or session.get(TopicBackfillDecision, self._decision_key(job, snapshot))):
                    result["skipped"] += 1
                    continue
                if item["action"] == "attach":
                    ids = self.records._concept_ids(session, capture.current_revision_id)
                    self.records._apply_update(session, capture, {}, change_kind="concept_enrichment",
                        concept_ids=[*ids, job.concept_id], reclassify=False, created_via="system")
                    result["applied"] += 1
                else:
                    result["rejected"] += 1
                session.add(TopicBackfillDecision(concept_id=job.concept_id, definition_hash=job.definition_hash,
                    capture_id=capture.id, content_hash=snapshot["content_hash"], policy_version=job.policy_version,
                    brain_id=self.brain_id, outcome=item["action"], created_at=utcnow()))
            return result

    def finish(self, claimed, status="completed", error_code=None):
        if status not in ("completed", "partial"):
            fail("VALIDATION_ERROR", "주제 보강 완료 상태가 올바르지 않습니다.")
        with self.db.write() as session:
            job = self._active(session, claimed)
            if job is None:
                return False
            if status == "completed":
                # A retry's fresh top results can omit a previously admitted
                # candidate. Completion must use durable work, not that result set.
                for capture_id in job.candidate_ids:
                    capture = session.get(Capture, capture_id)
                    if not self._eligible(session, capture, job.concept_id):
                        continue
                    snapshot = self._snapshot(session, capture)
                    if session.get(TopicBackfillDecision, self._decision_key(job, snapshot)) is None:
                        status, error_code = "partial", "INCOMPLETE_DECISIONS"
                        break
            job.status, job.completed_at, job.error_code = status, utcnow(), _error_code(error_code)
            job.lease_token = job.lease_until = None
            return True

    def defer(self, claimed, *, error_code=None, delay_seconds=30):
        if not 0 <= delay_seconds <= 3600:
            fail("VALIDATION_ERROR", "주제 보강 재시도 간격이 올바르지 않습니다.")
        with self.db.write() as session:
            job = self._active(session, claimed)
            if job is None:
                return False
            job.error_code = _error_code(error_code)
            if job.call_count >= MAX_CALLS or job.attempt_count >= MAX_ATTEMPTS:
                job.status, job.completed_at = "partial", utcnow()
            elif job.error_code in ACTION_REQUIRED_MODEL_ERRORS:
                job.status, job.completed_at = "failed", utcnow()
            else:
                job.status, job.available_at = "pending", _later(delay_seconds)
            job.lease_token = job.lease_until = None
            return True
