import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { createContext, useContext, type ReactNode } from "react";
import type { Element, Root } from "hast";

const TrailingContext = createContext<ReactNode>(undefined);

function MarkdownSpan({
  children,
  node,
}: {
  children?: ReactNode;
  node?: Element;
}) {
  const after = useContext(TrailingContext);
  return node?.properties?.dataAnswerCitations === true ? (
    after
  ) : (
    <span>{children}</span>
  );
}

// Keep renderer identities stable: opening a source panel must not replace the
// focused citation's DOM node before focus can return to it.
const components: Components = {
  span: MarkdownSpan,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  img: ({ alt }) => (
    <span className="muted">{alt ? `[이미지: ${alt}]` : "[이미지]"}</span>
  ),
};

function appendCitationSlot() {
  return (tree: Root) => {
    const slot: Element = {
      type: "element",
      tagName: "span",
      properties: { dataAnswerCitations: true },
      children: [],
    };
    const last = tree.children.at(-1);
    if (last?.type === "element" && last.tagName === "p") {
      last.children.push(slot);
    } else {
      // Lists, code and tables keep valid block structure; their citations sit
      // immediately below the block rather than being inserted into its content.
      tree.children.push({
        type: "element",
        tagName: "p",
        properties: { className: ["markdown-trailing"] },
        children: [slot],
      });
    }
  };
}

export function Markdown({
  children,
  after,
}: {
  children: string;
  after?: ReactNode;
}) {
  return (
    <TrailingContext.Provider value={after}>
      <div className="markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={after ? [appendCitationSlot] : []}
          skipHtml
          components={components}
        >
          {children}
        </ReactMarkdown>
      </div>
    </TrailingContext.Provider>
  );
}
