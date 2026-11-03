import type { AnswerResult, GraphData, SourceRef } from "./types";

const EMPTY_GRAPH: GraphData = { nodes: [], edges: [], truncated: false };

export function retrievalNodeId(source: SourceRef) {
  return `retrieval:${JSON.stringify([
    source.capture_id,
    source.revision_id,
    source.node_id ?? null,
    source.body_start ?? null,
    source.body_end ?? null,
  ])}`;
}

/** Request-local evidence only; never changes the canonical graph. */
export function withRetrievalGraph(
  base: GraphData | null,
  retrieval?: AnswerResult["retrieval"],
): GraphData {
  const original = base ?? EMPTY_GRAPH;
  if (!retrieval) return original;
  if (!retrieval.items.length)
    return retrieval.truncated
      ? { ...original, retrieval_truncated: true }
      : original;
  const nodes = original.nodes.slice(0, 50);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = original.edges
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    .slice(0, 100);
  let addedAnchors = 0;
  const chunks = new Map<string, GraphData["nodes"][number]>();
  let truncated = retrieval.truncated;
  // In a bounded view, keep the final answer's citations before unused evidence.
  for (const item of [...retrieval.items].sort(
    (a, b) => Number(b.cited) - Number(a.cited),
  )) {
    const id = retrievalNodeId(item.source);
    const duplicate = chunks.get(id);
    if (duplicate) {
      duplicate.cited ||= item.cited;
      continue;
    }
    const captureId = item.source.capture_id;
    let parent = nodes.find(
      (node) =>
        node.kind === "capture" &&
        (node.id === captureId || node.source?.capture_id === captureId),
    );
    if (chunks.size >= 20 || (!parent && addedAnchors >= 10)) {
      truncated = true;
      continue;
    }
    if (!parent) {
      addedAnchors++;
      parent = {
        id: `retrieval-capture:${captureId}`,
        kind: "capture",
        label: item.capture_label || "제목 없는 기록",
        source: { capture_id: captureId, revision_id: item.source.revision_id },
      };
      nodes.push(parent);
    }
    const chunk = {
      id,
      kind: "retrieved_chunk",
      label: item.label || "검색한 내용",
      capture_label: item.capture_label || "제목 없는 기록",
      source: item.source,
      cited: item.cited,
    };
    chunks.set(id, chunk);
    nodes.push(chunk);
    edges.push({
      id: `evidence:${id}`,
      source: parent.id,
      target: id,
      kind: "retrieval",
    });
  }
  return {
    nodes,
    edges,
    truncated:
      original.truncated ||
      original.nodes.length > 50 ||
      original.edges.length > 100,
    retrieval_truncated: truncated,
  };
}

export function sourceGraphNodeId(data: GraphData, source: SourceRef) {
  const id = retrievalNodeId(source);
  if (data.nodes.some((node) => node.id === id)) return id;
  if (source.node_id && data.nodes.some((node) => node.id === source.node_id))
    return source.node_id;
  return (
    data.nodes.find(
      (node) =>
        node.kind === "capture" &&
        (node.id === source.capture_id ||
          node.source?.capture_id === source.capture_id),
    )?.id || source.capture_id
  );
}
