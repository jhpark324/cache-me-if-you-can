import { expect, test, type Page } from "@playwright/test";
import { openHome, openLibrary } from "./navigation";

test.beforeEach(async ({ page }) => {
  await page.clock.install();
});

const captureId = "51111111-1111-4111-8111-111111111111";
const revisionId = "52222222-2222-4222-8222-222222222222";
const nodeId = "53333333-3333-4333-8333-333333333333";
const conceptId = "54444444-4444-4444-8444-444444444444";
const jobId = "55555555-5555-4555-8555-555555555555";
const source = { capture_id: captureId, revision_id: revisionId };

async function fixture(
  page: Page,
  initial:
    | "pending"
    | "running"
    | "needs_review"
    | "failed"
    | "ready"
    | "empty" = "pending",
) {
  let status = initial;
  let graphReads = 0;
  let graphFailure = false;
  let holdNext: Promise<void> | null = null;
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const capture = () => ({
    id: captureId,
    revision_id: revisionId,
    revision_no: 1,
    state_version: 1,
    title: "복습 방법을 정리한 기록",
    body_markdown: "배운 내용을 짧게 정리한 뒤 질문으로 복습한다.",
    kinds: ["knowledge"],
    visibility: "public",
    completion_state: null,
    created_at: "2026-11-04T00:00:00Z",
    updated_at: "2026-11-04T00:00:00Z",
    is_current: true,
    node_status: "absent",
    index_state: { status: "ready" },
    concept_state: {
      status,
      job_id: jobId,
      error_code: status === "failed" ? "MODEL_USAGE_LIMIT" : null,
      unresolved_hints: status === "needs_review" ? ["복습 도구 선택"] : [],
    },
    concepts:
      status === "needs_review"
        ? [{ id: conceptId, name: "학습과 기억" }]
        : [],
    concept_hints: [],
    nodes: [],
    sources: [],
    review_state: "valid",
  });
  const graph = () => ({
    nodes:
      status === "empty"
        ? []
        : [
            {
              id: captureId,
              kind: "capture",
              label: capture().title,
              source,
              kinds: ["knowledge"],
              concept_state: capture().concept_state,
            },
            ...(status === "ready"
              ? [
                  {
                    id: nodeId,
                    kind: "node",
                    label: "질문으로 복습하기",
                    source: { ...source, node_id: nodeId },
                  },
                  { id: conceptId, kind: "concept", label: "학습과 기억" },
                ]
              : []),
          ],
    edges:
      status === "ready"
        ? [
            { source: captureId, target: nodeId, kind: "contains" },
            { source: nodeId, target: conceptId, kind: "concept" },
          ]
        : [],
    truncated: false,
  });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const send = (data: unknown) =>
      route
        .fulfill({ json: { schema_version: 1, ok: true, data } })
        .catch(() => {});
    if (request.method() !== "GET")
      writes.push({ path, body: request.postDataJSON() });
    if (path === "/session") return send({ csrf_token: "graph-recovery" });
    if (path === "/settings")
      return send({
        auth: {
          connected: true,
          plan_enabled: true,
          email: "fixture@example.test",
          selected_model: "fixture-model",
          models: [{ slug: "fixture-model", display_name: "테스트 모델" }],
          request_blocked:
            status === "failed"
              ? {
                  code: "MODEL_USAGE_LIMIT",
                  message: "ChatGPT의 앱 사용 한도에 도달했습니다.",
                }
              : null,
        },
        index: {
          status: "ready",
          ready: true,
          index_counts: { ready: 1, pending: 0, failed: 0, excluded: 0 },
        },
      });
    if (path === "/graph") {
      graphReads++;
      const snapshot = graph();
      const waiting = holdNext;
      holdNext = null;
      if (waiting) await waiting;
      if (graphFailure)
        return route
          .fulfill({
            status: 503,
            json: {
              ok: false,
              error: {
                code: "GRAPH_TEMPORARILY_UNAVAILABLE",
                message: "연결 지도를 불러오지 못했습니다.",
                retryable: true,
              },
            },
          })
          .catch(() => {});
      return send(snapshot);
    }
    if (path === "/captures")
      return send({
        items: status === "empty" ? [] : [capture()],
        next_cursor: null,
      });
    if (path === "/concepts") return send({ items: [], next_cursor: null });
    if (path === `/captures/${captureId}`) return send(capture());
    if (path === `/captures/${captureId}/neighbors`) return send(graph());
    if (path === `/captures/${captureId}/concept-retry`) {
      status = "pending";
      return send({
        capture: capture(),
        committed_ref: source,
        request_id: request.postDataJSON().request_id,
        replayed: false,
        result_state: "available",
        warnings: [],
      });
    }
    if (path === "/sources/resolve")
      return send({
        source,
        capture: capture(),
        text: capture().body_markdown,
        is_current: true,
        current_revision_id: revisionId,
        node: null,
        review_state: "valid",
      });
    return route.fulfill({
      status: 404,
      json: {
        ok: false,
        error: { code: "NOT_FOUND", message: "Unexpected fixture route" },
      },
    });
  });
  return {
    errors,
    writes,
    get graphReads() {
      return graphReads;
    },
    setStatus(next: typeof status) {
      status = next;
    },
    failGraph(value: boolean) {
      graphFailure = value;
    },
    holdGraph(waiting: Promise<void>) {
      holdNext = waiting;
    },
  };
}

