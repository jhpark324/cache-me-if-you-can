import { expect, test, type Page } from "@playwright/test";
import type { AnswerResult, Capture, SourceRef } from "../src/types";

const stamp = "2026-11-02T00:00:00Z";
const captures: Capture[] = [
  [
    "복습 실험",
    "개념을 자신의 말로 설명하고 예제를 비교했다.\n\n막힌 부분만 다시 읽고 질문으로 남겼다.",
  ],
  [
    "홈 개요 밖의 회고",
    "지난 복습을 돌아보니 질문을 남긴 부분부터 다시 시작하기 편했다.",
  ],
  ["다른 생각", "산책하며 떠오른 아이디어를 기록했다."],
].map(([title, body_markdown], i) => ({
  id: `11111111-1111-4111-8111-${String(i).padStart(12, "0")}`,
  revision_id: `22222222-2222-4222-8222-${String(i).padStart(12, "0")}`,
  revision_no: 1,
  state_version: 1,
  title,
  body_markdown,
  kinds: ["knowledge"],
  visibility: "public",
  created_at: stamp,
  updated_at: stamp,
  is_current: true,
  node_status: "absent",
  index_state: { status: "ready" },
  concept_state: { status: "ready" },
  concepts: [],
  concept_hints: [],
  nodes: [],
  sources: [],
  review_state: "valid",
}));
const baseSource = (i: number): SourceRef => ({
  capture_id: captures[i].id,
  revision_id: captures[i].revision_id,
});
const sources: SourceRef[] = [
  {
    ...baseSource(0),
    node_id: "33333333-3333-4333-8333-333333333333",
    body_start: 0,
    body_end: 25,
  },
  {
    ...baseSource(0),
    node_id: "33333333-3333-4333-8333-333333333333",
    body_start: 27,
    body_end: 47,
  },
  { ...baseSource(1), body_start: 0, body_end: 30 },
];
const labels = [
  "예제와 함께 설명한 구간",
  "다음 질문을 남긴 구간",
  "복습을 돌아본 구간",
];
const answer: AnswerResult = {
  answer_id: "retrieval-fixture",
  evidence_status: "found",
  parts: [
    {
      part_id: "one-answer",
      kind: "stored_knowledge",
      text: "배운 개념을 자신의 말로 설명하고, 다음에 다시 볼 질문을 남겼습니다. 회고에서는 이 질문이 복습의 출발점이 되었다고 정리했습니다.",
      sources: [sources[0], sources[2]],
    },
  ],
  sources: [sources[0], sources[2]],
  limitations: [],
  retrieval: {
    items: sources.map((source, i) => ({
      source,
      label: labels[i],
      capture_label: captures[i === 2 ? 1 : 0].title!,
      cited: i !== 1,
    })),
    truncated: false,
  },
};
const homeGraph = {
  nodes: [0, 2].map((i) => ({
    id: captures[i].id,
    kind: "capture",
    label: captures[i].title,
    kinds: captures[i].kinds,
    source: baseSource(i),
  })),
  edges: [],
  truncated: false,
};

