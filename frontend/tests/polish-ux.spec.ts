import { test, expect } from "@playwright/test";
test("도움말이 화면높이로 늘어나지 않고 목록 필터를 바로 초기화한다", async ({
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
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const menu = page.getByRole("button", { name: "메뉴 열기", exact: true });
  await menu.focus();
  const tip = page.getByRole("tooltip", { name: "메뉴 열기" });
  await expect(tip).toBeVisible();
  const rect = await tip.boundingBox();
  expect(rect!.height).toBeLessThan(60);
  expect(rect!.width).toBeLessThan(260);
  await menu.click();
  await page.getByRole("button", { name: "모든 기록", exact: true }).click();
  await page
    .getByRole("combobox", { name: "기록 유형", exact: true })
    .selectOption("knowledge");
  const filter = page
    .getByRole("group", { name: "기록 필터", exact: true })
    .getByRole("button", { name: "필터 초기화", exact: true });
  await expect(
    page.getByRole("combobox", { name: "기록 유형", exact: true }),
  ).toHaveValue("knowledge");
  await filter.click();
  await expect(filter).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "기록 유형", exact: true }),
  ).toHaveValue("");
  await expect(
    page.getByRole("heading", { name: "모든 기록", exact: true }),
  ).toBeVisible();
});
