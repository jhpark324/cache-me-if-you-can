import { expect, test, type Page } from "@playwright/test";
import type { Settings } from "../src/types";

const catalog = [
  {
    slug: "fixture-reasoning",
    display_name: "테스트 추론 모델",
    supported_reasoning_efforts: [
      { effort: "low", description: "빠른 응답" },
      { effort: "high", description: "깊게 검토" },
    ],
    default_reasoning_effort: "low",
  },
  {
    slug: "fixture-basic",
    display_name: "테스트 기본 모델",
    supported_reasoning_efforts: [],
    default_reasoning_effort: null,
  },
];

async function fixture(
  page: Page,
  options: {
    connected?: boolean;
    cached?: boolean;
    catalogState?: "ready" | "empty" | "failed";
    failedRecords?: number;
    retried?: number;
    catalogWait?: Promise<void>;
    revocationConfirmed?: boolean;
  } = {},
) {
  const state: Settings = {
    auth: {
      connected: options.connected ?? true,
      plan_enabled: true,
      email: "current@example.test",
      active_account_id: "current",
      selected_model: "fixture-reasoning",
      selected_reasoning_effort: "high",
      models: options.cached ? structuredClone(catalog) : [],
    },
    index: {
      status: "ready",
      ready: true,
      index_counts: {
        ready: 4,
        pending: 0,
        failed: options.failedRecords ?? 0,
        excluded: 0,
      },
    },
    data_dir: "/tmp/settings-fixture",
  };
  // A legacy server response must not bring the old account picker back.
  Object.assign(state.auth!, {
    accounts: [
      { id: "current", email: "current@example.test" },
      { id: "previous", email: "previous@example.test" },
    ],
  });
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  let catalogReads = 0;
  let catalogState = options.catalogState ?? "ready";
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname.replace("/api/v1", "");
    const send = (data: unknown) =>
      route
        .fulfill({ json: { schema_version: 1, ok: true, data } })
        .catch(() => {});
    const fail = () =>
      route.fulfill({
        status: 503,
        json: {
          schema_version: 1,
          ok: false,
          error: {
            code: "CATALOG_UNAVAILABLE",
            message: "모델 목록을 가져오지 못했습니다.",
            retryable: true,
          },
        },
      });
    if (req.method() !== "GET") writes.push({ path, body: req.postDataJSON() });
    if (path === "/session") return send({ csrf_token: "fixture-csrf" });
    if (path === "/graph")
      return send({ nodes: [], edges: [], truncated: false });
    if (path === "/captures" || path === "/concepts")
      return send({ items: [], next_cursor: null });
    if (path === "/settings" && req.method() === "GET") return send(state);
    if (path === "/settings" && req.method() === "PATCH") {
      const body = req.postDataJSON();
      state.auth!.selected_model = body.model;
      state.auth!.selected_reasoning_effort = body.reasoning_effort;
      return send(state.auth);
    }
    if (path === "/auth/models") {
      catalogReads++;
      if (options.catalogWait) await options.catalogWait;
      if (catalogState === "failed") return fail();
      const models = catalogState === "empty" ? [] : structuredClone(catalog);
      if (state.auth!.connected) state.auth!.models = models;
      return send({ models });
    }
    if (path === "/auth/logout") {
      state.auth = { connected: false, models: [] };
      return send({
        remote_revocation_confirmed: options.revocationConfirmed ?? true,
      });
    }
    if (path === "/auth/login")
      return send({ authorization_url: "/?login=fixture" });
    if (path === "/index/retry") {
      const retried = options.retried ?? state.index!.index_counts.failed;
      state.index!.index_counts.failed = 0;
      state.index!.index_counts.pending = retried;
      return send({ retried });
    }
    return route.fulfill({ status: 404, body: "Unexpected fixture route" });
  });
  return {
    state,
    writes,
    get catalogReads() {
      return catalogReads;
    },
    recoverCatalog() {
      catalogState = "ready";
    },
  };
}

