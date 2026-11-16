import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
async function selectSpan(
  page: Page,
  label: string,
  start: number,
  end: number,
) {
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
async function settle(page: Page) {
  await page.evaluate(async () => {
    await new Promise(requestAnimationFrame);
    await Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => {})),
    );
  });
}
test("실제 API: 실패 주제 재시도, 대상만 병합, 구간 관계 생성과 이유 있는 철회", async ({
  page,
}) => {
  test.skip(
    !process.env.CACHE_ME_INTEGRATION ||
      !process.env.CACHE_ME_QA_DATA_DIR,
    "격리된 실제 서버를 지정한 통합 검증에서 실행",
  );
  test.setTimeout(60000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  const seed = await page.evaluate(async () => {
    const session = await (await fetch("/api/v1/session")).json();
    const headers = {
      "Content-Type": "application/json",
      "X-CSRF-Token": session.data.csrf_token,
    };
    const create = async (title: string, body_markdown: string) => {
      const response = await fetch("/api/v1/captures", {
        method: "POST",
        headers,
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          title,
          body_markdown,
          kinds: ["context"],
        }),
      });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error.message);
      return result.data.capture;
    };
    const stamp = Date.now();
    return {
      current: await create(
        "현재 복습 방식 " + stamp,
        "😀 학습 기록. 이제는 질문으로 복습한다.",
      ),
      other: await create(
        "이전 복습 방식 " + stamp,
        "😀 이전에는 읽기만 했다.",
      ),
    };
  });
  // Seed only this newly-created fixture job. This does not simulate a model call.
  execFileSync(
    resolve(
      "../backend/.venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    ),
    [
      "-c",
      "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); result=db.execute(\"UPDATE concept_enrichment_jobs SET status='failed', error_code='QA_CLASSIFICATION_FAILURE', attempt_count=1 WHERE capture_id=? AND requested_revision_id=? AND status='pending'\", (sys.argv[2],sys.argv[3])); assert result.rowcount==1; db.commit(); db.close()",
      resolve(process.env.CACHE_ME_QA_DATA_DIR!, "cache-me.sqlite3"),
      seed.current.id,
      seed.current.revision_id,
    ],
  );
  await page.goto("/#capture/" + seed.current.id);
  await expect(page.locator(".record-detail h1")).toHaveText(
    seed.current.title,
  );
  await expect(
    page.getByRole("button", { name: "주제 연결 다시 시도" }),
  ).toBeVisible({ timeout: 20000 });
  const beforeRetry = await page.evaluate(
    async (id) => (await (await fetch("/api/v1/captures/" + id)).json()).data,
    seed.current.id,
  );
  const retryResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/concept-retry") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "주제 연결 다시 시도" }).click();
  const retry = (await (await retryResponse).json()).data;
  expect(retry.capture.concept_state.status).toBe("pending");
  expect(retry.capture.concept_state.job_id).toBe(
    beforeRetry.concept_state.job_id,
  );
  expect(retry.capture.revision_id).toBe(beforeRetry.revision_id);
  expect(retry.capture.body_markdown).toBe(seed.current.body_markdown);
  await page.getByRole("button", { name: "기록 병합", exact: true }).click();
  const mergePicker = page.getByRole("group", {
    name: "병합할 출처",
    exact: true,
  });
  await mergePicker
    .getByLabel("병합할 출처 기록 찾기", { exact: true })
    .fill(seed.other.title);
  await mergePicker
    .getByRole("button", { name: new RegExp("^" + seed.other.title) })
    .click();
  await mergePicker.getByRole("button", { name: "이 기록 선택" }).click();
  await page.getByRole("button", { name: "최종 본문에 추가" }).click();
  const mergedBody = await page
    .getByRole("textbox", { name: "병합할 최종 내용", exact: true })
    .inputValue();
  await page.getByRole("button", { name: "이 기록에 병합" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".record-detail")).toContainText("버전 2");
  const stored = await page.evaluate(
    async (ids) =>
      Promise.all(
        ids.map(
          async (id) =>
            (await (await fetch("/api/v1/captures/" + id)).json()).data,
        ),
      ),
    [seed.current.id, seed.other.id],
  );
  expect(stored[0].body_markdown).toBe(mergedBody);
  expect(stored[0].revision_id).not.toBe(seed.current.revision_id);
  expect(stored[1].revision_id).toBe(seed.other.revision_id);
  expect(stored[1].body_markdown).toBe(seed.other.body_markdown);
  expect(
    stored[0].sources.some((s: any) => s.source.capture_id === seed.other.id),
  ).toBe(true);
  await page.getByRole("button", { name: "관계 관리", exact: true }).click();
  await page.getByRole("button", { name: "관계 추가", exact: true }).click();
  await page
    .getByRole("combobox", { name: "관계의 의미", exact: true })
    .selectOption("supersedes");
  const start = mergedBody.indexOf("이제는"),
    end = start + "이제는 질문으로 복습한다.".length;
  await selectSpan(page, "새 조건", start, end);
  const targetPicker = page.getByRole("group", {
    name: "이전 조건",
    exact: true,
  });
  await targetPicker
    .getByLabel("이전 조건 기록 찾기", { exact: true })
    .fill(seed.other.title);
  await targetPicker
    .getByRole("button", { name: new RegExp("^" + seed.other.title) })
    .click();
  await selectSpan(page, "이전 조건", 3, seed.other.body_markdown.length);
  await selectSpan(page, "근거", start, end);
  await page
    .getByLabel("적용 범위 · 필수")
    .fill("사용자의 현재 복습 방식에 한함");
  await page
    .getByLabel("근거 설명 · 필수")
    .fill("이제는 질문으로 복습한다는 명시적 변경을 확인");
  const relationResponse = page.waitForResponse(
    (r) => r.url().endsWith("/relations") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "관계 저장", exact: true }).click();
  const created = (await (await relationResponse).json()).data;
  expect(created.source.capture_id).toBe(seed.current.id);
  expect(created.target.capture_id).toBe(seed.other.id);
  expect(created.source.body_start).toBe(
    Array.from(mergedBody.slice(0, start)).length,
  );
  expect(created.target.body_start).toBe(2);
  await expect(page.locator(".relation-card")).toContainText(
    "이전 조건을 대체함",
  );
  await page.getByRole("button", { name: /근거 확인/ }).click();
  await expect(page.locator(".reference-preview")).toContainText(
    "이제는 질문으로 복습한다.",
  );
  await settle(page);
  await page.screenshot({
    path: "test-results/management-desktop-relations.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await settle(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/management-mobile-relations.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "관계 철회", exact: true }).click();
  await page
    .getByLabel("철회 이유", { exact: true })
    .fill("범위를 재정리하기 위해 관계만 철회한다.");
  await page.getByRole("button", { name: "이유를 남기고 철회" }).click();
  await expect(page.getByText("아직 연결한 관계가 없습니다.")).toBeVisible();
  await page.getByRole("button", { name: "관계 관리 닫기" }).click();
  const final = await page.evaluate(
    async (id) => ({
      capture: (await (await fetch("/api/v1/captures/" + id)).json()).data,
      relations: (
        await (await fetch("/api/v1/relations?capture_id=" + id)).json()
      ).data,
    }),
    seed.current.id,
  );
  expect(final.capture.body_markdown).toBe(mergedBody);
  expect(final.relations.items).toEqual([]);
  expect(errors).toEqual([]);
});
