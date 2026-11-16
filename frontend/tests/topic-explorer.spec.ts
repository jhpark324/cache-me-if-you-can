import { test, expect, type Page } from "@playwright/test";

const topicId = "33333333-3333-4333-8333-000000000001";
const records = [
  "DNS 전파와 캐시 만료를 정리한 기록",
  "서비스 변경 후 도메인 연결 확인",
  "다음 주에 읽을 책",
].map((title, i) => ({
  id: `11111111-1111-4111-8111-${String(i).padStart(12, "0")}`,
  revision_id: `22222222-2222-4222-8222-${String(i).padStart(12, "0")}`,
  title,
  body_markdown: `${title}\n\n설정 변경 뒤에는 기존 캐시의 유효 기간을 확인한다.`,
  revision_no: 1,
  state_version: 1,
  kinds: ["knowledge"],
  visibility: "private",
  is_current: true,
  created_at: "2026-11-16T00:00:00Z",
  updated_at: "2026-11-16T00:00:00Z",
  index_state: { status: "ready" },
  concept_state: { status: "ready" },
  review_state: "valid",
  concepts: [],
  nodes: [],
  sources: [],
  node_status: "absent",
}));
const source = (i: number) => ({
  capture_id: records[i].id,
  revision_id: records[i].revision_id,
});
async function fixture(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const send = (data: unknown) =>
      route.fulfill({ json: { schema_version: 1, ok: true, data } });
    if (path.endsWith("/session"))
      return send({ csrf_token: "topic-explorer" });
    if (path.endsWith("/concepts"))
      return send({ items: [{ id: topicId, name: "DNS" }], next_cursor: null });
    if (path.endsWith("/captures"))
      return send({
        items: url.searchParams.has("concept_ids")
          ? records.slice(0, 2)
          : records,
        next_cursor: null,
      });
    if (path.endsWith("/graph"))
      return send({
        nodes: [
          ...records.map((record, i) => ({
            id: record.id,
            kind: "capture",
            label: record.title,
            source: source(i),
          })),
          {
            id: "part",
            kind: "node",
            label: "만료 시간 확인",
            source: {
              ...source(0),
              node_id: "part",
              body_start: 0,
              body_end: 10,
            },
          },
          {
            id: `concept:${topicId}`,
            concept_id: topicId,
            kind: "concept",
            label: "DNS",
          },
        ],
        edges: [
          {
            source: records[0].id,
            target: `concept:${topicId}`,
            kind: "has_topic",
          },
          {
            source: records[1].id,
            target: `concept:${topicId}`,
            kind: "has_topic",
          },
          { source: records[0].id, target: "part", kind: "contains" },
          { source: "part", target: `concept:${topicId}`, kind: "has_topic" },
        ],
        truncated: true,
      });
    if (path.endsWith("/sources/resolve")) {
      const ref = route.request().postDataJSON();
      const capture = records.find((record) => record.id === ref.capture_id)!;
      return send({
        source: ref,
        capture,
        text: capture.body_markdown,
        node: null,
        is_current: true,
        current_revision_id: capture.revision_id,
        review_state: "valid",
      });
    }
    return route.fulfill({
      status: 404,
      json: { ok: false, error: { code: "NOT_FOUND", message: "fixture" } },
    });
  });
}

test("주제 선택은 현재 그래프를 강조하고 중복 없는 기록에서 출처와 목록으로 이동한다", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/");
  const graph = page.locator(".graph-world");
  await expect(graph).toHaveAttribute("data-render-state", "ready");
  await graph.locator("canvas").evaluate((canvas) => {
    canvas.dataset.identity = "topic-map";
  });
  await page.getByRole("searchbox", { name: "주제 이름 찾기" }).fill("dns");
  await page
    .getByRole("button", { name: "DNS, 연결 기록 2개", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "DNS", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("이 화면의 연결 기록 2개", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".topic-record-open")).toHaveCount(2);
  await expect(
    page.getByText("기록과 세부 항목의 주제", { exact: true }),
  ).toBeVisible();
  await expect(graph.locator("canvas")).toHaveAttribute(
    "data-identity",
    "topic-map",
  );
  await expect(
    graph.locator(`[data-node-id="${records[2].id}"]`).first(),
  ).toHaveAttribute("data-topic-dimmed", "true");
  await expect(page.locator(".record-browser")).toHaveCount(0);
  await page
    .getByRole("button", { name: `${records[0].title} 출처 보기`, exact: true })
    .click();
  await expect(page.locator(".source-panel")).toContainText(
    records[0].body_markdown.split("\n\n")[1],
  );
  await page
    .getByRole("button", { name: "전체 연결 보기", exact: true })
    .click();
  await expect(page.locator(".source-panel")).toHaveCount(0);
  await page
    .getByRole("button", { name: "DNS, 연결 기록 2개", exact: true })
    .click();
  await expect(graph).toHaveAttribute("data-topic-focus", `concept:${topicId}`);
  await expect(
    graph.locator(`[data-node-id="${records[2].id}"]`).first(),
  ).toHaveAttribute("data-topic-dimmed", "true");
  await page.screenshot({ path: "test-results/topic-explorer-desktop.png" });
  await page
    .getByRole("button", { name: "이 주제의 모든 기록", exact: true })
    .click();
  await expect(page.locator(".record-browser")).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "주제", exact: true }),
  ).toHaveValue(topicId);
});

test("모바일 WebGL 대체 목록에서도 주제를 선택하고 Escape로 전체 연결로 돌아간다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: any[]
    ) {
      return type.startsWith("webgl") || type === "experimental-webgl"
        ? null
        : getContext.apply(this, [type, ...args] as any);
    } as typeof getContext;
  });
  await fixture(page);
  await page.goto("/");
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "fallback",
  );
  await page
    .locator(".graph-list")
    .getByRole("button", { name: "DNS 주제", exact: true })
    .click();
  const heading = page.getByRole("heading", { name: "DNS", exact: true });
  await expect(heading).toBeFocused();
  await expect(page.locator(".topic-record-open")).toHaveCount(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "test-results/topic-explorer-mobile.png" });
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("searchbox", { name: "주제 이름 찾기" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "주제로 살펴보기", exact: true }),
  ).toBeFocused();
  await expect(
    page.getByRole("button", { name: "주제로 살펴보기", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await page
    .getByRole("textbox", { name: "저장된 지식 검색 또는 질문" })
    .fill("DNS");
  await page.getByRole("button", { name: "검색", exact: true }).click();
  await expect(page.locator(".topic-explorer")).toHaveCount(0);
});
