import { test, expect, type Page } from "@playwright/test";
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

test("실제 API: 기록 생성·정정·주변 그래프·출처·확인 삭제·설정", async ({
  page,
}) => {
  test.skip(
    !process.env.SECOND_BRAIN_INTEGRATION,
    "임시 실제 서버를 지정한 통합 검증에서 실행",
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "최근 기록" })).toBeVisible();
  await page
    .getByRole("button", { name: "새 기록", exact: true })
    .last()
    .click();
  const title = "실제 API 검증 " + Date.now();
  await page.getByLabel("제목").fill(title);
  await page
    .getByLabel("내용", { exact: true })
    .fill(
      "트랜잭션의 원자성은 **모든 변경을 반영하거나 취소**하는 성질이다.\n\n오늘 CPU로 동작하는 개인 지식 저장소를 학습했다.",
    );
  await page.getByText("유형과 공개 범위", { exact: true }).click();
  await page.getByLabel("지식", { exact: true }).check();
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.locator(".record-detail h1")).toHaveText(title);
  await expect(page.locator(".record-detail")).toContainText("버전 1");
  const id = page.url().split("#capture/")[1];
  expect(id).toBeTruthy();
  await page.getByRole("button", { name: "기록 수정", exact: true }).click();
  await page
    .getByLabel("내용", { exact: true })
    .fill("수정한 원자성: **변경을 함께 반영하거나 모두 취소**한다.");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.locator(".record-detail")).toContainText("버전 2");
  await expect(page.locator(".record-detail")).toContainText(
    "변경을 함께 반영하거나 모두 취소",
  );
  const seed = await page.evaluate(async () => {
    const session = await (await fetch("/api/v1/session")).json();
    const headers = {
      "Content-Type": "application/json",
      "X-CSRF-Token": session.data.csrf_token,
    };
    const make = async (path: string, body: unknown) => {
      const response = await fetch("/api/v1" + path, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error.message);
      return result.data;
    };
    const source = await make("/captures", {
      request_id: crypto.randomUUID(),
      title: "재검토 근거 " + Date.now(),
      body_markdown: "원자성 근거: 전부 반영하거나 전부 취소한다.",
    });
    const concept = await make("/concepts", {
      request_id: crypto.randomUUID(),
      name: "데이터베이스 " + Date.now(),
    });
    return { source: source.capture, concept };
  });
  await page.getByRole("button", { name: "주제 정정", exact: true }).click();
  await page.getByLabel(seed.concept.name, { exact: true }).check();
  await page.getByRole("button", { name: "주제 저장", exact: true }).click();
  await expect(page.locator(".record-detail")).toContainText(seed.concept.name);
  await page.getByRole("button", { name: "출처 재검토", exact: true }).click();
  await page.getByText("다른 기록을 출처로 추가", { exact: true }).click();
  await page.getByLabel("기록 찾기", { exact: true }).fill(seed.source.title);
  await page
    .getByRole("button", { name: new RegExp(seed.source.title) })
    .click();
  await expect(page.locator(".reference-preview")).toContainText("원자성 근거");
  await page.getByRole("button", { name: "이 기록을 출처에 추가" }).click();
  await page
    .getByLabel("정정 이유", { exact: true })
    .fill("원자성의 정의를 저장된 근거에서 직접 확인했습니다.");
  await page.getByRole("button", { name: "재검토 저장", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".detail-sources")).toContainText("출처 1");
  await page.evaluate(async (source) => {
    const session = await (await fetch("/api/v1/session")).json();
    const response = await fetch("/api/v1/captures/" + source.id, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": session.data.csrf_token,
      },
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        capture_id: source.id,
        expected_revision_id: source.revision_id,
        expected_state_version: source.state_version,
        changes: {
          body_markdown:
            "수정한 근거: 원자성은 트랜잭션 단위의 전체 반영 또는 전체 취소다.",
        },
      }),
    });
    if (!response.ok) throw new Error("source update failed");
  }, seed.source);
  await page.reload();
  await expect(page.locator(".record-detail")).toContainText(
    "출처가 변경되었습니다",
  );
  await page.getByRole("button", { name: "출처 재검토", exact: true }).click();
  await page.getByRole("button", { name: "기존 출처 1", exact: true }).click();
  await expect(page.locator(".reference-preview")).toContainText("당시 저장본");
  await page
    .getByRole("button", { name: "기존 출처 1 제외", exact: true })
    .click();
  await page.getByText("다른 기록을 출처로 추가", { exact: true }).click();
  await page.getByLabel("기록 찾기", { exact: true }).fill(seed.source.title);
  await page
    .getByRole("button", { name: new RegExp(seed.source.title) })
    .click();
  await expect(page.locator(".reference-preview").last()).toContainText(
    "수정한 근거",
  );
  await page.getByRole("button", { name: "이 기록을 출처에 추가" }).click();
  await page
    .getByLabel("정정 이유", { exact: true })
    .fill("수정된 근거를 다시 읽고 현재 저장본으로 교체했습니다.");
  await page.getByRole("button", { name: "재검토 저장", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".record-detail")).not.toContainText(
    "출처가 변경되었습니다",
  );
  await page.getByRole("button", { name: "주변 지식 보기" }).click();
  await expect(
    page.getByRole("button", { name: title, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: title, exact: true }).click();
  await expect(page.locator(".source-panel")).toContainText("현재 저장본");
  await expect(page.locator(".source-panel")).toContainText(
    "변경을 함께 반영하거나 모두 취소",
  );
  await settle(page);
  await page.screenshot({
    path: "test-results/integration-desktop-source.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "출처 닫기" }).click();
  await page.getByRole("button", { name: "기록 삭제", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "복원 기능은 제공하지 않습니다",
  );
  await page.getByRole("button", { name: "취소", exact: true }).click();
  await expect(page.locator(".record-detail h1")).toHaveText(title);
  await page.getByRole("button", { name: "기록 삭제", exact: true }).click();
  await page.getByRole("button", { name: "삭제하기", exact: true }).click();
  await expect(page.locator(".record-detail")).toHaveCount(0);
  const deleted = await page.evaluate(async (id) => {
    const r = await fetch("/api/v1/captures/" + id);
    return { status: r.status, body: await r.json() };
  }, id);
  expect(deleted.status).toBe(404);
  expect(deleted.body.error.code).toBe("NOT_FOUND");
  await page.getByRole("button", { name: "설정", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Continue with ChatGPT" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "모델 준비", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText(
    "백업에는 삭제 표시된 내부 기록도 포함",
  );
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "백업 다운로드" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/second-brain-.*\.zip$/);
  expect(await download.failure()).toBeNull();
  await page.getByRole("button", { name: "설정 닫기" }).click();
  await settle(page);
  await page.screenshot({
    path: "test-results/integration-desktop-home.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await settle(page);
  await page.screenshot({
    path: "test-results/integration-mobile-home.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
