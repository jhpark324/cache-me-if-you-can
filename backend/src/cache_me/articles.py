"""Authored articles and their immutable, independently versioned editions."""
from __future__ import annotations

import base64
import json

from markdown_it import MarkdownIt
from sqlalchemy import func, or_, select, tuple_

from .article_contracts import CreateArticleInput, UpdateArticleInput
from .db import new_id, utcnow
from .models import Article, ArticleReceipt, ArticleRevision
from .records import RecordService, canonical, digest, fail


def validate_citation_links(body: str, count: int) -> None:
    # The reader supports CommonMark and tables. Fenced and inline code are literal.
    numbers = {str(i) for i in range(1, count + 1)}
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    for block in parser.parse(body):
        inline = block.children or []
        for index, token in enumerate(inline):
            href = token.attrGet("href") or ""
            if token.type != "link_open" or not href.startswith("#cite-"):
                continue
            number = href.removeprefix("#cite-")
            label = inline[index + 1:index + 3]
            if (number not in numbers or len(label) != 2 or label[0].type != "text"
                    or label[0].content != number or label[1].type != "link_close"):
                fail("VALIDATION_ERROR", "아티클 본문의 인용 번호와 출처 번호가 일치해야 합니다.")


def record_sources(citations):
    return [citation["source"] for citation in citations if citation["kind"] == "record"]


class ArticleService:
    def __init__(self, records: RecordService):
        self.db = records.db
        self.brain_id = records.brain_id
        self.principal_scope = records.principal_scope
        self.records = records

    def _article(self, session, article_id):
        article = session.get(Article, str(article_id))
        if article is None or article.brain_id != self.brain_id or article.deleted_at is not None:
            fail("NOT_FOUND", "아티클을 찾을 수 없습니다.")
        return article

    def _revision(self, session, article, revision_id=None):
        revision = session.get(ArticleRevision, str(revision_id or article.current_revision_id))
        if revision is None or revision.article_id != article.id:
            fail("NOT_FOUND", "아티클 버전을 찾을 수 없습니다.")
        return revision

    def _view(self, session, article, revision, sources=None):
        if sources is None:
            sources = self.records.source_statuses(session, record_sources(revision.citations))
        return {"id": article.id, "revision_id": revision.id, "revision_no": revision.revision_no,
                "title": revision.title, "summary": revision.summary, "body_markdown": revision.body_markdown,
                "citations": revision.citations, "topics": revision.topics, "sources": sources,
                "created_at": article.created_at,
                "updated_at": article.updated_at if revision.id == article.current_revision_id else revision.created_at,
                "review_state": "needs_review" if any(s["review_state"] == "needs_review" for s in sources) else "valid"}

    def get(self, article_id, revision_id=None):
        with self.db.read() as session:
            article = self._article(session, article_id)
            return self._view(session, article, self._revision(session, article, revision_id))

    def list(self, *, query=None, limit=20, cursor=None):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            fail("VALIDATION_ERROR", "limit은 1부터 100까지입니다.")
        query = (query or "").strip()
        statement = select(Article.id, Article.created_at, Article.updated_at, ArticleRevision.title,
                           ArticleRevision.summary, ArticleRevision.topics).join(
            ArticleRevision, ArticleRevision.id == Article.current_revision_id
        ).where(Article.brain_id == self.brain_id, Article.deleted_at.is_(None))
        if query:
            topics = func.json_each(ArticleRevision.topics).table_valued("value")
            topic_match = select(1).select_from(topics).where(topics.c.value.icontains(query, autoescape=True)).exists()
            statement = statement.where(or_(ArticleRevision.title.icontains(query, autoescape=True),
                                            ArticleRevision.summary.icontains(query, autoescape=True), topic_match))
        filter_key = digest(["articles", self.brain_id, query])
        if cursor:
            try:
                saved_filter, created_at, article_id = json.loads(base64.urlsafe_b64decode(cursor))
                if saved_filter != filter_key or not isinstance(created_at, str) or not isinstance(article_id, str):
                    raise ValueError()
            except (TypeError, ValueError, UnicodeError):
                fail("CURSOR_STALE", "아티클 목록을 처음부터 다시 조회해 주세요.")
            statement = statement.where(tuple_(Article.created_at, Article.id) < (created_at, article_id))
        with self.db.read() as session:
            rows = session.execute(statement.order_by(Article.created_at.desc(), Article.id.desc()).limit(limit + 1)).mappings().all()
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            bookmark = canonical([filter_key, last["created_at"], last["id"]])
            next_cursor = base64.urlsafe_b64encode(bookmark.encode()).decode()
        return {"items": [dict(row) for row in rows[:limit]], "next_cursor": next_cursor}

    def create(self, data: CreateArticleInput):
        return self._save(CreateArticleInput.model_validate(data))

    def update(self, data: UpdateArticleInput):
        return self._save(UpdateArticleInput.model_validate(data))

    def _save(self, data: CreateArticleInput | UpdateArticleInput):
        operation = "article_update" if isinstance(data, UpdateArticleInput) else "article_create"
        request_id = str(data.request_id)
        payload = data.model_dump(mode="json")
        fingerprint = digest(payload)
        validate_citation_links(data.body_markdown, len(data.citations))
        with self.db.write() as session:
            receipt = session.get(ArticleReceipt, (self.principal_scope, request_id))
            if receipt:
                if receipt.operation != operation or receipt.request_fingerprint != fingerprint:
                    fail("IDEMPOTENCY_CONFLICT", "같은 request_id에 다른 요청을 사용할 수 없습니다.")
                article = self._article(session, receipt.article_id)
                revision = self._revision(session, article, receipt.committed_revision_id)
                return {"article": self._view(session, article, revision), "request_id": request_id, "replayed": True}

            now, revision_id = utcnow(), new_id()
            existing_sources = set()
            if isinstance(data, UpdateArticleInput):
                article = self._article(session, data.article_id)
                if article.current_revision_id != str(data.expected_revision_id):
                    fail("VERSION_CONFLICT", "아티클이 변경되었습니다. 최신 버전을 확인해 주세요.",
                         details={"revision_id": article.current_revision_id})
                previous = self._revision(session, article)
                revision_no = previous.revision_no + 1
                existing_sources = {canonical(source) for source in record_sources(previous.citations)}
                article.current_revision_id, article.updated_at = revision_id, now
            else:
                article = Article(id=new_id(), brain_id=self.brain_id, current_revision_id=revision_id,
                                  created_at=now, updated_at=now)
                session.add(article)
                revision_no = 1

            # Keep the edition's pinned evidence even when its source later changes.
            # A newly added reference must resolve to verifiable record content at commit.
            sources = self.records.source_statuses(session, record_sources(payload["citations"]))
            if any(status["review_state"] != "valid" and canonical(status["source"]) not in existing_sources
                   for status in sources):
                fail("INVALID_SOURCE_REF", "새로 추가하는 출처는 현재 검증 가능한 기록을 가리켜야 합니다.")
            session.flush()
            revision = ArticleRevision(id=revision_id, article_id=article.id, revision_no=revision_no,
                                       title=payload["title"], summary=payload["summary"], body_markdown=payload["body_markdown"],
                                       topics=payload["topics"], citations=payload["citations"], created_at=now)
            session.add(revision)
            session.flush()
            session.add(ArticleReceipt(principal_scope=self.principal_scope, request_id=request_id, operation=operation,
                                       request_fingerprint=fingerprint, article_id=article.id, committed_revision_id=revision.id))
            return {"article": self._view(session, article, revision, sources), "request_id": request_id, "replayed": False}
