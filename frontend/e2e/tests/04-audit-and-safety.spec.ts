// Audit and separation of duties (spec 4.25, 13.2, 13.4): the auditor finds a person's "no access"
// event by the reference number they were shown, checks the audit log is untampered, and the
// administrator cannot read the audit log. The remaining screens are checked for accessibility.
import { expect, test } from "@playwright/test";

import { expectAccessible, openMenu, recall, storageFor } from "../helpers";

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
