import { test, expect, type Page } from "@playwright/test";
import { openLibrary } from "./navigation";

const record = {
  id: "11111111-1111-4111-8111-111111111111",
  revision_id: "22222222-2222-4222-8222-222222222222",
  revision_no: 1,
  state_version: 1,
  title: "주제 목록 검증 기록",
  body_markdown: "주제 목록이 갱신되는지 확인한다.",
  kinds: ["knowledge"],
  visibility: "public",
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
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
const success = (data: unknown) => ({ schema_version: 1, ok: true, data });
async function baseFixture(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const send = (data: unknown) => route.fulfill({ json: success(data) });
    if (path === "/session") return send({ csrf_token: "final-review" });
    if (path === "/graph")
      return send({ nodes: [], edges: [], truncated: false });
    if (path === "/concepts") return send({ items: [], next_cursor: null });
    if (path === "/captures")
      return send({ items: [record], next_cursor: null });
    if (path === `/captures/${record.id}`) return send(record);
    return route.fulfill({ status: 500, body: "Unexpected fixture request" });
  });
}

test("library concepts include all pages and disambiguate duplicate names", async ({
  page,
}) => {
  await baseFixture(page);
  const pages: string[] = [];
  await page.route("**/api/v1/concepts?*", async (route) => {
    const cursor =
      new URL(route.request().url()).searchParams.get("cursor") || "";
    pages.push(cursor);
    return route.fulfill({
      json: success(
        cursor
          ? {
              items: [{ id: "last", name: "메모", description: "일상 기록" }],
              next_cursor: null,
            }
          : {
              items: Array.from({ length: 100 }, (_, i) => ({
                id: `concept-${i}`,
                name: i === 0 ? "메모" : `주제 ${i}`,
                description: i === 0 ? "개발 기록" : "",
              })),
              next_cursor: "next-page",
            },
      ),
    });
  });
  await page.goto("/");
  await openLibrary(page);
  const select = page.getByRole("combobox", { name: "주제", exact: true });
  await expect(select.locator("option")).toHaveCount(102);
  await expect(select.locator('option[value="last"]')).toHaveText(
    "메모 — 일상 기록",
  );
  const filtered = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return (
      url.pathname === "/api/v1/captures" &&
      url.searchParams.get("concept_ids") === "last"
    );
  });
  await select.selectOption("last");
  await filtered;
  expect(pages).toContain("next-page");
});

test("concept load failures are visible and recoverable without reloading records", async ({
  page,
}) => {
  await baseFixture(page);
  let failing = true;
  await page.route("**/api/v1/concepts?*", async (route) =>
    route.fulfill(
      failing
        ? {
            status: 503,
            json: {
              ok: false,
              error: {
                code: "TEMPORARY",
                message: "잠시 후 다시 시도해 주세요.",
              },
            },
          }
        : {
            json: success({
              items: [{ id: "new-topic", name: "복구한 주제" }],
              next_cursor: null,
            }),
          },
    ),
  );
  await page.goto("/");
  await openLibrary(page);
  await expect(page.getByRole("alert")).toContainText(
    "주제를 불러오지 못했습니다",
  );
  failing = false;
  await page.getByRole("button", { name: "주제 다시 불러오기" }).click();
  await expect(
    page
      .getByRole("combobox", { name: "주제", exact: true })
      .locator('option[value="new-topic"]'),
  ).toHaveText("복구한 주제");
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("saving a record refreshes its new concepts in the library filter", async ({
  page,
}) => {
  await baseFixture(page);
  let saved = false;
  await page.route("**/api/v1/concepts?*", async (route) =>
    route.fulfill({
      json: success({
        items: saved ? [{ id: "saved-topic", name: "저장 후 주제" }] : [],
        next_cursor: null,
      }),
    }),
  );
  await page.route("**/api/v1/captures", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    saved = true;
    return route.fulfill({
      json: success({
        capture: record,
        committed_ref: null,
        warnings: [],
        replayed: false,
        result_state: "available",
      }),
    });
  });
  await page.goto("/");
  await openLibrary(page);
  await page.getByRole("button", { name: "새 기록", exact: true }).click();
  await page.getByLabel("내용", { exact: true }).fill(record.body_markdown);
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: record.title, exact: true }),
  ).toBeVisible();
  await openLibrary(page);
  await expect(
    page
      .getByRole("combobox", { name: "주제", exact: true })
      .locator('option[value="saved-topic"]'),
  ).toHaveText("저장 후 주제");
});

test("completed automatic classification refreshes the concept filter", async ({
  page,
}) => {
  await baseFixture(page);
  let classified = false;
  await page.route("**/api/v1/concepts?*", async (route) =>
    route.fulfill({
      json: success({
        items: classified
          ? [{ id: "classified-topic", name: "자동 연결 주제" }]
          : [],
        next_cursor: null,
      }),
    }),
  );
  await page.route(`**/api/v1/captures/${record.id}`, async (route) => {
    const capture = {
      ...record,
      concept_state: { status: classified ? "ready" : "pending" },
    };
    classified = true;
    return route.fulfill({ json: success(capture) });
  });
  await page.goto("/");
  await openLibrary(page);
  await page.getByRole("button", { name: new RegExp(record.title) }).click();
  await expect(page.locator(".record-detail h1")).toHaveText(record.title);
  await expect(page.locator(".record-detail")).not.toContainText(
    "저장한 기록의 주제를 연결하고 있어요.",
    { timeout: 8000 },
  );
  await openLibrary(page);
  await expect(
    page
      .getByRole("combobox", { name: "주제", exact: true })
      .locator('option[value="classified-topic"]'),
  ).toHaveText("자동 연결 주제", { timeout: 8000 });
});

