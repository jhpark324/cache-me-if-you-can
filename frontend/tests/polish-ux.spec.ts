import { test, expect } from "@playwright/test";
test("도움말이 화면높이로 늘어나지 않고 선택한 검색 조건을 바로 해제한다", async ({
  page,
}) => {
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const data = path.endsWith("/session")
      ? { csrf_token: "test" }
      : path.endsWith("/graph")
        ? { nodes: [], edges: [], truncated: false }
        : { items: [], next_cursor: null };
    return route.fulfill({ json: { schema_version: 1, ok: true, data } });
  });
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto("/");
  const menu = page.getByRole("button", { name: "메뉴 열기", exact: true });
  await menu.focus();
  const tip = page.locator(".rt-TooltipContent");
  await expect(tip).toBeVisible();
  const rect = await tip.boundingBox();
  expect(rect!.height).toBeLessThan(60);
  expect(rect!.width).toBeLessThan(260);
  await menu.click();
  await page
    .getByRole("combobox", { name: "기록 유형", exact: true })
    .selectOption("knowledge");
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
  const filter = page.getByRole("button", {
    name: "기록 유형 필터 해제",
    exact: true,
  });
  await expect(filter).toContainText("지식");
  await filter.click();
  await expect(filter).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "첫 번째 생각을 남겨보세요" }),
  ).toBeVisible();
});
