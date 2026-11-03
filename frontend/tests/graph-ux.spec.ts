import { test, expect, type Page } from "@playwright/test";
const records = Array.from({ length: 40 }, (_, i) => ({
  id: `11111111-1111-4111-8111-${String(i).padStart(12, "0")}`,
  revision_id: `22222222-2222-4222-8222-${String(i).padStart(12, "0")}`,
  title: `기억 ${String(i + 1).padStart(2, "0")} · 배운 내용을 오래 기억하고 다시 꺼내 쓰기 위한 학습 기록`,
  body_markdown: "배운 내용을 자신의 언어로 정리하고 다음 질문과 연결한다.",
  revision_no: 1,
  state_version: 1,
  kinds: ["knowledge"],
  visibility: "public",
  is_current: true,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
  index_state: { status: "ready" },
  concept_state: { status: "ready" },
  review_state: "valid",
  concepts: [],
  nodes: [],
  sources: [],
  node_status: "absent",
}));
const concepts = Array.from({ length: 10 }, (_, i) => ({
  id: `33333333-3333-4333-8333-${String(i).padStart(12, "0")}`,
  name: `학습 주제 ${i + 1}`,
}));
async function fixture(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname,
      body = route.request().postDataJSON();
    const send = (data: unknown) =>
      route.fulfill({ json: { schema_version: 1, ok: true, data } });
    if (path.endsWith("/session")) return send({ csrf_token: "graph-ux" });
    if (path.endsWith("/concepts"))
      return send({ items: concepts, next_cursor: null });
    if (path.endsWith("/captures"))
      return send({ items: records, next_cursor: null });
    if (path.endsWith("/graph"))
      return send({
        nodes: [
          ...records.map((r) => ({
            id: r.id,
            kind: "capture",
            label: r.title,
            kinds: r.kinds,
            source: { capture_id: r.id, revision_id: r.revision_id },
          })),
          ...concepts.map((c) => ({ ...c, kind: "concept", label: c.name })),
        ],
        edges: records.map((r, i) => ({
          source: r.id,
          target: concepts[i % 10].id,
        })),
        truncated: false,
      });
    if (path.endsWith("/sources/resolve")) {
      const capture = records.find((r) => r.id === body.capture_id)!;
      return send({
        source: body,
        capture,
        text: capture.body_markdown,
        is_current: true,
        current_revision_id: capture.revision_id,
        node: null,
        review_state: "valid",
      });
    }
    return route.fulfill({
      status: 404,
      json: {
        ok: false,
        error: { code: "NOT_FOUND", message: "missing fixture" },
      },
    });
  });
}
async function ready(page: Page) {
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "ready",
  );
}
const visibleCount = (page: Page) =>
  page
    .locator(".graph-world .graph-label-layer > span")
    .evaluateAll(
      (labels) =>
        labels.filter((l) => getComputedStyle(l).opacity === "1").length,
    );

test("50개 연결 목록을 한글로 검색하고 선택한 출처가 그래프와 목록에 유지된다", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/");
  await ready(page);
  const trigger = page.getByRole("button", {
    name: "연결 목록 보기",
    exact: true,
  });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const search = page.getByRole("searchbox", { name: "연결 목록에서 찾기" });
  await expect(search).toBeFocused();
  await expect(page.locator(".graph-result-count")).toHaveText("50개 항목");
  await search.fill("기억 09");
  await expect(page.locator(".graph-list .chip")).toHaveCount(1);
  await expect(page.locator(".graph-result-count")).toHaveText("50개 중 1개");
  await page.locator(".graph-list .chip").click();
  await expect(page.locator(".source-panel")).toContainText(records[8].title);
  await page.mouse.move(1, 1);
  await expect(page.locator(".graph-list .chip")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    page.locator('.graph-label-layer > span[data-selected="true"]'),
  ).toHaveText(records[8].title);
  await page.screenshot({ path: "test-results/graph-ux-selected-source.png" });
});

test("연결 목록은 Escape와 닫기 버튼 모두 원래 제어로 포커스를 돌린다", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/");
  await ready(page);
  const trigger = page.getByRole("button", {
    name: "연결 목록 보기",
    exact: true,
  });
  await trigger.click();
  await page
    .getByRole("searchbox", { name: "연결 목록에서 찾기" })
    .fill("없는 항목");
  await expect(page.getByText("일치하는 항목이 없어요.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".graph-list")).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await page.keyboard.press("Enter");
  await page
    .getByRole("button", { name: "연결 목록 닫기", exact: true })
    .click();
  await expect(trigger).toBeFocused();
});

test("화면 크기를 바꾸면 투영 좌표와 글자 폭을 갱신하고 그래프를 다시 만들지 않는다", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page);
  await page.goto("/");
  await ready(page);
  await expect.poll(() => visibleCount(page)).toBeGreaterThan(5);
  const canvas = page.locator(".graph-world canvas");
  await canvas.evaluate((el) => (el.dataset.identity = "kept"));
  const first = page.locator(".graph-label-layer > span").first();
  const before = await first.evaluate((el) => el.style.transform);
  await page.screenshot({ path: "test-results/graph-ux-50-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => first.evaluate((el) => el.style.transform))
    .not.toBe(before);
  await expect(canvas).toHaveAttribute("data-identity", "kept");
  expect(
    await first.evaluate((el) => el.getBoundingClientRect().width),
  ).toBeLessThanOrEqual(150.1);
  await page
    .getByRole("button", { name: "그래프 화면 맞추기", exact: true })
    .click();
  await expect.poll(() => visibleCount(page)).toBeGreaterThan(5);
  await page.screenshot({ path: "test-results/graph-ux-50-mobile.png" });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
