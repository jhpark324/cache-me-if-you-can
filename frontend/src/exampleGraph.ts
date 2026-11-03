import type { GraphData } from "./types";
// Frontend-only illustration, shown only after choosing “예시 보기”. No SourceRefs or API writes.
export const exampleGraph: GraphData = {
  nodes: [
    { id: "example-study", kind: "concept", label: "배우고 이해하기" },
    { id: "example-daily", kind: "concept", label: "나를 돌아보기" },
    { id: "example-build", kind: "concept", label: "만들고 연결하기" },
    {
      id: "example-1",
      kind: "capture",
      label: "내 언어로 설명하는 공부",
      kinds: ["knowledge"],
    },
    {
      id: "example-2",
      kind: "capture",
      label: "배움이 오래 남는 질문",
      kinds: ["knowledge"],
    },
    {
      id: "example-3",
      kind: "capture",
      label: "작은 성취를 기록하는 일",
      kinds: ["episode"],
    },
    {
      id: "example-4",
      kind: "capture",
      label: "오늘 산책에서 떠오른 생각",
      kinds: ["episode"],
    },
    {
      id: "example-5",
      kind: "capture",
      label: "기억을 연결하는 도구",
      kinds: ["idea"],
    },
    {
      id: "example-6",
      kind: "capture",
      label: "작게 시작하기로 한 결정",
      kinds: ["decision"],
    },
    {
      id: "example-7",
      kind: "capture",
      label: "다음 주에 시도할 것",
      kinds: ["idea"],
    },
    { id: "example-8", kind: "node", label: "다시 꺼내 볼 수 있는 생각" },
  ],
  edges: [
    ["example-1", "example-study"],
    ["example-2", "example-study"],
    ["example-3", "example-daily"],
    ["example-4", "example-daily"],
    ["example-5", "example-build"],
    ["example-6", "example-build"],
    ["example-7", "example-build"],
    ["example-8", "example-5"],
    ["example-1", "example-5"],
    ["example-3", "example-7"],
    ["example-2", "example-8"],
  ].map(([source, target]) => ({ source, target, kind: "example" })),
  truncated: false,
};
