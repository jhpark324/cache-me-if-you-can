import { expect, test } from "@playwright/test";
import { sourceGraphNodeId, withRetrievalGraph } from "../src/retrievalGraph";
import type { AnswerResult, GraphData } from "../src/types";

const item = (index: number, cited = false) => ({
  source: {
    capture_id: `capture-${index}`,
    revision_id: `revision-${index}`,
    body_start: 0,
    body_end: 20,
  },
  label: `검색 구간 ${index}`,
  capture_label: `기록 ${index}`,
  cited,
});

test("기존 기록 20개의 청크는 앵커 한도와 무관하게 모두 표시하고 정본 그래프를 바꾸지 않는다", () => {
  const base: GraphData = {
    nodes: Array.from({ length: 50 }, (_, index) => ({
      id: `capture-${index}`,
      kind: "capture",
      source: item(index).source,
    })),
    edges: [],
    truncated: false,
  };
  const snapshot = structuredClone(base);
  const result = withRetrievalGraph(base, {
    items: Array.from({ length: 25 }, (_, index) => item(index)),
    truncated: false,
  });
  expect(
    result.nodes.filter((node) => node.kind === "retrieved_chunk"),
  ).toHaveLength(20);
  expect(result.nodes.filter((node) => node.kind === "capture")).toHaveLength(
    50,
  );
  expect(result.edges).toHaveLength(20);
  expect(result.retrieval_truncated).toBe(true);
  expect(base).toEqual(snapshot);
  const ids = new Set(result.nodes.map((node) => node.id));
  expect(
    result.edges.every((edge) => ids.has(edge.source) && ids.has(edge.target)),
  ).toBe(true);
});

test("새 앵커는 10개까지 추가하며 인용 구간을 먼저 포함한다", () => {
  const result = withRetrievalGraph(null, {
    items: Array.from({ length: 12 }, (_, index) => item(index, index >= 10)),
    truncated: false,
  });
  expect(result.nodes.filter((node) => node.kind === "capture")).toHaveLength(
    10,
  );
  expect(
    result.nodes.filter((node) => node.kind === "retrieved_chunk"),
  ).toHaveLength(10);
  expect(result.edges).toHaveLength(10);
  expect(result.retrieval_truncated).toBe(true);
  for (const index of [10, 11]) {
    expect(
      result.nodes.some(
        (node) =>
          node.kind === "retrieved_chunk" &&
          node.source?.capture_id === `capture-${index}` &&
          node.cited,
      ),
    ).toBe(true);
  }
});

test("홈 개요 밖의 부모 기록을 선택하면 보충한 앵커가 강조된다", () => {
  const evidence = item(0, true);
  const result = withRetrievalGraph(null, {
    items: [evidence],
    truncated: false,
  });
  const anchor = result.nodes.find((node) => node.kind === "capture")!;
  expect(sourceGraphNodeId(result, anchor.source!)).toBe(anchor.id);
  const chunk = result.nodes.find((node) => node.kind === "retrieved_chunk")!;
  expect(sourceGraphNodeId(result, evidence.source)).toBe(chunk.id);
});

test("출처 전체를 기준으로 중복만 합치고 같은 Node의 다른 구간은 유지한다", () => {
  const first = {
    ...item(0),
    source: { ...item(0).source, node_id: "same-node" },
  };
  const reordered = {
    ...first,
    cited: true,
    source: {
      body_end: 20,
      body_start: 0,
      node_id: "same-node",
      revision_id: "revision-0",
      capture_id: "capture-0",
    },
  };
  const later = {
    ...first,
    source: { ...first.source, body_start: 22, body_end: 40 },
  };
  const evidence: AnswerResult["retrieval"] = {
    items: [first, reordered, later],
    truncated: false,
  };
  const result = withRetrievalGraph(null, evidence);
  const chunks = result.nodes.filter((node) => node.kind === "retrieved_chunk");
  expect(chunks).toHaveLength(2);
  expect(chunks.find((node) => node.source?.body_start === 0)?.cited).toBe(
    true,
  );
  expect(chunks.find((node) => node.source?.body_start === 22)?.cited).toBe(
    false,
  );
  expect(new Set(chunks.map((node) => node.id)).size).toBe(2);
  expect(result.nodes.filter((node) => node.kind === "capture")).toHaveLength(
    1,
  );
  expect(result.edges).toHaveLength(2);
  expect(result.retrieval_truncated).toBe(false);
});
