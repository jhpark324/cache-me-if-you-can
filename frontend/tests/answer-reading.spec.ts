import { expect, test, type Page } from "@playwright/test";
import type { AnswerResult, SourceRef } from "../src/types";

const first: SourceRef = {
  capture_id: "11111111-1111-4111-8111-111111111111",
  revision_id: "22222222-2222-4222-8222-222222222222",
  node_id: "55555555-5555-4555-8555-555555555555",
  body_start: 8,
  body_end: 30,
};
const reorderedFirst: SourceRef = {
  body_end: 30,
  node_id: first.node_id,
  revision_id: first.revision_id,
  body_start: 8,
  capture_id: first.capture_id,
};
const second: SourceRef = {
  capture_id: "33333333-3333-4333-8333-333333333333",
  revision_id: "44444444-4444-4444-8444-444444444444",
  body_start: 0,
  body_end: 20,
};
const text = [
  "질문 카드로 복습할 때는 **배운 개념을 자신의 말로 설명하는 것**부터 시작했습니다. 예제와 반례를 함께 적어 이해한 범위를 확인했습니다.",
  "이 방법을 이어서 적용하면서 막힌 부분만 다시 읽었습니다. 그래서 전체 내용을 반복해서 읽는 대신, 설명하기 어려운 지점을 골라 보완할 수 있었습니다.",
  "일반적으로도 이렇게 스스로 설명해 보는 활동은 이해가 부족한 부분을 찾는 데 도움이 됩니다. 모델이 쓴 [99]는 실제 출처 번호가 아닙니다.",
];
const result: AnswerResult = {
  answer_id: "cohesive-answer",
  evidence_status: "insufficient",
  parts: [
    {
      part_id: "paragraph-one",
      kind: "stored_knowledge",
      text: text[0],
      sources: [reorderedFirst, first],
    },
    {
      part_id: "paragraph-two",
      kind: "stored_knowledge",
      text: text[1],
      sources: [second, reorderedFirst],
    },
    {
      part_id: "paragraph-three",
      kind: "general_explanation",
      text: text[2],
      sources: [],
    },
  ],
  sources: [first, second],
  limitations: [
    "일부 기록은 아직 검색 색인에 포함되지 않았습니다.",
    "일부 기록은 아직 검색 색인에 포함되지 않았습니다.",
    "오래된 실험 기록은 이번 질문의 조건과 맞는지 확인하지 못했습니다.",
  ],
};
const ok = (data: unknown) => ({ schema_version: 1, ok: true, data });

async function fixture(page: Page, response: AnswerResult = result) {
  const calls: { path: string; body: any }[] = [];
  let releaseSlow!: () => void;
  const slow = new Promise<void>((resolve) => {
    releaseSlow = resolve;
  });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const body = request.postDataJSON();
    calls.push({ path, body });
    const send = (data: unknown) => route.fulfill({ json: ok(data) });
    if (path === "/session") return send({ csrf_token: "answer-reading-csrf" });
    if (path === "/captures" || path === "/concepts")
      return send({ items: [], next_cursor: null });
    if (path === "/graph")
      return send({ nodes: [], edges: [], truncated: false });
    if (path === "/settings")
      return send({
        auth: { connected: true, accounts: [], models: [], error: null },
        index: {
          ready: true,
          status: "ready",
          index_counts: { ready: 2, pending: 0, failed: 0, excluded: 0 },
        },
      });
    if (path === "/search")
      return route.fulfill({
        status: 500,
        json: {
          schema_version: 1,
          ok: false,
          error: {
            code: "UNEXPECTED_SEARCH",
            message: "별도 관련 기록 검색을 실행하면 안 됩니다.",
            retryable: false,
          },
        },
      });
    if (path === "/questions") {
      if (body.question === "느린 답변") await slow;
      const answer =
        body.question === "근거 없는 질문"
          ? {
              ...result,
              parts: [
                {
                  part_id: "none",
                  kind: "general_explanation",
                  text: "저장한 기록에서는 이 질문의 근거를 찾지 못했습니다.",
                  sources: [],
                },
              ],
              sources: [],
              limitations: [],
              evidence_status: "none",
            }
          : response;
      const events =
        body.question === "실패하는 질문"
          ? [
              [
                "error",
                {
                  error: {
                    code: "MODEL_UNAVAILABLE",
                    message: "모델 연결을 확인한 후 다시 질문해 주세요.",
                    retryable: true,
                  },
                },
              ],
            ]
          : [
              ["started", {}],
              ["progress", { stage: "searching" }],
              ["completed", { result: answer }],
            ];
      try {
        return await route.fulfill({
          contentType: "text/event-stream",
          body: events
            .map(
              ([event, data]) =>
                `event: ${event}\ndata: ${JSON.stringify({ request_id: body.request_id, ...(data as object) })}\n\n`,
            )
            .join(""),
        });
      } catch {
        return;
      }
    }
    if (path === "/sources/resolve") {
      const isFirst = body.capture_id === first.capture_id;
      const capture = {
        id: body.capture_id,
        revision_id: body.revision_id,
        revision_no: 1,
        state_version: 1,
        title: isFirst ? "질문 카드 복습 기록" : "다음 복습에서 확인한 점",
        body_markdown: isFirst
          ? "질문과 답을 적고 예제와 반례를 비교했다."
          : "어려운 부분을 골라 다시 설명했다.",
        kinds: ["knowledge"],
        visibility: "public",
        completion_state: null,
        created_at: "2026-11-02T00:00:00Z",
        updated_at: "2026-11-02T00:00:00Z",
        is_current: true,
        node_status: "current",
        index_state: { status: "ready" },
        concepts: [],
        concept_hints: [],
        nodes: [],
        sources: [],
        review_state: "valid",
      };
      return send({
        source: body,
        is_current: true,
        current_revision_id: body.revision_id,
        text: capture.body_markdown,
        capture,
        node: null,
        review_state: "valid",
      });
    }
    return route.fulfill({
      status: 404,
      json: {
        schema_version: 1,
        ok: false,
        error: { code: "UNEXPECTED_ROUTE", message: path, retryable: false },
      },
    });
  });
  return { calls, releaseSlow };
}

