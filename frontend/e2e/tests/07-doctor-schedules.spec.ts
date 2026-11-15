// Doctor schedules (HIMS-OPD-001; spec 4.6): the administrator adds a doctor and posts him in
// Cardiology, gives him a weekly OPD session on every day, records him away for part of tomorrow
// (the answer lists the session it takes off) and opens a session's free slots; the front desk
// (the nurse from tests 03 and 06) sees the schedule but cannot change it. Every person is invented.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { localDate } from "../../src/components/dates";
import { NEW_STAFF_PASSWORD } from "../config.mjs";
import { expectAccessible, openMenu, recall, signIn, storageFor } from "../helpers";

const NURSE_EMAIL = "asha.nurse@synthetic.test";

test.describe.configure({ mode: "serial" });

async function asAdmin(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ storageState: storageFor("admin") });
  return context.newPage();
}

test("a doctor gets a weekly OPD session in Cardiology", async ({ browser }) => {
  const admin = await asAdmin(browser);
  await admin.goto("/staff");
  await admin.getByRole("button", { name: "Add staff member" }).click();
  const add = admin.getByRole("dialog");
  await add.getByRole("textbox", { name: "First name" }).fill("Ravi");
  await add.getByRole("textbox", { name: "Last name" }).fill("Doctor");
  await add.getByRole("textbox", { name: "Employee number" }).fill("E2E-1003");
  await add.getByRole("combobox", { name: "Staff type" }).click();
  await admin.getByRole("option", { name: "Doctor", exact: true }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await add.getByLabel("Joined on").fill("2026-01-05");
  await add.getByRole("button", { name: "Add", exact: true }).click();
  await expect(admin.getByRole("heading", { name: /Ravi Doctor/ })).toBeVisible();
  await admin.getByRole("button", { name: "Add posting" }).click();
  const posting = admin.getByRole("dialog");
  await posting.getByRole("combobox", { name: "Department" }).click();
  await admin.getByRole("option", { name: /Cardiology/ }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await posting.getByRole("combobox", { name: /Designation/ }).click();
  await admin.getByRole("option").first().click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await posting.getByRole("button", { name: "Add", exact: true }).click();
  await expect(posting).toBeHidden();

  await openMenu(admin, "Doctor schedules");
  await expect(admin.getByRole("heading", { name: "Doctor schedules", level: 1 })).toBeVisible();
  const grid = admin.getByRole("table", { name: "Doctor schedules for Cardiology" });
  await expect(grid).toContainText("Ravi Doctor");
  await expectAccessible(admin, "Doctor schedules");
  await admin.getByRole("button", { name: "Add weekly session" }).click();
  const session = admin.getByRole("dialog");
  for (const day of ["Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) await session.getByLabel(day).check();
  await session.getByLabel("Note (optional)").fill("Room 4");
  await expectAccessible(admin, "Add weekly session dialog");
  await session.getByRole("button", { name: "Add", exact: true }).click();
  await expect(session).toBeHidden();
  await expect(grid.getByText("09:00-13:00 · 24 slots").first()).toBeVisible();
  await expect(admin.getByRole("table", { name: "Weekly sessions" })).toContainText("Room 4");
});

test("the doctor is away for part of tomorrow; the session keeps its other slots", async ({ browser }) => {
  const admin = await asAdmin(browser);
  await admin.goto("/doctor-schedules");
  await admin.getByRole("button", { name: "Doctor away" }).click();
  const away = admin.getByRole("dialog");
  await away.getByLabel("First day").fill(localDate(new Date(Date.now() + 86_400_000)));
  await away.getByLabel("From (optional)").fill("11:00");
  await away.getByLabel("Until (optional)").fill("13:00");
  await away.getByLabel("Why?").fill("Hospital committee");
  await expectAccessible(admin, "Doctor away dialog");
  await away.getByRole("button", { name: "Record" }).click();
  await expect(away).toContainText("1 session(s) are off");
  await away.getByRole("button", { name: "Done" }).click();

  await admin.getByRole("button", { name: /^09:00-13:00 .*, Ravi Doctor, .*: see the slots$/ }).first().click();
  const slots = admin.getByRole("dialog");
  await expect(slots.getByRole("list", { name: "Free slots" })).toBeVisible();
  await expectAccessible(admin, "Free slots");
});

test("the front desk sees the doctors' sessions but cannot change them", async ({ browser }) => {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, NURSE_EMAIL, NEW_STAFF_PASSWORD, recall("nurse-secret"));
  await expect(page.getByRole("navigation")).toBeVisible();
  await openMenu(page, "Doctor schedules");
  await expect(page.getByRole("table", { name: "Doctor schedules for Cardiology" })).toContainText("Ravi Doctor");
  await expect(page.getByRole("button", { name: "Add weekly session" })).toHaveCount(0);
  await expect(page.getByRole("table", { name: "Schedule exceptions" })).not.toContainText("Hospital committee");
  await expectAccessible(page, "Doctor schedules (front desk)");
});
