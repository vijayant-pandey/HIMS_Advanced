// Patients (HIMS-PAT-001; spec 4.5, 13): the administrator makes the nurse from test 03 the front
// desk; she registers a patient with an age, a mobile and an ID number; the record opens with its
// MRN and the number masked; the same number on a second patient is refused; the administrator can
// look but not register. Every person and number is invented.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { NEW_STAFF_PASSWORD } from "../config.mjs";
import { expectAccessible, openMenu, recall, signIn, storageFor } from "../helpers";

const NURSE_EMAIL = "asha.nurse@synthetic.test";
const AADHAAR = "2999 9000 0337"; // invented; its check digit is right

test.describe.configure({ mode: "serial" });

async function asAdmin(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ storageState: storageFor("admin") });
  return context.newPage();
}

async function asDesk(browser: Browser): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, NURSE_EMAIL, NEW_STAFF_PASSWORD);
  await expect(page.getByRole("navigation")).toBeVisible();
  return page;
}

async function fillPatient(page: Page, given: string) {
  await page.getByRole("textbox", { name: "Given name" }).fill(given);
  await page.getByRole("textbox", { name: "Family name" }).fill("Kumari");
  await page.getByRole("radio", { name: "Age in years" }).check();
  await page.getByRole("spinbutton", { name: "Age (years)" }).fill("41");
  await page.getByRole("combobox", { name: "Sex" }).click();
  await page.getByRole("option", { name: "Female" }).click();
  await page.getByRole("textbox", { name: "Mobile" }).fill("98765 40001");
  await page.getByRole("button", { name: "Add an ID number" }).click();
  await page.getByRole("combobox", { name: "Kind" }).click();
  await page.getByRole("option", { name: "Aadhaar number" }).click();
  await page.getByRole("textbox", { name: "Number" }).fill(AADHAAR);
}

test("the administrator makes the nurse the front desk", async ({ browser }) => {
  const admin = await asAdmin(browser);
  await admin.goto(new URL(recall("nurse-staff-url")).pathname);
  await admin.getByRole("tab", { name: "Access" }).click();
  await admin.getByRole("button", { name: "Give access" }).click();
  const dialog = admin.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Role" }).click();
  await admin.getByRole("option", { name: "Receptionist / front desk" }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await dialog.getByRole("radio", { name: "Whole hospital" }).check();
  await dialog.getByRole("textbox", { name: "Reason" }).fill("Covers the front desk");
  await dialog.getByRole("button", { name: "Give access" }).click();
  await expect(dialog).toBeHidden();
  await expect(admin.getByRole("table", { name: "Access" }).getByText("Receptionist / front desk")).toBeVisible();
});

test("the front desk registers a patient: MRN given, ID number masked", async ({ browser }) => {
  const page = await asDesk(browser);
  await openMenu(page, "Patients");
  await expectAccessible(page, "Patients");
  await page.getByRole("link", { name: "Register new patient" }).click();
  await expect(page.getByRole("heading", { name: "Register new patient" })).toBeVisible();
  await fillPatient(page, "Leela");
  await expectAccessible(page, "Register new patient");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Leela Kumari" })).toBeVisible();
  await expect(page.getByText(/^MRN-\d{8}$/).first()).toBeVisible(); // breadcrumb and header
  await expect(page.getByText("XXXX XXXX 0337")).toBeVisible();
  await expect(page.getByText(AADHAAR)).toHaveCount(0); // the full number is never shown
  await expectAccessible(page, "Patient record");
});

test("the same Aadhaar on a second patient is refused", async ({ browser }) => {
  const page = await asDesk(browser);
  await page.goto("/patients/register");
  await fillPatient(page, "Meena");
  await page.getByRole("button", { name: "Register", exact: true }).click();
  await expect(page.getByText(/already recorded for patient MRN-\d{8}/)).toBeVisible();
});

test("the administrator looks the patient up but does not register", async ({ browser }) => {
  const admin = await asAdmin(browser);
  await admin.goto("/");
  await openMenu(admin, "Patients");
  await expect(admin.getByRole("table", { name: "Patients" }).getByText("Leela Kumari")).toBeVisible();
  await expect(admin.getByRole("link", { name: "Register new patient" })).toHaveCount(0);
});
