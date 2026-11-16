"""SQLite canonical storage. Large text is kept only in immutable revisions."""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LocalBrain(Base):
    __tablename__ = "local_brain"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[str]
    active_index_build_id: Mapped[str | None] = mapped_column(String, nullable=True)
    __table_args__ = (ForeignKeyConstraint(["active_index_build_id", "id"], ["index_builds.id", "index_builds.brain_id"], deferrable=True, initially="DEFERRED"),)


class Capture(Base):
    __tablename__ = "captures"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str] = mapped_column(ForeignKey("local_brain.id"), index=True)
    current_revision_id: Mapped[str]
    visibility: Mapped[str] = mapped_column(default="public")
    deleted_at: Mapped[str | None]
    state_version: Mapped[int] = mapped_column(default=1)
    index_generation: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str]
    updated_at: Mapped[str]
    __table_args__ = (
        UniqueConstraint("id", "brain_id"),
        ForeignKeyConstraint(["current_revision_id", "id", "brain_id"], ["capture_revisions.id", "capture_revisions.capture_id", "capture_revisions.brain_id"], deferrable=True, initially="DEFERRED", name="fk_capture_current_revision"),
        CheckConstraint("visibility IN ('public','private')"),
        CheckConstraint("state_version >= 1 AND index_generation >= 1"),
    )


class CaptureRevision(Base):
    __tablename__ = "capture_revisions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str]
    capture_id: Mapped[str]
    revision_no: Mapped[int]
    title: Mapped[str | None]
    body_markdown: Mapped[str] = mapped_column(Text)
    concept_hints: Mapped[list] = mapped_column(JSON, default=list)
    completion_state: Mapped[str | None]
    event_time: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    node_status: Mapped[str]
    change_kind: Mapped[str]
    review_reason: Mapped[str | None]
    created_via: Mapped[str]
    created_at: Mapped[str]
    __table_args__ = (
        ForeignKeyConstraint(["capture_id", "brain_id"], ["captures.id", "captures.brain_id"], deferrable=True, initially="DEFERRED"),
        UniqueConstraint("id", "capture_id", "brain_id"), UniqueConstraint("id", "brain_id"), UniqueConstraint("capture_id", "revision_no"),
        CheckConstraint("revision_no >= 1 AND length(trim(body_markdown)) > 0"),
        CheckConstraint("completion_state IS NULL OR completion_state IN ('incomplete','completed')"),
        CheckConstraint("node_status IN ('absent','current','stale')"),
        CheckConstraint("change_kind IN ('create','edit','merge','completion_change','source_review','concept_enrichment')"),
        CheckConstraint("created_via IN ('web','mcp','import','system')"),
        CheckConstraint("change_kind != 'source_review' OR (review_reason IS NOT NULL AND length(trim(review_reason)) > 0)"),
    )


class RevisionKind(Base):
    # Keep all historical values in the SQLite CHECK: revisions are immutable.
    # Public reads and new writes use the six canonical kinds in record_kinds.
    __tablename__ = "revision_kinds"
    revision_id: Mapped[str] = mapped_column(ForeignKey("capture_revisions.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(primary_key=True)
    __table_args__ = (CheckConstraint("kind IN ('knowledge','procedure','context','episode','reflection','idea','decision','plan','artifact')"),)


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str]
    revision_id: Mapped[str]
    ordinal: Mapped[int]
    kind: Mapped[str]
    body_start: Mapped[int]
    body_end: Mapped[int]
    label: Mapped[str | None]
    origin: Mapped[str]
    verification_state: Mapped[str]
    verification_note: Mapped[str | None]
    concept_hints: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (
        ForeignKeyConstraint(["revision_id", "brain_id"], ["capture_revisions.id", "capture_revisions.brain_id"]),
        UniqueConstraint("revision_id", "ordinal"), UniqueConstraint("id", "revision_id", "brain_id"), UniqueConstraint("id", "brain_id"),
        CheckConstraint("body_start >= 0 AND body_end > body_start AND ordinal >= 0"),
        CheckConstraint("kind IN ('explanation','interpretation','hypothesis','question','event','emotion','proposal','decision','action','result')"),
        CheckConstraint("origin IN ('user_report','user_interpretation','ai_explanation','unspecified')"),
        CheckConstraint("verification_state IN ('unknown','unverified','verified')"),
        CheckConstraint("verification_state != 'verified' OR (verification_note IS NOT NULL AND length(trim(verification_note)) > 0)"),
    )


class Concept(Base):
    __tablename__ = "concepts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str] = mapped_column(ForeignKey("local_brain.id"), index=True)
    name: Mapped[str]
    description: Mapped[str | None]
    state_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str]
    updated_at: Mapped[str]
    __table_args__ = (UniqueConstraint("id", "brain_id"), CheckConstraint("length(trim(name)) > 0 AND state_version >= 1"))