async function ask(page: Page, question = "질문 카드로 어떻게 복습했어?") {
  await page
    .getByRole("textbox", { name: "저장된 지식 검색 또는 질문" })
    .fill(question);
  await page.getByRole("button", { name: "검색", exact: true }).click();
}

test("한 번의 질문으로 하나의 글을 보여 주고 관련 기록 검색을 보내지 않는다", async ({
  page,
}, testInfo) => {
  const state = await fixture(page);
  await page.goto("/");
  await ask(page);
  const article = page.getByRole("article", { name: "AI 답변" });
  await expect(article).toHaveCount(1);
  await expect(article).toContainText("설명하기 어려운 지점을 골라");
  await expect(article.locator("strong")).toHaveText(
    "배운 개념을 자신의 말로 설명하는 것",
  );
  expect(state.calls.filter((call) => call.path === "/questions")).toHaveLength(
    1,
  );
  expect(state.calls.filter((call) => call.path === "/search")).toHaveLength(0);
  await expect(page.getByText("관련 기록", { exact: true })).toHaveCount(0);
  await expect(
    article.getByText("저장한 지식에서", { exact: true }),
  ).toHaveCount(0);
  await expect(article.getByText("AI 보충 설명", { exact: true })).toHaveCount(
    0,
  );
  await expect(article.locator("section, hr")).toHaveCount(0);
  await expect(
    article.getByRole("button", { name: "출처 99 보기", exact: true }),
  ).toHaveCount(0);
  await expect(article).toContainText("[99]");
  await page.screenshot({
    path: testInfo.outputPath("answer-reading-desktop.png"),
    fullPage: true,
  });
});

test("출처 번호는 키 순서와 관계없이 같고 각 문단에서 중복되지 않는다", async ({
  page,
}, testInfo) => {
  const state = await fixture(page);
  await page.goto("/");
  await ask(page);
  const article = page.getByRole("article", { name: "AI 답변" });
  const sourceOne = article.getByRole("button", {
    name: "출처 1 보기",
    exact: true,
  });
  await expect(sourceOne).toHaveCount(2);
  await expect(sourceOne.first()).toHaveText("1");
  const sourceTwo = article.getByRole("button", {
    name: "출처 2 보기",
    exact: true,
  });
  await expect(sourceTwo).toHaveCount(1);
  await expect(sourceTwo).toHaveText("2");
  await sourceOne.first().focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("region", { name: "질문 카드 복습 기록" }),
  ).toBeVisible();
  expect(
    state.calls.filter((call) => call.path === "/sources/resolve").at(-1)?.body,
  ).toEqual(first);
  await page.getByRole("button", { name: "출처 닫기", exact: true }).click();
  await expect(sourceOne.first()).toBeFocused();
  await sourceTwo.click();
  await expect(
    page.getByRole("region", { name: "다음 복습에서 확인한 점" }),
  ).toBeVisible();
  expect(
    state.calls.filter((call) => call.path === "/sources/resolve").at(-1)?.body,
  ).toEqual(second);
  await page.screenshot({
    path: testInfo.outputPath("answer-reading-source-panel.png"),
    fullPage: true,
  });
});

