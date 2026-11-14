// Patients (HIMS-PAT-001; spec 4.5, 13): the administrator makes the nurse from test 03 the front
// desk; she registers a patient with an age, a mobile and an ID number; the record opens with its
// MRN and the number masked; the same number on a second patient is refused; the administrator can
// look but not register; then she finds the patient again by another spelling, phone and ID number
// (HIMS-PAT-002); the chart keeps its header on every tab and shows medical records who opened it
// (HIMS-PAT-005); as medical records (two-factor required) she restricts the record, which the
// administrator then cannot find by name or open, and lifts it again (HIMS-PAT-006). Every person
// and number is invented.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { NEW_STAFF_PASSWORD } from "../config.mjs";
import { expectAccessible, freshCode, openMenu, recall, remember, signIn, storageFor } from "../helpers";

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

/** After she becomes medical records (HIMS-PAT-006: restricted records need two-factor). */
async function asRecords(browser: Browser): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signIn(page, NURSE_EMAIL, NEW_STAFF_PASSWORD, recall("nurse-secret"));
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

// HIMS-PAT-002: one search box finds her by another spelling (in any order, with her age), by
// phone and by ID number; a name nobody has offers registration.
test("the front desk finds the patient by spelling, phone and ID number", async ({ browser }) => {
  const page = await asDesk(browser);
  await page.goto("/patients");
  const table = page.getByRole("table", { name: "Patients" });
  const searchFor = async (text: string) => {
    await page.getByRole("textbox", { name: "Search" }).fill(text);
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Search results" })).toBeVisible();
  };
  await searchFor("Kumaari Leelaa 41");
  await expect(table.getByText("Leela Kumari")).toBeVisible();
  await expect(table.getByRole("cell", { name: "Name", exact: true })).toBeVisible(); // found by
  await expectAccessible(page, "Patient search results");
  await searchFor("98765 40001");
  await expect(table.getByText("Leela Kumari")).toBeVisible();
  await expect(table.getByRole("cell", { name: "Phone", exact: true })).toBeVisible();
  await searchFor(AADHAAR);
  await expect(table.getByText("Leela Kumari")).toBeVisible();
  await expect(table.getByText(AADHAAR)).toHaveCount(0); // only the minimum is shown
  await searchFor("Zebedee Quartermaine");
  await expect(page.getByText(/No patient found/)).toBeVisible();
});