class ConceptAlias(Base):
    __tablename__ = "concept_aliases"
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), primary_key=True)
    alias: Mapped[str] = mapped_column(primary_key=True)
    __table_args__ = (CheckConstraint("length(trim(alias)) > 0"),)


class RevisionConcept(Base):
    __tablename__ = "revision_concepts"
    revision_id: Mapped[str] = mapped_column(primary_key=True)
    concept_id: Mapped[str] = mapped_column(primary_key=True)
    brain_id: Mapped[str]
    __table_args__ = (
        ForeignKeyConstraint(["revision_id", "brain_id"], ["capture_revisions.id", "capture_revisions.brain_id"]),
        ForeignKeyConstraint(["concept_id", "brain_id"], ["concepts.id", "concepts.brain_id"]),
    )


class NodeConcept(Base):
    __tablename__ = "node_concepts"
    node_id: Mapped[str] = mapped_column(primary_key=True)
    concept_id: Mapped[str] = mapped_column(primary_key=True)
    brain_id: Mapped[str]
    __table_args__ = (
        ForeignKeyConstraint(["node_id", "brain_id"], ["knowledge_nodes.id", "knowledge_nodes.brain_id"]),
        ForeignKeyConstraint(["concept_id", "brain_id"], ["concepts.id", "concepts.brain_id"]),
    )


class ProvenanceLink(Base):
    __tablename__ = "provenance_links"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str]
    derived_revision_id: Mapped[str]
    source_capture_id: Mapped[str]
    source_revision_id: Mapped[str]
    source_node_id: Mapped[str | None]
    source_body_start: Mapped[int | None]
    source_body_end: Mapped[int | None]
    __table_args__ = (
        ForeignKeyConstraint(["derived_revision_id", "brain_id"], ["capture_revisions.id", "capture_revisions.brain_id"]),
        ForeignKeyConstraint(["source_revision_id", "source_capture_id", "brain_id"], ["capture_revisions.id", "capture_revisions.capture_id", "capture_revisions.brain_id"]),
        ForeignKeyConstraint(["source_node_id", "source_revision_id", "brain_id"], ["knowledge_nodes.id", "knowledge_nodes.revision_id", "knowledge_nodes.brain_id"]),
        CheckConstraint("(source_body_start IS NULL AND source_body_end IS NULL) OR (source_body_start IS NOT NULL AND source_body_end IS NOT NULL AND source_body_start >= 0 AND source_body_end > source_body_start)"),
    )


class Relation(Base):
    __tablename__ = "relations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str] = mapped_column(ForeignKey("local_brain.id"))
    relation_type: Mapped[str]
    source_capture_id: Mapped[str]
    source_revision_id: Mapped[str]
    source_node_id: Mapped[str | None]
    source_body_start: Mapped[int | None]
    source_body_end: Mapped[int | None]
    target_capture_id: Mapped[str]
    target_revision_id: Mapped[str]
    target_node_id: Mapped[str | None]
    target_body_start: Mapped[int | None]
    target_body_end: Mapped[int | None]
    evidence_capture_id: Mapped[str]
    evidence_revision_id: Mapped[str]
    evidence_node_id: Mapped[str | None]
    evidence_body_start: Mapped[int | None]
    evidence_body_end: Mapped[int | None]
    scope_note: Mapped[str | None]
    evidence_note: Mapped[str | None]
    created_at: Mapped[str]
    withdrawn_at: Mapped[str | None]
    withdrawal_reason: Mapped[str | None]
    __table_args__ = tuple(
        constraint for prefix in ("source", "target", "evidence") for constraint in (
            ForeignKeyConstraint([f"{prefix}_revision_id", f"{prefix}_capture_id", "brain_id"], ["capture_revisions.id", "capture_revisions.capture_id", "capture_revisions.brain_id"]),
            ForeignKeyConstraint([f"{prefix}_node_id", f"{prefix}_revision_id", "brain_id"], ["knowledge_nodes.id", "knowledge_nodes.revision_id", "knowledge_nodes.brain_id"]),
            CheckConstraint(f"({prefix}_body_start IS NULL AND {prefix}_body_end IS NULL) OR ({prefix}_body_start IS NOT NULL AND {prefix}_body_end IS NOT NULL AND {prefix}_body_start >= 0 AND {prefix}_body_end > {prefix}_body_start)"),
        )
    ) + (
        CheckConstraint("relation_type IN ('related_to','clarifies','corrects','supports','contradicts','merged_from','supersedes')"),
        CheckConstraint("(withdrawn_at IS NULL AND withdrawal_reason IS NULL) OR (withdrawn_at IS NOT NULL AND withdrawal_reason IS NOT NULL AND length(trim(withdrawal_reason)) > 0)"),
        CheckConstraint("relation_type != 'supersedes' OR (scope_note IS NOT NULL AND evidence_note IS NOT NULL AND length(trim(scope_note)) > 0 AND length(trim(evidence_note)) > 0)"),
    )


