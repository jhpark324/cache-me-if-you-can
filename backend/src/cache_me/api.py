"""Thin HTTP adapter. Authentication and trusted confirmation belong to app setup."""
from __future__ import annotations

import asyncio
import inspect
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .article_contracts import (ArticleMutationResult, ArticleSummary, ArticleView,
                                CreateArticleInput, UpdateArticleInput)
from .articles import ArticleService
from .records import DomainError, HumanConfirmation, RecordService
from .outputs import (CaptureSummary, CaptureView, ConceptMutationView, ConceptView,
                      DeleteResult, DeletionPreview, MutationResult, NodeView,
                      OutputEnvelope, Page, RelationMutationView, RelationView, SourceDetail)
from .schemas import (CreateCaptureInput, CreateConceptInput, DeleteCaptureInput,
                      MergeCapturesInput, PrepareDeletionInput, RecordKinds, RelationInput,
                      RelationType, RetractRelationInput, ReviewSourcesInput, SetConceptsInput,
                      RetryConceptsInput, SourceRef, UpdateCaptureInput, UpdateConceptInput)

router = APIRouter(prefix="/api/v1")


def get_records(request: Request) -> RecordService:
    return getattr(request.state, "records", request.app.state.records)


Records = Annotated[RecordService, Depends(get_records)]


def success(data):
    return {"schema_version": 1, "ok": True, "data": data}


def check_path(path_id, payload_id):
    if str(path_id) != str(payload_id):
        raise DomainError("VALIDATION_ERROR", "경로와 요청의 식별자가 다릅니다.")


