import { expect, test, type Locator, type Page } from "@playwright/test";
import type {
  ArticleDocument,
  ArticleSummary,
  Capture,
  SourceRef,
} from "../src/types";

const articleId = "aa000001-1111-4111-8111-111111111111";
const recordId = "bb000002-2222-4222-8222-222222222222";
const title = "키워드로 찾고 의미로 보완하는 방법";
const summary = "같은 질문을 두 가지 검색 방식으로 살펴본다.";
const excerpt = "약어의 철자가 일치하는 기록을 먼저 찾았다.";
const prefix = "실험의 첫 번째 관찰\n\n";
const source: SourceRef = {
  capture_id: recordId,
  revision_id: "cc000003-3333-4333-8333-333333333333",
  body_start: prefix.length,
  body_end: prefix.length + excerpt.length,
};
const external = {
  kind: "external" as const,
  title: "검색 방식 비교 원문",
  url: "https://example.test/research/search",
  note: "이 자료는 실험에 사용한 검색 방식의 동작을 설명한다.",
};

function paragraphs(label: string) {
  return Array.from(
    { length: 26 },
    (_, i) =>
      `${label} ${i + 1}. 같은 질문을 다른 단어로 표현한 뒤, 어떤 관찰이 달라졌는지 확인했다.`,
  ).join("\n\n");
}

const citedRecord: Capture = {
  id: recordId,
  revision_id: source.revision_id,
  revision_no: 2,
  state_version: 3,
  title: "두 검색 방식의 관찰 기록",
  body_markdown: prefix + excerpt + "\n\n" + paragraphs("관찰"),
  kinds: ["knowledge"],
  visibility: "private",
  is_current: false,
  created_at: "2026-11-10T00:00:00Z",
  updated_at: "2026-11-12T00:00:00Z",
  node_status: "absent",
  index_state: { status: "ready" },
  concepts: [],
  concept_hints: [],
  nodes: [],
  sources: [],
  review_state: "valid",
};
const listed: ArticleSummary = {
  id: articleId,
  title,
  summary,
  topics: ["키워드 검색", "의미 검색"],
  created_at: "2026-11-15T00:00:00Z",
  updated_at: "2026-11-16T00:00:00Z",
};
const article: ArticleDocument = {
  ...listed,
  revision_id: "dd000004-4444-4444-8444-444444444444",
  revision_no: 1,
  body_markdown: [
    "## 검색 과정을 한눈에",
    "```article-flow\n질문 작성\n키워드 검색\n의미 검색\n결과 비교\n```",
    "| 방식 | 단서 |\n| --- | --- |\n| 키워드 | 약어 |\n| 의미 | 유사한 표현 |",
    paragraphs("실험 과정"),
    "## 관찰 결과",
    "약어를 넣은 경우를 보자. [1](#cite-1) 원문에서도 비교 기준을 확인할 수 있다. [2](#cite-2)",
    paragraphs("적용 예시"),
  ].join("\n\n"),
  citations: [{ kind: "record", source }, external],
  sources: [
    {
      source,
      availability: "available",
      review_state: "needs_review",
      reason: "source_changed",
    },
  ],
  review_state: "needs_review",
};

async function fixture(page: Page, document: ArticleDocument = article) {
  const resolved: SourceRef[] = [];
  const dataRequests: string[] = [];
  await page.route("**/api/v1/**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace("/api/v1", "");
    const send = (data: unknown) =>
      route.fulfill({ json: { schema_version: 1, ok: true, data } });
    if (path === "/session")
      return send({ csrf_token: "article-reading-token" });
    dataRequests.push(route.request().method() + " " + path + url.search);
    if (path === "/articles")
      return send({ items: [listed], next_cursor: null });
    if (path === "/articles/" + articleId) return send(document);
    if (path === "/sources/resolve") {
      resolved.push(route.request().postDataJSON());
      return send({
        source,
        is_current: false,
        current_revision_id: "ee000005-5555-4555-8555-555555555555",
        text: excerpt,
        capture: citedRecord,
        node: null,
        review_state: "valid",
      });
    }
    return route.fulfill({
      status: 404,
      json: { ok: false, error: { code: "NOT_FOUND", message: path } },
    });
  });
  return { resolved, dataRequests };
}

