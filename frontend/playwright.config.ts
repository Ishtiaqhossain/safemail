import { defineConfig, devices } from "@playwright/test";

// Browser E2E for SafeMail. The backend (API + Postgres + Redis, migrated, with the
// /v1/dev seed seam enabled) must already be running on :8000 — CI and the local
// recipe in docs/DEVELOPMENT.md start it. Playwright boots the Vite dev server,
// whose /v1 proxy forwards to the API (same-origin → the refresh cookie works).
const PORT = Number(process.env.PORT) || 3000;
const API_TARGET = process.env.VITE_API_TARGET || "http://localhost:8000";
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // Specs mutate shared backend state via per-test namespaced parents; keep it
  // serial until isolation is proven, then revisit.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 7_500 },
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    // Stabilize click timing.
    actionTimeout: 10_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // Inline the env so the dev server reliably gets the right port + proxy
    // target regardless of how Playwright merges webServer.env (POSIX shells).
    command: `PORT=${PORT} VITE_API_TARGET=${API_TARGET} npm run dev`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
