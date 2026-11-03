import { test, expect, type Page } from "@playwright/test";

const captureId = "11111111-1111-4111-8111-111111111111";
const revisionId = "22222222-2222-4222-8222-222222222222";
const source = { capture_id: captureId, revision_id: revisionId };
const base = {
  id: captureId,
  revision_id: revisionId,
  revision_no: 1,
  state_version: 1,
  title: "저장된 기록",
  body_markdown: "저장된 본문",
  kinds: ["knowledge"],
  visibility: "public",
  completion_state: null,
  concept_hints: [],
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
  is_current: true,
  node_status: "absent",
  index_state: { status: "pending" },
  concept_state: { status: "pending" },
  concepts: [],
  nodes: [],
  sources: [],
  review_state: "valid",
};

async function fixture(page: Page, initial = false) {
  let record: any = initial ? structuredClone(base) : null;
  let failures = 0;
  let pending: Promise<void> | null = null;
  const writes: any[] = [];
  // All API requests are synthetic; these tests never write to a running DB.
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    const method = request.method();
    const body = request.postDataJSON();
    const send = (data: unknown) =>
      route.fulfill({ json: { schema_version: 1, ok: true, data } });
    if (path === "/session") return send({ csrf_token: "editor-fixture" });
    if (path === "/concepts") return send({ items: [], next_cursor: null });
    if (path === "/graph")
      return send({ nodes: [], edges: [], truncated: false });
    if (path === "/settings")
      return send({
        auth: { connected: false, accounts: [], models: [] },
        index: { status: "not_prepared", index_counts: {} },
        data_dir: "/fixture-only",
      });
    if (path === "/captures" && method === "GET")
      return send({ items: record ? [record] : [], next_cursor: null });
    if (path === `/captures/${captureId}` && method === "GET")
      return send(record);
    if (
      (path === "/captures" && method === "POST") ||
      (path === `/captures/${captureId}` && method === "PATCH")
    ) {
      writes.push(body);
      if (pending) await pending;
      if (failures > 0) {
        failures--;
        return route.fulfill({
          status: 503,
          json: {
            schema_version: 1,
            ok: false,
            error: {
              code: "TEMPORARY_ERROR",
              message: "일시적 오류입니다. 다시 저장해 주세요.",
              retryable: true,
            },
          },
        });
      }
      record = { ...base, ...(record || {}), ...(body.changes || body) };
      return send({
        capture: record,
        committed_ref: source,
        request_id: body.request_id,
        replayed: false,
        result_state: "available",
        warnings: [],
      });
    }
    if (path === "/search") return send({ items: [], next_cursor: null });
    if (path === "/questions")
      return route.fulfill({
        contentType: "text/event-stream",
        body: `event: completed\ndata: ${JSON.stringify({
          request_id: body.request_id,
          result: {
            answer_id: "editor-answer",
            parts: [
              {
                part_id: "1",
                kind: "stored_knowledge",
                text: "답변에서 전달한 초안입니다.",
                sources: [source],
              },
            ],
            sources: [source],
            limitations: [],
            evidence_status: "found",
          },
        })}\n\n`,
      });
    return route.fulfill({
      status: 404,
      json: {
        schema_version: 1,
        ok: false,
        error: {
          code: "NOT_FOUND",
          message: "Unexpected fixture route",
          retryable: false,
        },
      },
    });
  });
  return {
    writes,
    failNext: (count = 1) => {
      failures = count;
    },
    holdSave: () => {
      let release!: () => void;
      pending = new Promise<void>((resolve) => {
        release = resolve;
      });
      return () => {
        pending = null;
        release();
      };
    },
  };
}

const editor = (page: Page) =>
  page.getByRole("dialog", { name: /새 기록|기록 수정/ });
const confirmation = (page: Page) =>
  page.getByRole("alertdialog", { name: "작성 중인 내용을 버릴까요?" });
async function openEditor(page: Page) {
  const menu = page.getByRole("button", { name: "메뉴 열기", exact: true });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("button", { name: "새 기록", exact: true })
    .last()
    .click();
  await expect(editor(page)).toBeVisible();
}

