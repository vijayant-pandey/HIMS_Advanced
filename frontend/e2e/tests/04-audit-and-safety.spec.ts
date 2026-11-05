// Audit and separation of duties (spec 4.25, 13.2, 13.4): the auditor finds a person's "no access"
// event by the reference number they were shown, checks the audit log is untampered, and the
// administrator cannot read the audit log. The remaining screens are checked for accessibility.
import { expect, test } from "@playwright/test";

import { ADMIN, AUDITOR, E2E } from "../config.mjs";
import { expectAccessible, freshCode, openMenu, recall, storageFor } from "../helpers";

test.describe("auditor", () => {
  test.use({ storageState: storageFor("auditor") });

  test("finds the nurse's 'no access yet' visit by its reference number", async ({ page }) => {
    const reference = recall("nurse-no-access-reference");
    await page.goto("/");
    await openMenu(page, "Audit log");
    await expectAccessible(page, "Audit log");
    await page.getByLabel("Reference number").fill(reference.toUpperCase()); // any letter case
    await page.getByRole("button", { name: "Search" }).click();
    const table = page.getByRole("table", { name: "Audit events" });
    await expect(table.getByText("Signed in without any access yet")).toBeVisible();
    await expect(table.getByText(/Asha Nurse/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Download CSV" })).toBeVisible();

    await table.getByText("Signed in without any access yet").click();
    const details = page.getByRole("dialog");
    await expect(details.getByText(reference)).toBeVisible();
    await expectAccessible(page, "Audit event details");
  });

  test("downloading the audit log asks to confirm it's you first", async ({ page }) => {
    await page.goto("/security");
    await page.getByRole("button", { name: "End now" }).click();
    await expect(page.getByText("Not confirmed.")).toBeVisible();
    await page.goto("/audit");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByRole("table", { name: "Audit events" })).toBeVisible();
    await page.getByRole("link", { name: "Download CSV" }).click();
    const confirm = page.getByRole("dialog", { name: "Confirm it's you" });
    await confirm.getByLabel("Your password").fill(AUDITOR.password);
    await confirm.getByLabel("Authenticator code").fill(await freshCode(recall("auditor-secret")));
    const download = page.waitForEvent("download");
    await confirm.getByRole("button", { name: "Confirm" }).click();
    expect((await download).suggestedFilename()).toMatch(/\.csv$/);
  });

  test("checks that nobody changed the audit log", async ({ page }) => {
    await page.goto("/");
    await openMenu(page, "Audit integrity");
    await expect(page.getByText("Never checked")).toBeVisible();
    await page.getByRole("button", { name: "Check now" }).click();
    await expect(page.getByText(/Passed: [\d,]+ record\(s\) checked, nothing was changed\./)).toBeVisible();
    await expect(page.getByRole("table", { name: "Past integrity checks" }).getByText("Passed")).toBeVisible();
    await expectAccessible(page, "Audit integrity");
  });

  test("can read access reviews but not decide", async ({ page }) => {
    await page.goto("/");
    await openMenu(page, "Access reviews");
    await page.getByRole("link", { name: /^Access review / }).first().click();
    await expect(page.getByRole("link", { name: "Download (CSV)" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Keep / })).toHaveCount(0);
    await expectAccessible(page, "Access review (auditor)");
  });
});

test.describe("administrator", () => {
  test.use({ storageState: storageFor("admin") });

  test("cannot open the audit log (separation of duties) and gets a reference", async ({ page }) => {
    // The menu hides the page; typing the address shows the form, but the server refuses the
    // search itself (the real boundary) and records the attempt under a reference number.
    await page.goto("/audit");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByText("You don't have access to this")).toBeVisible();
    await expect(page.getByText(/Reference:/).first()).toBeVisible();
  });

  test("remaining screens are accessible", async ({ page }) => {
    for (const [menu, heading] of [
      ["Access", /Access|Roles/],
      ["Accounts", /Accounts/],
      ["Licence expiry", /Licence/],
      ["Job titles & catalogs", /Job titles/],
      ["Messages", /Messages/],
      ["Compliance", /Compliance/],
    ] as const) {
      await page.goto("/");
      await openMenu(page, menu);
      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      await expectAccessible(page, menu);
    }
    await page.goto("/security");
    await expect(page.getByRole("heading", { name: "Security", level: 1 })).toBeVisible();
    await expectAccessible(page, "Security");
  });

  test("a security incident gets its legal deadline; the reference is shown", async ({ page }) => {
    await page.goto("/security");
    await page.getByRole("button", { name: "Report a security incident" }).click();
    const report = page.getByRole("dialog");
    await report.getByLabel(/What happened/).fill("Laptop left on a train");
    await report.getByLabel(/Details/).fill("Encrypted laptop, no patient details");
    await expectAccessible(page, "Report incident dialog");
    await report.getByRole("button", { name: "Send report" }).click();
    await expect(report.getByText(/Reference:/)).toBeVisible();
    await report.getByRole("button", { name: "Close" }).click();

    await page.goto("/compliance");
    await page.getByRole("tab", { name: "Incidents" }).click();
    const table = page.getByRole("table", { name: "Security incidents" });
    await expect(table.getByText("Laptop left on a train")).toBeVisible();
    await expect(table.getByText("India: CERT-In report")).toBeVisible();
    await expectAccessible(page, "Compliance incidents");
  });

  test("a sensitive action asks to confirm it's you, then finishes by itself", async ({ page }) => {
    await page.goto("/security");
    await expectAccessible(page, "Security (sensitive actions)");
    await expect(page.getByText(/^Confirmed until/)).toBeVisible();
    await page.getByRole("button", { name: "End now" }).click();
    await expect(page.getByText("Not confirmed.")).toBeVisible();

    await page.goto("/");
    await openMenu(page, "Features");
    await page.getByRole("button", { name: "Change Forgot-password emails" }).click();
    const change = page.getByRole("dialog", { name: /Forgot-password emails/ });
    await change.getByRole("radio", { name: "Off", exact: true }).check();
    await change.getByLabel(/Reason/).fill("Browser test");
    await change.getByRole("button", { name: "Save" }).click();

    const confirm = page.getByRole("dialog", { name: "Confirm it's you" });
    await expect(confirm).toBeVisible();
    await expectAccessible(page, "Confirm it's you");
    await confirm.getByLabel("Your password").fill("Synthetic-Wrong-Passw0rd-1234");
    await confirm.getByLabel("Authenticator code").fill("000000");
    await confirm.getByRole("button", { name: "Confirm" }).click();
    await expect(confirm.getByText(/was not accepted/)).toBeVisible();

    await confirm.getByLabel("Your password").fill(ADMIN.password);
    await confirm.getByLabel("Authenticator code").fill(await freshCode(recall("admin-secret")));
    await confirm.getByRole("button", { name: "Confirm" }).click();
    // Nothing more to click: the change that was waiting goes through.
    await expect(confirm).toHaveCount(0);
    await expect(change).toHaveCount(0);

    // Confirmed now, so changing it back does not ask.
    await page.getByRole("button", { name: "Change Forgot-password emails" }).click();
    await change.getByRole("radio", { name: "On", exact: true }).check();
    await change.getByLabel(/Reason/).fill("Browser test finished");
    await change.getByRole("button", { name: "Save" }).click();
    await expect(change).toHaveCount(0);
    await expect(confirm).toHaveCount(0);
  });

  test("browser protection: no screen so far was blocked, and injected code is", async ({ page }) => {
    const response = await page.goto("/compliance");
    const policy = response!.headers()["content-security-policy"];
    expect(policy).toContain("script-src 'self';");
    expect(policy).toContain("report-uri /api/v1/security/browser-reports/");
    await page.getByRole("tab", { name: "Browser protection" }).click();
    // Every earlier test ran under the policy, so a blocked script or call on any screen shows here.
    await expect(page.getByText("Nothing has been blocked.")).toBeVisible();
    await expect(page.getByText(/HIMS sees your address as/)).toBeVisible();
    await expectAccessible(page, "Browser protection");

    const ran = await page.evaluate(
      () =>
        new Promise<boolean>((resolve) => {
          document.addEventListener("securitypolicyviolation", () => resolve(false), { once: true });
          const script = document.createElement("script");
          script.src = "https://blocked.example/steal.js";
          script.onload = () => resolve(true);
          document.head.append(script);
        }),
    );
    expect(ran).toBe(false);
    await expect(async () => {
      await page.reload();
      await page.getByRole("tab", { name: "Browser protection" }).click();
      const table = page.getByRole("table", { name: "What browsers blocked" });
      await expect(table.getByText("https://blocked.example")).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    await page.getByRole("button", { name: /^Mark reviewed/ }).click();
    await expect(page.getByRole("button", { name: /^Mark reviewed/ })).toHaveCount(0);
  });

  test("admin console works under its browser protection rules", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    const blocked: string[] = [];
    page.on("console", (message) => {
      if (message.text().includes("Content Security Policy")) blocked.push(message.text());
    });
    const missing: string[] = [];
    page.on("response", (response) => {
      // 304 "not changed, use your saved copy" is fine; only real errors mean a file is missing.
      if (response.url().includes("/static/") && response.status() >= 400) missing.push(response.url());
    });
    const console = `http://127.0.0.1:${E2E.apiPort}/admin/`;
    const first = await page.goto(console);
    expect(first!.headers()["content-security-policy"]).toContain("script-src 'self';");
    await page.getByLabel("Email").fill(ADMIN.email);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByLabel("Authenticator code").fill(await freshCode(recall("admin-secret")));
    await page.getByRole("button", { name: /Log in|Sign in/ }).click();
    await expect(page).toHaveURL(/\/admin\/$/);
    for (const path of ["compliance/browsersecurityreport/", "facilities/facility/", "facilities/facility/add/"]) {
      await page.goto(`${console}${path}`);
      await expect(page.locator("#content")).toBeVisible();
    }
    // The console's own scripts really ran: Django's script sets this up.
    expect(await page.evaluate(() => "jQuery" in ((window as unknown as { django?: object }).django ?? {}))).toBe(true);
    await page.goto(`${console}confirm-identity/?next=/admin/`);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByLabel("Authenticator code").fill(await freshCode(recall("admin-secret")));
    await page.getByRole("button", { name: "Confirm" }).click();
    await expect(page).toHaveURL(/\/admin\/$/);
    expect(missing).toEqual([]);
    expect(blocked).toEqual([]);
    await context.close();
  });

  test("keyboard only: the menu can be reached and used with Tab and Enter", async ({ page }) => {
    await page.goto("/");
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press("Tab");
      const focused = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? "");
      if (focused === "Facilities") break;
    }
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/facilities$/);
    await expect(page.getByRole("heading", { name: "Facilities", level: 1 })).toBeVisible();
  });
});
