import { test, expect } from "./fixtures";

test.describe("route guards", () => {
  test("a non-admin parent is redirected away from /admin", async ({ page, seed }) => {
    await seed.seedParent({ isAdmin: false });
    await seed.login();
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/dashboard/);
  });
});
