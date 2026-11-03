import { expect, type Page } from "@playwright/test";

export async function openLibrary(page: Page) {
  if (await page.locator(".record-browser").isVisible()) return;
  const destination = page
    .getByRole("navigation")
    .getByRole("button", { name: "모든 기록", exact: true });
  if (!(await destination.isVisible()))
    await page.getByRole("button", { name: "메뉴 열기", exact: true }).click();
  await destination.click();
  await expect(page.locator(".record-browser")).toBeVisible();
}

export async function openHome(page: Page) {
  const destination = page
    .getByRole("navigation")
    .getByRole("button", { name: "지식 공간", exact: true });
  if (!(await destination.isVisible()))
    await page.getByRole("button", { name: "메뉴 열기", exact: true }).click();
  await destination.click();
}
