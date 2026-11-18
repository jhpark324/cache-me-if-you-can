import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import { unified } from "unified";
import { visit } from "unist-util-visit";

const parser = unified().use(remarkParse).use(remarkGfm);

// Parse the original so reference definitions outside a selected span still
// resolve, and citation-shaped text in code blocks remains literal.
export function mergeArticleExcerpt(
  markdown: string,
  excerpt: string,
  bodyStart = 0,
) {
  const tree = parser.parse(markdown);
  const start = Array.from(markdown).slice(0, bodyStart).join("").length;
  const end = start + excerpt.length;
  const definitions = new Map<string, string>();
  visit(tree, "definition", (node) => {
    if (!definitions.has(node.identifier))
      definitions.set(node.identifier, node.url);
  });
  const edits: { start: number; end: number; text: string }[] = [];
  visit(tree, (node) => {
    let url;
    if (node.type === "link" || node.type === "definition") url = node.url;
    else if (node.type === "linkReference")
      url = definitions.get(node.identifier);
    const number = url?.match(/^#cite-([1-9]\d*)$/)?.[1];
    const from = node.position?.start.offset;
    const to = node.position?.end.offset;
    if (
      !number ||
      from === undefined ||
      to === undefined ||
      from < start ||
      to > end
    )
      return;
    edits.push({
      start: from - start,
      end: to - start,
      text: node.type === "definition" ? "" : `(원문 출처 ${number})`,
    });
  });
  let result = excerpt;
  for (const edit of edits.reverse()) {
    result = result.slice(0, edit.start) + edit.text + result.slice(edit.end);
  }
  return result;
}