async function ready(page: Page) {
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "ready",
  );
  await expect(page.locator(".graph-world canvas")).toBeVisible();
}

test("주제 연결 완료를 자동 반영하고 세부 항목의 주제 간선까지 그린다", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const f = await fixture(page);
  await page.goto("/");
  await ready(page);
  const status = page.getByRole("status", { name: "주제 연결 상태" });
  await expect(status).toContainText(
    "표시 중인 기록의 주제 연결: 처리 중 0개 · 대기 1개.",
  );
  await page.screenshot({ path: testInfo.outputPath("graph-pending.png") });
  await page
    .locator(".graph-world canvas")
    .evaluate((el) => el.setAttribute("data-identity", "same-canvas"));
  f.setStatus("running");
  await page.clock.fastForward(8100);
  await expect(status).toContainText(
    "표시 중인 기록의 주제 연결: 처리 중 1개 · 대기 0개.",
  );
  f.setStatus("ready");
  await page.clock.fastForward(8100);
  await expect.poll(() => f.graphReads).toBeGreaterThanOrEqual(3);
  await expect(page.locator(".graph-world .graph-label")).toHaveCount(3);
  await expect(status).toHaveCount(0);
  await expect(page.locator(".graph-world canvas")).toHaveAttribute(
    "data-identity",
    "same-canvas",
  );
  await ready(page);
  await page.screenshot({ path: testInfo.outputPath("graph-connected.png") });
  expect(f.errors).toEqual([]);
});

test("확인이 필요한 주제는 연결 실패와 구분하고 기존 연결을 상세에서 보여준다", async ({
  page,
}) => {
  const f = await fixture(page, "needs_review");
  await page.goto("/");
  await ready(page);
  const status = page.getByRole("status", { name: "주제 연결 상태" });
  await expect(status).toContainText(
    "표시 중인 기록 1개에 확인이 필요한 주제가 있어요.",
  );
  await expect(status).not.toContainText("실패");
  await page
    .getByRole("button", { name: "주제 검토가 필요한 기록 확인", exact: true })
    .click();
  const detail = page.locator(".record-detail");
  await expect(detail).toContainText("복습 방법을 정리한 기록");
  await expect(detail).toContainText(
    "확정하기 어려운 주제는 연결을 보류했어요. 주제 정정에서 확인하고 직접 선택할 수 있어요.",
  );
  await expect(detail).toContainText("학습과 기억");
  await expect(
    detail.getByRole("button", { name: "주제 정정", exact: true }),
  ).toBeVisible();
  expect(
    f.writes.filter((write) => write.path.endsWith("/concept-retry")),
  ).toHaveLength(0);
  expect(f.errors).toEqual([]);
});

test("조용한 갱신 실패와 같은 데이터 응답은 기존 그래프·화면 위치를 유지한다", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const f = await fixture(page, "ready");
  await page.goto("/");
  await ready(page);
  const label = page.locator(".graph-world .graph-label").first();
  await expect
    .poll(() => label.evaluate((el) => el.style.transform))
    .not.toBe("");
  const beforeZoom = await label.evaluate((el) => el.style.transform);
  await page.getByRole("button", { name: "그래프 확대", exact: true }).click();
  await expect
    .poll(() => label.evaluate((el) => el.style.transform))
    .not.toBe(beforeZoom);
  const position = await label.evaluate((el) => el.style.transform);
  f.failGraph(true);
  const beforeFailure = f.graphReads;
  await page.clock.fastForward(8100);
  await expect.poll(() => f.graphReads).toBeGreaterThan(beforeFailure);
  await expect(page.locator(".graph-world .graph-label")).toHaveCount(3);
  await ready(page);
  f.failGraph(false);
  const beforeRecovery = f.graphReads;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => f.graphReads).toBeGreaterThan(beforeRecovery);
  expect(await label.evaluate((el) => el.style.transform)).toBe(position);
  expect(f.errors).toEqual([]);
});

test("목록 화면에서는 조회를 멈추고 홈 복귀 후 늦은 응답을 무시한다", async ({
  page,
}) => {
  const f = await fixture(page);
  await page.goto("/");
  await ready(page);
  let release!: () => void;
  f.holdGraph(
    new Promise<void>((resolve) => {
      release = resolve;
    }),
  );
  await page.clock.fastForward(8100);
  await expect.poll(() => f.graphReads).toBe(2);
  await openLibrary(page);
  const hiddenReads = f.graphReads;
  await page.clock.fastForward(24000);
  expect(f.graphReads).toBe(hiddenReads);
  f.setStatus("ready");
  await openHome(page);
  await expect(page.locator(".graph-world .graph-label")).toHaveCount(3);
  release();
  await page.clock.fastForward(1000);
  await expect(page.locator(".graph-world .graph-label")).toHaveCount(3);
  await expect(
    page.getByRole("status", { name: "주제 연결 상태" }),
  ).toHaveCount(0);
  expect(f.errors).toEqual([]);
});

