import type { GraphData, SourceRef } from "./types";

export type GraphNodeData = GraphData["nodes"][number];
export type GraphTopicRecord = {
  id: string;
  label: string;
  source: SourceRef;
  via: "capture" | "node" | "both";
};
export type GraphTopicGroup = {
  node: GraphNodeData;
  records: GraphTopicRecord[];
  nodeIds: Set<string>;
  edgeIds: Set<string>;
};

export function graphNodeId(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "id" in value)
    return typeof value.id === "string" ? value.id : null;
  return null;
}

// ForceGraph replaces endpoint strings with node objects after layout starts.
export function graphEdgeKey(edge: {
  id?: string;
  source?: unknown;
  target?: unknown;
  kind?: string;
}): string {
  return (
    edge.id ??
    JSON.stringify([
      graphNodeId(edge.source),
      graphNodeId(edge.target),
      edge.kind ?? "",
    ])
  );
}

/** Only connections actually present in this graph contribute to topic groups. */
export function topicGroups(data: GraphData): GraphTopicGroup[] {
  const nodes = new Map(data.nodes.map((node) => [node.id, node]));
  const captures = new Map(
    data.nodes
      .filter((node) => node.kind === "capture")
      .map((node) => [node.source?.capture_id || node.id, node]),
  );
  const groups = new Map(
    data.nodes
      .filter((node) => node.kind === "concept")
      .map((node) => [
        node.id,
        {
          node,
          records: new Map<string, GraphTopicRecord>(),
          nodeIds: new Set([node.id]),
          edgeIds: new Set<string>(),
        },
      ]),
  );
  const parents = new Map<string, { node: GraphNodeData; edgeId: string }[]>();
  for (const edge of data.edges) {
    if (edge.kind !== "contains") continue;
    const source = nodes.get(graphNodeId(edge.source) || "");
    const target = nodes.get(graphNodeId(edge.target) || "");
    if (source?.kind !== "capture" || target?.kind !== "node") continue;
    const anchors = parents.get(target.id) || [];
    anchors.push({ node: source, edgeId: graphEdgeKey(edge) });
    parents.set(target.id, anchors);
  }
  for (const edge of data.edges) {
    if (edge.kind !== "has_topic") continue;
    const source = nodes.get(graphNodeId(edge.source) || "");
    const target = nodes.get(graphNodeId(edge.target) || "");
    const topic =
      target?.kind === "concept"
        ? target
        : source?.kind === "concept"
          ? source
          : null;
    const owner = topic === target ? source : target;
    if (!topic || !owner || !["capture", "node"].includes(owner.kind)) continue;
    const group = groups.get(topic.id)!;
    group.nodeIds.add(owner.id);
    group.edgeIds.add(graphEdgeKey(edge));
    const anchors = parents.get(owner.id) || [];
    const capture =
      owner.kind === "capture"
        ? owner
        : captures.get(owner.source?.capture_id || "") || anchors[0]?.node;
    const recordSource = capture?.source || owner.source;
    if (!recordSource) continue;
    const recordId = recordSource.capture_id;
    if (capture) {
      group.nodeIds.add(capture.id);
      for (const anchor of anchors)
        if (anchor.node.id === capture.id) group.edgeIds.add(anchor.edgeId);
    }
    const via = owner.kind === "capture" ? "capture" : "node";
    const previous = group.records.get(recordId);
    if (previous) {
      if (previous.via !== via) previous.via = "both";
      if (capture?.source) previous.source = capture.source;
    } else {
      group.records.set(recordId, {
        id: recordId,
        label:
          capture?.label ||
          capture?.name ||
          owner.capture_label ||
          "제목 없는 기록",
        source: recordSource,
        via,
      });
    }
  }
  return [...groups.values()]
    .map((group) => ({
      ...group,
      records: [...group.records.values()].sort(
        (a, b) =>
          a.label.localeCompare(b.label, "ko") || a.id.localeCompare(b.id),
      ),
    }))
    .sort(
      (a, b) =>
        b.records.length - a.records.length ||
        (a.node.label || a.node.name || "").localeCompare(
          b.node.label || b.node.name || "",
          "ko",
        ) ||
        a.node.id.localeCompare(b.node.id),
    );
}
