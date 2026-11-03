import { test, expect, type Page } from "@playwright/test";

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

for (const viewport of [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 1024, height: 768 },
]) {
  test.describe(`${viewport.name} navigation`, () => {
    test.use({
      viewport: { width: viewport.width, height: viewport.height },
      reducedMotion: "reduce",
    });

    test("menu keeps keyboard focus visible and Escape returns to its opener", async ({
      page,
    }) => {
      const state = await fixture(page);
      await page.goto("/");
      const opener = page.getByRole("button", {
        name: "메뉴 열기",
        exact: true,
      });
      await expect(opener).toBeVisible();
      await opener.focus();
      await page.keyboard.press("Enter");
      await expectFocusInsideMenu(page);
      await expect(
        page.getByRole("combobox", { name: "기록 유형", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("combobox", { name: "주제", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: new RegExp(capture.title) }),
      ).toBeVisible();

      // Cross both ends of the drawer's focus order; background controls must
      // never receive a hidden focus while the menu covers the workspace.
      for (const key of ["Tab", "Shift+Tab"]) {
        for (let i = 0; i < 14; i++) {
          await page.keyboard.press(key);
          await expectFocusInsideMenu(page);
        }
      }
      await page.keyboard.press("Escape");
      await expect(opener).toBeFocused();
      await expect(
        page.getByRole("complementary", { name: "주 메뉴" }),
      ).toHaveCount(0);
      expect(state.unexpectedRequests).toEqual([]);
    });

    test("selecting a record closes the drawer and focuses the record heading", async ({
      page,
    }) => {
      const state = await fixture(page);
      await page.goto("/");
      await page
        .getByRole("button", { name: "메뉴 열기", exact: true })
        .click();
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
      ).toHaveCount(0);
      expect(state.detailReads()).toBe(1);
      expect(state.unexpectedRequests).toEqual([]);
    });

    test("failed record read stays visible in main and can be retried", async ({
      page,
    }) => {
      const state = await fixture(page, true);
      await page.goto("/");
      await page
        .getByRole("button", { name: "메뉴 열기", exact: true })
        .click();
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
