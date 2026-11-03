import { test, expect, type Page, type Route } from "@playwright/test";
import { openLibrary } from "./navigation";
const captureId = "11111111-1111-4111-8111-111111111111",
  revisionId = "22222222-2222-4222-8222-222222222222";
const ref = { capture_id: captureId, revision_id: revisionId };
const base = {
  id: captureId,
  revision_id: revisionId,
  revision_no: 1,
  state_version: 1,
  title: "트랜잭션 공부",
  body_markdown: "원자성은 **전부 반영하거나 취소**하는 성질이다.",
  kinds: ["knowledge"],
  visibility: "public",
  completion_state: null,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
  revision_created_at: "2026-11-02T00:00:00Z",
  is_current: true,
  node_status: "absent",
  index_state: { status: "pending" },
  concept_state: { status: "pending" },
  concepts: [],
  concept_hints: [],
  nodes: [],
  sources: [],
  review_state: "valid",
};
const success = (data: unknown) => ({ schema_version: 1, ok: true, data });
function answer(question: string) {
  return {
    answer_id: "answer",
    limitations: [],
    parts: [
      {
        part_id: "1",
        kind: "stored_knowledge",
        text: question + " 답변: 원자성은 변경을 함께 처리합니다.",
        sources: [ref],
      },
    ],
    evidence_status: "found",
    sources: [ref],
  };
}
async function fixture(page: Page, initial = false) {
  let record: any = initial ? structuredClone(base) : null;
  let session = false;
  const calls: { path: string; method: string; body: any }[] = [];
  let failCreate = false;
  let conflict = false;
  await page.route("**/api/v1/**", async (route) => {
    const r = route.request(),
      u = new URL(r.url()),
      path = u.pathname.replace("/api/v1", ""),
      method = r.method(),
      body = r.postDataJSON();
    calls.push({ path, method, body });
    const send = (data: unknown) => route.fulfill({ json: success(data) });
    const fail = (code: string, message: string, status = 409) =>
      route.fulfill({
        status,
        json: {
          schema_version: 1,
          ok: false,
          error: { code, message, retryable: false },
        },
      });
    if (path === "/session") {
      session = true;
      return send({ csrf_token: "test-csrf" });
    }
    if (!session) return fail("SESSION_REQUIRED", "세션 없음", 401);
    if (method !== "GET" && r.headers()["x-csrf-token"] !== "test-csrf")
      return fail("CSRF_REQUIRED", "CSRF 없음", 403);
    if (path === "/graph")
      return send({
        nodes: record
          ? [
              {
                id: record.id,
                kind: "capture",
                label: record.title,
                source: ref,
                kinds: record.kinds,
              },
            ]
          : [],
        edges: [],
        truncated: false,
      });
    if (path === "/concepts") return send({ items: [], next_cursor: null });
    if (path === "/captures" && method === "GET")
      return send({
        items: record ? [{ ...record, excerpt: record.body_markdown }] : [],
        next_cursor: null,
      });
    if (path === "/captures" && method === "POST") {
      if (failCreate) {
        failCreate = false;
        return fail(
          "TEMPORARY_ERROR",
          "일시적 오류입니다. 다시 저장해 주세요.",
          503,
        );
      }
      record = { ...structuredClone(base), ...body };
      return send({
        capture: record,
        request_id: body.request_id,
        replayed: false,
        result_state: "available",
        committed_ref: ref,
        warnings: [],
      });
    }
    if (path === `/captures/${captureId}` && method === "GET")
      return record
        ? send(record)
        : fail("NOT_FOUND", "조회할 수 없는 기록", 404);
    if (path === `/captures/${captureId}` && method === "PATCH") {
      if (conflict) return fail("VERSION_CONFLICT", "기록이 변경됨");
      record = { ...record, ...body.changes, revision_no: 2, state_version: 2 };
      return send({
        capture: record,
        request_id: body.request_id,
        replayed: false,
        result_state: "available",
        committed_ref: ref,
        warnings: [],
      });
    }
    if (path.endsWith("/deletion-preview"))
      return send({
        confirmation_token: "x".repeat(40),
        capture_id: captureId,
        expected_revision_id: revisionId,
        expected_state_version: 1,
        title: record.title,
        expires_at: "2026-11-02T00:05:00Z",
      });
    if (path.endsWith("/deletion")) {
      record = null;
      return send({
        capture_id: captureId,
        deleted_at: "2026-11-02T00:01:00Z",
      });
    }
    if (path === "/sources/resolve")
      return send({
        source: body,
        is_current: true,
        current_revision_id: revisionId,
        text: base.body_markdown,
        capture: base,
        node: null,
        review_state: "valid",
      });
    if (path === "/search" && body.query === "긴 질문")
      return fail("QUERY_TOO_LONG", "검색어가 너무 깁니다.");
    if (path === "/search")
      return send({
        items: [
          {
            source: ref,
            excerpt: base.body_markdown,
            score: 1,
            score_kind: "rrf",
          },
        ],
        next_cursor: null,
      });
    if (path === "/questions") {
      const question = body.question;
      if (question === "느린 질문")
        await new Promise((r) => setTimeout(r, 650));
      const events =
        question === "변경된 근거"
          ? [
              ["started", {}],
              ["answer_part", { part: answer(question).parts[0] }],
              ["invalidated", { part_ids: ["1"], reason: "source_changed" }],
            ]
          : [
              ["started", {}],
              ["progress", { stage: "searching" }],
              ["completed", { result: answer(question) }],
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
    if (path === "/settings")
      return send({
        auth: { connected: false, accounts: [], models: [], error: null },
        index: {
          status: "unloaded",
          ready: false,
          index_counts: {
            ready: 0,
            pending: record ? 1 : 0,
            failed: 0,
            excluded: 0,
          },
        },
        data_dir: "/tmp/second-brain-test",
      });
    if (path === "/index/prepare") return send({ status: "preparing" });
    return fail("NOT_FOUND", "테스트에서 처리하지 않은 경로 " + path, 404);
  });
  return {
    calls,
    failNextCreate: () => {
      failCreate = true;
    },
    conflict: () => {
      conflict = true;
    },
  };
}
async function openEditor(page: Page) {
  await openLibrary(page);
  await page
    .getByRole("button", { name: "새 기록", exact: true })
    .last()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
}
async function search(page: Page, question: string) {
  await page
    .getByRole("textbox", { name: "저장된 지식 검색 또는 질문" })
    .fill(question);
  await page.getByRole("button", { name: "검색", exact: true }).click();
}
test("빈 화면에서 실제 저장 응답을 보여 주며 세션과 CSRF를 먼저 확보한다", async ({
  page,
}) => {
  const f = await fixture(page);
  await page.goto("/");
  await expect(page.getByText("첫 번째 생각을 남겨보세요")).toBeVisible();
  await openLibrary(page);
  const filter = page.getByRole("combobox", { name: "기록 유형", exact: true });
  await expect(filter.locator("option")).toHaveText([
    "모든 유형",
    "지식",
    "경험·회고",
    "맥락",
    "아이디어·계획",
    "결정",
    "자료",
  ]);
  await openEditor(page);
  await page.getByText("유형과 공개 범위", { exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("checkbox")).toHaveCount(6);
  for (const name of [
    "지식",
    "경험·회고",
    "맥락",
    "아이디어·계획",
    "결정",
    "자료",
  ])
    await expect(
      page.getByRole("checkbox", { name, exact: true }),
    ).not.toBeChecked();
  await page
    .getByRole("textbox", { name: "제목 선택", exact: true })
    .fill("오늘 배운 원자성");
  await page.getByLabel("내용", { exact: true }).fill(base.body_markdown);
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.locator(".record-detail h1")).toHaveText(
    "오늘 배운 원자성",
  );
  expect(f.calls[0].path).toBe("/session");
  const create = f.calls.find(
    (c) => c.path === "/captures" && c.method === "POST",
  );
  expect(create?.body.visibility).toBe("public");
  expect(create?.body.kinds).toEqual([]);
  await expect(page.locator(".record-detail")).toContainText(
    "전부 반영하거나 취소",
  );
  await expect(page.getByRole("dialog")).not.toBeVisible();
});
test("저장 재시도는 같은 request_id를 사용하고 수정 충돌은 초안을 보존한다", async ({
  page,
}) => {
  const f = await fixture(page);
  f.failNextCreate();
  await page.goto("/");
  await openEditor(page);
  await page.getByLabel("내용", { exact: true }).fill("보존할 초안");
  await page.getByText("유형과 공개 범위", { exact: true }).click();
  await page.getByRole("checkbox", { name: "경험·회고", exact: true }).check();
  await page
    .getByRole("checkbox", { name: "아이디어·계획", exact: true })
    .check();
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("다시 저장");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.locator(".record-detail")).toContainText("보존할 초안");
  const writes = f.calls.filter(
    (c) => c.path === "/captures" && c.method === "POST",
  );
  expect(writes).toHaveLength(2);
  expect(writes[0].body.request_id).toBe(writes[1].body.request_id);
  expect(writes[0].body.kinds).toEqual(["episode", "idea"]);
  expect(writes[1].body.kinds).toEqual(["episode", "idea"]);
  await expect(page.locator(".record-detail")).toContainText("경험·회고");
  await expect(page.locator(".record-detail")).toContainText("아이디어·계획");
  f.conflict();
  await page.getByRole("button", { name: "기록 수정", exact: true }).click();
  await page.getByLabel("내용", { exact: true }).fill("충돌해도 보존할 초안");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("다른 곳에서 수정");
  await expect(page.getByLabel("내용", { exact: true })).toHaveValue(
    "충돌해도 보존할 초안",
  );
  await page.getByText("유형과 공개 범위", { exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "경험·회고", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "아이디어·계획", exact: true }),
  ).toBeChecked();
});
test("삭제는 미리보기 후 사람의 확인 버튼을 눌러야 전송한다", async ({
  page,
}) => {
  const f = await fixture(page, true);
  await page.goto("/#capture/" + captureId);
  await expect(page.locator(".record-detail h1")).toHaveText(base.title);
  await page.getByRole("button", { name: "기록 삭제", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "복원 기능은 제공하지 않습니다",
  );
  expect(f.calls.filter((c) => c.path.endsWith("/deletion"))).toHaveLength(0);
  await page.getByRole("button", { name: "취소", exact: true }).click();
  await expect(page.locator(".record-detail")).toBeVisible();
  await page.getByRole("button", { name: "기록 삭제", exact: true }).click();
  await page.getByRole("button", { name: "삭제하기", exact: true }).click();
  await expect(page.getByText("첫 번째 생각을 남겨보세요")).toBeVisible();
  expect(f.calls.filter((c) => c.path.endsWith("/deletion"))).toHaveLength(1);
  await expect(page.getByText("휴지통", { exact: true })).toHaveCount(0);
});
test("새 검색이 늦게 오는 이전 결과를 덮지 않고 출처의 정확한 참조를 조회한다", async ({
  page,
}) => {
  const f = await fixture(page, true);
  await page.goto("/");
  await search(page, "느린 질문");
  await search(page, "새 질문");
  await expect(page.getByRole("article", { name: "AI 답변" })).toContainText(
    "새 질문 답변",
  );
  await page.waitForTimeout(800);
  await expect(
    page.getByRole("article", { name: "AI 답변" }),
  ).not.toContainText("느린 질문 답변");
  await page.getByRole("button", { name: "출처 1 보기", exact: true }).click();
  await expect(page.getByRole("region", { name: base.title })).toBeVisible();
  const resolve = f.calls.find((c) => c.path === "/sources/resolve");
  expect(resolve?.body).toEqual(ref);
  await expect(page.locator(".source-panel")).toContainText("현재 저장본");
  await page.getByRole("button", { name: "출처 닫기" }).click();
  await expect(page.getByRole("article", { name: "AI 답변" })).toContainText(
    "새 질문 답변",
  );
});
test("무효화된 중간 답변은 확정 응답으로 표시하지 않는다", async ({ page }) => {
  await fixture(page, true);
  await page.goto("/");
  await search(page, "변경된 근거");
  await expect(page.getByRole("alert")).toContainText("출처가 변경");
  await expect(page.getByRole("article", { name: "AI 답변" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "답변을 기록으로 저장" }),
  ).toHaveCount(0);
});
test("모바일 출처 모달은 Escape로 닫고 답변과 포커스를 유지한다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page, true);
  await page.goto("/");
  await search(page, "원자성");
  await page.getByRole("button", { name: "출처 1 보기", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(await page.locator(".workspace").getAttribute("inert")).not.toBeNull();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("article", { name: "AI 답변" })).toContainText(
    "원자성 답변",
  );
  await expect(
    page.getByRole("button", { name: "출처 1 보기", exact: true }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/mobile-workspace.png",
    fullPage: true,
  });
});
test("설정은 사용자 동작 전 모델 다운로드를 시작하지 않는다", async ({
  page,
}) => {
  const f = await fixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "설정", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Continue with ChatGPT" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "모델 준비", exact: true }),
  ).toBeVisible();
  expect(f.calls.filter((c) => c.path === "/index/prepare")).toHaveLength(0);
  await page.getByRole("button", { name: "모델 준비", exact: true }).click();
  await expect
    .poll(() => f.calls.filter((c) => c.path === "/index/prepare").length)
    .toBe(1);
});