async function fixture(page: Page) {
  const calls: { path: string; method: string; body: any }[] = [];
  let releaseSlow!: () => void;
  let slowFinished = false;
  let saved: Capture | null = null;
  const slow = new Promise<void>((resolve) => {
    releaseSlow = resolve;
  });
  // Every API request, including mutations, stays inside this fixture.
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    const body = request.postDataJSON();
    calls.push({ path, method, body });
    const send = (data: unknown) =>
      route.fulfill({
        json: { schema_version: 1, ok: true, data },
      });
    if (path === "/session") return send({ csrf_token: "retrieval-fixture" });
    if (path === "/concepts") return send({ items: [], next_cursor: null });
    if (path === "/graph") return send(homeGraph);
    if (path === "/captures" && method === "GET")
      return send({
        items: saved ? [...captures, saved] : captures,
        next_cursor: null,
      });
    if (path === "/captures" && method === "POST") {
      saved = {
        ...captures[0],
        id: "44444444-4444-4444-8444-444444444444",
        revision_id: "55555555-5555-4555-8555-555555555555",
        title: body.title,
        body_markdown: body.body_markdown,
      };
      return send({
        capture: saved,
        committed_ref: null,
        warnings: [],
        replayed: false,
        result_state: "available",
      });
    }
    if (path.startsWith("/captures/") && method === "GET")
      return send(
        [saved, ...captures].find(
          (capture) => capture && path.endsWith(capture.id),
        ),
      );
    if (path === "/sources/resolve") {
      const capture = captures.find((item) => item.id === body.capture_id)!;
      return send({
        source: body,
        capture,
        text: Array.from(capture.body_markdown)
          .slice(body.body_start ?? 0, body.body_end ?? undefined)
          .join(""),
        node: null,
        is_current: true,
        current_revision_id: capture.revision_id,
        review_state: "valid",
      });
    }
    if (path === "/questions") {
      const question = body.question as string;
      if (question === "느린 질문") await slow;
      let result = answer;
      if (question === "근거 없는 질문")
        result = {
          ...answer,
          sources: [],
          parts: [
            {
              part_id: "none",
              kind: "general_explanation",
              text: "저장된 근거가 없습니다.",
              sources: [],
            },
          ],
          evidence_status: "none",
          retrieval: { items: [], truncated: false },
        };
      if (question === "이전 API 질문") {
        const { retrieval: _retrieval, ...legacy } = answer;
        result = legacy;
      }
      const events: [string, object][] = [["completed", { result }]];
      if (question === "완료 뒤 오류")
        events.push([
          "error",
          { error: { code: "FAILED", message: "응답을 완료하지 못했습니다." } },
        ]);
      if (question === "완료 뒤 취소") events.push(["cancelled", {}]);
      if (question === "완료 뒤 무효화") events.push(["invalidated", {}]);
      try {
        await route.fulfill({
          contentType: "text/event-stream",
          body: events
            .map(
              ([event, data]) =>
                `event: ${event}\ndata: ${JSON.stringify({ request_id: body.request_id, ...data })}\n\n`,
            )
            .join(""),
        });
      } catch {
        // A deliberately cancelled request may already be detached from the page.
      } finally {
        if (question === "느린 질문") slowFinished = true;
      }
      return;
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
  return { calls, releaseSlow, slowFinished: () => slowFinished };
}

const chunks = (page: Page) =>
  page.locator('.graph-label-layer [data-kind="retrieved_chunk"]');
const chunk = (page: Page, index: number) =>
  chunks(page).filter({ hasText: labels[index] });
async function ask(page: Page, question = "복습을 어떻게 이어갔어?") {
  await page
    .getByRole("textbox", { name: "저장된 지식 검색 또는 질문" })
    .fill(question);
  await page.getByRole("button", { name: "검색", exact: true }).click();
}
async function ready(page: Page) {
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "ready",
  );
}
async function complete(page: Page) {
  await ask(page);
  await expect(chunks(page)).toHaveCount(3);
}

