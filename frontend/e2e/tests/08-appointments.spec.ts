// Appointments (HIMS-OPD-002; spec 4.6): the front desk (the nurse from tests 03 and 06) opens
// Leela Kumari's chart and books her with Ravi Doctor (test 07) next week from the Book button;
// moves the appointment to a later slot, then cancels it with the reason; books her again, and
// the chart's Overview shows the next appointment. The administrator records the doctor away
// that day: the answer names the booked patient, who is then listed under To move. Next week's
// slots are in the future at any hour the test runs. Every person is invented.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { localDate } from "../../src/components/dates";
import { NEW_STAFF_PASSWORD } from "../config.mjs";
import { expectAccessible, recall, signIn, storageFor } from "../helpers";

const NURSE_EMAIL = "asha.nurse@synthetic.test";
const NEXT_WEEK = localDate(new Date(Date.now() + 7 * 86_400_000));

test.describe.configure({ mode: "serial" });

async function asDesk(browser: Browser): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, NURSE_EMAIL, NEW_STAFF_PASSWORD, recall("nurse-secret"));
  await expect(page.getByRole("navigation")).toBeVisible();
  return page;
}

async function openChart(page: Page) {
  await page.goto("/patients");
  await page.getByRole("textbox", { name: "Search" }).fill("Leela Kumari");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("table", { name: "Patients" }).getByRole("link", { name: /^MRN-/ }).click();
  await expect(page.getByRole("region", { name: "Patient header" })).toBeVisible();
}

async function bookFromChart(page: Page, time: string) {
  await openChart(page);
  await page.getByRole("button", { name: "Book", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Appointments", level: 1 })).toBeVisible();
  await expect(page.getByText(/Booking for Leela Kumari/)).toBeVisible();
  await page.getByLabel("Day").fill(NEXT_WEEK);
  await page.getByRole("button", { name: `${time} free: book with Ravi Doctor` }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Patient: Leela Kumari");
  await dialog.getByRole("textbox", { name: /Reason/ }).fill("Blood pressure review");
  return dialog;
}

test("the front desk books a patient from her chart into a free slot", async ({ browser }) => {
  const page = await asDesk(browser);
  const dialog = await bookFromChart(page, "09:00");
  await expectAccessible(page, "Book dialog");
  await dialog.getByRole("button", { name: "Book", exact: true }).click();
  await expect(dialog).toBeHidden();
  const table = page.getByRole("table", { name: "Appointments in Cardiology" });
  await expect(table).toContainText("Leela Kumari");
  await expect(table).toContainText("Booked");
  await expect(page.getByRole("listitem").filter({ hasText: "09:00 booked" }).first()).toBeVisible();
  await expectAccessible(page, "Appointments");
});

test("she moves it to a later slot, then cancels it with the reason", async ({ browser }) => {
  const page = await asDesk(browser);
  await page.goto("/appointments");
  await page.getByLabel("Day").fill(NEXT_WEEK);
  const table = page.getByRole("table", { name: "Appointments in Cardiology" });
  await table.getByRole("button", { name: /^Move Leela Kumari/ }).click();
  const move = page.getByRole("dialog");
  await move.getByRole("combobox", { name: "Free slot" }).click();
  await page.getByRole("option", { name: "09:30 (09:00-13:00)" }).click();
  await expect(page.locator(".MuiMenu-root")).toHaveCount(0);
  await move.getByRole("textbox", { name: /Why it moves/ }).fill("The patient asked for later");
  await expectAccessible(page, "Move dialog");
  await move.getByRole("button", { name: "Move", exact: true }).click();
  await expect(move).toBeHidden();
  await expect(table).toContainText("Cancelled (Moved to another time)");

  await table.getByRole("button", { name: "Cancel Leela Kumari, 09:30" }).click();
  const cancel = page.getByRole("dialog");
  await expectAccessible(page, "Cancel dialog");
  await cancel.getByRole("button", { name: "Cancel appointment" }).click();
  await expect(cancel).toBeHidden();
  await expect(table).toContainText("Cancelled (The patient asked)");
  await expect(table.getByRole("button", { name: /^Move / })).toHaveCount(0);
});

test("booked again, the chart shows it; the doctor away puts her under To move", async ({ browser }) => {
  const page = await asDesk(browser);
  const dialog = await bookFromChart(page, "10:00");
  await dialog.getByRole("button", { name: "Book", exact: true }).click();
  await expect(dialog).toBeHidden();
  await openChart(page);
  await expect(page.getByRole("region", { name: "Clinical summary" })).toContainText("Ravi Doctor, Cardiology");

  const admin = await (await browser.newContext({ storageState: storageFor("admin") })).newPage();
  await admin.goto("/doctor-schedules");
  await admin.getByRole("button", { name: "Doctor away" }).click();
  const away = admin.getByRole("dialog");
  await away.getByLabel("First day").fill(NEXT_WEEK);
  await away.getByLabel("Why?").fill("Conference");
  await away.getByRole("button", { name: "Record" }).click();
  await expect(away).toContainText("1 booked patient(s) to move or cancel");
  await expect(away).toContainText("Leela Kumari");
  await away.getByRole("button", { name: "Done" }).click();

  await page.goto("/appointments");
  const toMove = page.getByRole("table", { name: "Appointments to move" });
  await expect(toMove).toContainText("Leela Kumari");
  await expect(toMove).toContainText("Away"); // why a doctor is away is for those keeping schedules
  await expect(toMove).not.toContainText("Conference");
  await expectAccessible(page, "Appointments with patients to move");
});
