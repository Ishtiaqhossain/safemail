import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

// Register a fresh (incomplete) parent through the UI, then walk the wizard.
async function register(page: Page, seed: { email: string; password: string }) {
  await page.goto("/login");
  await page.getByTestId("mode-register").click();
  await page.getByTestId("login-fullname").fill("Test Parent");
  await page.getByTestId("login-email").fill(seed.email);
  await page.getByTestId("login-password").fill(seed.password);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/onboarding/);
}

test.describe("onboarding", () => {
  test("walk the wizard through add-child and skip to dashboard", async ({ page, seed }) => {
    await register(page, seed);
    await page.getByRole("button", { name: "Get started" }).click();
    await page.getByRole("button", { name: "Continue" }).click();            // How it works
    await page.getByRole("checkbox").check();                                 // consent
    await page.getByRole("button", { name: "I agree" }).click();
    await expect(page.getByRole("heading", { name: "Add your child" })).toBeVisible();
    await page.getByTestId("onboarding-child-name").fill("Alex");
    await page.getByRole("button", { name: "Continue" }).click();            // creates child
    await page.getByTestId("onboarding-skip").click();
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("reloading mid-wizard resumes the same step", async ({ page, seed }) => {
    await register(page, seed);
    await page.getByRole("button", { name: "Get started" }).click();
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "I agree" }).click();
    await expect(page.getByRole("heading", { name: "Add your child" })).toBeVisible();
    await page.reload();
    // localStorage (sm_onboarding) restores the step after a full reload.
    await expect(page.getByRole("heading", { name: "Add your child" })).toBeVisible();
  });
});
