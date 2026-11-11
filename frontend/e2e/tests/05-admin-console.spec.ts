// The admin console (ADR-016; spec 19.2; HIMS-QA-003): its own sign-in with two-factor, the
// auditor's read-only view, a change made there showing in the app and in the audit log, no
// delete buttons, and the performance check run from it showing on the app's Performance screen.
// Runs last: it changes the facility set up in 02-hospital-setup.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { ADMIN, AUDITOR, E2E } from "../config.mjs";
import { expectAccessible, freshCode, recall, storageFor } from "../helpers";

const CONSOLE = `http://127.0.0.1:${E2E.apiPort}/admin/`;

test.describe.configure({ mode: "serial" });

async function consoleSignIn(browser: Browser, person: typeof ADMIN, role: "admin" | "auditor"): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(CONSOLE);
  await page.getByLabel("Email").fill(person.email);
  await page.getByLabel("Password").fill(person.password);
  await page.getByLabel("Authenticator code").fill(await freshCode(recall(`${role}-secret`)));
  await page.getByRole("button", { name: /Log in|Sign in/ }).click();
  await expect(page).toHaveURL(/\/admin\/$/);
  return page;
}

test("console sign-in refuses a wrong authenticator code", async ({ page }) => {
  await page.goto(CONSOLE);
  await expectAccessible(page, "Console sign-in");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByLabel("Authenticator code").fill("000000");
  await page.getByRole("button", { name: /Log in|Sign in/ }).click();
  await expect(page.locator(".errornote")).toBeVisible();
  await expect(page).toHaveURL(/\/admin\/login\//);
});

test("the auditor sees the audit log only, and cannot change or add anything", async ({ browser }) => {
  const page = await consoleSignIn(browser, AUDITOR, "auditor");
  await expect(page.getByRole("link", { name: /Audit events/i }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Facilities", exact: true })).toHaveCount(0);
  await page.goto(`${CONSOLE}audit/auditevent/`);
  await expect(page.locator("#content")).toBeVisible();
  await expect(page.getByRole("link", { name: /^Add/ })).toHaveCount(0);
  await expectAccessible(page, "Console audit log (auditor)");
  // The facilities page is not hers: the console refuses it.
  await page.goto(`${CONSOLE}facilities/facility/`);
  await expect(page.getByText("Test Branch One")).toHaveCount(0);
});

test("a change made in the console shows in the app and in the audit log; nothing can be deleted", async ({
  browser,
}) => {
  const page = await consoleSignIn(browser, ADMIN, "admin");
  await page.goto(`${CONSOLE}facilities/facility/`);
  await expectAccessible(page, "Console facilities");
  await page.locator("#result_list tr", { hasText: "Test Branch One" }).getByRole("link").first().click();
  await expect(page.getByRole("link", { name: /Delete/ })).toHaveCount(0);
  await page.getByLabel("City").fill("Nashik");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator(".messagelist .success")).toBeVisible();

  const app = await (await browser.newContext({ storageState: storageFor("admin") })).newPage();
  await app.goto("/facilities");
  const row = app.getByRole("table", { name: "Facilities" }).getByRole("row").filter({ hasText: "Test Branch One" });
  await expect(row.getByText("Nashik")).toBeVisible();

  const auditor = await (await browser.newContext({ storageState: storageFor("auditor") })).newPage();
  await auditor.goto("/audit");
  await auditor.getByRole("combobox", { name: "Area" }).click();
  await auditor.getByRole("option", { name: "Admin console changes" }).click();
  await auditor.getByRole("button", { name: "Search" }).click();
  await expect(
    auditor.getByRole("table", { name: "Audit events" }).getByText("Admin console: facility changed").first(),
  ).toBeVisible();
});

test("performance: the index check run in the console shows on the app's Performance screen", async ({ browser }) => {
  const page = await consoleSignIn(browser, ADMIN, "admin");
  await page.goto(`${CONSOLE}performance/performancecheck/`);
  await page.getByRole("button", { name: "Run the index check now" }).click();
  await expect(page.locator(".messagelist")).toContainText(/Index check (passed|failed)/);
  await expect(page.locator("#content")).toContainText("Results");
  await expectAccessible(page, "Console performance check");

  const app = await (await browser.newContext({ storageState: storageFor("admin") })).newPage();
  await app.goto("/performance");
  await expect(app.getByRole("heading", { name: "Performance", level: 1 })).toBeVisible();
  const checks = app.getByRole("table", { name: "Performance checks" });
  await expect(checks.getByText("Index check (query plans)").first()).toBeVisible();
  await expect(checks.getByText("E2E Admin").first()).toBeVisible();
  await expectAccessible(app, "Performance");

  // The app's own button does the same, and each query's result can be opened.
  await app.getByRole("button", { name: "Run the index check now" }).click();
  await app.getByRole("link", { name: "See each query" }).click();
  await expect(app.getByRole("table", { name: "Queries" }).getByText("Audit log: one person's actions")).toBeVisible();
  await expectAccessible(app, "Performance check detail");
});
