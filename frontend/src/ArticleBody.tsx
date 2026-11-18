import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { ArticleMarkdown } from "./ArticleMarkdown";
import { ArticleSource } from "./ArticleSource";
import { sourceKey, type ArticleDocument, type SourceView } from "./types";

function reviewNote(status?: SourceView) {
  if (status?.availability === "unavailable")
    return "인용한 기록을 더 이상 열 수 없습니다.";
  if (status?.review_state !== "needs_review") return "";
  if (status.reason === "upstream_invalid")
    return "이 기록이 인용한 출처의 재검토가 필요합니다.";
  if (status.reason === "source_changed")
    return "원래 기록이 변경되어 인용한 내용의 재검토가 필요합니다.";
  return "인용한 내용의 재검토가 필요합니다.";
}

export function ArticleBody({ article }: { article: ArticleDocument }) {
  const body = useRef<HTMLElement>(null);
  const contents = useRef<HTMLDetailsElement>(null);
  const [headings, setHeadings] = useState<HTMLHeadingElement[]>([]);
  useEffect(() => {
    // The Markdown renderer has already distinguished headings from code examples.
    setHeadings(
      Array.from(
        body.current?.querySelectorAll<HTMLHeadingElement>(
          ":scope > .markdown h2",
        ) ?? [],
      ),
    );
  }, [article.body_markdown]);
  const jumpTo = (heading: HTMLHeadingElement) => {
    if (contents.current) contents.current.open = false;
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
    heading.scrollIntoView({ block: "start" });
  };
  const [number, setNumber] = useState<number | null>(null);
  const opener = useRef<{
    trigger: HTMLElement;
    scroller: HTMLElement | null;
  } | null>(null);
  const open = (index: number, trigger: HTMLElement) => {
    const scroller = trigger.closest<HTMLElement>(".article-workspace");
    opener.current = { trigger, scroller };
    setNumber(index);
  };
  const close = useCallback(() => {
    const position = opener.current;
    const top = position?.scroller?.scrollTop;
    opener.current = null;
    setNumber(null);
    requestAnimationFrame(() => {
      if (!position?.trigger.isConnected) return;
      position.trigger.focus({ preventScroll: true });
      if (position.scroller && top !== undefined)
        position.scroller.scrollTop = top;
    });
  }, []);
  const references = new Map(
    article.sources.map((entry) => [sourceKey(entry.source), entry]),
  );
  const citations = article.citations;
  const notes = citations.map((citation) =>
    citation.kind === "record"
      ? reviewNote(references.get(sourceKey(citation.source)))
      : "",
  );
  const citation = number !== null ? citations[number - 1] : null;
  return (
    <section
      ref={body}
      className="article-body"
      data-source-open={Boolean(citation)}
      aria-label="아티클 본문"
    >
      {headings.length >= 3 && (
        <details className="article-contents" ref={contents}>
          <summary>목차</summary>
          <ol>
            {headings.map((heading, index) => (
              <li key={index}>
                <Button
                  variant="ghost"
                  label={heading.textContent || String(index + 1)}
                  onClick={() => jumpTo(heading)}
                />
              </li>
            ))}
          </ol>
        </details>
      )}
      {notes.some(Boolean) && (
        <VStack gap={1} className="article-review" aria-label="출처 상태">
          {notes.map(
            (note, index) =>
              note && (
                <Text as="p" key={index}>
                  출처 {index + 1} · {note}
                </Text>
              ),
          )}
        </VStack>
      )}
      <ArticleMarkdown
        body={article.body_markdown}
        citations={{ count: citations.length, open }}
      />
      {citation && number !== null && (
        <ArticleSource
          key={number}
          citation={citation}
          number={number}
          note={notes[number - 1]}
          unavailable={
            citation.kind === "record" &&
            references.get(sourceKey(citation.source))?.availability ===
              "unavailable"
          }
          onClose={close}
        />
      )}
    </section>
  );
}
