import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useMediaQuery } from "@astryxdesign/core/hooks";
import { ExternalLink, X } from "lucide-react";
import { errorText, post } from "./api";
import { ArticleMarkdown } from "./ArticleMarkdown";
import { Markdown } from "./Markdown";
import { ErrorMessage, Loading, Tool } from "./ui";
import type { ArticleCitation, SourceDetail, SourceRef } from "./types";

function RecordExcerpt({ source, note }: { source: SourceRef; note: string }) {
  const [detail, setDetail] = useState<SourceDetail | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setDetail(null);
    post<SourceDetail>("/sources/resolve", source, controller.signal).then(
      (result) => {
        if (!controller.signal.aborted) setDetail(result);
      },
      (reason) => {
        if (!controller.signal.aborted) setError(errorText(reason));
      },
    );
    return () => controller.abort();
  }, [source, attempt]);
  if (error) {
    return (
      <VStack gap={3}>
        <ErrorMessage error={error} />
        <Button
          variant="secondary"
          label="출처 다시 불러오기"
          onClick={() => setAttempt((n) => n + 1)}
        />
      </VStack>
    );
  }
  if (!detail) return <Loading text="인용한 기록을 불러오는 중…" />;
  const excerpt = detail.text !== detail.capture.body_markdown;
  const preview = (text: string) =>
    detail.capture.article ? (
      <ArticleMarkdown body={text} />
    ) : (
      <Markdown>{text}</Markdown>
    );
  return (
    <VStack gap={4}>
      <VStack gap={1}>
        <Text type="supporting" color="secondary">
          {detail.is_current ? "현재 저장본" : "과거 저장본"} · 버전{" "}
          {detail.capture.revision_no}
        </Text>
        <Heading level={3}>{detail.capture.title || "제목 없는 기록"}</Heading>
      </VStack>
      {(note || detail.review_state === "needs_review") && (
        <Text as="p" color="secondary">
          {note || "이 출처는 재검토가 필요합니다."}
        </Text>
      )}
      {excerpt && <Heading level={4}>참조한 부분</Heading>}
      {preview(detail.text)}
      {excerpt && (
        <details>
          <summary>기록 전체 보기</summary>
          {preview(detail.capture.body_markdown)}
        </details>
      )}
    </VStack>
  );
}

function originalUrl(url: string) {
  try {
    const parsed = new URL(url);
    return ["https:", "http:"].includes(parsed.protocol) ? parsed : null;
  } catch {
    return null;
  }
}

export function ArticleSource({
  citation,
  number,
  note,
  unavailable,
  onClose,
}: {
  citation: ArticleCitation;
  number: number;
  note: string;
  unavailable: boolean;
  onClose: () => void;
}) {
  const mobile = useMediaQuery("(max-width: 70em)");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (mobile) return;
    heading.current?.focus({ preventScroll: true });
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [mobile, number, onClose]);

  const url = citation.kind === "external" ? originalUrl(citation.url) : null;
  const content =
    citation.kind === "record" ? (
      unavailable ? (
        <ErrorMessage error={note} />
      ) : (
        <RecordExcerpt source={citation.source} note={note} />
      )
    ) : (
      <VStack gap={4}>
        <VStack gap={1}>
          {url && (
            <Text color="secondary" type="supporting">
              {url.hostname}
            </Text>
          )}
          <Heading level={3}>{citation.title}</Heading>
        </VStack>
        <Text as="p" className="article-source-note">
          {citation.note}
        </Text>
        {url && (
          <Button
            href={url.href}
            target="_blank"
            rel="noopener noreferrer"
            variant="secondary"
            icon={<ExternalLink />}
            label="원문 열기"
          />
        )}
      </VStack>
    );
  const title = `출처 ${number}`;
  const close = (
    <Tool label="출처 닫기" onClick={onClose}>
      <X />
    </Tool>
  );
  if (mobile) {
    return (
      <Dialog
        isOpen
        onOpenChange={(open) => {
          if (!open) onClose();
        }}
        purpose="info"
        className="article-source-mobile"
        width="min(36rem, 94vw)"
        maxHeight="88dvh"
        aria-describedby={undefined}
      >
        <DialogHeader title={title} endContent={close} />
        <VStack className="article-source-scroll" isScrollable minHeight={0}>
          {content}
        </VStack>
      </Dialog>
    );
  }
  return createPortal(
    <aside
      className="article-source-panel"
      role="region"
      aria-labelledby="article-source-title"
    >
      <HStack
        className="article-source-heading"
        vAlign="center"
        hAlign="between"
      >
        <Heading
          level={2}
          ref={heading}
          tabIndex={-1}
          id="article-source-title"
        >
          {title}
        </Heading>
        {close}
      </HStack>
      <VStack className="article-source-scroll" isScrollable minHeight={0}>
        {content}
      </VStack>
    </aside>,
    document.body,
  );
}
