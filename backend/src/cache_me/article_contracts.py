"""Input and output contracts for authored learning articles."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, HttpUrl, field_validator

from .outputs import OutputModel, SourceView
from .schemas import InputModel, SourceRef, nonblank, unique, validate_body


class RecordCitation(InputModel):
    kind: Literal["record"]
    source: SourceRef


class ExternalCitation(InputModel):
    kind: Literal["external"]
    title: str
    url: HttpUrl
    note: str

    _text = field_validator("title", "note")(nonblank)


Citation = Annotated[RecordCitation | ExternalCitation, Field(discriminator="kind")]


class CreateArticleInput(InputModel):
    request_id: UUID
    title: str
    summary: str
    body_markdown: str
    citations: list[Citation]
    topics: list[str] = Field(default_factory=list)

    _title = field_validator("title")(nonblank)
    _body = field_validator("body_markdown")(validate_body)

    @field_validator("summary")
    @classmethod
    def one_line_summary(cls, value: str) -> str:
        if len(value.splitlines()) != 1:
            raise ValueError("article summary must be one line")
        return nonblank(value).strip()

    @field_validator("topics")
    @classmethod
    def topic_names(cls, value: list[str]) -> list[str]:
        return unique([nonblank(name).strip() for name in value])


class UpdateArticleInput(CreateArticleInput):
    article_id: UUID
    expected_revision_id: UUID
    topics: list[str]


class ArticleSummary(OutputModel):
    id: UUID
    title: str
    summary: str
    topics: list[str]
    created_at: str
    updated_at: str


class ArticleView(ArticleSummary):
    revision_id: UUID
    revision_no: int = Field(ge=1)
    body_markdown: str
    citations: list[Citation]
    sources: list[SourceView]
    review_state: Literal["valid", "needs_review"]


class ArticleMutationResult(OutputModel):
    article: ArticleView
    request_id: UUID
    replayed: bool
