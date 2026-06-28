import { test, expect } from "./fixtures";

test.describe("alerts", () => {
  test("list, open detail, and submit feedback", async ({ page, seed }) => {
    await seed.seedParent();
    await seed.seedAlert({
      severity: "high",
      category: "grooming",
      summary: "An adult repeatedly asked to meet in private and keep it secret.",
    });
    await seed.login();

    await page.goto("/alerts");
    const row = page.getByTestId("alert-row").first();
    await expect(row).toBeVisible();
    await row.getByRole("link").first().click();

    await expect(page).toHaveURL(/\/alerts\/[0-9a-f-]+/);
    await expect(page.getByText(/asked to meet in private/i)).toBeVisible();

    await page.getByTestId("feedback-correct").click();
    await expect(page.getByTestId("feedback-correct")).toBeDisabled();
  });
});
