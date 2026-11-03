import { test, expect, type Page } from "@playwright/test";
import { openHome, openLibrary } from "./navigation";
const stamp = "2026-11-02T00:00:00Z";
const titles = [
  "트랜잭션과 원자성",
  "기억에 남는 학습법",
  "오늘의 작은 발견",
  "검색과 임베딩",
  "한 문장으로 정리하기",
  "이번 주의 회고",
  "프로젝트의 첫 결정",
  "반복해서 배우는 이유",
];
const records = titles.map((title, i) => ({
  id: `11111111-1111-4111-8111-${String(i).padStart(12, "0")}`,
  revision_id: `22222222-2222-4222-8222-${String(i).padStart(12, "0")}`,
  revision_no: 1,
  state_version: 1,
  title,
  body_markdown: `${title}\n\n배운 내용을 내 언어로 설명하면 이해한 부분과 더 공부할 부분을 구분할 수 있다.`,
  kinds: [i % 3 === 0 ? "knowledge" : i % 3 === 1 ? "episode" : "idea"],
  visibility: "public",
  completion_state: null,
  created_at: stamp,
  updated_at: stamp,
  index_state: { status: "ready" },
  concept_state: { status: "ready" },
  concepts: [],
  sources: [],
  nodes: [],
  node_status: "absent",
  review_state: "valid",
  is_current: true,
}));
const ref = (i: number) => ({
  capture_id: records[i].id,
  revision_id: records[i].revision_id,
});
const concepts = ["학습과 기억", "세컨드 브레인", "나의 일상"].map(
  (name, i) => ({
    id: `33333333-3333-4333-8333-${String(i).padStart(12, "0")}`,
    name,
  }),
);
function graph(indices = records.map((_, i) => i)) {
  return {
    nodes: [
      ...indices.map((i) => ({
        id: records[i].id,
        kind: "capture",
        label: records[i].title,
        kinds: records[i].kinds,
        source: ref(i),
      })),
      ...concepts.map((c) => ({ ...c, kind: "concept", label: c.name })),
    ],
    edges: indices.map((i) => ({
      source: records[i].id,
      target: concepts[i % 3].id,
      kind: "concept",
    })),
    truncated: false,
  };
}
async function fixture(page: Page, empty = false) {
  const calls: string[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const u = new URL(route.request().url()),
      path = u.pathname.replace("/api/v1", ""),
      body = route.request().postDataJSON();
    calls.push(path + u.search);
    const send = (data: unknown) =>
      route.fulfill({ json: { schema_version: 1, ok: true, data } });
    if (path === "/session") return send({ csrf_token: "csrf" });
    if (path === "/concepts")
      return send({ items: concepts, next_cursor: null });
    if (path === "/captures") {
      if (u.searchParams.get("kinds") === "knowledge")
        await new Promise((resolve) => setTimeout(resolve, 350));
      return send({
        items: empty
          ? []
          : records
              .filter(
                (r) =>
                  !u.searchParams.get("kinds") ||
                  r.kinds.includes(u.searchParams.get("kinds")!),
              )
              .map((r) => ({ ...r, excerpt: r.body_markdown })),
        next_cursor: null,
      });
    }
    if (path === "/graph") {
      if (u.searchParams.get("kinds") === "knowledge")
        await new Promise((resolve) => setTimeout(resolve, 350));
      return send(
        empty
          ? { nodes: [], edges: [], truncated: false }
          : graph(
              u.searchParams.get("kinds") === "episode" ? [1, 4, 7] : undefined,
            ),
      );
    }
    if (path.endsWith("/neighbors")) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      return send(graph([0]));
    }
    if (path.startsWith("/captures/"))
      return send(records.find((r) => path.endsWith(r.id)));
    if (path === "/sources/resolve") {
      const r = records.find((r) => r.id === body.capture_id)!;
      return send({
        source: body,
        is_current: true,
        current_revision_id: r.revision_id,
        text: r.body_markdown,
        capture: r,
        node: null,
        review_state: "valid",
      });
    }
    if (path === "/search")
      return send({
        items: [
          {
            source: ref(1),
            excerpt: records[1].body_markdown,
            score: 1,
            score_kind: "rrf",
          },
        ],
        next_cursor: null,
      });
    if (path === "/questions")
      return route.fulfill({
        contentType: "text/event-stream",
        body: `event: completed\ndata: ${JSON.stringify({ request_id: body.request_id, result: { answer_id: "answer", parts: [{ part_id: "part", kind: "stored_knowledge", text: "배운 것을 자신의 말로 정리하면 **다음 생각과 연결**할 수 있어요.", sources: [ref(1)] }], sources: [ref(1)], limitations: [], evidence_status: "found" } })}\n\n`,
      });
    return route.fulfill({
      status: 404,
      json: { ok: false, error: { code: "NOT_FOUND", message: "not found" } },
    });
  });
  return calls;
}
async function ready(page: Page) {
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "ready",
  );
  await expect(page.locator(".graph-world canvas")).toBeVisible();
}
test("홈 canvas가 검색·출처에서 유지되고 검색 위치·키보드 목록이 보존된다", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await fixture(page);
  await page.goto("/");
  await ready(page);
  await expect(page).toHaveTitle("Cache Me If You Can");
  const input = page.getByRole("textbox", {
      name: "저장된 지식 검색 또는 질문",
    }),
    before = await input.boundingBox();
  await page
    .locator(".graph-world canvas")
    .evaluate((el) => el.setAttribute("data-original", "yes"));
  await page.screenshot({ path: "test-results/home-graph-desktop.png" });
  await input.fill("배운 내용을 어떻게 정리했지?");
  await page.getByRole("button", { name: "검색", exact: true }).click();
  await expect(page.getByRole("article", { name: "AI 답변" })).toContainText(
    "다음 생각과 연결",
  );
  expect((await input.boundingBox())!.y).toBe(before!.y);
  await page.getByRole("button", { name: "출처 1 보기", exact: true }).click();
  await expect(page.locator(".source-panel")).toContainText(records[1].title);
  await expect(page.locator(".graph-world canvas")).toHaveAttribute(
    "data-original",
    "yes",
  );
  const answerBox = (await page.locator(".answer-area").boundingBox())!,
    panelBox = (await page.locator(".source-panel").boundingBox())!;
  expect(answerBox.x + answerBox.width).toBeLessThanOrEqual(panelBox.x);
  await page.screenshot({ path: "test-results/home-graph-answer-source.png" });
  await page.getByRole("button", { name: "출처 닫기", exact: true }).click();
  await page
    .getByRole("button", { name: "검색 응답 닫기", exact: true })
    .click();
  await expect(input).toHaveValue("배운 내용을 어떻게 정리했지?");
  await page
    .getByRole("button", { name: "연결 목록 보기", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await page
    .getByRole("button", { name: records[0].title + " 지식", exact: true })
    .click();
  await expect(page.locator(".source-panel")).toContainText(records[0].title);
  expect(errors).toEqual([]);
});
test("빠른 목록 필터는 이전 결과를 무시하고 홈 그래프와 질문은 전체 범위를 유지한다", async ({
  page,
}) => {
  const calls = await fixture(page);
  await page.goto("/");
  await ready(page);
  await openLibrary(page);
  await page
    .getByRole("combobox", { name: "기록 유형", exact: true })
    .selectOption("knowledge");
  await page
    .getByRole("combobox", { name: "기록 유형", exact: true })
    .selectOption("episode");
  await expect(page.locator(".rb-record")).toHaveCount(3);
  await expect(page.locator(".record-browser")).toContainText(records[1].title);
  await page.waitForTimeout(500);
  await expect(page.locator(".record-browser")).not.toContainText(
    records[0].title,
  );
  await openHome(page);
  await ready(page);
  await page
    .getByRole("button", { name: "연결 목록 보기", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "지식 연결 지도" }),
  ).toContainText(records[1].title);
  await expect(page.locator(".graph-list")).toContainText(records[0].title);
  expect(
    calls.some(
      (c) => c.startsWith("/captures?") && c.includes("kinds=episode"),
    ),
  ).toBe(true);
  expect(
    calls
      .filter((c) => c.startsWith("/graph"))
      .every((c) => !c.includes("kinds=")),
  ).toBe(true);
  const question = page.waitForRequest(
    (request) => new URL(request.url()).pathname === "/api/v1/questions",
  );
  await page
    .getByRole("textbox", { name: "저장된 지식 검색 또는 질문" })
    .fill("전체 저장소에 질문");
  await page.getByRole("button", { name: "검색", exact: true }).click();
  const payload = (await question).postDataJSON();
  expect(payload.kinds).toBeUndefined();
  expect(payload.concept_ids).toBeUndefined();
});
test("빈 저장소는 무대를 유지하고 목데이터 없이 첫 기록을 시작한다", async ({
  page,
}) => {
  const calls = await fixture(page, true);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "첫 번째 생각을 남겨보세요" }),
  ).toBeVisible();
  await expect(page.locator(".graph-stage")).toBeVisible();
  await expect(page.locator(".graph-world canvas")).toHaveCount(0);
  await page.screenshot({ path: "test-results/home-graph-empty.png" });
  await page
    .getByRole("button", { name: "기록 시작하기", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(calls.filter((c) => c === "/questions")).toHaveLength(0);
});
test("모바일 그래프·메뉴·출처는 가로 넘침 없이 열리고 축소 모션을 따른다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page);
  await page.goto("/");
  await ready(page);
  await expect(page.locator(".app-shell")).toHaveAttribute(
    "data-reduced-motion",
    "true",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("button", { name: "Cache Me If You Can 홈" }),
  ).toHaveCount(0);
  await page.screenshot({ path: "test-results/home-graph-mobile.png" });
  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await expect(
    page.getByRole("button", { name: "모든 기록", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "타임라인", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page
    .getByRole("textbox", { name: "저장된 지식 검색 또는 질문" })
    .fill("학습 정리");
  await page.getByRole("button", { name: "검색", exact: true }).click();
  await page.getByRole("button", { name: "출처 1 보기", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(records[1].title);
  await page.keyboard.press("Escape");
  await ready(page);
  await expect(page.getByRole("article", { name: "AI 답변" })).toContainText(
    "다음 생각과 연결",
  );
  await page.screenshot({ path: "test-results/home-graph-mobile-answer.png" });
});

test("예시는 명시적으로 열며 원문 API·검색·저장과 섞이지 않는다", async ({
  page,
}) => {
  const calls = await fixture(page, true);
  await page.goto("/");
  await expect(page.locator(".graph-world")).toHaveCount(0);
  await page.getByRole("button", { name: "예시 보기", exact: true }).click();
  await ready(page);
  await expect(
    page.getByText("예시 · 읽기 전용", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "저장된 지식 검색 또는 질문" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "연결 목록 보기" }).click();
  await page
    .getByRole("button", { name: "내 언어로 설명하는 공부 지식", exact: true })
    .click();
  await expect(page.locator(".example-selection")).toContainText(
    "내 기록에 저장되지 않아요",
  );
  expect(
    calls.filter((c) => c === "/sources/resolve" || c === "/questions"),
  ).toEqual([]);
  await page.getByRole("button", { name: "연결 목록 닫기" }).click();
  await page.screenshot({ path: "test-results/home-graph-example.png" });
  await page.getByRole("button", { name: "내 지식으로 돌아가기" }).click();
  await expect(
    page.getByRole("heading", { name: "첫 번째 생각을 남겨보세요" }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "저장된 지식 검색 또는 질문" }),
  ).toBeEnabled();
});

test("WebGL을 쓸 수 없어도 연결 목록에서 출처를 열 수 있다", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: any[]
    ) {
      if (
        type === "webgl" ||
        type === "webgl2" ||
        type === "experimental-webgl"
      )
        return null;
      return original.apply(this, [type, ...args] as any);
    } as typeof original;
  });
  await fixture(page);
  await page.goto("/");
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "fallback",
  );
  await expect(
    page.getByText("3D 보기를 열 수 없어 연결 목록으로 표시합니다."),
  ).toBeVisible();
  await page
    .locator(".graph-list")
    .getByRole("button", { name: records[0].title + " 지식", exact: true })
    .click();
  await expect(page.locator(".source-panel")).toContainText(records[0].title);
});

test("기록을 바꾸면 이전 주변 그래프 응답이 새 상세에 나타나지 않는다", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/#capture/" + records[0].id);
  await page
    .getByRole("button", { name: "주변 지식 보기", exact: true })
    .click();
  await openLibrary(page);
  await page
    .locator(".rb-record")
    .filter({ hasText: records[1].title })
    .click();
  await expect(page.locator(".record-detail h1")).toHaveText(records[1].title);
  await page.waitForTimeout(650);
  await expect(page.locator(".graph-neighborhood")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "주변 지식 보기", exact: true }),
  ).toBeEnabled();
});
