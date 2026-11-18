"""Validated response contracts shared by OpenAPI and MCP output schemas."""
from __future__ import annotations

from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_serializer, model_validator

from .schemas import Article, Completion, EventTime, NodeInput, RecordKind, RelationType, SourceRef, Visibility

T = TypeVar("T")


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DomainErrorView(OutputModel):
    code: str
    message: str
    retryable: bool
    details: dict | None = None


class OutputEnvelope(OutputModel, Generic[T]):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "oneOf": [
            {"properties": {"ok": {"const": True}, "data": {"not": {"type": "null"}}}, "required": ["data"], "not": {"required": ["error"]}},
            {"properties": {"ok": {"const": False}, "error": {"not": {"type": "null"}}}, "required": ["error"], "not": {"required": ["data"]}},
        ],
    })
    schema_version: Literal[1] = 1
    ok: StrictBool
    data: T | None = None
    error: DomainErrorView | None = None

    @model_validator(mode="after")
    def exclusive_payload(self):
        if self.ok:
            if "data" not in self.model_fields_set or self.data is None or "error" in self.model_fields_set:
                raise ValueError("success requires data and forbids error")
        elif "error" not in self.model_fields_set or self.error is None or "data" in self.model_fields_set:
            raise ValueError("failure requires error and forbids data")
        return self

    @model_serializer(mode="wrap")
    def serialize_branch(self, handler):
        value = handler(self)
        value.pop("error" if self.ok else "data", None)
        return value


class Page(OutputModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class IndexState(OutputModel):
    status: Literal["pending", "ready", "failed", "excluded"]
    profile_id: UUID | None
    build_id: UUID | None
    index_generation: int = Field(ge=1)
    error_code: str | None = None


class ConceptState(OutputModel):
    status: Literal["pending", "running", "ready", "failed"]
    job_id: UUID | None = None
    requested_revision_id: UUID | None = None
    applied_revision_id: UUID | None = None
    unresolved_hints: list[str] = Field(default_factory=list, description="Compatibility field; deferred candidates remain in internal job history.")
    error_code: str | None = None


class ConceptView(OutputModel):
    id: UUID
    name: str
    description: str | None
    aliases: list[str]
    state_version: int = Field(ge=1)
    created_at: str
    updated_at: str


class ConceptMutationView(ConceptView):
    request_id: UUID
    replayed: bool


class SourceView(OutputModel):
    source: SourceRef
    resolved_source: SourceRef | None
    availability: Literal["available", "unavailable"]
    review_state: Literal["valid", "needs_review"]
    reason: Literal["source_changed", "source_deleted", "upstream_invalid"] | None


class NodeView(NodeInput):
    id: UUID
    revision_id: UUID
    ordinal: int = Field(ge=0)
    text: str
    concepts: list[ConceptView]
    source: SourceRef
    review_state: Literal["valid", "needs_review"]


class CaptureView(OutputModel):
    id: UUID
    revision_id: UUID
    revision_no: int = Field(ge=1)
    is_current: bool
    state_version: int = Field(ge=1)
    title: str | None
    body_markdown: str
    article: Article | None = None
    kinds: list[RecordKind]
    visibility: Visibility
    completion_state: Completion | None
    event_time: EventTime | None
    deleted_at: None
    created_at: str
    updated_at: str
    revision_created_at: str
    index_state: IndexState
    node_status: Literal["absent", "current", "stale"]
    nodes: list[NodeView]
    concept_hints: list[str]
    concept_state: ConceptState
    concepts: list[ConceptView]
    sources: list[SourceView]
    review_state: Literal["valid", "needs_review"]
    review_reason: str | None


class CaptureSummary(OutputModel):
    id: UUID
    revision_id: UUID
    revision_no: int = Field(ge=1)
    state_version: int = Field(ge=1)
    title: str | None
    excerpt: str
    article_summary: str | None = None
    article_topics: list[str] = Field(default_factory=list)
    kinds: list[RecordKind]
    visibility: Visibility
    completion_state: Completion | None
    event_time: EventTime | None
    created_at: str
    updated_at: str
    index_state: IndexState
    node_status: Literal["absent", "current", "stale"]
    concept_state: ConceptState
    review_state: Literal["valid", "needs_review"]


class MutationResult(OutputModel):
    capture: CaptureView | None
    committed_ref: SourceRef | None
    request_id: UUID
    replayed: bool
    result_state: Literal["available", "unavailable"]
    warnings: list[str]

    @model_validator(mode="after")
    def result_availability(self):
        if self.result_state == "available" and (self.capture is None or self.committed_ref is None):
            raise ValueError("available mutation requires saved capture and reference")
        if self.result_state == "unavailable" and (self.capture is not None or self.committed_ref is not None):
            raise ValueError("unavailable mutation must not expose capture or reference")
        return self


class SourceDetail(OutputModel):
    source: SourceRef
    is_current: bool
    current_revision_id: UUID | None
    text: str
    capture: CaptureView
    node: NodeView | None
    review_state: Literal["valid", "needs_review"]


class DeletionPreview(OutputModel):
    confirmation_token: str
    capture_id: UUID
    expected_revision_id: UUID
    expected_state_version: int = Field(ge=1)
    title: str | None
    excerpt: str
    expires_at: str


class ExcludedIndexState(OutputModel):
    status: Literal["excluded"]


class DeleteResult(OutputModel):
    request_id: UUID
    capture_id: UUID
    revision_id: UUID
    state_version: int = Field(ge=1)
    deleted_at: str
    index_state: ExcludedIndexState
    replayed: bool


class RelationView(OutputModel):
    id: UUID
    relation_type: RelationType
    source: SourceRef
    target: SourceRef
    evidence: SourceRef
    scope_note: str | None
    evidence_note: str | None
    created_at: str
    withdrawn_at: str | None
    withdrawal_reason: str | None


class RelationMutationView(RelationView):
    request_id: UUID
    replayed: bool
