import { test, expect, type Page } from "@playwright/test";
test.use({ timezoneId: "Asia/Seoul", reducedMotion: "reduce" });
const capture = (id: string, title: string, created_at: string) => ({
  id,
  title,
  created_at,
  updated_at: "2026-11-03T12:00:00Z",
  revision_id: "revision-" + id,
  revision_created_at: created_at,
  revision_no: 1,
  state_version: 1,
  body_markdown: "저장 당시의 내용을 읽습니다.",
  kinds: ["knowledge"],
  visibility: "public",
  completion_state: null,
  index_state: { status: "ready" },
  concept_state: { status: "completed" },
  node_status: "absent",
  is_current: true,
  review_state: "valid",
  concepts: [],
  concept_hints: [],
  nodes: [],
  sources: [],
  excerpt: "기록을 남긴 날짜로 탐색합니다.",
});
const a = capture("a", "월 경계 직후", "2026-10-31T15:00:00Z");
const b = capture("b", "같은 날 다른 기록", "2026-10-31T16:00:00Z");
const c = capture("c", "10월 마지막 기록", "2026-10-31T14:59:59Z");
async function fixture(page: Page, stale = false) {
  const urls: string[] = [];
  const questions: any[] = [];
  let staleOnce = stale;
  let created: ReturnType<typeof capture> | null = null;
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    const path = u.pathname.replace("/api/v1", "");
    urls.push(path + u.search);
    const send = (data: unknown) =>
      route.fulfill({ json: { schema_version: 1, ok: true, data } });
    if (path === "/session") return send({ csrf_token: "test" });
    if (path === "/concepts")
      return send({
        items: [{ id: "topic", name: "기록 탐색" }],
        next_cursor: null,
      });
    if (path === "/graph")
      return send({ nodes: [], edges: [], truncated: false });
    if (path === "/captures" && req.method() === "POST") {
      const body = req.postDataJSON();
      created = capture("new", body.title, "2026-11-03T00:00:00Z");
      created.body_markdown = body.body_markdown;
      return send({
        capture: created,
        result_state: "available",
        warnings: [],
      });
    }
    if (path === "/captures") {
      if (staleOnce && u.searchParams.has("cursor")) {
        staleOnce = false;
        return route.fulfill({
          status: 409,
          json: {
            ok: false,
            error: {
              code: "CURSOR_STALE",
              message:
                "목록 기준이 변경되었습니다. 처음부터 다시 조회해 주세요.",
            },
          },
        });
      }
      if (u.searchParams.has("created_from"))
        return send({ items: [b, a], next_cursor: null });
      if (u.searchParams.get("sort") === "title_asc")
        return send({ items: [c, b, a], next_cursor: null });
      return send(
        u.searchParams.has("cursor")
          ? { items: [a, c], next_cursor: null }
          : { items: created ? [created, b] : [b], next_cursor: "page2" },
      );
    }
    if (path.startsWith("/captures/"))
      return send([a, b, c].find((item) => item.id === path.split("/").at(-1)));
    if (path === "/questions") {
      questions.push(req.postDataJSON());
      return route.fulfill({
        contentType: "text/event-stream",
        body:
          "event: completed\ndata: " +
          JSON.stringify({
            parts: [
              {
                part_id: "p",
                kind: "general_explanation",
                text: "전체 기록에서 질문합니다.",
                sources: [],
              },
            ],
            sources: [],
            limitations: [],
            evidence_status: "none",
          }) +
          "\n\n",
      });
    }
    return route.fulfill({ status: 500, body: "Unexpected " + path });
  });
  return { urls, questions };
}

test("저장일 타임라인은 현지 날짜로 페이지를 합치며 월 경계를 서버에 전송한다", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/#timeline");
  await expect(page.locator("[data-record-id]")).toHaveCount(1);
  await page.getByRole("button", { name: "기록 더 보기", exact: true }).click();
  await expect(page.locator("[data-record-id]")).toHaveCount(3);
  await expect(page.locator(".rb-date-group")).toHaveCount(2);
  await expect(page.locator(".rb-date-group").first()).toContainText(
    "11월 1일",
  );
  await expect(page.locator(".rb-date-group").last()).toContainText(
    "10월 31일",
  );
  await page.getByLabel("저장 월", { exact: true }).fill("2026-11");
  await expect(page.locator("[data-record-id]")).toHaveCount(2);
  const latest = new URL(
    "http://test" +
      state.urls.filter((url) => url.startsWith("/captures?")).at(-1),
  );
  expect(latest.searchParams.get("created_from")).toBe(
    "2026-10-31T15:00:00.000Z",
  );
  expect(latest.searchParams.get("created_before")).toBe(
    "2026-11-30T15:00:00.000Z",
  );
  expect(latest.searchParams.has("cursor")).toBe(false);
});

test("월 필터는 타임라인에만 적용하고 제목 정렬은 목록 API에 보낸다", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/#timeline");
  await page.getByLabel("저장 월", { exact: true }).fill("2026-11");
  await page.getByRole("button", { name: "모든 기록", exact: true }).click();
  await page.getByLabel("기록 정렬", { exact: true }).selectOption("title_asc");
  await expect(page.locator("[data-record-id]").first()).toHaveAttribute(
    "data-record-id",
    "c",
  );
  const latest = new URL(
    "http://test" +
      state.urls.filter((url) => url.startsWith("/captures?")).at(-1),
  );
  expect(latest.searchParams.get("sort")).toBe("title_asc");
  expect(latest.searchParams.has("created_from")).toBe(false);
  await page.getByRole("button", { name: "타임라인", exact: true }).click();
  await expect(page.getByLabel("저장 월", { exact: true })).toHaveValue(
    "2026-11",
  );
  await expect
    .poll(() =>
      new URL(
        "http://test" +
          state.urls.filter((url) => url.startsWith("/captures?")).at(-1),
      ).searchParams.get("sort"),
    )
    .toBe("created_desc");
});

