import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import { Button } from "@astryxdesign/core/Button";
import { HStack } from "@astryxdesign/core/HStack";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { ArrowLeft, ArrowUpRight } from "lucide-react";
import { ApiError, api, errorText } from "./api";
import { ArticleBody } from "./ArticleBody";
import type { ArticleDocument, ArticleSummary, Page } from "./types";
import { ErrorMessage, Loading } from "./ui";

interface ArticleWorkspaceProps {
  articleId: string | null;
  onOpenArticle: (id: string) => void;
  onBack: () => void;
}

function navigate(
  event: MouseEvent<HTMLAnchorElement>,
  onNavigate: () => void,
) {
  if (
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  )
    return;
  event.preventDefault();
  onNavigate();
}

const publicationDate = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "long",
  day: "numeric",
});

function ArticleDate({ value }: { value: string }) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : (
    <time className="article-date" dateTime={value}>
      {publicationDate.format(date)}
    </time>
  );
}

function ArticleLibrary({ onOpen }: { onOpen: (id: string) => void }) {
  const [rows, setRows] = useState<ArticleSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  const load = useCallback(async (cursor: string | null) => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setLoading(true);
    setError("");
    if (cursor === null) {
      setNextCursor(null);
      setRows([]);
    }
    const listPath = "/articles";
    try {
      let page: Page<ArticleSummary>;
      try {
        page = await api(
          cursor
            ? listPath + "?cursor=" + encodeURIComponent(cursor)
            : listPath,
          { signal: controller.signal },
        );
      } catch (reason) {
        if (
          controller.signal.aborted ||
          !cursor ||
          !(reason instanceof ApiError) ||
          reason.code !== "CURSOR_STALE"
        )
          throw reason;
        cursor = null;
        setNextCursor(null);
        setRows([]);
        page = await api(listPath, { signal: controller.signal });
      }
      if (controller.signal.aborted) return;
      setRows((previous) => {
        const byId = new Map(
          (cursor ? previous : []).map((row) => [row.id, row]),
        );
        for (const row of page.items) byId.set(row.id, row);
        return [...byId.values()];
      });
      setNextCursor(page.next_cursor);
    } catch (reason) {
      if (!controller.signal.aborted) setError(errorText(reason));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load(null);
    return () => pending.current?.abort();
  }, [load]);
  return (
    <section
      aria-labelledby="article-library-title"
      className="article-workspace"
    >
      <VStack className="article-shelf" gap={8}>
        <Heading
          level={1}
          className="article-page-title"
          id="article-library-title"
        >
          아티클
        </Heading>
        {rows.length > 0 && (
          <ul className="article-rows">
            {rows.map((row) => (
              <li key={row.id}>
                <a
                  className="article-row"
                  href={"#article/" + encodeURIComponent(row.id)}
                  onClick={(event) => navigate(event, () => onOpen(row.id))}
                  aria-labelledby={"article-row-" + row.id}
                >
                  <VStack gap={2}>
                    <HStack
                      gap={2}
                      className="article-row-meta"
                      vAlign="center"
                    >
                      <ArticleDate value={row.created_at} />
                      {row.topics.length > 0 && (
                        <Text
                          type="supporting"
                          color="secondary"
                          className="article-topics"
                        >
                          {row.topics.join(" · ")}
                        </Text>
                      )}
                    </HStack>
                    <Heading level={2} id={"article-row-" + row.id}>
                      {row.title || "제목 없는 아티클"}
                    </Heading>
                    <Text as="p" color="secondary">
                      {row.summary}
                    </Text>
                  </VStack>
                  <ArrowUpRight size="1.15em" aria-hidden="true" />
                </a>
              </li>
            ))}
          </ul>
        )}
        {!rows.length && !error && !loading && (
          <VStack className="article-empty" gap={2}>
            <Heading level={2}>아직 등록한 아티클이 없습니다</Heading>
            <Text as="p" color="secondary">
              Codex에 공부한 주제를 아티클로 작성해 달라고 요청해 보세요.
            </Text>
          </VStack>
        )}
        {loading && <Loading text="아티클을 불러오는 중…" />}
        {error && <ErrorMessage error={error} />}
        {!loading && (error || nextCursor) && (
          <Button
            variant="secondary"
            label={error ? "아티클 다시 불러오기" : "아티클 더 보기"}
            onClick={() => void load(nextCursor)}
          />
        )}
      </VStack>
    </section>
  );
}

function ArticleReader({
  articleId,
  onBack,
}: {
  articleId: string;
  onBack: () => void;
}) {
  const [article, setArticle] = useState<ArticleDocument | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setArticle(null);
    api<ArticleDocument>("/articles/" + encodeURIComponent(articleId), {
      signal: controller.signal,
    }).then(
      (item) => {
        if (!controller.signal.aborted) setArticle(item);
      },
      (reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof ApiError && reason.code === "NOT_FOUND"
              ? "이 주소에서 등록된 아티클을 찾을 수 없습니다."
              : errorText(reason),
          );
      },
    );
    return () => controller.abort();
  }, [articleId, attempt]);
  useEffect(() => {
    if (article || error) heading.current?.focus({ preventScroll: true });
  }, [article, error]);

  return (
    <section className="article-workspace" aria-label="아티클 읽기">
      <VStack className="article-reader" gap={8}>
        <a
          href="#articles"
          className="article-back"
          onClick={(event) => navigate(event, onBack)}
        >
          <ArrowLeft size="1em" aria-hidden="true" /> 아티클 목록으로
        </a>
        {article ? (
          <article aria-labelledby="article-title">
            <VStack className="article-intro" gap={3}>
              <ArticleDate value={article.created_at} />
              <Heading
                level={1}
                id="article-title"
                className="article-page-title"
                tabIndex={-1}
                ref={heading}
              >
                {article.title || "제목 없는 아티클"}
              </Heading>
              <Text as="p" className="article-summary" color="secondary">
                {article.summary}
              </Text>
            </VStack>
            <ArticleBody article={article} />
          </article>
        ) : error ? (
          <VStack gap={3}>
            <Heading level={1} tabIndex={-1} ref={heading}>
              아티클을 열 수 없어요
            </Heading>
            <ErrorMessage error={error} />
            <Button
              variant="secondary"
              label="아티클 다시 불러오기"
              onClick={() => setAttempt((n) => n + 1)}
            />
          </VStack>
        ) : (
          <Loading text="아티클을 불러오는 중…" />
        )}
      </VStack>
    </section>
  );
}

export function ArticleWorkspace({
  articleId,
  onOpenArticle,
  onBack,
}: ArticleWorkspaceProps) {
  return articleId === null ? (
    <ArticleLibrary onOpen={onOpenArticle} />
  ) : (
    <ArticleReader key={articleId} articleId={articleId} onBack={onBack} />
  );
}

export default ArticleWorkspace;