async function openSettings(page: Page) {
  const button = page.getByRole("button", { name: "설정", exact: true });
  const menu = page.getByRole("button", { name: "메뉴 열기", exact: true });
  if (await menu.isVisible()) await menu.click();
  await button.click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test("재시작 후 모델 목록을 자동으로 불러오고 추론 수준 선택을 보존한다", async ({
  page,
}) => {
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  const f = await fixture(page, { catalogWait: waiting });
  await page.goto("/");
  await openSettings(page);
  const model = page.getByRole("combobox", { name: "답변 모델", exact: true });
  await expect(model).toBeVisible();
  await expect(model).toBeDisabled();
  await expect.poll(() => f.catalogReads).toBe(1);
  release();
  await expect(model).toBeEnabled();
  await expect(model).toHaveValue("fixture-reasoning");
  await expect(
    page.getByText("current@example.test", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("previous@example.test")).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "연결할 계정", exact: true }),
  ).toHaveCount(0);
  const effort = page.getByRole("combobox", { name: "추론 수준", exact: true });
  await expect(effort).toHaveValue("high");
  await effort.selectOption("low");
  await expect
    .poll(() => f.writes.filter((w) => w.path === "/settings"))
    .toEqual([
      {
        path: "/settings",
        body: { model: "fixture-reasoning", reasoning_effort: "low" },
      },
    ]);
  await expect(effort).toBeEnabled();
  await page.getByRole("button", { name: "설정 닫기" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await openSettings(page);
  await expect(
    page.getByRole("combobox", { name: "추론 수준", exact: true }),
  ).toHaveValue("low");
  await model.selectOption("fixture-basic");
  await expect
    .poll(() => f.writes.at(-1))
    .toEqual({
      path: "/settings",
      body: { model: "fixture-basic", reasoning_effort: null },
    });
  await expect(
    page.getByRole("combobox", { name: "추론 수준", exact: true }),
  ).toHaveCount(0);
  await model.selectOption("fixture-reasoning");
  await expect(
    page.getByRole("combobox", { name: "추론 수준", exact: true }),
  ).toHaveValue("");
});

for (const catalogState of ["empty", "failed"] as const) {
  test(`모델 목록 ${catalogState} 상태에서 자동 재요청을 반복하지 않고 수동으로 복구한다`, async ({
    page,
  }) => {
    const f = await fixture(page, { catalogState });
    await page.clock.install();
    await page.goto("/");
    await openSettings(page);
    const retry = page.getByRole("button", {
      name: "모델 목록 다시 불러오기",
      exact: true,
    });
    await expect(retry).toBeEnabled();
    await expect(
      page.getByRole("combobox", { name: "답변 모델", exact: true }),
    ).toBeVisible();
    await page.clock.fastForward(10000);
    expect(f.catalogReads).toBe(1);
    f.recoverCatalog();
    await retry.click();
    await expect(
      page.getByRole("combobox", { name: "답변 모델", exact: true }),
    ).toBeEnabled();
    await expect(
      page
        .getByRole("combobox", { name: "답변 모델", exact: true })
        .locator("option"),
    ).toContainText(["테스트 추론 모델", "테스트 기본 모델"]);
    expect(f.catalogReads).toBe(2);
  });
}

test("연결 전에도 모델 선택 위치와 로그인 안내를 표시한다", async ({
  page,
}) => {
  const f = await fixture(page, { connected: false });
  await page.goto("/");
  await openSettings(page);
  await expect(
    page.getByRole("combobox", { name: "답변 모델", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Continue with ChatGPT" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "계정 변경", exact: true }),
  ).toHaveCount(0);
  expect(f.catalogReads).toBe(0);
});

test("계정 변경은 이전 계정을 선택하지 않고 새 연결을 요청한다", async ({
  page,
}) => {
  const f = await fixture(page, { cached: true });
  await page.goto("/");
  await openSettings(page);
  await page.getByRole("button", { name: "계정 변경", exact: true }).click();
  await expect
    .poll(() => f.writes.find((w) => w.path === "/auth/login"))
    .toEqual({
      path: "/auth/login",
      body: { replace_account: true },
    });
});

test("로그아웃 뒤 늦게 도착한 모델 목록이 연결 상태를 되살리지 않는다", async ({
  page,
}) => {
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  const f = await fixture(page, { catalogWait: waiting });
  await page.goto("/");
  await openSettings(page);
  await expect.poll(() => f.catalogReads).toBe(1);
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Continue with ChatGPT" }),
  ).toBeVisible();
  release();
  await expect(
    page.getByRole("combobox", { name: "답변 모델", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("current@example.test", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "추론 수준", exact: true }),
  ).toHaveCount(0);
});

test("원격 연결 해제 확인 실패를 로컬 로그아웃과 구분해 안내한다", async ({
  page,
}) => {
  await fixture(page, { cached: true, revocationConfirmed: false });
  await page.goto("/");
  await openSettings(page);
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Continue with ChatGPT" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    "ChatGPT에서 해제를 확인하지 못했습니다",
  );
});

test("검색 준비 완료 상태에는 불필요한 재시도를 표시하지 않는다", async ({
  page,
}) => {
  await fixture(page, { cached: true });
  await page.goto("/");
  await openSettings(page);
  await expect(page.getByRole("dialog")).toContainText(
    "저장한 기록을 검색할 수 있도록 준비합니다.",
  );
  await expect(page.getByRole("dialog")).toContainText("검색 가능 4개");
  await expect(
    page.getByRole("button", { name: "검색 준비 다시 시도", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "색인 다시 시도", exact: true }),
  ).toHaveCount(0);
});

for (const retried of [0, 2]) {
  test(`실패한 검색 준비 재시도 결과 ${retried}건을 정확하게 안내한다`, async ({
    page,
  }) => {
    const f = await fixture(page, { cached: true, failedRecords: 2, retried });
    await page.goto("/");
    await openSettings(page);
    await expect(page.getByRole("dialog")).toContainText("준비 실패 2개");
    await page
      .getByRole("button", { name: "검색 준비 다시 시도", exact: true })
      .click();
    await expect
      .poll(() => f.writes.filter((w) => w.path === "/index/retry").length)
      .toBe(1);
    if (retried === 0)
      await expect(
        page.getByText("다시 준비할 기록이 없습니다.", { exact: true }),
      ).toBeVisible();
    else await expect(page.getByRole("dialog")).toContainText("준비 대기 2개");
    await expect(
      page.getByRole("button", { name: "검색 준비 다시 시도", exact: true }),
    ).toHaveCount(0);
  });
}

test("좁은 화면에서 설정을 키보드로 조작하고 가로 넘침 없이 닫는다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page, { cached: true, failedRecords: 2 });
  await page.goto("/");
  await openSettings(page);
  const effort = page.getByRole("combobox", { name: "추론 수준", exact: true });
  await effort.focus();
  await expect(effort).toBeFocused();
  await page.keyboard.press("Home");
  await page.keyboard.press("Enter");
  await expect(effort).toHaveValue("");
  const dialog = page.getByRole("dialog");
  const bounds = await dialog.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});