test("목록 조건은 홈 그래프와 질문을 제한하지 않으며 타임라인으로 돌아올 수 있다", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/#timeline");
  await page.getByLabel("기록 유형", { exact: true }).selectOption("knowledge");
  await page.locator('[data-record-id="b"]').click();
  await expect(page.locator("#record-title")).toBeFocused();
  await page
    .locator(".record-detail")
    .getByRole("button", { name: "타임라인", exact: true })
    .click();
  await expect(page.locator('[data-record-id="b"]')).toBeFocused();
  await expect(page.getByLabel("기록 유형", { exact: true })).toHaveValue(
    "knowledge",
  );
  await page.getByRole("button", { name: "지식 공간", exact: true }).click();
  await page.getByLabel("저장된 지식 검색 또는 질문").fill("전체 지식");
  await page.getByRole("button", { name: "검색", exact: true }).click();
  await expect(page.locator(".answer-area")).toContainText(
    "전체 기록에서 질문합니다.",
  );
  expect(state.questions[0]).not.toHaveProperty("kinds");
  expect(state.questions[0]).not.toHaveProperty("concept_ids");
  expect(
    state.urls
      .filter((url) => url.startsWith("/graph"))
      .every((url) => !url.includes("kinds") && !url.includes("concept_ids")),
  ).toBe(true);
});

test("만료 커서는 이전 목록에 덧붙이지 않고 처음부터 다시 불러온다", async ({
  page,
}) => {
  await fixture(page, true);
  await page.goto("/#library");
  await page.getByRole("button", { name: "기록 더 보기", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("처음부터");
  await page
    .getByRole("button", { name: "다시 불러오기", exact: true })
    .click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator("[data-record-id]")).toHaveCount(1);
});

for (const width of [320, 390, 1024, 1440])
  test(`기록·타임라인 ${width}px 표시와 탐색`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    await fixture(page);
    await page.goto("/#timeline");
    await expect(page.locator("[data-record-id]")).toHaveCount(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const row = page.locator("[data-record-id]").first();
    await row.click();
    await expect(page.locator(".record-detail")).toBeVisible();
    await page
      .locator(".record-detail")
      .getByRole("button", { name: "타임라인", exact: true })
      .click();
    await expect(row).toBeFocused();
    if (width <= 800) {
      await page
        .getByRole("button", { name: "메뉴 열기", exact: true })
        .click();
      await page
        .getByRole("button", { name: "모든 기록", exact: true })
        .click();
    } else
      await page
        .getByRole("button", { name: "모든 기록", exact: true })
        .click();
    await expect(page.locator(".rb-heading h1")).toHaveText("모든 기록");
    await page.getByRole("button", { name: "새 기록", exact: true }).click();
    await expect(
      page.getByRole("textbox", { name: "제목 선택", exact: true }),
    ).toBeFocused();
    await page.getByRole("button", { name: "편집 닫기" }).click();
    await expect(
      page.getByRole("button", { name: "새 기록", exact: true }),
    ).toBeFocused();
  });

test("타임라인에서 만든 기록은 상세와 브라우저 뒤로가기에 원래 보기를 유지한다", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "타임라인", exact: true }).click();
  await page.getByRole("button", { name: "새 기록", exact: true }).click();
  await page
    .getByRole("textbox", { name: "제목 선택", exact: true })
    .fill("새 타임라인 기록");
  await page
    .getByRole("textbox", { name: "내용", exact: true })
    .fill("계속 기억할 내용입니다.");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.locator(".record-detail h1")).toHaveText(
    "새 타임라인 기록",
  );
  await expect(
    page
      .locator(".record-detail")
      .getByRole("button", { name: "타임라인", exact: true }),
  ).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/#timeline$/);
  await expect(page.locator('[data-record-id="new"]')).toBeVisible();
});

test("브라우저 뒤로가기는 각 상세를 연 기록 보기까지 복원한다", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/#timeline");
  await page.locator('[data-record-id="b"]').click();
  await page
    .locator("nav")
    .getByRole("button", { name: "모든 기록", exact: true })
    .click();
  await page.getByRole("button", { name: "기록 더 보기", exact: true }).click();
  await page.locator('[data-record-id="a"]').click();
  await expect(page.locator(".record-detail")).toContainText("월 경계 직후");
  await page.goBack();
  await page.goBack();
  await expect(page.locator(".record-detail")).toContainText(
    "같은 날 다른 기록",
  );
  await expect(
    page
      .locator(".record-detail")
      .getByRole("button", { name: "타임라인", exact: true }),
  ).toBeVisible();
});

for (const view of ["library", "timeline"])
  test(`${view} 본문 바로가기는 현재 보기와 주소를 유지한다`, async ({
    page,
  }) => {
    await fixture(page);
    await page.goto("/#" + view);
    const skip = page.getByRole("link", { name: "본문으로 이동" });
    await skip.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("main")).toBeFocused();
    await expect(page).toHaveURL(new RegExp("#" + view + "$"));
    await expect(page.locator(".record-browser")).toBeVisible();
  });
