// The OPD queue (HIMS-OPD-003; spec 4.6): the front desk (the nurse from tests 03 and 06) checks
// Leela Kumari in as a walk-in with Ravi Doctor (test 07), who has an OPD session every day: she gets
// his next token and waits; the front desk calls her in to the doctor, then marks her seen. The
// administrator sees the queue but does not move it. A walk-in needs only a session today, so this
// runs at any hour; the queue asks the server for today, on the hospital's clock. Every person is
// invented.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { NEW_STAFF_PASSWORD } from "../config.mjs";
import { expectAccessible, openMenu, recall, signIn, storageFor } from "../helpers";

const NURSE_EMAIL = "asha.nurse@synthetic.test";

test.describe.configure({ mode: "serial" });

async function asDesk(browser: Browser): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, NURSE_EMAIL, NEW_STAFF_PASSWORD, recall("nurse-secret"));
  await expect(page.getByRole("navigation")).toBeVisible();
  return page;
}

test("the front desk checks in a walk-in, calls her in to the doctor and marks her seen", async ({ browser }) => {
  const page = await asDesk(browser);
  await openMenu(page, "OPD queue");
  await expect(page.getByRole("heading", { name: "OPD queue", level: 1 })).toBeVisible();
  const queue = page.getByRole("region", { name: "Queue, Ravi Doctor" });
  await expect(queue).toBeVisible();

  await page.getByRole("button", { name: "Walk in for Ravi Doctor" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "Find the patient" }).fill("Leela Kumari");
  await dialog.getByRole("button", { name: "Search", exact: true }).click();
  // Picking her replaces the list with her name (so click, not check: the radio goes away).
  await dialog.getByLabel(/^Leela Kumari · MRN-/).click();
  await expect(dialog).toContainText("Patient: Leela Kumari");
  await dialog.getByRole("textbox", { name: /Reason/ }).fill("Fever since yesterday");
  await expectAccessible(page, "Walk-in dialog");
  await dialog.getByRole("button", { name: "Check in", exact: true }).click();
  await expect(dialog).toBeHidden();

  const table = page.getByRole("table", { name: "Patients of Ravi Doctor" });
  const leela = table.getByRole("row").filter({ hasText: "Leela Kumari" });
  await expect(leela).toContainText("Walk-in");
  await expect(leela).toContainText(/Waiting \d+ min/);
  await expect(queue).toContainText("Waiting 1");
  await expectAccessible(page, "OPD queue");

  await page.getByRole("button", { name: "Call next for Ravi Doctor" }).click();
  await expect(leela).toContainText("With the doctor");
  await page.getByRole("button", { name: "Seen: Leela Kumari" }).click();
  await expect(leela).toContainText("Seen");
  await expect(queue).toContainText("Seen 1");
  await expect(page.getByRole("button", { name: "Call next for Ravi Doctor" })).toBeDisabled();
});

test("the administrator sees the queue but does not move it", async ({ browser }) => {
  const admin = await (await browser.newContext({ storageState: storageFor("admin") })).newPage();
  await admin.goto("/opd-queue");
  const table = admin.getByRole("table", { name: "Patients of Ravi Doctor" });
  await expect(table).toContainText("Leela Kumari");
  await expect(admin.getByRole("button", { name: /^Call next/ })).toHaveCount(0);
  await expect(admin.getByRole("button", { name: /^Walk in/ })).toHaveCount(0);
});