for (const dismiss of ["Escape", "outside", "close", "cancel"]) {
  test(`미저장 초안은 ${dismiss} 닫기에서 확인하고 계속 작성과 Escape로 보존한다`, async ({
    page,
  }) => {
    const f = await fixture(page);
    await page.goto("/");
    await openEditor(page);
    await page.getByLabel("제목").fill("삭제하면 안 되는 제목");
    await page.getByLabel("내용", { exact: true }).fill("입력 중인 **본문**");
    if (dismiss === "Escape") await page.keyboard.press("Escape");
    if (dismiss === "outside") await page.mouse.click(8, 8);
    if (dismiss === "close")
      await page.getByRole("button", { name: "편집 닫기" }).click();
    if (dismiss === "cancel")
      await page.getByRole("button", { name: "취소", exact: true }).click();
    await expect(confirmation(page)).toBeVisible();
    await expect(page.getByRole("button", { name: "계속 작성" })).toBeFocused();
    await page.getByRole("button", { name: "계속 작성" }).click();
    await expect(confirmation(page)).toBeHidden();
    await expect(page.getByLabel("내용", { exact: true })).toHaveValue(
      "입력 중인 **본문**",
    );
    await page.getByLabel("내용", { exact: true }).focus();
    await page.keyboard.press("Escape");
    await expect(confirmation(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(confirmation(page)).toBeHidden();
    await expect(page.getByLabel("내용", { exact: true })).toBeFocused();
    await expect(page.getByLabel("제목")).toHaveValue("삭제하면 안 되는 제목");
    await page.getByRole("button", { name: "편집 닫기" }).click();
    await page.getByRole("button", { name: "버리기", exact: true }).click();
    await expect(editor(page)).toBeHidden();
    await expect(
      page.getByRole("button", { name: "새 기록", exact: true }).last(),
    ).toBeFocused();
    expect(f.writes).toHaveLength(0);
  });
}

test("빈 새 기록과 변경하지 않거나 되돌린 수정은 불필요한 확인 없이 닫힌다", async ({
  page,
}) => {
  await fixture(page, true);
  await page.goto("/");
  await openEditor(page);
  await page.keyboard.press("Escape");
  await expect(editor(page)).toBeHidden();
  await expect(confirmation(page)).toBeHidden();
  await expect(
    page.getByRole("button", { name: "새 기록", exact: true }).last(),
  ).toBeFocused();
  await page.goto("/#capture/" + captureId);
  await page.getByRole("button", { name: "기록 수정", exact: true }).click();
  await page.getByRole("button", { name: "편집 닫기" }).click();
  await expect(editor(page)).toBeHidden();
  await expect(confirmation(page)).toBeHidden();
  await expect(
    page.getByRole("button", { name: "기록 수정", exact: true }),
  ).toBeFocused();
  await page.getByRole("button", { name: "기록 수정", exact: true }).click();
  await page.getByLabel("내용", { exact: true }).fill("임시 변경");
  await page.getByLabel("내용", { exact: true }).fill(base.body_markdown);
  await page.keyboard.press("Escape");
  await expect(editor(page)).toBeHidden();
  await expect(confirmation(page)).toBeHidden();
});

test("저장 중 닫기와 편집 및 중복 저장을 막고 Ctrl Enter 저장을 지원한다", async ({
  page,
}) => {
  const f = await fixture(page);
  const release = f.holdSave();
  await page.goto("/");
  await openEditor(page);
  await page.getByLabel("내용", { exact: true }).fill("저장 중 보존할 내용");
  await page.keyboard.press("Control+Enter");
  await expect.poll(() => f.writes.length).toBe(1);
  await expect(
    page.getByRole("button", { name: "저장 중…", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("button", { name: "편집 닫기" })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "취소", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("내용", { exact: true })).toBeDisabled();
  await page.keyboard.press("Escape");
  await page.mouse.click(8, 8);
  await page.keyboard.press("Control+Enter");
  await expect(editor(page)).toBeVisible();
  await expect(confirmation(page)).toBeHidden();
  expect(f.writes).toHaveLength(1);
  release();
  await expect(editor(page)).toBeHidden();
  await expect(page.locator(".record-detail")).toContainText(
    "저장 중 보존할 내용",
  );
  await expect(page.locator(".record-detail h1")).toBeFocused();
});

test("실패한 저장은 내용과 request_id를 유지하고 변경된 내용은 새 요청으로 저장한다", async ({
  page,
}) => {
  const f = await fixture(page);
  f.failNext(2);
  await page.goto("/");
  await openEditor(page);
  await page.getByLabel("내용", { exact: true }).fill("재시도 초안");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("다시 저장");
  await expect(page.getByLabel("내용", { exact: true })).toHaveValue(
    "재시도 초안",
  );
  await page.getByRole("button", { name: "편집 닫기" }).click();
  await page.getByRole("button", { name: "계속 작성" }).click();
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect.poll(() => f.writes.length).toBe(2);
  await expect(page.getByRole("alert")).toContainText("다시 저장");
  expect(f.writes[0].request_id).toBe(f.writes[1].request_id);
  await page.getByLabel("내용", { exact: true }).fill("정정 후 저장할 초안");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(editor(page)).toBeHidden();
  expect(f.writes).toHaveLength(3);
  expect(f.writes[2].request_id).not.toBe(f.writes[1].request_id);
  expect(f.writes[2].body_markdown).toBe("정정 후 저장할 초안");
  await page.getByRole("button", { name: "기록 수정", exact: true }).click();
  await page
    .getByLabel("내용", { exact: true })
    .fill("같은 기록을 다시 정정한 내용");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(editor(page)).toBeHidden();
  await expect(page.locator(".record-detail")).toContainText(
    "같은 기록을 다시 정정한 내용",
  );
  await expect(page.locator(".record-detail h1")).toBeFocused();
  expect(f.writes[3].changes.body_markdown).toBe(
    "같은 기록을 다시 정정한 내용",
  );
});

test("답변에서 채운 새 기록도 첫 닫기부터 보호하고 출처와 함께 저장한다", async ({
  page,
}) => {
  const f = await fixture(page);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "저장된 지식 검색 또는 질문" })
    .fill("답변 저장 확인");
  await page.getByRole("button", { name: "검색", exact: true }).click();
  await page.getByRole("button", { name: "답변을 기록으로 저장" }).click();
  await expect(editor(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(confirmation(page)).toBeVisible();
  await page.getByRole("button", { name: "계속 작성" }).click();
  await expect(page.getByLabel("내용", { exact: true })).toHaveValue(
    "답변에서 전달한 초안입니다.",
  );
  await page.getByRole("button", { name: "미리 보기" }).click();
  await expect(page.locator(".editor-preview")).toContainText(
    "답변에서 전달한 초안",
  );
  await page.keyboard.press("Meta+Enter");
  await expect(editor(page)).toBeHidden();
  expect(f.writes).toHaveLength(1);
  expect(f.writes[0].sources).toEqual([source]);
});

test("작은 화면과 축소 모션에서 메타데이터 초안도 보호하며 확인 버튼이 화면 안에 있다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page);
  await page.goto("/");
  await openEditor(page);
  await page.getByText("유형과 공개 범위", { exact: true }).click();
  await page.getByRole("checkbox", { name: "지식", exact: true }).check();
  await editor(page).getByLabel("공개 범위").selectOption("private");
  await editor(page).getByLabel("완료 상태").selectOption("completed");
  await page.getByLabel("주제 힌트").fill("학습, 데이터베이스");
  await page.getByRole("button", { name: "편집 닫기" }).click();
  await expect(confirmation(page)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "계속 작성" }),
  ).toBeInViewport();
  await expect(
    page.getByRole("button", { name: "버리기", exact: true }),
  ).toBeInViewport();
  const box = await confirmation(page).boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  await page.keyboard.press("Escape");
  await expect(confirmation(page)).toBeHidden();
  await expect(
    page.getByRole("checkbox", { name: "지식", exact: true }),
  ).toBeChecked();
  await expect(editor(page).getByLabel("공개 범위")).toHaveValue("private");
  await expect(editor(page).getByLabel("완료 상태")).toHaveValue("completed");
  await expect(page.getByLabel("주제 힌트")).toHaveValue("학습, 데이터베이스");
});

test("모바일 메뉴에서 연 편집기를 취소하면 메뉴 열기로 초점이 돌아간다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fixture(page);
  await page.goto("/");
  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await page
    .getByRole("dialog", { name: "기록과 탐색" })
    .getByRole("button", { name: "새 기록", exact: true })
    .click();
  await expect(editor(page)).toBeVisible();
  await page.getByRole("button", { name: "편집 닫기" }).click();
  await expect(editor(page)).toBeHidden();
  await expect(
    page.getByRole("button", { name: "메뉴 열기", exact: true }),
  ).toBeFocused();
});
