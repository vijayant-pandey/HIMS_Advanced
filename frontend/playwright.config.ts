import { defineConfig, devices } from "@playwright/test";

import { E2E } from "./e2e/config.mjs";

/**
 * Browser tests (spec 19.2 "end-to-end tests using Playwright", "accessibility checks";
 * HIMS-QA-001). Run with `npm run e2e`; see docs/testing/browser-tests.md.
 *
 * Starts its own throw-away backend (port 8100, database hims_e2e) and app (port 5180), so the
 * normal local hospitals keep running untouched. Tests run one after another because they build
 * on the same synthetic hospital (set up hospital → invite staff → give access → audit).
 */
export default defineConfig({
  testDir: "./e2e/tests",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  // No retries: the tests are one story on one hospital (a retry would e.g. add the same nurse
  // twice), so a failure must be fixed, not retried.
  retries: 0,
  timeout: 90_000,
  expect: { timeout: process.env.CI ? 20_000 : 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: E2E.appUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    { name: "chromium", dependencies: ["setup"], testMatch: /.*\.spec\.ts/ },
  ],
  webServer: [
    {
      command: "node e2e/start-backend.mjs",
      url: `http://127.0.0.1:${E2E.apiPort}/health/ready/`,
      timeout: 240_000,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // The production build, as hospitals get it (no slow first-visit compiling like the dev
      // server). `vite preview` uses the same /api proxy as the dev server.
      command: `npx vite build --logLevel warn && npx vite preview --port ${E2E.appPort} --strictPort`,
      url: E2E.appUrl,
      timeout: 180_000,
      reuseExistingServer: false,
      env: { VITE_API_TARGET: `http://127.0.0.1:${E2E.apiPort}`, VITE_DEV_PORT: String(E2E.appPort) },
    },
  ],
});
