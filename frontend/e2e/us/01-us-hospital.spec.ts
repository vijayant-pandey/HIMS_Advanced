// The US hospital (spec 19.2, ADR-003; HIMS-QA-003): a separate deployment with its own database,
// country, time zone, currency, catalogs and legal rules. Run with `npm run e2e:us`.
//
// One story on one synthetic US hospital: settings and features follow the country; a facility and
// department are set up; a nurse is added with US qualifications and licences, activates her account
// and signs in; a security incident gets the HIPAA deadlines; the auditor finds it all in the audit
// log; and the hospital's own admin console answers.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { ADMIN, E2E, NEW_STAFF_PASSWORD } from "../config.mjs";
import {
  expectAccessible,
  freshCode,
  newLinkFromEmail,
  openMenu,
  recall,
  remember,
  signIn,
  storageFor,
} from "../helpers";

const NURSE = { email: "jordan.nurse@synthetic.test", first: "Jordan", last: "Nurse" };

test.describe.configure({ mode: "serial" });

async function asAdmin(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ storageState: storageFor("admin") });
  return context.newPage();
}

test("this run is the US hospital", () => {
  expect(E2E.deployment).toBe("us");
  expect(E2E.apiPort).toBe(8110);
});

test("hospital settings show the United States, Eastern time and dollars", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/");
  await openMenu(page, "Hospital settings");
  await expect(page.getByRole("heading", { name: "Hospital settings", level: 1 })).toBeVisible();
  await expect(page.getByText("E2E Synthetic Medical Center", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("United States", { exact: true })).toBeVisible();
  await expect(page.getByText("USD", { exact: true })).toBeVisible();
  await expect(page.getByText("America/New_York", { exact: true })).toBeVisible();
  await expectAccessible(page, "Hospital settings (US)");
});

test("features: US insurance is offered here, India's ABDM and TPAs are not", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/features");
  await expect(page.getByRole("heading", { name: "Features", level: 1 })).toBeVisible();
  const row = (name: string) => page.getByRole("row").filter({ hasText: name });
  await expect(row("US insurance (Stedi)").getByText("Not offered in this country")).toHaveCount(0);
  await expect(row("ABDM (Ayushman Bharat Digital Mission)").getByText("Not offered in this country")).toBeVisible();
  await expect(row("Indian insurers, TPAs and government schemes").getByText("Not offered in this country")).toBeVisible();
  await expectAccessible(page, "Features (US)");
});

test("set up a facility in New York and a department", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/facilities");
  await page.getByRole("button", { name: "New facility" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "Code", exact: true }).fill("NYC1");
  await dialog.getByRole("textbox", { name: "Name", exact: true }).fill("Synthetic Manhattan Campus");
  // A new branch starts in the hospital's own country and time zone.
  await expect(dialog.getByRole("combobox", { name: "Country" })).toHaveText("United States");
  await expect(dialog.getByLabel("Time zone (IANA)")).toHaveValue("America/New_York");
  await dialog.getByLabel("State / region").fill("New York");
  await dialog.getByLabel("City").fill("New York");
  await dialog.getByLabel("Address line 1").fill("1 Synthetic Avenue");
  await dialog.getByLabel("Postal code").fill("10001");
  await expectAccessible(page, "New facility dialog (US)");
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("table", { name: "Facilities" }).getByText("Synthetic Manhattan Campus")).toBeVisible();

  await page.goto("/departments");
  await page.getByRole("button", { name: "Add department" }).click();
  const department = page.getByRole("dialog");
  await department.getByRole("combobox", { name: "Facility" }).click();
  await page.getByRole("option", { name: "Synthetic Manhattan Campus" }).click();
  await department.getByRole("textbox", { name: "Name", exact: true }).fill("Emergency Medicine");
  await department.getByRole("textbox", { name: "Code", exact: true }).fill("EM");
  await department.getByRole("button", { name: "Add", exact: true }).click();
  await expect(department).toBeHidden();
  await expect(page.getByText("Emergency Medicine").first()).toBeVisible();
});

