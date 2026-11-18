import { test, expect, type Page } from "@playwright/test";
import { openLibrary } from "./navigation";

const capture = {
  id: "11111111-1111-4111-8111-111111111111",
  revision_id: "22222222-2222-4222-8222-222222222222",
  revision_no: 1,
  state_version: 1,
  title: "키보드로 읽는 학습 기록",
  body_markdown: "오늘 배운 내용을 다시 설명하며 이해한 부분을 확인했다.",
  kinds: ["knowledge"],
  visibility: "public",
  completion_state: null,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
  revision_created_at: "2026-11-02T00:00:00Z",
  is_current: true,
  node_status: "absent",
  index_state: { status: "ready" },
  concept_state: { status: "ready" },
  concepts: [],
  concept_hints: [],
  nodes: [],
  sources: [],
  review_state: "valid",
};

async function fixture(page: Page, failFirstRead = false) {
  let detailReads = 0;
  const unexpectedRequests: string[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const send = (data: unknown) =>
      route.fulfill({ json: { schema_version: 1, ok: true, data } });
    if (request.method() === "GET") {
      if (path === "/session") return send({ csrf_token: "navigation-test" });
      if (path === "/concepts") return send({ items: [], next_cursor: null });
      if (path === "/captures")
        return send({
          items: [{ ...capture, excerpt: capture.body_markdown }],
          next_cursor: null,
        });
      // Navigation behavior does not depend on WebGL or the embedding runtime.
      if (path === "/graph")
        return send({ nodes: [], edges: [], truncated: false });
      if (path === `/captures/${capture.id}`) {
        detailReads++;
        if (failFirstRead && detailReads === 1)
          return route.fulfill({
            status: 503,
            json: {
              schema_version: 1,
              ok: false,
              error: {
                code: "TEMPORARY_ERROR",
                message: "기록을 불러오지 못했습니다. 다시 시도해 주세요.",
                retryable: true,
              },
            },
          });
        return send(capture);
      }
    }
    unexpectedRequests.push(`${request.method()} ${path}`);
    return route.fulfill({ status: 500, body: "Unexpected test request" });
  });
  return { detailReads: () => detailReads, unexpectedRequests };
}

async function expectFocusInsideMenu(page: Page) {
  await expect
    .poll(() =>
      page.locator(".sidebar").evaluate((menu) => {
        const focused = document.activeElement;
        if (!(focused instanceof HTMLElement) || !menu.contains(focused))
          return false;
        const rect = focused.getBoundingClientRect();
        const top = document.elementFromPoint(
          rect.x + rect.width / 2,
          rect.y + rect.height / 2,
        );
        return Boolean(top && focused.contains(top));
      }),
    )
    .toBe(true);
}

test("기록 주소에 아티클 ID를 넣으면 기록 조회 오류를 표시한다", async ({
  page,
}) => {
  const articleId = "33333333-3333-4333-8333-333333333333";
  const state = await fixture(page);
  await page.route(`**/api/v1/captures/${articleId}`, (route) =>
    route.fulfill({
      status: 404,
      json: { ok: false, error: { code: "NOT_FOUND", message: "기록 없음" } },
    }),
  );

  await page.goto(`/#capture/${articleId}`);
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "더 이상 조회할 수 없는 기록입니다",
  );
  await expect(page).toHaveURL(new RegExp(`#capture/${articleId}$`));
  expect(state.unexpectedRequests).toEqual([]);
});

for (const viewport of [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 1024, height: 768 },
]) {
  test.describe(`${viewport.name} navigation`, () => {
    test.use({
      viewport: { width: viewport.width, height: viewport.height },
      reducedMotion: "reduce",
    });

    test("navigation keeps visible keyboard focus and matches the viewport", async ({
      page,
    }) => {
      const state = await fixture(page);
      await page.goto("/");
      const opener = page.getByRole("button", {
        name: "메뉴 열기",
        exact: true,
      });
      if (viewport.width <= 800) {
        await expect(opener).toBeVisible();
        await opener.focus();
        await page.keyboard.press("Enter");
        await expectFocusInsideMenu(page);
      } else {
        await expect(opener).toHaveCount(0);
        await expect(
          page.getByRole("complementary", { name: "주 메뉴" }),
        ).toBeVisible();
        await expect(
          page.getByRole("dialog", { name: "기록과 탐색" }),
        ).toHaveCount(0);
      }
      for (const name of ["지식 공간", "모든 기록", "타임라인", "설정"])
        await expect(
          page.getByRole("button", { name, exact: true }),
        ).toBeVisible();
      await expect(
        page.getByRole("combobox", { name: "기록 유형", exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: new RegExp(capture.title) }),
      ).toHaveCount(0);

      if (viewport.width <= 800) {
        // Both ends wrap inside the modal drawer; covered background controls
        // must never receive focus.
        for (const key of ["Tab", "Shift+Tab"])
          for (let i = 0; i < 14; i++) {
            await page.keyboard.press(key);
            await expectFocusInsideMenu(page);
          }
        await page.keyboard.press("Escape");
        await expect(opener).toBeFocused();
        await expect(
          page.getByRole("complementary", { name: "주 메뉴" }),
        ).toHaveCount(0);
      } else {
        await page
          .getByRole("button", { name: "모든 기록", exact: true })
          .focus();
        await page.keyboard.press("Enter");
        await expect(page.locator(".record-browser")).toBeVisible();
        await expect(
          page.getByRole("complementary", { name: "주 메뉴" }),
        ).toBeVisible();
        await expect(
          page.getByRole("combobox", { name: "기록 유형", exact: true }),
        ).toBeVisible();
      }
      expect(state.unexpectedRequests).toEqual([]);
    });

    test("opening the library closes the mobile drawer and record selection focuses its heading", async ({
      page,
    }) => {
      const state = await fixture(page);
      await page.goto("/");
      await openLibrary(page);
      await expect(
        page.getByRole("dialog", { name: "기록과 탐색" }),
      ).toHaveCount(0);
      const record = page.getByRole("button", {
        name: new RegExp(capture.title),
      });
      await record.focus();
      await page.keyboard.press("Enter");
      const heading = page.getByRole("heading", {
        name: capture.title,
        exact: true,
      });
      await expect(heading).toBeVisible();
      await expect(heading).toBeFocused();
      await expect(
        page.getByRole("complementary", { name: "주 메뉴" }),
      ).toHaveCount(viewport.width <= 800 ? 0 : 1);
      expect(state.detailReads()).toBe(1);
      expect(state.unexpectedRequests).toEqual([]);
    });

    test("failed record read stays visible in main and can be retried", async ({
      page,
    }) => {
      const state = await fixture(page, true);
      await page.goto("/");
      await openLibrary(page);
      await page
        .getByRole("button", { name: new RegExp(capture.title) })
        .click();
      const main = page.getByRole("main");
      await expect(main.getByRole("alert")).toContainText(
        "기록을 불러오지 못했습니다",
      );
      await expect(main.getByRole("alert")).toBeInViewport();
      const retry = main.getByRole("button", {
        name: "기록 다시 불러오기",
        exact: true,
      });
      await expect(retry).toBeVisible();
      await retry.focus();
      await page.keyboard.press("Enter");
      await expect(
        main.getByRole("heading", { name: capture.title, exact: true }),
      ).toBeFocused();
      await expect(main.getByRole("alert")).toHaveCount(0);
      expect(state.detailReads()).toBe(2);
      expect(state.unexpectedRequests).toEqual([]);
    });
  });
}
