import { expect, test, type Page } from "@playwright/test";

async function fixture(page: Page) {
  await page.addInitScript(() => {
    const state = window as typeof window & { __graphDraws: number };
    state.__graphDraws = 0;
    for (const context of [WebGLRenderingContext, WebGL2RenderingContext]) {
      const draw = context.prototype.drawElements;
      context.prototype.drawElements = function (...args) {
        state.__graphDraws++;
        return draw.apply(this, args);
      };
    }
  });
  const records = Array.from({ length: 3 }, (_, index) => ({
    id: `11111111-1111-4111-8111-${String(index).padStart(12, "0")}`,
    revision_id: `22222222-2222-4222-8222-${String(index).padStart(12, "0")}`,
    revision_no: 1,
    state_version: 1,
    title: `지식 연결 ${index + 1}`,
    kinds: ["knowledge"],
    visibility: "public",
    created_at: "2026-11-03T00:00:00Z",
    updated_at: "2026-11-03T00:00:00Z",
    index_state: { status: "ready" },
    concept_state: { status: "ready" },
    review_state: "valid",
    node_status: "absent",
  }));
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const data = path.endsWith("/session")
      ? { csrf_token: "graph-visibility" }
      : path.endsWith("/concepts")
        ? { items: [], next_cursor: null }
        : path.endsWith("/captures")
          ? { items: records, next_cursor: null }
          : {
              nodes: records.map((record) => ({
                id: record.id,
                kind: "capture",
                label: record.title,
                source: {
                  capture_id: record.id,
                  revision_id: record.revision_id,
                },
              })),
              edges: [
                { source: records[0].id, target: records[1].id },
                { source: records[1].id, target: records[2].id },
              ],
              truncated: false,
            };
    return route.fulfill({ json: { schema_version: 1, ok: true, data } });
  });
}
const drawCount = (page: Page) =>
  page.evaluate(
    () => (window as typeof window & { __graphDraws: number }).__graphDraws,
  );
async function expectStopped(page: Page) {
  // Observe multiple browser frames after the navigation effect has settled.
  await page.waitForTimeout(100);
  const before = await drawCount(page);
  await page.waitForTimeout(200);
  expect(await drawCount(page)).toBe(before);
}

for (const preference of ["no-preference", "reduce"] as const) {
  test(`숨긴 그래프는 렌더링을 멈추고 같은 canvas와 모션 설정으로 복귀한다 (${preference})`, async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: preference });
    await fixture(page);
    await page.goto("/");
    await expect(page.locator(".graph-world")).toHaveAttribute(
      "data-render-state",
      "ready",
      { timeout: 15_000 },
    );
    const canvas = page.locator(".graph-world canvas");
    await canvas.evaluate((element) => (element.dataset.identity = "retained"));
    if (preference === "no-preference")
      await page
        .getByRole("button", { name: "모션 일시정지", exact: true })
        .click();
    await expect(page.locator(".app-shell")).toHaveAttribute(
      "data-reduced-motion",
      "true",
    );
    await page.getByRole("button", { name: "모든 기록", exact: true }).click();
    await expect(page.locator(".graph-stage")).toBeHidden();
    await expectStopped(page);
    const hiddenDraws = await drawCount(page);
    await page.getByRole("button", { name: "지식 공간", exact: true }).click();
    await expect(canvas).toBeVisible();
    await expect(canvas).toHaveAttribute("data-identity", "retained");
    await expect.poll(() => drawCount(page)).toBeGreaterThan(hiddenDraws);
    await expect(page.locator(".app-shell")).toHaveAttribute(
      "data-reduced-motion",
      "true",
    );
    const motion = page.getByRole("button", { name: "모션 켜기", exact: true });
    if (preference === "reduce") await expect(motion).toBeDisabled();
    else await expect(motion).toBeEnabled();
    const first = page.locator(".graph-label").first();
    const beforeZoom = await first.evaluate(
      (element) => element.style.transform,
    );
    await page
      .getByRole("button", { name: "그래프 확대", exact: true })
      .click();
    await expect
      .poll(() => first.evaluate((element) => element.style.transform))
      .not.toBe(beforeZoom);
  });
}

test("목록 주소로 시작해도 숨긴 canvas를 그대로 사용해 홈 그래프를 연다", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page);
  await page.goto("/#library");
  const canvas = page.locator(".graph-world canvas");
  await expect(canvas).toHaveCount(1);
  await canvas.evaluate(
    (element) => (element.dataset.identity = "initially-hidden"),
  );
  await expectStopped(page);
  await page.getByRole("button", { name: "지식 공간", exact: true }).click();
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "ready",
  );
  await expect(canvas).toBeVisible();
  await expect(canvas).toHaveAttribute("data-identity", "initially-hidden");
  await expect.poll(() => drawCount(page)).toBeGreaterThan(0);
});
