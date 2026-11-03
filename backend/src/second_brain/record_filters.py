"""Shared record/topic predicates for lists, retrieval and graph overviews.

The caller selects CaptureRevision (normally joined to a current Capture).
Record topics and current Node topics match independently; this does not copy
Node assignments onto their parent. Values within each filter are OR, while
different filters are AND.
"""
from sqlalchemy import or_, select

from .models import CaptureRevision, KnowledgeNode, NodeConcept, RevisionConcept, RevisionKind
from .record_kinds import storage_kinds_for_filter


def record_filter_predicates(*, kinds=(), concept_ids=()):
    predicates = []
    if kinds:
        predicates.append(select(RevisionKind.revision_id).where(
            RevisionKind.revision_id == CaptureRevision.id,
            RevisionKind.kind.in_(storage_kinds_for_filter(kinds))).exists())
    if concept_ids:
        ids = list(map(str, concept_ids))
        predicates.append(or_(
            select(RevisionConcept.revision_id).where(
                RevisionConcept.revision_id == CaptureRevision.id,
                RevisionConcept.concept_id.in_(ids)).exists(),
            select(KnowledgeNode.id).join(NodeConcept, KnowledgeNode.id == NodeConcept.node_id).where(
                KnowledgeNode.revision_id == CaptureRevision.id,
                CaptureRevision.node_status == "current",
                NodeConcept.concept_id.in_(ids)).exists()))
    return predicates


def matches_record_filters(session, revision, *, kinds=(), concept_ids=()):
    predicates = record_filter_predicates(kinds=kinds, concept_ids=concept_ids)
    if not predicates:
        return True
    return session.scalar(select(CaptureRevision.id).where(
        CaptureRevision.id == revision.id, *predicates)) is not None
