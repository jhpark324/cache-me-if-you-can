import { Markdown } from "./Markdown";
import type { AnswerResult, SourceRef } from "./types";

function sourceKey(source: SourceRef) {
  return JSON.stringify([
    source.capture_id,
    source.revision_id,
    source.node_id ?? null,
    source.body_start ?? null,
    source.body_end ?? null,
  ]);
}

export function buildAnswerDraft(answer: AnswerResult) {
  const body = answer.parts
    .map((part) => part.text.trim())
    .filter(Boolean)
    .join("\n\n");
  return answer.parts.some((part) => part.kind === "general_explanation")
    ? `${body}\n\n> AI가 덧붙인 일반 설명이 포함된 답변입니다.`
    : body;
}

export default function AnswerResponse({
  answer,
  onOpenSource,
}: {
  answer: AnswerResult;
  onOpenSource: (source: SourceRef) => void;
}) {
  const numbers = new Map<string, number>();
  for (const source of answer.sources) {
    const key = sourceKey(source);
    if (!numbers.has(key)) numbers.set(key, numbers.size + 1);
  }
  const limitations = [
    ...new Set(
      (answer.limitations || []).map((text) => text.trim()).filter(Boolean),
    ),
  ];

  return (
    <>
      <article className="answer-prose" aria-label="AI 답변">
        {answer.parts.map((part) => {
          // Only the server's verified references create controls. Markdown text
          // such as “[99]” never becomes a fabricated citation.
          const seen = new Set<string>();
          const sources = part.sources.filter((source) => {
            const key = sourceKey(source);
            if (!numbers.has(key) || seen.has(key)) return false;
            seen.add(key);
            return true;
          });
          return (
            <div className="answer-paragraph" key={part.part_id}>
              <Markdown
                after={
                  sources.length ? (
                    <span className="answer-citations">
                      {sources.map((source) => {
                        const key = sourceKey(source);
                        const number = numbers.get(key)!;
                        return (
                          <button
                            key={key}
                            type="button"
                            className="citation"
                            aria-label={`출처 ${number} 보기`}
                            title={`출처 ${number} 보기`}
                            onClick={() => onOpenSource(source)}
                          >
                            {number}
                          </button>
                        );
                      })}
                    </span>
                  ) : undefined
                }
              >
                {part.text}
              </Markdown>
            </div>
          );
        })}
      </article>
      {limitations.length > 0 && (
        <details className="answer-scope">
          <summary aria-label="답변 범위 자세히">
            <span>확인 범위에 제한이 있어요</span>
            <span className="answer-scope-action" aria-hidden="true">
              자세히
            </span>
          </summary>
          <div className="answer-scope-notes">
            {limitations.map((note) => (
              <p key={note}>{note}</p>
            ))}
          </div>
        </details>
      )}
    </>
  );
}