test("숨긴 브라우저 탭과 읽기 전용 예시에서는 반복 조회하지 않는다", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const state = window as typeof window & { __graphTabHidden: boolean };
    state.__graphTabHidden = false;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => state.__graphTabHidden,
    });
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => (state.__graphTabHidden ? "hidden" : "visible"),
    });
  });
  const f = await fixture(page, "empty");
  await page.goto("/");
  await expect(page.getByRole("button", { name: "예시 보기" })).toBeVisible();
  await page.evaluate(() => {
    (window as typeof window & { __graphTabHidden: boolean }).__graphTabHidden =
      true;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const hiddenReads = f.graphReads;
  await page.clock.fastForward(24000);
  expect(f.graphReads).toBe(hiddenReads);
  await page.evaluate(() => {
    (window as typeof window & { __graphTabHidden: boolean }).__graphTabHidden =
      false;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect.poll(() => f.graphReads).toBeGreaterThan(hiddenReads);
  await page.getByRole("button", { name: "예시 보기" }).click();
  await expect(
    page.getByText("예시 · 읽기 전용", { exact: true }),
  ).toBeVisible();
  const exampleReads = f.graphReads;
  await page.clock.fastForward(24000);
  expect(f.graphReads).toBe(exampleReads);
  await page.getByRole("button", { name: "내 지식으로 돌아가기" }).click();
  await expect.poll(() => f.graphReads).toBeGreaterThan(exampleReads);
});

test("주제 연결 사용 한도 실패에서 원인·사용량 링크와 명시적 재시도를 제공한다", async ({
  page,
}, testInfo) => {
  const f = await fixture(page, "failed");
  await page.goto("/");
  await ready(page);
  await expect(
    page.getByRole("status", { name: "주제 연결 상태" }),
  ).toContainText("표시 중인 기록 1개의 주제 연결에 실패했습니다.");
  await page.setViewportSize({ width: 390, height: 844 });
  const failure = page.getByRole("status", { name: "주제 연결 상태" });
  await expect(failure).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("graph-failed-mobile.png"),
  });
  await page
    .getByRole("button", { name: "연결 실패 기록 확인", exact: true })
    .click();
  await expect(page.locator(".record-detail")).toContainText(
    "ChatGPT의 앱 사용 한도에 도달했습니다.",
  );
  const usage = page.getByRole("link", {
    name: "ChatGPT 사용량 확인",
    exact: true,
  });
  await expect(usage).toHaveAttribute(
    "href",
    "https://chatgpt.com/settings/usage",
  );
  await expect(usage).toHaveAttribute("target", "_blank");
  await page.screenshot({ path: testInfo.outputPath("graph-usage-limit.png") });
  expect(
    f.writes.filter((w) => w.path.endsWith("/concept-retry")),
  ).toHaveLength(0);
  await page
    .getByRole("button", { name: "주제 연결 다시 시도", exact: true })
    .click();
  await expect(page.locator(".record-detail")).toContainText(
    "저장한 기록의 주제를 연결하고 있어요.",
  );
  await expect(usage).toHaveCount(0);
  const retry = f.writes.filter((w) => w.path.endsWith("/concept-retry"));
  expect(retry).toHaveLength(1);
  expect(retry[0].body).toMatchObject({
    job_id: jobId,
    expected_revision_id: revisionId,
    expected_state_version: 1,
  });
  f.setStatus("failed");
  await page.clock.fastForward(2600);
  await expect(
    page.getByRole("button", { name: "주제 연결 다시 시도", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "주제 연결 다시 시도", exact: true })
    .click();
  await expect
    .poll(
      () => f.writes.filter((w) => w.path.endsWith("/concept-retry")).length,
    )
    .toBe(2);
  const secondRetry = f.writes.filter((w) =>
    w.path.endsWith("/concept-retry"),
  )[1];
  expect(secondRetry.body).toMatchObject({
    job_id: jobId,
    expected_revision_id: revisionId,
    expected_state_version: 1,
  });
  expect(secondRetry.body.request_id).not.toBe(retry[0].body.request_id);
  expect(f.errors).toEqual([]);
});

test("설정에서 AI 사용 차단 이유를 확인하는 동안 홈 그래프 조회를 멈춘다", async ({
  page,
}) => {
  const f = await fixture(page, "failed");
  await page.goto("/");
  await ready(page);
  await page.getByRole("button", { name: "설정", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("ChatGPT의 앱 사용 한도에 도달했습니다.");
  await expect(dialog).toContainText(
    "원인을 해결한 뒤 기록 상세에서 주제 연결을 다시 시도",
  );
  await expect(
    dialog.getByRole("link", { name: "ChatGPT 사용량 확인", exact: true }),
  ).toHaveAttribute("href", "https://chatgpt.com/settings/usage");
  const reads = f.graphReads;
  await page.clock.fastForward(24000);
  expect(f.graphReads).toBe(reads);
  await page.getByRole("button", { name: "설정 닫기", exact: true }).click();
  await expect.poll(() => f.graphReads).toBeGreaterThan(reads);
});