class EmbeddingProfile(Base):
    __tablename__ = "embedding_profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str] = mapped_column(ForeignKey("local_brain.id"))
    model_id: Mapped[str]
    model_revision: Mapped[str]
    configuration: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str]
    __table_args__ = (UniqueConstraint("id", "brain_id"),)


class IndexBuild(Base):
    __tablename__ = "index_builds"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str] = mapped_column(ForeignKey("local_brain.id"))
    profile_id: Mapped[str] = mapped_column(ForeignKey("embedding_profiles.id"))
    table_name: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str]
    created_at: Mapped[str]
    activated_at: Mapped[str | None]
    __table_args__ = (UniqueConstraint("id", "brain_id"), ForeignKeyConstraint(["profile_id", "brain_id"], ["embedding_profiles.id", "embedding_profiles.brain_id"]), CheckConstraint("status IN ('building','active','retired','failed')"))


class CaptureIndexState(Base):
    __tablename__ = "capture_index_states"
    capture_id: Mapped[str] = mapped_column(ForeignKey("captures.id"), primary_key=True)
    build_id: Mapped[str] = mapped_column(ForeignKey("index_builds.id"), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("capture_revisions.id"))
    index_generation: Mapped[int]
    status: Mapped[str]
    error_code: Mapped[str | None]
    updated_at: Mapped[str]
    __table_args__ = (CheckConstraint("status IN ('pending','ready','failed','excluded')"),)


class IndexJob(Base):
    __tablename__ = "index_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    capture_id: Mapped[str] = mapped_column(ForeignKey("captures.id"))
    revision_id: Mapped[str] = mapped_column(ForeignKey("capture_revisions.id"))
    profile_id: Mapped[str] = mapped_column(ForeignKey("embedding_profiles.id"))
    build_id: Mapped[str] = mapped_column(ForeignKey("index_builds.id"))
    index_generation: Mapped[int]
    operation: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[str]
    lease_token: Mapped[str | None]
    lease_until: Mapped[str | None]
    last_error_code: Mapped[str | None]
    __table_args__ = (
        UniqueConstraint("capture_id", "revision_id", "build_id", "index_generation", "operation"),
        CheckConstraint("operation IN ('upsert','remove')"),
        CheckConstraint("status IN ('pending','running','done','failed','superseded')"),
    )


class ConceptEnrichmentJob(Base):
    __tablename__ = "concept_enrichment_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brain_id: Mapped[str] = mapped_column(ForeignKey("local_brain.id"))
    capture_id: Mapped[str] = mapped_column(ForeignKey("captures.id"))
    requested_revision_id: Mapped[str] = mapped_column(ForeignKey("capture_revisions.id"))
    expected_state_version: Mapped[int]
    policy_version: Mapped[str] = mapped_column(default="concept-v1")
    status: Mapped[str] = mapped_column(default="pending", index=True)
    applied_revision_id: Mapped[str | None] = mapped_column(ForeignKey("capture_revisions.id"))
    unresolved_hints: Mapped[list] = mapped_column(JSON, default=list)
    attempt_count: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[str]
    lease_token: Mapped[str | None]
    lease_until: Mapped[str | None]
    error_code: Mapped[str | None]
    created_at: Mapped[str]
    completed_at: Mapped[str | None]
    __table_args__ = (
        UniqueConstraint("capture_id", "requested_revision_id", "expected_state_version", "policy_version"),
        CheckConstraint("status IN ('pending','running','completed','needs_review','failed','superseded')"),
    )


class MutationReceipt(Base):
    __tablename__ = "mutation_receipts"
    principal_scope: Mapped[str] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(primary_key=True)
    operation: Mapped[str]
    request_fingerprint: Mapped[str]
    capture_id: Mapped[str | None] = mapped_column(ForeignKey("captures.id"))
    concept_id: Mapped[str | None] = mapped_column(ForeignKey("concepts.id"))
    relation_id: Mapped[str | None] = mapped_column(ForeignKey("relations.id"))
    committed_revision_id: Mapped[str | None] = mapped_column(ForeignKey("capture_revisions.id"))
    committed_state_version: Mapped[int | None]
    committed_deleted_at: Mapped[str | None]
    outcome: Mapped[str]
    created_at: Mapped[str]


class DeletionConfirmation(Base):
    __tablename__ = "deletion_confirmations"
    token_hash: Mapped[str] = mapped_column(primary_key=True)
    brain_id: Mapped[str] = mapped_column(ForeignKey("local_brain.id"))
    principal_scope: Mapped[str]
    session_scope: Mapped[str]
    capture_id: Mapped[str] = mapped_column(ForeignKey("captures.id"))
    expected_revision_id: Mapped[str]
    expected_state_version: Mapped[int]
    expires_at: Mapped[str]
    used_at: Mapped[str | None]


Index("ix_provenance_revision", ProvenanceLink.derived_revision_id)
Index("ix_node_revision", KnowledgeNode.revision_id)
