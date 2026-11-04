import { test, expect, type Page } from "@playwright/test";
const currentId = "31111111-1111-4111-8111-111111111111",
  otherId = "41111111-1111-4111-8111-111111111111";
const makeCapture = (id: string, title: string, body: string) => ({
  id,
  title,
  body_markdown: body,
  revision_id: id.replace("1111-4111", "2222-4222"),
  revision_no: 1,
  state_version: 1,
  kinds: ["knowledge"],
  visibility: "public",
  completion_state: null,
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
  is_current: true,
  node_status: "absent",
  index_state: { status: "ready" },
  concept_state: {
    status: "ready",
    job_id: "51111111-1111-4111-8111-111111111111",
  },
  concepts: [],
  concept_hints: [],
  nodes: [],
  sources: [],
  review_state: "valid",
});
const current = makeCapture(
    currentId,
    "새 학습 원칙",
    "😀 앞말. 반복 문장. 이제는 학습 뒤 질문으로 복습한다. 반복 문장.",
  ),
  other = makeCapture(
    otherId,
    "이전 학습 원칙",
    "😀 이전에는 단순히 읽기만 했다.",
  );
const ref = (record: any) => ({
  capture_id: record.id,
  revision_id: record.revision_id,
});
async function fixture(
  page: Page,
  { failed = false, mergeConflict = false } = {},
) {
  const records = new Map([
    [currentId, structuredClone(current)],
    [otherId, structuredClone(other)],
  ]);
  if (failed) records.get(currentId)!.concept_state.status = "failed";
  let relations: any[] = [];
  let firstConflict = mergeConflict;
  const writes: { path: string; body: any }[] = [];
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname.replace("/api/v1", ""),
      body = req.postDataJSON();
    const send = (data: unknown) =>
      route.fulfill({ json: { schema_version: 1, ok: true, data } });
    const fail = (code: string, message: string) =>
      route.fulfill({
        status: 409,
        json: {
          schema_version: 1,
          ok: false,
          error: { code, message, retryable: false },
        },
      });
    if (req.method() !== "GET") writes.push({ path, body });
    if (path === "/session") return send({ csrf_token: "csrf" });
    if (path === "/graph")
      return send({
        nodes: [...records.values()].map((r) => ({
          id: r.id,
          kind: "capture",
          label: r.title,
          source: ref(r),
        })),
        edges: [],
        truncated: false,
      });
    if (path === "/concepts") return send({ items: [], next_cursor: null });
    if (path === "/captures") {
      const query = url.searchParams.get("query") || "";
      return send({
        items: [...records.values()]
          .filter((r) => (r.title + r.body_markdown).includes(query))
          .map((r) => ({ ...r, excerpt: r.body_markdown })),
        next_cursor: null,
      });
    }
    if (path === "/captures/" + currentId) return send(records.get(currentId));
    if (path === "/captures/" + otherId) return send(records.get(otherId));
    if (path.endsWith("/merge")) {
      if (firstConflict) {
        firstConflict = false;
        return fail("VERSION_CONFLICT", "기록이 변경되었습니다.");
      }
      const capture = {
        ...records.get(currentId)!,
        body_markdown: body.merged_body_markdown,
        revision_no: 2,
        state_version: 2,
        sources: body.sources.map((s: any) => ({
          source: s,
          availability: "available",
          review_state: "valid",
        })),
      };
      records.set(currentId, capture);
      return send({
        capture,
        request_id: body.request_id,
        replayed: false,
        result_state: "available",
        committed_ref: ref(capture),
        warnings: [],
      });
    }
    if (path === "/relations" && req.method() === "GET")
      return send({ items: relations, next_cursor: null });
    if (path === "/relations" && req.method() === "POST") {
      const relation = {
        ...body,
        id: "relation-1",
        created_at: "2026-11-02T01:00:00Z",
        withdrawn_at: null,
      };
      relations.push(relation);
      return send(relation);
    }
    if (path.endsWith("/retraction")) {
      const result = {
        ...relations[0],
        withdrawn_at: "2026-11-02T01:01:00Z",
        withdrawal_reason: body.withdrawal_reason,
      };
      relations = [];
      return send(result);
    }
    if (path === "/sources/resolve") {
      const capture = records.get(body.capture_id)!;
      return send({
        source: body,
        is_current: true,
        current_revision_id: capture.revision_id,
        text: Array.from(capture.body_markdown)
          .slice(body.body_start ?? 0, body.body_end ?? undefined)
          .join(""),
        capture,
        node: null,
        review_state: "valid",
      });
    }
    if (path.endsWith("/concept-retry")) {
      const capture = records.get(currentId)!;
      capture.concept_state.status = "pending";
      return send({
        capture,
        request_id: body.request_id,
        replayed: false,
        result_state: "available",
        committed_ref: ref(capture),
        warnings: [],
      });
    }
    return fail("NOT_FOUND", "처리되지 않은 경로 " + path);
  });
  return { records, writes };
}
async function openCurrent(page: Page) {
  await page.goto("/#capture/" + currentId);
  await expect(page.locator(".record-detail h1")).toHaveText(current.title);
}
async function pick(page: Page, label: string, title: string) {
  const picker = page.getByRole("group", { name: label, exact: true });
  await picker.getByLabel(label + " 기록 찾기", { exact: true }).fill(title);
  await picker.getByRole("button", { name: new RegExp("^" + title) }).click();
  await picker
    .getByRole("button", { name: "이 기록 선택", exact: true })
    .click();
}
async function span(page: Page, label: string, start: number, end: number) {
  const box = page.getByRole("textbox", {
    name: label + " 원문 구간",
    exact: true,
  });
  await box.focus();
  await box.evaluate(
    (el, args) => {
      const input = el as HTMLTextAreaElement;
      input.setSelectionRange(args[0], args[1]);
      input.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    },
    [start, end],
  );
  await page
    .getByRole("group", { name: label, exact: true })
    .getByRole("button", { name: "선택한 구간 사용" })
    .click();
}
test("병합은 대상 버전과 출처를 보내고 충돌 후 초안·동일 요청을 보존한다", async ({
  page,
}) => {
  const f = await fixture(page, { mergeConflict: true });
  await openCurrent(page);
  await page.getByRole("button", { name: "기록 병합", exact: true }).click();
  await pick(page, "병합할 출처", other.title);
  await page.getByRole("button", { name: "최종 본문에 추가" }).click();
  const draft = await page
    .getByLabel("병합할 최종 내용", { exact: true })
    .inputValue();
  await page
    .getByRole("button", { name: "이 기록에 병합", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("다른 곳에서 수정");
  await expect(
    page.getByLabel("병합할 최종 내용", { exact: true }),
  ).toHaveValue(draft);
  await page
    .getByRole("button", { name: "이 기록에 병합", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const requests = f.writes.filter((w) => w.path.endsWith("/merge"));
  expect(requests).toHaveLength(2);
  expect(requests[0].body).toEqual(requests[1].body);
  expect(requests[0].body.expected_revision_id).toBe(current.revision_id);
  expect(requests[0].body.sources).toEqual([ref(other)]);
  expect(f.records.get(otherId)).toEqual(other);
  await expect(page.locator(".record-detail")).toContainText(
    other.body_markdown,
  );
});
test("지원 관계 유형을 선택하고 명확히 설명함 관계의 방향·근거를 보존해 저장·철회한다", async ({
  page,
}) => {
  const f = await fixture(page);
  await openCurrent(page);
  await page.getByRole("button", { name: "관계 관리", exact: true }).click();
  await page.getByRole("button", { name: "관계 추가", exact: true }).click();
  const relationType = page.getByLabel("관계의 의미", { exact: true });
  expect(
    await relationType.locator("option").evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value),
    ),
  ).toEqual([
    "related_to",
    "clarifies",
    "corrects",
    "supports",
    "contradicts",
    "merged_from",
    "supersedes",
  ]);
  await relationType.selectOption({ label: "명확히 설명함" });
  await pick(page, "대상", other.title);
  await page
    .getByRole("group", { name: "근거", exact: true })
    .getByRole("button", { name: "이 기록 선택", exact: true })
    .click();
  await page
    .getByLabel("근거 설명", { exact: true })
    .fill("복습 방식에 관한 두 기록을 비교했다.");
  await page.getByRole("button", { name: "관계 저장", exact: true }).click();
  await expect(page.locator(".relation-card")).toContainText(current.title);
  await expect(page.locator(".relation-card")).toContainText(other.title);
  await expect(page.locator(".relation-card")).toContainText("명확히 설명함");
  const created = f.writes.find((w) => w.path === "/relations")!.body;
  expect(created.relation_type).toBe("clarifies");
  expect(created.source).toEqual(ref(current));
  expect(created.target).toEqual(ref(other));
  expect(created.evidence).toEqual(ref(current));
  await page.getByRole("button", { name: /근거 확인/ }).click();
  await expect(page.locator(".reference-preview")).toContainText(
    current.body_markdown,
  );
  await page.getByRole("button", { name: "관계 철회", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "명확히 설명함 관계 철회", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "이유를 남기고 철회" }),
  ).toBeDisabled();
  await page
    .getByLabel("철회 이유", { exact: true })
    .fill("범위를 다시 확인해 관계를 철회한다.");
  await page.getByRole("button", { name: "이유를 남기고 철회" }).click();
  await expect(page.getByText("아직 연결한 관계가 없습니다.")).toBeVisible();
  expect(f.writes.some((w) => w.path.includes("/deletion"))).toBe(false);
  expect(f.records.get(currentId)).toEqual(current);
});
test("대체 관계는 원문의 정확한 Unicode 구간과 새 조건에서 이전 조건 방향을 보존한다", async ({
  page,
}) => {
  const f = await fixture(page);
  await openCurrent(page);
  await page.getByRole("button", { name: "관계 관리", exact: true }).click();
  await page.getByRole("button", { name: "관계 추가", exact: true }).click();
  await page
    .getByLabel("관계의 의미", { exact: true })
    .selectOption("supersedes");
  const newStart = current.body_markdown.indexOf("이제는"),
    newEnd = current.body_markdown.indexOf(" 반복 문장.", newStart);
  await span(page, "새 조건", newStart, newEnd);
  const picker = page.getByRole("group", { name: "이전 조건", exact: true });
  await picker.getByLabel("이전 조건 기록 찾기").fill(other.title);
  await picker
    .getByRole("button", { name: new RegExp("^" + other.title) })
    .click();
  await span(page, "이전 조건", 3, other.body_markdown.length);
  await span(page, "근거", newStart, newEnd);
  await page
    .getByLabel("적용 범위 · 필수")
    .fill("사용자의 현재 학습 복습 방식");
  await page
    .getByLabel("근거 설명 · 필수")
    .fill("이제는 질문으로 복습한다는 명시적 변경");
  await page.getByRole("button", { name: "관계 저장", exact: true }).click();
  await expect(page.locator(".relation-card")).toContainText(
    "이전 조건을 대체함",
  );
  const body = f.writes.find((w) => w.path === "/relations")!.body;
  expect(body.source.capture_id).toBe(currentId);
  expect(body.target.capture_id).toBe(otherId);
  expect(body.source.body_start).toBe(
    Array.from(current.body_markdown.slice(0, newStart)).length,
  );
  expect(body.source.body_end).toBe(
    Array.from(current.body_markdown.slice(0, newEnd)).length,
  );
  expect(body.target.body_start).toBe(2);
  expect(body.scope_note).toBeTruthy();
  expect(body.evidence_note).toBeTruthy();
});
test("실패한 주제 작업의 재시도는 현재 job와 버전을 보내며 본문을 유지한다", async ({
  page,
}) => {
  const f = await fixture(page, { failed: true });
  await openCurrent(page);
  await expect(
    page.getByText("기록은 저장되었지만 주제를 연결하지 못했습니다."),
  ).toBeVisible();
  await page.getByRole("button", { name: "주제 연결 다시 시도" }).click();
  await expect(
    page.getByText("저장한 기록의 주제를 연결하고 있어요."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "주제 연결 다시 시도" }),
  ).toHaveCount(0);
  const body = f.writes.find((w) => w.path.endsWith("/concept-retry"))!.body;
  expect(body.job_id).toBe(current.concept_state.job_id);
  expect(body.expected_revision_id).toBe(current.revision_id);
  expect(body.expected_state_version).toBe(1);
  expect(f.records.get(currentId)?.body_markdown).toBe(current.body_markdown);
  expect(f.records.get(currentId)?.revision_id).toBe(current.revision_id);
});
test("모바일 병합·관계 관리 모달은 가로 넘침 없이 키보드로 닫힌다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fixture(page);
  await openCurrent(page);
  await page.getByRole("button", { name: "기록 병합", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "기록 병합", exact: true }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "관계 관리", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "기록의 관계" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("로그인 시도 취소는 현재 연결된 계정의 로그아웃과 구분한다", async ({
  page,
}) => {
  await fixture(page);
  let pending = true,
    cancelled = 0;
  await page.route("**/api/v1/settings", (route) =>
    route.fulfill({
      json: {
        schema_version: 1,
        ok: true,
        data: {
          auth: {
            connected: true,
            pending_login: pending,
            email: "local@example.test",
            models: [],
          },
          index: {
            status: "not_prepared",
            ready: false,
            index_counts: { ready: 0, pending: 0, failed: 0, excluded: 0 },
          },
          data_dir: "/tmp/test",
        },
      },
    }),
  );
  await page.route("**/api/v1/auth/cancel", (route) => {
    pending = false;
    cancelled++;
    return route.fulfill({
      json: { schema_version: 1, ok: true, data: { cancelled: true } },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "설정", exact: true }).click();
  await page
    .getByRole("button", { name: "로그인 시도 취소", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "로그인 시도 취소", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "로그아웃", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("local@example.test")).toBeVisible();
  expect(cancelled).toBe(1);
});