test("검색은 맨 위에 있고 완료된 검색 구간과 인용을 같은 canvas에 표시한다", async ({
  page,
}, testInfo) => {
  const state = await fixture(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await ready(page);
  const searchDock = page.locator(".search-dock");
  const initial = (await searchDock.boundingBox())!;
  expect(initial.y).toBeGreaterThanOrEqual(12);
  expect(initial.y).toBeLessThanOrEqual(24);
  await expect(page.locator(".topbar")).toHaveCount(0);
  await expect(page.getByText("내 공간", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "새 기록", exact: true }),
  ).toHaveCount(1);
  const canvas = page.locator(".graph-world canvas");
  await canvas.evaluate((element) =>
    element.setAttribute("data-identity", "same-canvas"),
  );
  await page.screenshot({
    path: testInfo.outputPath("retrieval-desktop-before.png"),
    fullPage: true,
  });
  await complete(page);
  await expect(canvas).toHaveAttribute("data-identity", "same-canvas");
  expect((await searchDock.boundingBox())!.y).toBe(initial.y);
  await expect(chunk(page, 0)).toHaveAttribute("data-cited", "true");
  await expect(chunk(page, 1)).toHaveAttribute("data-cited", "false");
  await expect(chunk(page, 2)).toHaveAttribute("data-cited", "true");
  await expect(chunk(page, 0).locator(".graph-label-context")).toContainText(
    captures[0].title!,
  );
  await expect(chunk(page, 2).locator(".graph-label-context")).toContainText(
    captures[1].title!,
  );
  expect(await chunk(page, 0).getAttribute("data-node-id")).not.toBe(
    await chunk(page, 1).getAttribute("data-node-id"),
  );
  await expect(
    page
      .locator('.graph-label-layer [data-kind="capture"]')
      .filter({ hasText: captures[1].title! }),
  ).toHaveCount(1);
  const citedColor = await chunk(page, 0).evaluate(
    (element) => getComputedStyle(element).color,
  );
  const readColor = await chunk(page, 1).evaluate(
    (element) => getComputedStyle(element).color,
  );
  expect(citedColor).not.toBe(readColor);
  await page.screenshot({
    path: testInfo.outputPath("retrieval-desktop-answer.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "출처 1 보기", exact: true }).click();
  await expect(page.locator(".source-panel")).toContainText(captures[0].title!);
  expect(
    state.calls.filter((call) => call.path === "/sources/resolve").at(-1)?.body,
  ).toEqual(sources[0]);
  await expect(chunk(page, 0)).toHaveAttribute("data-selected", "true");
  await expect(chunk(page, 1)).toHaveAttribute("data-selected", "false");
  await expect(canvas).toHaveAttribute("data-identity", "same-canvas");
  await page.screenshot({
    path: testInfo.outputPath("retrieval-source-panel.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "출처 닫기", exact: true }).click();

  // Hit the actual WebGL node at its projected position. Re-read while the
  // source panel closes and resizes the Canvas; label height is independent.
  // Hover can match for one frame before the final resize projection settles.
  // Require the same point across samples before clicking its small hit target.
  let target: { index: number; x: number; y: number } | null = null;
  await expect
    .poll(async () => {
      const previous = target;
      target = await chunks(page).evaluateAll((elements, expectedLabels) => {
        for (const element of elements) {
          const canvas = element
            .closest(".graph-section")
            ?.querySelector(".graph-canvas");
          if (!canvas) continue;
          const origin = canvas.getBoundingClientRect();
          const x = origin.x + Number((element as HTMLElement).dataset.screenX);
          const y = origin.y + Number((element as HTMLElement).dataset.screenY);
          const index = expectedLabels.findIndex((label) =>
            element.textContent?.includes(label),
          );
          if (
            index >= 0 &&
            Number.isFinite(x) &&
            Number.isFinite(y) &&
            getComputedStyle(element).opacity === "1" &&
            document.elementFromPoint(x, y)?.tagName === "CANVAS"
          )
            return { index, x, y };
        }
        return null;
      }, labels);
      if (!target) return false;
      await page.mouse.move(target.x, target.y);
      return (
        previous?.index === target.index &&
        Math.abs(previous.x - target.x) < 0.5 &&
        Math.abs(previous.y - target.y) < 0.5 &&
        (await chunk(page, target.index).getAttribute("data-highlighted")) ===
        "true"
      );
    })
    .toBe(true);
  const hit = target as unknown as { index: number; x: number; y: number };
  const index = hit.index;
  expect(index).toBeGreaterThanOrEqual(0);
  await expect(chunk(page, index)).toHaveAttribute("data-highlighted", "true");
  await page.mouse.click(hit.x, hit.y);
  await expect(page.locator(".source-panel")).toBeVisible();
  expect(
    state.calls.filter((call) => call.path === "/sources/resolve").at(-1)?.body,
  ).toEqual(sources[index]);
  await expect(canvas).toHaveAttribute("data-identity", "same-canvas");
  expect(state.calls.filter((call) => call.path === "/questions")).toHaveLength(
    1,
  );
  expect(state.calls.filter((call) => call.path === "/search")).toHaveLength(0);
  expect(
    state.calls
      .filter((call) => call.method !== "GET")
      .every((call) => ["/questions", "/sources/resolve"].includes(call.path)),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("WebGL 없이도 키보드 목록에서 같은 기록의 다른 검색 구간을 연다", async ({
  page,
}, testInfo) => {
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: any[]
    ) {
      if (["webgl", "webgl2", "experimental-webgl"].includes(type)) return null;
      return getContext.apply(this, [type, ...args] as any);
    } as typeof getContext;
  });
  const state = await fixture(page);
  await page.goto("/");
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "fallback",
  );
  await ask(page);
  const search = page.getByRole("searchbox", { name: "연결 목록에서 찾기" });
  await search.fill(labels[1]);
  const selected = page.locator(
    '.graph-list button[data-kind="retrieved_chunk"]',
  );
  await expect(selected).toHaveCount(1);
  await expect(selected).toContainText("검색한 내용");
  await expect(selected).toHaveAttribute("data-cited", "false");
  await selected.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".source-panel")).toContainText(captures[0].title!);
  expect(
    state.calls.filter((call) => call.path === "/sources/resolve").at(-1)?.body,
  ).toEqual(sources[1]);
  await expect(selected).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({
    path: testInfo.outputPath("retrieval-webgl-fallback.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "출처 닫기", exact: true }).click();
  await search.fill(captures[1].title!);
  const anchor = page.locator(".graph-list").getByRole("button", {
    name: `${captures[1].title} 기록`,
    exact: true,
  });
  await anchor.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".source-panel")).toContainText(captures[1].title!);
  expect(
    state.calls.filter((call) => call.path === "/sources/resolve").at(-1)?.body,
  ).toEqual(baseSource(1));
  await expect(anchor).toHaveAttribute("aria-pressed", "true");
});

test("새 질문·닫기·필터에서 검색 그래프를 비우고 늦은 응답을 무시한다", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/");
  await ready(page);
  await complete(page);
  await ask(page, "느린 질문");
  await expect(page.getByRole("region", { name: "검색 응답" })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  await expect
    .poll(
      () =>
        state.calls.filter(
          (call) =>
            call.path === "/questions" && call.body.question === "느린 질문",
        ).length,
    )
    .toBe(1);
  await expect(chunks(page)).toHaveCount(0);
  await page
    .getByRole("button", { name: "검색 응답 닫기", exact: true })
    .click();
  state.releaseSlow();
  await expect.poll(state.slowFinished).toBe(true);
  await expect(page.getByRole("article", { name: "AI 답변" })).toHaveCount(0);
  await expect(chunks(page)).toHaveCount(0);
  await complete(page);
  await page
    .getByRole("combobox", { name: "기록 유형", exact: true })
    .selectOption("knowledge");
  await expect(chunks(page)).toHaveCount(0);
  await complete(page);
  await page
    .getByRole("button", { name: "검색 응답 닫기", exact: true })
    .click();
  await expect(chunks(page)).toHaveCount(0);
  expect(state.calls.filter((call) => call.path === "/search")).toHaveLength(0);
});

test("취소·실패·무효화와 근거 없는 응답은 이전 청크를 남기지 않는다", async ({
  page,
}) => {
  await fixture(page);
  await page.goto("/");
  await ready(page);
  for (const question of ["완료 뒤 오류", "완료 뒤 취소", "완료 뒤 무효화"]) {
    await complete(page);
    await ask(page, question);
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(chunks(page)).toHaveCount(0);
    await expect(page.getByRole("article", { name: "AI 답변" })).toHaveCount(0);
  }
  for (const question of ["근거 없는 질문", "이전 API 질문"]) {
    await complete(page);
    await ask(page, question);
    await expect(page.getByRole("article", { name: "AI 답변" })).toBeVisible();
    await expect(chunks(page)).toHaveCount(0);
    await expect(
      page.locator('.graph-label-layer [data-kind="capture"]'),
    ).toHaveCount(homeGraph.nodes.length);
  }
});

test("답변을 기록으로 저장하면 임시 검색 그래프를 제거한다", async ({
  page,
}) => {
  const state = await fixture(page);
  await page.goto("/");
  await ready(page);
  await complete(page);
  await page
    .getByRole("button", { name: "답변을 기록으로 저장", exact: true })
    .click();
  await page
    .getByLabel("제목 선택", { exact: true })
    .fill("검색 답변을 정리한 기록");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "검색 답변을 정리한 기록", exact: true }),
  ).toBeVisible();
  await expect(chunks(page)).toHaveCount(0);
  await expect(page.getByRole("article", { name: "AI 답변" })).toHaveCount(0);
  expect(
    state.calls.filter(
      (call) => call.path === "/captures" && call.method === "POST",
    ),
  ).toHaveLength(1);
});

test("모바일 검색·메뉴·출처와 축소 모션 그래프 도구가 겹치지 않는다", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page);
  await page.goto("/");
  await ready(page);
  await expect(page.locator(".app-shell")).toHaveAttribute(
    "data-reduced-motion",
    "true",
  );
  const menu = page.getByRole("button", { name: "메뉴 열기", exact: true });
  const form = page.locator(".search-form");
  const menuBox = (await menu.boundingBox())!;
  const formBox = (await form.boundingBox())!;
  const inputBox = (await page
    .getByRole("textbox", { name: "저장된 지식 검색 또는 질문" })
    .boundingBox())!;
  expect(formBox.y).toBeLessThanOrEqual(24);
  expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(inputBox.x);
  expect(
    Math.abs(menuBox.y + menuBox.height / 2 - formBox.y - formBox.height / 2),
  ).toBeLessThan(6);
  await menu.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "기록과 탐색" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
  await complete(page);
  await page.screenshot({
    path: testInfo.outputPath("retrieval-mobile-answer.png"),
    fullPage: true,
  });
  const controls = (await page.locator(".graph-controls").boundingBox())!;
  expect(controls.y).toBeGreaterThan(formBox.y + formBox.height);
  expect(controls.x).toBeGreaterThanOrEqual(0);
  expect(controls.x + controls.width).toBeLessThanOrEqual(390);
  const citation = page.getByRole("button", {
    name: "출처 2 보기",
    exact: true,
  });
  await citation.click();
  await expect(page.getByRole("dialog")).toContainText(captures[1].title!);
  await expect(chunk(page, 2)).toHaveAttribute("data-selected", "true");
  await page.screenshot({
    path: testInfo.outputPath("retrieval-mobile-source.png"),
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(citation).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