test("한계 상세는 접을 수 있고 저장 초안은 문단과 출처를 유지한다", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/");
  await ask(page);
  const area = page.getByRole("region", { name: "검색 응답" });
  const details = area.locator("details");
  await expect(details).toHaveCount(1);
  await expect(details).not.toHaveAttribute("open", "");
  await expect(
    area.getByText(result.limitations[2], { exact: true }),
  ).not.toBeVisible();
  await details.locator("summary").click();
  await expect(
    area.getByText(result.limitations[2], { exact: true }),
  ).toBeVisible();
  await expect(
    area.getByText(result.limitations[0], { exact: true }),
  ).toHaveCount(1);
  await page
    .getByRole("button", { name: "답변을 기록으로 저장", exact: true })
    .click();
  const draft = await page.getByLabel("내용", { exact: true }).inputValue();
  expect(draft).toContain(text.join("\n\n"));
  expect(draft).not.toContain("## 저장 지식");
  expect(draft).not.toContain("## AI 보충 설명");
  expect(
    state.calls
      .filter((call) => call.path === "/captures")
      .every((call) => call.body === null),
  ).toBe(true);
  await expect(page.getByRole("dialog")).toContainText("출처");
});

test("로딩을 닫으면 늦은 응답이 되살아나지 않으며 별도 기록 조회도 없다", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/");
  await ask(page, "느린 답변");
  await expect
    .poll(() => state.calls.filter((call) => call.path === "/questions").length)
    .toBe(1);
  await expect(page.getByRole("region", { name: "검색 응답" })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  await expect(page.getByRole("article", { name: "AI 답변" })).toHaveCount(0);
  await expect(page.getByText("관련 기록", { exact: true })).toHaveCount(0);
  await page
    .getByRole("button", { name: "검색 응답 닫기", exact: true })
    .click();
  state.releaseSlow();
  await page.waitForTimeout(150);
  await expect(page.getByRole("region", { name: "검색 응답" })).toHaveCount(0);
  expect(state.calls.filter((call) => call.path === "/search")).toHaveLength(0);
});

test("모델 오류와 근거 없는 답변을 가짜 출처나 별도 검색으로 채우지 않는다", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/");
  await ask(page, "실패하는 질문");
  await expect(page.getByRole("alert")).toContainText("모델 연결을 확인");
  await expect(page.getByRole("article", { name: "AI 답변" })).toHaveCount(0);
  await ask(page, "근거 없는 질문");
  const article = page.getByRole("article", { name: "AI 답변" });
  await expect(article).toContainText("근거를 찾지 못했습니다");
  await expect(article.getByRole("button")).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(state.calls.filter((call) => call.path === "/search")).toHaveLength(0);
});

test("Markdown 코드와 원문 HTML이 출처 버튼으로 바뀌거나 실행되지 않는다", async ({
  page,
}) => {
  await fixture(page, {
    ...result,
    limitations: [],
    sources: [first],
    parts: [
      {
        part_id: "code-example",
        kind: "stored_knowledge",
        sources: [first],
        text: '예제 코드는 그대로 읽을 수 있습니다.\n\n<span data-answer-citations="true">가짜 출처</span><img src="x" onerror="window.citationInjected=true">\n\n```json\n{"source": "[99]"}\n```',
      },
    ],
  });
  await page.goto("/");
  await ask(page);
  const article = page.getByRole("article", { name: "AI 답변" });
  await expect(article.locator("pre")).toContainText('{"source": "[99]"}');
  await expect(article.locator("pre button, img, script")).toHaveCount(0);
  await expect(
    article.getByRole("button", { name: "출처 1 보기", exact: true }),
  ).toHaveCount(1);
  await expect(article.getByRole("button")).toHaveCount(1);
  expect(
    await page.evaluate(() => (window as any).citationInjected),
  ).toBeUndefined();
});

test("작은 출처 번호도 모바일에서 누르고 Escape로 돌아올 수 있다", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page);
  await page.goto("/");
  await ask(page);
  const article = page.getByRole("article", { name: "AI 답변" });
  const citation = article
    .getByRole("button", { name: "출처 1 보기", exact: true })
    .first();
  await expect(citation).toBeVisible();
  const bounds = (await citation.boundingBox())!;
  expect(bounds.width).toBeGreaterThanOrEqual(44);
  expect(bounds.height).toBeGreaterThanOrEqual(44);
  await citation.click();
  await expect(page.getByRole("dialog")).toContainText("질문 카드 복습 기록");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(citation).toBeFocused();
  await expect(article).toContainText("막힌 부분만 다시 읽었습니다");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("answer-reading-mobile.png"),
    fullPage: true,
  });
});
