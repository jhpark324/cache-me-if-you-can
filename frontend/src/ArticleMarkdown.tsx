import { createContext, useContext } from "react";
import { Button } from "@astryxdesign/core/Button";
import { ArrowDown } from "lucide-react";
import type { Components } from "react-markdown";
import { Markdown } from "./Markdown";

interface CitationControls {
  count: number;
  open: (number: number, trigger: HTMLElement) => void;
}

const CitationContext = createContext<CitationControls | null>(null);

const renderers: Components = {
  a: function ArticleLink({ children, href }) {
    const citations = useContext(CitationContext);
    if (!href?.startsWith("#cite-")) {
      return (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      );
    }
    const match = /^#cite-([1-9]\d*)$/.exec(href);
    const number = Number(match?.[1]);
    if (
      !citations ||
      !match ||
      number > citations.count ||
      children !== match[1]
    ) {
      return <>{children}</>;
    }
    return (
      <Button
        className="article-citation"
        size="sm"
        variant="ghost"
        aria-label={`출처 ${number} 보기`}
        label={String(number)}
        onClick={(event) => citations.open(number, event.currentTarget)}
      />
    );
  },
  pre: ({ children, node }) => {
    const code = node?.children[0];
    if (
      code?.type !== "element" ||
      code.tagName !== "code" ||
      !Array.isArray(code.properties.className) ||
      !code.properties.className.includes("language-article-flow")
    ) {
      return <pre>{children}</pre>;
    }
    const content = code.children[0];
    if (content?.type !== "text") return <pre>{children}</pre>;
    const steps = content.value
      .split("\n")
      .map((step) => step.trim())
      .filter(Boolean);
    if (!steps.length) return null;
    const compact =
      steps.length >= 2 &&
      steps.length <= 4 &&
      steps.every((step) => [...step].length <= 20);
    return (
      <ol
        data-layout={compact ? "compact" : "vertical"}
        className="article-flow"
        aria-label="단계별 흐름"
        role="list"
      >
        {steps.map((step, index) => (
          <li key={index}>
            {index > 0 && <ArrowDown aria-hidden="true" size="1em" />}
            {step}
          </li>
        ))}
      </ol>
    );
  },
};

export function ArticleMarkdown({
  body,
  citations,
}: {
  body: string;
  citations?: CitationControls;
}) {
  return (
    <CitationContext.Provider value={citations ?? null}>
      <Markdown renderers={renderers}>{body}</Markdown>
    </CitationContext.Provider>
  );
}
