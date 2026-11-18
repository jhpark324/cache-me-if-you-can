"""Shared, strict HTTP/MCP domain inputs. Positions are Unicode code points."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, StrictInt, field_validator, model_validator

from .record_kinds import LEGACY_KIND_ALIASES, RecordKind, RecordKinds, normalize_record_kinds
NodeKind = Literal["explanation", "interpretation", "hypothesis", "question", "event", "emotion", "proposal", "decision", "action", "result"]
RelationType = Literal["related_to", "clarifies", "corrects", "supports", "contradicts", "merged_from", "supersedes"]
Visibility = Literal["public", "private"]
Completion = Literal["incomplete", "completed"]
Hints = Annotated[list[str], Field(max_length=20)]


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def validate_body(value: str) -> str:
    nonblank(value)
    if len(value) > 100_000 or len(value.encode("utf-8")) > 1_048_576:
        raise ValueError("body exceeds the 100000 code point / 1 MiB limit")
    return value


def validate_hints(value: list[str]) -> list[str]:
    for hint in value:
        nonblank(hint)
        if len(hint) > 100:
            raise ValueError("concept hint exceeds 100 code points")
    return value


def unique(value: list) -> list:
    if len(value) != len(set(value)):
        raise ValueError("duplicates are not allowed")
    return value


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True, revalidate_instances="always")
    _legacy_kinds: tuple[str, ...] | None = PrivateAttr(default=None)

    @model_validator(mode="wrap")
    @classmethod
    def preserve_legacy_request_kinds(cls, value, handler):
        # Old receipts hashed the original enum values. Keep those values only
        # in memory so an exact historical retry can still be verified.
        raw = value.get("kinds") if isinstance(value, dict) else getattr(value, "_legacy_kinds", None)
        legacy = tuple(raw) if isinstance(raw, (list, tuple)) and any(isinstance(kind, str) and kind in LEGACY_KIND_ALIASES for kind in raw) else None
        result = handler(value)
        if legacy is not None:
            result._legacy_kinds = legacy
        return result

    def legacy_request_payload(self):
        payload = self.model_dump(mode="json", exclude_unset=True)
        for name in payload:
            child = getattr(self, name)
            if isinstance(child, InputModel):
                payload[name] = child.legacy_request_payload()
        # A model_copy that changes kinds must never revive a stale fingerprint.
        if self._legacy_kinds is not None and normalize_record_kinds(self._legacy_kinds) == payload.get("kinds"):
            payload["kinds"] = list(self._legacy_kinds)
        return payload


class EventTime(InputModel):
    expression: str | None = None
    precision: Literal["unknown", "year", "month", "day", "instant"]
    value: str | None = None
    timezone: str | None = None

    @model_validator(mode="after")
    def validate_precision(self):
        if self.precision == "unknown":
            if self.value is not None:
                raise ValueError("unknown precision cannot have an ISO value")
            return self
        if self.value is None:
            raise ValueError("known precision requires an ISO value")
        patterns = {"year": r"\d{4}", "month": r"\d{4}-\d{2}", "day": r"\d{4}-\d{2}-\d{2}"}
        if self.precision in patterns:
            if not re.fullmatch(patterns[self.precision], self.value):
                raise ValueError("value does not match precision")
            date.fromisoformat(self.value + {"year": "-01-01", "month": "-01", "day": ""}[self.precision])
        else:
            if not re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T", self.value):
                raise ValueError("instant requires a YYYY-MM-DD calendar date")
            parsed = datetime.fromisoformat(self.value.replace("Z", "+00:00"))
            if "T" not in self.value or parsed.tzinfo is None:
                raise ValueError("instant requires an ISO datetime with offset")
        return self


class SourceRef(InputModel):
    capture_id: UUID
    revision_id: UUID
    node_id: UUID | None = None
    body_start: Annotated[StrictInt, Field(ge=0)] | None = None
    body_end: Annotated[StrictInt, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def validate_span(self):
        if (self.body_start is None) != (self.body_end is None):
            raise ValueError("both span boundaries are required")
        if self.body_start is not None and self.body_end is not None and self.body_start >= self.body_end:
            raise ValueError("span must be nonempty")
        return self


class NodeInput(InputModel):
    kind: NodeKind
    body_start: Annotated[StrictInt, Field(ge=0)]
    body_end: Annotated[StrictInt, Field(ge=1)]
    label: str | None = None
    origin: Literal["user_report", "user_interpretation", "ai_explanation", "unspecified"] = "unspecified"
    verification_state: Literal["unknown", "unverified", "verified"] = "unknown"
    verification_note: str | None = None
    concept_hints: Hints = Field(default_factory=list)

    _hints = field_validator("concept_hints")(validate_hints)

    @model_validator(mode="after")
    def validate_node(self):
        if self.body_start >= self.body_end:
            raise ValueError("Node span must be nonempty")
        if self.verification_state == "verified" and not (self.verification_note or "").strip():
            raise ValueError("verified Node requires verification_note")
        return self


class CreateCaptureInput(InputModel):
    request_id: UUID
    body_markdown: str
    title: str | None = None
    kinds: RecordKinds = Field(default_factory=list)
    visibility: Visibility = "public"
    completion_state: Completion | None = None
    event_time: EventTime | None = None
    nodes: Annotated[list[NodeInput], Field(max_length=200)] = Field(default_factory=list)
    concept_hints: Hints = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)

    _body = field_validator("body_markdown")(validate_body)
    _hints = field_validator("concept_hints")(validate_hints)
    _unique = field_validator("kinds")(unique)

    @model_validator(mode="after")
    def validate_nodes(self):
        if any(node.body_end > len(self.body_markdown) for node in self.nodes):
            raise ValueError("Node span exceeds body")
        return self


class CaptureChanges(InputModel):
    title: str | None = None
    body_markdown: str | None = None
    kinds: RecordKinds | None = None
    visibility: Visibility | None = None
    completion_state: Completion | None = None
    event_time: EventTime | None = None
    nodes: Annotated[list[NodeInput], Field(max_length=200)] | None = None
    concept_hints: Hints | None = None
    sources: list[SourceRef] | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("changes must not be empty")
        for field in ("body_markdown", "kinds", "visibility", "nodes", "concept_hints", "sources"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.body_markdown is not None:
            validate_body(self.body_markdown)
        if self.kinds is not None:
            unique(self.kinds)
        if self.concept_hints is not None:
            validate_hints(self.concept_hints)
        return self


class ExpectedVersion(InputModel):
    expected_revision_id: UUID
    expected_state_version: Annotated[StrictInt, Field(ge=1)]


class UpdateCaptureInput(ExpectedVersion):
    request_id: UUID
    capture_id: UUID
    changes: CaptureChanges


class MergeCapturesInput(ExpectedVersion):
    request_id: UUID
    target_capture_id: UUID
    sources: list[SourceRef] = Field(min_length=1)
    merged_body_markdown: str
    nodes: Annotated[list[NodeInput], Field(max_length=200)] | None = None
    concept_hints: Hints | None = None
    kinds: RecordKinds | None = None

    _body = field_validator("merged_body_markdown")(validate_body)

    @model_validator(mode="after")
    def validate_optional_values(self):
        for field in ("nodes", "concept_hints", "kinds"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.concept_hints is not None:
            validate_hints(self.concept_hints)
        if self.kinds is not None:
            unique(self.kinds)
        if self.nodes is not None and any(node.body_end > len(self.merged_body_markdown) for node in self.nodes):
            raise ValueError("Node span exceeds merged body")
        return self


class ReviewSourcesInput(ExpectedVersion):
    request_id: UUID
    capture_id: UUID
    replacement_sources: list[SourceRef]
    review_reason: str
    body_markdown: str | None = None
    nodes: Annotated[list[NodeInput], Field(max_length=200)] | None = None

    _reason = field_validator("review_reason")(nonblank)

    @field_validator("body_markdown")
    @classmethod
    def body(cls, value):
        return validate_body(value) if value is not None else None

    @model_validator(mode="after")
    def validate_optional_values(self):
        for field in ("body_markdown", "nodes"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class NodeConceptInput(InputModel):
    node_id: UUID
    concept_ids: list[UUID]
    _unique = field_validator("concept_ids")(unique)


class SetConceptsInput(ExpectedVersion):
    request_id: UUID
    capture_id: UUID
    concept_ids: list[UUID]
    node_concepts: list[NodeConceptInput] | None = None
    _unique = field_validator("concept_ids")(unique)


class RetryConceptsInput(ExpectedVersion):
    request_id: UUID
    capture_id: UUID
    job_id: UUID


class CreateConceptInput(InputModel):
    request_id: UUID
    name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    _name = field_validator("name")(nonblank)

    @field_validator("aliases")
    @classmethod
    def alias_values(cls, value):
        unique(value)
        for alias in value:
            nonblank(alias)
        return value


class ConceptChanges(InputModel):
    name: str | None = None
    description: str | None = None
    aliases: list[str] | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("changes must not be empty")
        if "name" in self.model_fields_set:
            if self.name is None:
                raise ValueError("name cannot be null")
            nonblank(self.name)
        if "aliases" in self.model_fields_set:
            if self.aliases is None:
                raise ValueError("aliases cannot be null")
            CreateConceptInput.alias_values(self.aliases)
        return self


class UpdateConceptInput(InputModel):
    request_id: UUID
    concept_id: UUID
    expected_state_version: Annotated[StrictInt, Field(ge=1)]
    changes: ConceptChanges


class RelationInput(InputModel):
    request_id: UUID
    relation_type: RelationType
    source: SourceRef
    target: SourceRef
    evidence: SourceRef
    scope_note: str | None = None
    evidence_note: str | None = None


class RetractRelationInput(InputModel):
    request_id: UUID
    relation_id: UUID
    withdrawal_reason: str
    _reason = field_validator("withdrawal_reason")(nonblank)


class PrepareDeletionInput(ExpectedVersion):
    capture_id: UUID


class DeleteCaptureInput(ExpectedVersion):
    request_id: UUID
    capture_id: UUID
    confirmation_token: str = Field(min_length=20, max_length=200)
