import { test, expect } from "./fixtures";

test.describe("dashboard", () => {
  test("shows the seeded child, recent alert, and stats", async ({ page, seed }) => {
    await seed.seedParent();
    await seed.seedAlert({ severity: "high", category: "grooming" });
    await seed.login();

    await expect(page.getByText("Test Child").first()).toBeVisible();
    await expect(page.getByTestId("recent-alert").first()).toBeVisible();
    // Stat cards (unique labels — "Children" alone clashes with the section heading).
    await expect(page.getByText("Active connections")).toBeVisible();
    await expect(page.getByText("Unreviewed alerts")).toBeVisible();
  });
});