test("긴 질문도 별도 직접 검색 없이 AI 응답만 요청한다", async ({ page }) => {
  const fixtureState = await fixture(page, true);
  await page.goto("/");
  await search(page, "긴 질문");
  await expect(page.getByRole("article", { name: "AI 답변" })).toContainText(
    "긴 질문 답변",
  );
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(
    fixtureState.calls.filter((call) => call.path === "/search"),
  ).toHaveLength(0);
  expect(
    fixtureState.calls.filter((call) => call.path === "/questions"),
  ).toHaveLength(1);
});

test("질문 길이는 Unicode code point로 검사하고 원문을 자르지 않는다", async ({
  page,
}) => {
  await fixture(page, true);
  const questions: string[] = [];
  await page.route("**/api/v1/questions", (route) => {
    const body = route.request().postDataJSON();
    questions.push(body.question);
    return route.fulfill({
      contentType: "text/event-stream",
      body: `event: completed\ndata: ${JSON.stringify({ request_id: body.request_id, result: answer("허용된 질문") })}\n\n`,
    });
  });
  await page.goto("/");
  const allowed = "😀".repeat(10000);
  await search(page, allowed);
  await expect(page.getByRole("article", { name: "AI 답변" })).toContainText(
    "허용된 질문",
  );
  expect(questions).toEqual([allowed]);
  await search(page, allowed + "가");
  await expect(page.getByRole("alert")).toContainText("최대 10,000자");
  expect(questions).toHaveLength(1);
  await expect(
    page.getByRole("textbox", { name: "저장된 지식 검색 또는 질문" }),
  ).toHaveValue(allowed + "가");
});
test("편집과 설정 모달은 첫 Escape로 닫힌다", async ({ page }) => {
  await fixture(page);
  await page.goto("/");
  await openEditor(page);
  await expect(
    page.getByRole("textbox", { name: "제목 선택", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "설정", exact: true }).click();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("heading", { name: "설정", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("서버 재시작 세션 오류는 같은 본문으로 한 번만 재시도한다", async ({
  page,
}) => {
  const fixtureState = await fixture(page);
  let attempts = 0;
  const writes: any[] = [];
  await page.route("**/api/v1/captures", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    attempts++;
    writes.push(route.request().postDataJSON());
    if (attempts === 1)
      return route.fulfill({
        status: 401,
        json: {
          schema_version: 1,
          ok: false,
          error: {
            code: "SESSION_REQUIRED",
            message: "세션을 갱신해 주세요.",
            retryable: false,
          },
        },
      });
    return route.fallback();
  });
  await page.goto("/");
  await openEditor(page);
  await page
    .getByLabel("내용", { exact: true })
    .fill("세션 갱신 후 보존할 기록");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.locator(".record-detail")).toContainText(
    "세션 갱신 후 보존할 기록",
  );
  expect(writes).toHaveLength(2);
  expect(writes[0]).toEqual(writes[1]);
  expect(fixtureState.calls.filter((c) => c.path === "/session")).toHaveLength(
    2,
  );
});
test("반복된 CSRF 오류는 두 번째 시도에서 멈추고 초안을 유지한다", async ({
  page,
}) => {
  await fixture(page);
  let attempts = 0;
  await page.route("**/api/v1/captures", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    attempts++;
    return route.fulfill({
      status: 403,
      json: {
        schema_version: 1,
        ok: false,
        error: {
          code: "CSRF_REQUIRED",
          message: "세션 확인에 실패했습니다.",
          retryable: false,
        },
      },
    });
  });
  await page.goto("/");
  await openEditor(page);
  await page
    .getByLabel("내용", { exact: true })
    .fill("확인 실패해도 남는 초안");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("세션 확인에 실패");
  expect(attempts).toBe(2);
  await expect(page.getByLabel("내용", { exact: true })).toHaveValue(
    "확인 실패해도 남는 초안",
  );
});
test("공개 범위만 정정하면 본문을 PATCH에 다시 보내지 않는다", async ({
  page,
}) => {
  const f = await fixture(page, true);
  await page.goto("/#capture/" + captureId);
  await page.getByRole("button", { name: "기록 수정", exact: true }).click();
  await page.getByText("유형과 공개 범위", { exact: true }).click();
  await page.getByLabel("공개 범위", { exact: false }).selectOption("private");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(f.calls.find((c) => c.method === "PATCH")?.body.changes).toEqual({
    visibility: "private",
  });
});
