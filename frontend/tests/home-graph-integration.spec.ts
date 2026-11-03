import { test, expect } from "@playwright/test";
test("실제 API: 홈 그래프는 저장한 기록·주제를 보여주고 확인 삭제 후 갱신한다", async ({
  page,
}) => {
  test.skip(
    !process.env.SECOND_BRAIN_INTEGRATION,
    "격리된 실제 서버에서만 실행",
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
    async function write(path: string, body: unknown) {
      const r = await (
        await fetch("/api/v1" + path, {
          method: "POST",
          headers,
          body: JSON.stringify(body),
        })
      ).json();
      if (!r.ok) throw Error(r.error.message);
      return r.data;
    }
    // The deletion assertion below verifies that another record stays visible.
    // Seed it here so the test also works on a completely empty isolated store.
    const survivor = (
      await write("/captures", {
        request_id: crypto.randomUUID(),
        title: "삭제 후 남는 그래프 기록 " + Date.now(),
        body_markdown: "다른 기록의 삭제가 이 기록을 숨기지 않는지 확인한다.",
        kinds: ["knowledge"],
      })
    ).capture;
    const record = (
      await write("/captures", {
        request_id: crypto.randomUUID(),
        title: "홈 그래프 실제 검증 " + Date.now(),
        body_markdown: "저장한 지식과 주제의 연결을 그래프에서 확인한다.",
        kinds: ["knowledge"],
      })
    ).capture;
    const concept = await write("/concepts", {
      request_id: crypto.randomUUID(),
      name: "그래프 검증 " + Date.now(),
    });
    const concepts = await (
      await fetch(`/api/v1/captures/${record.id}/concepts`, {
        method: "PUT",
        headers,
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          capture_id: record.id,
          expected_revision_id: record.revision_id,
          expected_state_version: record.state_version,
          concept_ids: [concept.id],
        }),
      })
    ).json();
    if (!concepts.ok) throw Error(concepts.error.message);
    return { record: concepts.data.capture, concept, survivor };
  });
  await page.reload();
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "ready",
  );
  const graph = await page.evaluate(
    async () => (await (await fetch("/api/v1/graph")).json()).data,
  );
  expect(graph.nodes.length).toBeLessThanOrEqual(50);
  expect(graph.edges.length).toBeLessThanOrEqual(100);
  expect(
    graph.nodes.some((n: any) => n.source?.capture_id === seed.record.id),
  ).toBe(true);
  expect(
    graph.edges.some(
      (e: any) => e.source === seed.record.id && e.target === seed.concept.id,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "연결 목록 보기" }).click();
  await page
    .locator(".graph-list")
    .getByRole("button", { name: seed.record.title + " 지식", exact: true })
    .click();
  await expect(page.locator(".source-panel")).toContainText(
    seed.record.body_markdown,
  );
  await expect(page.locator(".graph-world canvas")).toBeVisible();
  await page.getByRole("button", { name: "현재 기록 열기" }).click();
  await expect(page.locator(".record-detail")).toContainText(seed.concept.name);
  await page.getByRole("button", { name: "기록 삭제", exact: true }).click();
  await page.getByRole("button", { name: "삭제하기", exact: true }).click();
  await expect(page.locator(".record-detail")).toHaveCount(0);
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "ready",
  );
  await page.getByRole("button", { name: "연결 목록 보기" }).click();
  await expect(page.locator(".graph-list")).not.toContainText(
    seed.record.title,
  );
  const after = await page.evaluate(
    async () => (await (await fetch("/api/v1/graph")).json()).data,
  );
  expect(
    after.nodes.some((n: any) => n.source?.capture_id === seed.record.id),
  ).toBe(false);
  expect(
    after.nodes.some((n: any) => n.source?.capture_id === seed.survivor.id),
  ).toBe(true);
  await page.getByRole("button", { name: "연결 목록 닫기" }).click();
  await page.screenshot({ path: "test-results/home-graph-real-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await expect(page.locator(".graph-world")).toHaveAttribute(
    "data-render-state",
    "ready",
  );
  await expect
    .poll(async () =>
      page
        .locator(".graph-label-layer>span")
        .evaluateAll(
          (labels) =>
            labels.filter((l) => getComputedStyle(l).opacity === "1").length,
        ),
    )
    .toBeGreaterThan(0);
  await page.screenshot({ path: "test-results/home-graph-real-mobile.png" });
  expect(errors).toEqual([]);
});