test("a US nurse: US qualifications and licences only, then the invitation", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/staff");
  await page.getByRole("button", { name: "Add staff member" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "First name" }).fill(NURSE.first);
  await dialog.getByRole("textbox", { name: "Last name" }).fill(NURSE.last);
  await dialog.getByRole("textbox", { name: "Employee number" }).fill("US-2001");
  await dialog.getByRole("combobox", { name: "Staff type" }).click();
  await page.getByRole("option", { name: "Nurse" }).click();
  await expect(page.locator(".MuiMenu-root")).toHaveCount(0);
  await dialog.getByLabel("Joined on").fill("2026-02-02");
  await dialog.getByRole("textbox", { name: "Work email (optional)" }).fill(NURSE.email);
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Jordan Nurse/ })).toBeVisible();
  await expect(page.getByText(/Invitation sent to jordan\.nurse@synthetic\.test/)).toBeVisible();
  remember("us-nurse-link", await newLinkFromEmail(NURSE.email, "activate"));

  // Qualifications: the US list (BSN), not India's (B.Sc. Nursing).
  await page.getByRole("tab", { name: /Qualifications/ }).click();
  await page.getByRole("button", { name: "Add qualification" }).click();
  const qualification = page.getByRole("dialog");
  await qualification.getByRole("combobox", { name: "Qualification" }).click();
  await expect(page.getByRole("option", { name: "BSN (Bachelor of Science in Nursing)" })).toBeVisible();
  await expect(page.getByRole("option", { name: "B.Sc. Nursing" })).toHaveCount(0);
  await page.getByRole("option", { name: "BSN (Bachelor of Science in Nursing)" }).click();
  await qualification.getByRole("textbox", { name: "Institution" }).fill("Synthetic State University");
  await qualification.getByRole("button", { name: "Add", exact: true }).click();
  await expect(qualification).toBeHidden();
  await expect(page.getByText("BSN (Bachelor of Science in Nursing)")).toBeVisible();

  // A state licence (US).
  await page.getByRole("tab", { name: /Licences/ }).click();
  await page.getByRole("button", { name: "Add licence" }).click();
  const licence = page.getByRole("dialog");
  await licence.getByRole("combobox", { name: "Type" }).click();
  await page.getByRole("option", { name: "State licence (US)" }).click();
  await expect(page.locator(".MuiMenu-root")).toHaveCount(0);
  await licence.getByRole("textbox", { name: "Registration number" }).fill("RN-NY-000123");
  await licence.getByRole("textbox", { name: "Region" }).fill("US-NY");
  await licence.getByRole("textbox", { name: "Issued by" }).fill("Synthetic State Board of Nursing");
  await licence.getByLabel("Expires on").fill("2028-06-30");
  await expectAccessible(page, "Add licence dialog (US)");
  await licence.getByRole("button", { name: "Add", exact: true }).click();
  await expect(licence).toBeHidden();
  await expect(page.getByText("State licence (US)").first()).toBeVisible();
  await expectAccessible(page, "Staff detail (US)");
});

test("the nurse activates her account; she has no access yet", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(recall("us-nurse-link"));
  await expect(page.getByText(/Activate your account/i)).toBeVisible();
  await page.getByLabel("New password").fill(NEW_STAFF_PASSWORD);
  await page.getByLabel("Confirm password").fill(NEW_STAFF_PASSWORD);
  await page.getByRole("button", { name: "Activate and sign in" }).click();
  await expect(page.getByText(/don't have access to any area of HIMS yet/i)).toBeVisible();
  await context.close();

  // She can sign in again with her new password (no two-factor: she has no privileged access).
  const again = await (await browser.newContext()).newPage();
  await signIn(again, NURSE.email, NEW_STAFF_PASSWORD);
  await expect(again.getByText(/don't have access to any area of HIMS yet/i)).toBeVisible();
});

test("a security incident with personal data gets the HIPAA deadlines, not India's", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/security");
  await page.getByRole("button", { name: "Report a security incident" }).click();
  const report = page.getByRole("dialog");
  await report.getByLabel(/What happened/).fill("Email sent to the wrong address");
  await report.getByLabel(/Details/).fill("Synthetic test incident, no real people");
  await report.getByLabel("Personal or patient data may be affected").check();
  await report.getByRole("button", { name: "Send report" }).click();
  await expect(report.getByText(/Reference:/)).toBeVisible();
  await report.getByRole("button", { name: "Close" }).click();

  await page.goto("/compliance");
  await page.getByRole("tab", { name: "Incidents" }).click();
  const table = page.getByRole("table", { name: "Security incidents" });
  await expect(table.getByText("Email sent to the wrong address")).toBeVisible();
  await expect(table.getByText("US: tell the affected people")).toBeVisible();
  await expect(table.getByText("India: CERT-In report")).toHaveCount(0);
  await expectAccessible(page, "Compliance incidents (US)");
});

test("compliance lists the HIPAA requirements, not India's DPDP ones", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/compliance");
  const requirements = page.getByRole("table", { name: "Compliance requirements" });
  await expect(requirements.getByText(/HIPAA/).first()).toBeVisible();
  await expect(requirements.getByText(/DPDP/)).toHaveCount(0);
  await expectAccessible(page, "Compliance requirements (US)");
});

test("the auditor finds the nurse's invitation and the incident in the US audit log", async ({ browser }) => {
  const context = await browser.newContext({ storageState: storageFor("auditor") });
  const page = await context.newPage();
  await page.goto("/audit");
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
  const log = page.getByRole("table", { name: "Audit events" });
  // The nurse's own sign-ins, by her name.
  await page.getByLabel("Person").fill("Jordan");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(log.getByText(/Jordan Nurse/).first()).toBeVisible();
  // The incident, by its area.
  await page.getByLabel("Person").fill("");
  await page.getByRole("combobox", { name: "Area" }).click();
  await page.getByRole("option", { name: "Compliance" }).click();
  await page.getByRole("button", { name: "Search" }).click();
  await expect(log.getByText("Security incident reported").first()).toBeVisible();
  await expectAccessible(page, "Audit log (US)");
  await context.close();
});

test("the US hospital's own admin console answers, showing the US organization", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  const console = `http://127.0.0.1:${E2E.apiPort}/admin/`;
  await page.goto(console);
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByLabel("Authenticator code").fill(await freshCode(recall("admin-secret")));
  await page.getByRole("button", { name: /Log in|Sign in/ }).click();
  await expect(page).toHaveURL(/\/admin\/$/);
  await page.goto(`${console}organizations/organization/`);
  await expect(page.getByRole("link", { name: "E2E Synthetic Medical Center" })).toBeVisible();
  await page.goto(`${console}staff/staffmember/`);
  await expect(page.locator("#result_list").getByText(/Jordan/).first()).toBeVisible();
  await context.close();
});
