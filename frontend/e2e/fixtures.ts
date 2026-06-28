import { test as base, expect } from "@playwright/test";

// Talks to the DEBUG-only seed router through the Vite proxy (baseURL → /v1 → API).
const SECRET = process.env.E2E_SEED_SECRET || "dev";
const HEADERS = { "X-E2E-Seed-Secret": SECRET };
const PASSWORD = "Sup3rSecret!";

type SeedAlertOpts = { severity?: string; category?: string; summary?: string };

type Seed = {
  email: string;
  password: string;
  seedParent: (opts?: { complete?: boolean; isAdmin?: boolean }) => Promise<void>;
  seedAlert: (opts?: SeedAlertOpts) => Promise<{ child_id: string; alert_id: string }>;
  /** Log in through the UI as this parent and land on the dashboard. */
  login: () => Promise<void>;
};

// Each test gets its own namespaced parent (title + worker + retry → unique email),
// reset before AND after so a killed run or a retry never reuses dirty state.
export const test = base.extend<{ seed: Seed }>({
  seed: async ({ request, page }, use, testInfo) => {
    const slug = testInfo.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 28);
    const email = `e2e-${slug}-w${testInfo.workerIndex}-r${testInfo.retry}@example.com`;

    const reset = () => request.post("/v1/dev/reset", { headers: HEADERS, data: { email } });
    await reset();

    const seed: Seed = {
      email,
      password: PASSWORD,
      seedParent: async (opts = {}) => {
        const r = await request.post("/v1/dev/seed-parent", {
          headers: HEADERS,
          data: { email, password: PASSWORD, complete: opts.complete ?? true, is_admin: opts.isAdmin ?? false },
        });
        expect(r.ok(), `seed-parent failed: ${r.status()}`).toBeTruthy();
      },
      seedAlert: async (opts = {}) => {
        const r = await request.post("/v1/dev/seed-alert", { headers: HEADERS, data: { email, ...opts } });
        expect(r.ok(), `seed-alert failed: ${r.status()}`).toBeTruthy();
        return r.json();
      },
      login: async () => {
        await page.goto("/login");
        await page.getByTestId("login-email").fill(email);
        await page.getByTestId("login-password").fill(PASSWORD);
        await page.getByTestId("login-submit").click();
        await page.waitForURL("**/dashboard");
      },
    };

    await use(seed);
    await reset();
  },
});

export { expect };