// HIMS-PAT-005: the chart header stays on every tab; the front desk sees no History tab; once the
// administrator makes her a medical records officer too, History shows who opened the record.
test("the chart: header on every tab, and medical records see who opened it", async ({ browser }) => {
  const page = await asDesk(browser);
  await page.goto("/patients");
  await page.getByRole("textbox", { name: "Search" }).fill("Leela Kumari");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("table", { name: "Patients" }).getByRole("link", { name: /^MRN-/ }).click();
  const header = page.getByRole("region", { name: "Patient header" });
  await expect(header.getByRole("heading", { name: "Leela Kumari" })).toBeVisible();
  await expect(header.getByText("Allergies not asked yet")).toBeVisible();
  await expect(page.getByRole("region", { name: "Clinical summary" })).toBeVisible();
  await expect(page.getByRole("region", { name: "ID numbers" }).getByText("XXXX XXXX 0337")).toBeVisible();
  await expectAccessible(page, "Patient chart overview");
  await page.getByRole("tab", { name: "Demographics" }).click();
  await expect(header).toBeVisible();
  await expect(page.getByRole("table", { name: "ID numbers" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "History" })).toHaveCount(0);
  const chart = page.url();

  const admin = await asAdmin(browser);
  await admin.goto(new URL(recall("nurse-staff-url")).pathname);
  await admin.getByRole("tab", { name: "Access" }).click();
  await admin.getByRole("button", { name: "Give access" }).click();
  const dialog = admin.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Role" }).click();
  await admin.getByRole("option", { name: "Medical records officer" }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await dialog.getByRole("radio", { name: "Whole hospital" }).check();
  await dialog.getByRole("textbox", { name: "Reason" }).fill("Keeps the patient records");
  await dialog.getByRole("button", { name: "Give access" }).click();
  await expect(dialog).toBeHidden();

  // Signs in again, now with the new role. It holds restricted records and the review of emergency
  // access, so two-factor is required (P0 part 04, HIMS-PAT-006): she sets it up as anyone would.
  const records = await (await browser.newContext()).newPage();
  await signIn(records, NURSE_EMAIL, NEW_STAFF_PASSWORD);
  await expect(records.getByText(/two-factor sign-in is required before you can continue/i)).toBeVisible();
  await records.getByRole("button", { name: "Set up two-factor sign-in" }).click();
  const secret = (await records.getByTestId("manual-key").innerText()).replace(/\s/g, "");
  remember("nurse-secret", secret);
  await records.getByLabel("6-digit code").fill(await freshCode(secret));
  await records.getByRole("button", { name: "Turn on" }).click();
  await records.getByRole("button", { name: "I've saved them" }).click();
  await expect(records.getByRole("navigation")).toBeVisible();
  remember("leela-chart", chart);
  await records.goto(chart);
  await records.getByRole("tab", { name: "History" }).click();
  const history = records.getByRole("table", { name: "Record history" });
  await expect(history.getByText("Patient registered (MRN issued)")).toBeVisible();
  await expect(history.getByText("Patient record opened").first()).toBeVisible();
  await expect(history.getByText("Asha Nurse").first()).toBeVisible();
  await expect(records.getByRole("region", { name: "Patient header" })).toBeVisible();
  await expectAccessible(records, "Patient chart history");
});

// HIMS-PAT-006: medical records restrict her record (VIP or staff). The administrator, who may
// open patients but not restricted ones, no longer finds her by name; her exact MRN shows only
// "Restricted record", and opening it says to ask medical records (administrators have no
// emergency access). Medical records see the opening listed and lift the restriction.
test("restricted record: hidden from search and opened only by medical records", async ({ browser }) => {
  const records = await asRecords(browser);
  await records.goto(recall("leela-chart"));
  const header = records.getByRole("region", { name: "Patient header" });
  await header.getByRole("button", { name: "Restrict record" }).click();
  const dialog = records.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Why" }).click();
  await records.getByRole("option", { name: "Member of staff (or their family)" }).click();
  await expect(records.locator(".MuiMenu-root")).toHaveCount(0);
  await dialog.getByRole("textbox", { name: "Reason" }).fill("She works in this hospital");
  await expectAccessible(records, "Restrict record dialog");
  await dialog.getByRole("button", { name: "Restrict record" }).click();
  await expect(dialog).toBeHidden();
  await expect(header.getByText("Restricted record")).toBeVisible();
  const mrn = (await header.getByText(/^MRN-\d{8}$/).innerText()).trim();

  const admin = await asAdmin(browser);
  await admin.goto("/patients");
  const table = admin.getByRole("table", { name: "Patients" });
  await admin.getByRole("textbox", { name: "Search" }).fill("Leela Kumari");
  await admin.getByRole("button", { name: "Search", exact: true }).click();
  await expect(admin.getByText(/No patient found/)).toBeVisible();
  await admin.getByRole("textbox", { name: "Search" }).fill(mrn);
  await admin.getByRole("button", { name: "Search", exact: true }).click();
  await expect(table.getByText("Restricted record")).toBeVisible();
  await expect(table.getByText("Leela Kumari")).toHaveCount(0);
  await table.getByRole("link", { name: mrn }).click();
  const gate = admin.getByRole("region", { name: "Restricted record" });
  await expect(gate.getByText(/ask medical records/)).toBeVisible();
  await expect(admin.getByText("Leela Kumari")).toHaveCount(0);
  await expectAccessible(admin, "Restricted record gate");

  await openMenu(records, "Emergency access");
  await expect(records.getByRole("heading", { name: "Emergency access" })).toBeVisible();
  await expectAccessible(records, "Emergency access");
  await records.getByRole("tab", { name: "Restricted record openings" }).click();
  const openings = records.getByRole("table", { name: "Restricted record openings" });
  await expect(openings.getByRole("link", { name: mrn }).first()).toBeVisible();
  await expect(openings.getByText("Medical records").first()).toBeVisible();

  await records.goto(recall("leela-chart"));
  await header.getByRole("button", { name: "Lift restriction" }).click();
  await dialog.getByRole("textbox", { name: "Reason" }).fill("Asked to lift it for the demo");
  await dialog.getByRole("button", { name: "Lift restriction" }).click();
  await expect(dialog).toBeHidden();
  await expect(header.getByText("Restricted record")).toHaveCount(0);
});
