import { test, expect } from "./fixtures";

test.describe("settings", () => {
  test("changing a preference saves", async ({ page, seed }) => {
    await seed.seedParent();
    await seed.seedAlert(); // gives the parent a child whose prefs panel renders
    await seed.login();

    await page.goto("/settings");
    const digest = page.getByRole("combobox").first();
    await expect(digest).toBeVisible();
    await digest.selectOption("daily");
    await expect(page.getByTestId("prefs-saved").first()).toBeVisible();
  });

  test("add a child via the form", async ({ page, seed }) => {
    await seed.seedParent();
    await seed.login();

    await page.goto("/settings");
    await page.getByTestId("settings-child-name").fill("Second Kid");
    await page.getByTestId("settings-add-child").click();
    await expect(page.getByText("Second Kid").first()).toBeVisible();
  });
});