async function position(citation: Locator) {
  return citation.evaluate((element) => ({
    scroll: element.closest("section.article-workspace")!.scrollTop,
    y: element.getBoundingClientRect().top,
  }));
}

for (const [device, width, height] of [
  ["데스크톱", 1440, 900],
  ["모바일", 390, 844],
] as const) {
  test(`${device}에서 출처를 읽어도 본문 주소·위치·포커스를 유지한다`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const { resolved, dataRequests } = await fixture(page);
    await page.goto("/#article/" + articleId);
    const originalUrl = page.url();
    const reader = page.getByRole("article", { name: title });
    const citation = reader.getByRole("button", { name: "출처 1 보기" });
    await expect(
      reader.getByRole("list", { name: "단계별 흐름" }).getByRole("listitem"),
    ).toHaveText(["질문 작성", "키워드 검색", "의미 검색", "결과 비교"]);
    await expect(
      reader.getByRole("table").getByRole("cell", { name: "약어" }),
    ).toHaveCount(1);
    await page.screenshot({ path: testInfo.outputPath("article.png") });
    await citation.evaluate((element) =>
      element.scrollIntoView({ block: "center" }),
    );
    await citation.focus();
    const before = await position(citation);
    expect(before.scroll).toBeGreaterThan(0);
    expect(new Set(dataRequests)).toEqual(
      new Set(["GET /articles/" + articleId]),
    );
    expect(resolved).toEqual([]);
    await page.keyboard.press("Enter");
    const panelRole = device === "모바일" ? "dialog" : "region";
    const panel = page.getByRole(panelRole, { name: "출처 1", exact: true });
    await expect(panel).toBeVisible();
    await expect(
      panel.getByText(excerpt, { exact: true }).filter({ visible: true }),
    ).toHaveCount(1);
    await expect(panel).toContainText("과거 저장본");
    await expect(panel).toContainText("재검토");
    expect(resolved).toEqual([source]);
    await panel.getByText("기록 전체 보기", { exact: true }).click();
    const panelScroll = panel.locator(".article-source-scroll");
    await panelScroll.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    expect(
      await panelScroll.evaluate((element) => element.scrollTop),
    ).toBeGreaterThan(0);
    expect(page.url()).toBe(originalUrl);
    expect(await position(citation)).toEqual(before);
    await page.keyboard.press("Escape");
    await expect(panel).not.toBeVisible();
    await expect(citation).toBeFocused();
    expect(await position(citation)).toEqual(before);

    const externalCitation = reader.getByRole("button", {
      name: "출처 2 보기",
    });
    await externalCitation.click();
    const externalPanel = page.getByRole(panelRole, {
      name: "출처 2",
      exact: true,
    });
    await expect(externalPanel).toContainText(external.note);
    await expect(
      externalPanel.getByRole("heading", { name: external.title }),
    ).toBeVisible();
    const original = externalPanel.getByRole("link", { name: "원문 열기" });
    await expect(original).toHaveAttribute("href", external.url);
    expect(page.context().pages()).toHaveLength(1);
    await page.screenshot({ path: testInfo.outputPath("external-source.png") });
    await page
      .context()
      .route(external.url, (route) =>
        route.fulfill({ contentType: "text/plain", body: "검색 자료 원문" }),
      );
    const popup = page.waitForEvent("popup");
    await original.click();
    const externalPage = await popup;
    await expect(externalPage).toHaveURL(external.url);
    await externalPage.close();
    expect(page.url()).toBe(originalUrl);
    await externalPanel.getByRole("button", { name: "출처 닫기" }).click();
    await expect(externalCitation).toBeFocused();
    expect(resolved).toEqual([source]);
    expect(new Set(dataRequests)).toEqual(
      new Set(["GET /articles/" + articleId, "POST /sources/resolve"]),
    );
  });
}