def install_error_handlers(app: FastAPI):
    @app.exception_handler(DomainError)
    async def domain_error(_request, error):
        statuses = {"NOT_FOUND": 404, "VERSION_CONFLICT": 409, "IDEMPOTENCY_CONFLICT": 409, "CURSOR_STALE": 409,
                    "CONFIRMATION_REQUIRED": 403, "CONFIRMATION_EXPIRED": 409, "CONFIRMATION_UNSUPPORTED": 409,
                    "INDEX_NOT_READY": 503, "RESULT_UNAVAILABLE": 410, "JOB_NOT_RETRYABLE": 409}
        return JSONResponse(status_code=statuses.get(error.code, 422), content={"schema_version": 1, "ok": False, "error": error.as_dict()})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        # Pydantic errors contain the submitted input by default; never echo it.
        details = {"fields": [{"location": list(item["loc"]), "type": item["type"]} for item in error.errors()]}
        return JSONResponse(status_code=422, content={"schema_version": 1, "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "요청 형식이나 범위가 올바르지 않습니다.", "retryable": False, "details": details}})


def get_articles(records: Records) -> ArticleService:
    return ArticleService(records)


Articles = Annotated[ArticleService, Depends(get_articles)]


@router.post("/articles", response_model=OutputEnvelope[ArticleMutationResult])
def article_create(data: CreateArticleInput, articles: Articles):
    return success(articles.create(data))


@router.get("/articles", response_model=OutputEnvelope[Page[ArticleSummary]])
def article_list(articles: Articles, query: str | None = None, limit: int = Query(20, ge=1, le=100), cursor: str | None = None):
    return success(articles.list(query=query, limit=limit, cursor=cursor))


@router.get("/articles/{article_id}", response_model=OutputEnvelope[ArticleView])
def article_get(article_id: UUID, articles: Articles, revision_id: UUID | None = None):
    return success(articles.get(article_id, revision_id))


@router.patch("/articles/{article_id}", response_model=OutputEnvelope[ArticleMutationResult])
def article_update(article_id: UUID, data: UpdateArticleInput, articles: Articles):
    check_path(article_id, data.article_id)
    return success(articles.update(data))


@router.post("/captures", response_model=OutputEnvelope[MutationResult])
def capture_create(data: CreateCaptureInput, records: Records):
    return success(records.create(data))


@router.get("/captures", response_model=OutputEnvelope[Page[CaptureSummary]])
def capture_list(records: Records, query: str | None = None, kinds: Annotated[RecordKinds | None, Query()] = None,
                 concept_ids: Annotated[list[UUID] | None, Query()] = None, limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
                 created_from: str | None = None, created_before: str | None = None,
                 sort: Literal["created_desc", "title_asc"] = "created_desc"):
    return success(records.list(query=query, kinds=kinds, concept_ids=concept_ids, limit=limit, cursor=cursor,
                                created_from=created_from, created_before=created_before, sort=sort))


@router.get("/captures/{capture_id}", response_model=OutputEnvelope[CaptureView])
def capture_get(capture_id: UUID, records: Records, revision_id: UUID | None = None):
    return success(records.get(capture_id, revision_id))


@router.patch("/captures/{capture_id}", response_model=OutputEnvelope[MutationResult])
def capture_update(capture_id: UUID, data: UpdateCaptureInput, records: Records):
    check_path(capture_id, data.capture_id)
    return success(records.update(data))


@router.post("/captures/{capture_id}/merge", response_model=OutputEnvelope[MutationResult])
def capture_merge(capture_id: UUID, data: MergeCapturesInput, records: Records):
    check_path(capture_id, data.target_capture_id)
    return success(records.merge(data))


@router.put("/captures/{capture_id}/concepts", response_model=OutputEnvelope[MutationResult])
def capture_set_concepts(capture_id: UUID, data: SetConceptsInput, records: Records):
    check_path(capture_id, data.capture_id)
    return success(records.set_concepts(data))


@router.post("/captures/{capture_id}/source-review", response_model=OutputEnvelope[MutationResult])
def capture_review_sources(capture_id: UUID, data: ReviewSourcesInput, records: Records):
    check_path(capture_id, data.capture_id)
    return success(records.review_sources(data))


@router.post("/captures/{capture_id}/concept-retry", response_model=OutputEnvelope[MutationResult])
async def capture_retry_concepts(capture_id: UUID, data: RetryConceptsInput, request: Request, records: Records):
    check_path(capture_id, data.capture_id)
    result = await asyncio.to_thread(records.retry_concepts, data)
    auth = getattr(request.app.state, "auth", None)
    if auth is not None and not result['replayed']:
        auth.resume_requests()
    return success(result)


@router.post("/captures/{capture_id}/deletion-preview", response_model=OutputEnvelope[DeletionPreview])
def capture_delete_prepare(capture_id: UUID, data: PrepareDeletionInput, records: Records):
    check_path(capture_id, data.capture_id)
    return success(records.prepare_delete(data))


@router.post("/captures/{capture_id}/deletion", response_model=OutputEnvelope[DeleteResult])
async def capture_delete(capture_id: UUID, data: DeleteCaptureInput, request: Request, records: Records):
    check_path(capture_id, data.capture_id)
    hook = getattr(request.app.state, "confirm_deletion", None)
    if hook is None:
        raise DomainError("CONFIRMATION_REQUIRED", "사용자 삭제 확인 경로가 연결되지 않았습니다.")
    confirmation = hook(request, data, records)
    if inspect.isawaitable(confirmation):
        confirmation = await confirmation
    if not isinstance(confirmation, HumanConfirmation):
        raise DomainError("CONFIRMATION_REQUIRED", "사용자의 명시적인 삭제 확인이 필요합니다.")
    return success(records.delete(data, confirmation=confirmation))


@router.post("/sources/resolve", response_model=OutputEnvelope[SourceDetail])
def source_get(data: SourceRef, records: Records):
    return success(records.source_get(data))


@router.get("/nodes/{node_id}", response_model=OutputEnvelope[NodeView])
def node_get(node_id: UUID, records: Records):
    return success(records.node_get(node_id))


@router.post("/concepts", response_model=OutputEnvelope[ConceptMutationView])
def concept_create(data: CreateConceptInput, records: Records):
    return success(records.concept_create(data))


@router.get("/concepts", response_model=OutputEnvelope[Page[ConceptView]])
def concept_list(records: Records, query: str | None = None, limit: int = Query(20, ge=1, le=100), cursor: str | None = None):
    return success(records.concept_list(query=query, limit=limit, cursor=cursor))


@router.get("/concepts/{concept_id}", response_model=OutputEnvelope[ConceptView])
def concept_get(concept_id: UUID, records: Records):
    return success(records.concept_get(concept_id))


@router.patch("/concepts/{concept_id}", response_model=OutputEnvelope[ConceptMutationView])
def concept_update(concept_id: UUID, data: UpdateConceptInput, records: Records):
    check_path(concept_id, data.concept_id)
    return success(records.concept_update(data))


@router.post("/relations", response_model=OutputEnvelope[RelationMutationView])
def relation_create(data: RelationInput, records: Records):
    return success(records.relation_create(data))


@router.get("/relations", response_model=OutputEnvelope[Page[RelationView]])
def relation_list(records: Records, capture_id: UUID | None = None, node_id: UUID | None = None, relation_type: RelationType | None = None,
                  direction: str = "both", limit: int = Query(20, ge=1, le=100), cursor: str | None = None):
    return success(records.relation_list(capture_id=capture_id, node_id=node_id, relation_type=relation_type, direction=direction, limit=limit, cursor=cursor))


@router.post("/relations/{relation_id}/retraction", response_model=OutputEnvelope[RelationMutationView])
def relation_retract(relation_id: UUID, data: RetractRelationInput, records: Records):
    check_path(relation_id, data.relation_id)
    return success(records.relation_retract(data))