test("back during a detail request clears loading and ignores the late record", async ({
  page,
}) => {
  await baseFixture(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/v1/captures/${record.id}`, async (route) => {
    await held;
    await route.fulfill({ json: success(record) });
  });
  await page.goto("/");
  await openLibrary(page);
  await page.getByRole("button", { name: new RegExp(record.title) }).click();
  await expect(page).toHaveURL(new RegExp(`#capture/${record.id}`));
  await expect(page.getByRole("main")).toContainText("기록을 불러오는 중");
  await page.goBack();
  await expect(page.getByRole("main")).not.toContainText("기록을 불러오는 중");
  const completed = page.waitForResponse((response) =>
    response.url().endsWith(`/captures/${record.id}`),
  );
  release();
  await completed;
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await expect(
    page.getByRole("heading", { name: record.title, exact: true }),
  ).toHaveCount(0);
});

test("a malformed record deep link shows a recoverable error", async ({
  page,
}) => {
  await baseFixture(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/#capture/%E0%A4%A");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "기록 주소가 올바르지 않습니다",
  );
  await page
    .getByRole("button", { name: "Cache Me If You Can 홈", exact: true })
    .click();
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  expect(errors).toEqual([]);
});

for (const newline of ["\r\n", "\n", "\r"]) {
  test(`SSE preserves Korean events split byte-by-byte with ${JSON.stringify(newline)} delimiters`, async ({
    page,
  }) => {
    test.skip(
      Boolean(process.env.SECOND_BRAIN_TEST_URL),
      "Vite source module regression; external API integration has separate tests.",
    );
    await baseFixture(page);
    await page.goto("/");
    const result = await page.evaluate(async (ending) => {
      // The production parser runs here; only transport is replaced in this isolated page.
      // @ts-expect-error Vite serves source modules during this test.
      const { streamQuestion } = await import("/src/api.ts");
      const events: { event: string; data: unknown }[] = [];
      const text =
        [
          `event: progress${ending}data: {"stage":"searching"}`,
          "event: completed" +
            ending +
            'data: {"parts":[{"text":"한국어 답변"}]}',
        ].join(ending + ending) +
        ending +
        ending;
      const bytes = new TextEncoder().encode(text);
      const original = window.fetch;
      window.fetch = async () =>
        new Response(
          new ReadableStream({
            start(controller) {
              for (const byte of bytes)
                controller.enqueue(new Uint8Array([byte]));
              controller.close();
            },
          }),
          { headers: { "content-type": "text/event-stream" } },
        );
      try {
        await streamQuestion(
          {},
          new AbortController().signal,
          (event: string, data: unknown) => events.push({ event, data }),
        );
      } finally {
        window.fetch = original;
      }
      return events;
    }, newline);
    expect(result).toEqual([
      { event: "progress", data: { stage: "searching" } },
      { event: "completed", data: { parts: [{ text: "한국어 답변" }] } },
    ]);
  });
}

test("settings polling cannot revive an older login state after logout", async ({
  page,
}) => {
  await baseFixture(page);
  await page.clock.install();
  let reads = 0;
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const connected = {
    auth: { connected: true, email: "fixture@example.test" },
    index: { status: "preparing", ready: false },
  };
  await page.route("**/api/v1/settings", async (route) => {
    reads++;
    const n = reads;
    if (n === 2) await held;
    await route
      .fulfill({
        json: success(
          n <= 2
            ? connected
            : {
                auth: { connected: false },
                index: { status: "ready", ready: true },
              },
        ),
      })
      .catch(() => {});
  });
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: success({ logged_out: true }) }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "설정", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "로그아웃", exact: true }),
  ).toBeVisible();
  await page.clock.fastForward(3100);
  await expect.poll(() => reads).toBe(2);
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Continue with ChatGPT" }),
  ).toBeVisible();
  release();
  await page.clock.fastForward(1000);
  await expect(
    page.getByRole("button", { name: "로그아웃", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Continue with ChatGPT" }),
  ).toBeVisible();
});

test("a late delete preview cannot reopen after navigating home", async ({
  page,
}) => {
  await baseFixture(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/captures/*/deletion-preview", async (route) => {
    await held;
    await route.fulfill({
      json: success({
        confirmation_token: "fixture-only",
        capture_id: record.id,
        title: record.title,
      }),
    });
  });
  await page.goto("/");
  await openLibrary(page);
  await page.getByRole("button", { name: new RegExp(record.title) }).click();
  await page.getByRole("button", { name: "기록 삭제", exact: true }).click();
  await page
    .getByRole("button", { name: "Cache Me If You Can 홈", exact: true })
    .click();
  const completed = page.waitForResponse((response) =>
    response.url().endsWith("/deletion-preview"),
  );
  release();
  await completed;
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await expect(
    page.getByRole("dialog", { name: "이 기록을 삭제할까요?" }),
  ).toHaveCount(0);
});