test("아티클 전용 목록·직접 주소·새로고침과 브라우저 뒤로 가기가 같은 글을 가리킨다", async ({
  page,
}) => {
  const { dataRequests } = await fixture(page);
  await page.goto("/#articles");
  await expect(
    page.getByRole("button", { name: "아티클", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    page.getByRole("heading", { level: 1, name: "아티클", exact: true }),
  ).toBeVisible();
  const row = page.getByRole("link", { name: title, exact: true });
  await expect(row).toContainText(summary);
  await expect(row).toContainText("키워드 검색 · 의미 검색");
  await expect(
    page.getByRole("heading", { name: citedRecord.title! }),
  ).toHaveCount(0);
  await row.click();
  await expect(page).toHaveURL(new RegExp("#article/" + articleId + "$"));
  await page.reload();
  await expect(
    page.getByRole("heading", { name: title, level: 1 }),
  ).toBeVisible();
  await page.goBack();
  await expect(row).toBeVisible();
  await page.goForward();
  await expect(
    page.getByRole("heading", { name: title, level: 1 }),
  ).toBeVisible();
  await page.goto("/#article/" + recordId);
  await expect(page.getByRole("alert")).toContainText(
    "등록된 아티클을 찾을 수 없습니다",
  );
  await expect(page.getByRole("article")).toHaveCount(0);
  expect(new Set(dataRequests)).toEqual(
    new Set([
      "GET /articles",
      "GET /articles/" + articleId,
      "GET /articles/" + recordId,
    ]),
  );
});

test("더 보기를 누른 사이 아티클 목록이 변경되면 첫 페이지부터 갱신한다", async ({
  page,
}) => {
  await fixture(page);
  const cursor = "page+/=";
  let refreshed = false;
  await page.route(
    (url) => url.pathname === "/api/v1/articles",
    (route) => {
      const url = new URL(route.request().url());
      if (url.searchParams.get("cursor") === cursor) {
        refreshed = true;
        return route.fulfill({
          status: 409,
          json: {
            ok: false,
            error: { code: "CURSOR_STALE", message: "목록 변경" },
          },
        });
      }
      return route.fulfill({
        json: {
          ok: true,
          data: {
            items: [refreshed ? { ...listed, title: "수정한 아티클" } : listed],
            next_cursor: refreshed ? null : cursor,
          },
        },
      });
    },
  );
  await page.goto("/#articles");
  await expect(
    page.getByRole("link", { name: title, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "아티클 더 보기" }).click();
  await expect(page.getByRole("link", { name: "수정한 아티클" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: title, exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "아티클 더 보기" }),
  ).toHaveCount(0);
});

test("삭제된 기록 출처를 선택하면 주소를 유지하고 내용 조회를 생략한다", async ({
  page,
}) => {
  const { resolved, dataRequests } = await fixture(page, {
    ...article,
    sources: [
      {
        source,
        availability: "unavailable",
        review_state: "needs_review",
        reason: "source_deleted",
      },
    ],
  });
  await page.goto("/#article/" + articleId);
  const citation = page.getByRole("button", { name: "출처 1 보기" });
  await citation.click();
  const panel = page.getByRole("region", { name: "출처 1", exact: true });
  await expect(panel.getByRole("alert")).toContainText(
    "더 이상 열 수 없습니다",
  );
  await expect(panel).not.toContainText(excerpt);
  expect(resolved).toEqual([]);
  expect(new Set(dataRequests)).toEqual(
    new Set(["GET /articles/" + articleId]),
  );
  await panel.getByRole("button", { name: "출처 닫기" }).click();
  await expect(citation).toBeFocused();
  await expect(page).toHaveURL(new RegExp("#article/" + articleId + "$"));
});
