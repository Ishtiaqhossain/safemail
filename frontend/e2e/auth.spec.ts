import { test, expect } from "./fixtures";

test.describe("auth", () => {
  test("register a new account lands on onboarding", async ({ page, seed }) => {
    await page.goto("/login");
    await page.getByTestId("mode-register").click();
    await page.getByTestId("login-fullname").fill("Test Parent");
    await page.getByTestId("login-email").fill(seed.email);
    await page.getByTestId("login-password").fill(seed.password);
    await page.getByTestId("login-submit").click();
    await expect(page).toHaveURL(/\/onboarding/);
  });

  test("login then logout", async ({ page, seed }) => {
    await seed.seedParent();
    await seed.login();
    await expect(page).toHaveURL(/\/dashboard/);
    await page.getByTestId("logout").click();
    await expect(page).toHaveURL(/\/login/);
  });

  test("protected route redirects to login when logged out", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });

  test("wrong password shows an error", async ({ page, seed }) => {
    await seed.seedParent();
    await page.goto("/login");
    await page.getByTestId("login-email").fill(seed.email);
    await page.getByTestId("login-password").fill("wrong-password");
    await page.getByTestId("login-submit").click();
    await expect(page.getByTestId("login-error")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });
});
