// Staff onboarding and access (spec 4.3, 4.4, 13.2, 21 steps 4–5): add a staff member, invite
// them, they activate in their own browser and see "no access yet" with a reference number; the
// administrator gives a role; cover is arranged. Uses two browsers like two real people.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { localDate } from "../../src/components/dates";
import { ADMIN, AUDITOR, NEW_STAFF_PASSWORD } from "../config.mjs";
import {
  expectAccessible,
  newLinkFromEmail,
  openMenu,
  recall,
  remember,
  signIn,
  storageFor,
  subjectsFor,
} from "../helpers";

const NURSE = { email: "asha.nurse@synthetic.test", first: "Asha", last: "Nurse" };
const NURSE_PASSWORD = NEW_STAFF_PASSWORD;

test.describe.configure({ mode: "serial" });

async function asAdmin(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ storageState: storageFor("admin") });
  return context.newPage();
}

test("add a staff member and send the invitation", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/");
  await openMenu(page, "Staff");
  await expectAccessible(page, "Staff list");
  await page.getByRole("button", { name: "Add staff member" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "First name" }).fill(NURSE.first);
  await dialog.getByRole("textbox", { name: "Last name" }).fill(NURSE.last);
  await dialog.getByRole("textbox", { name: "Employee number" }).fill("E2E-1002");
  await dialog.getByRole("combobox", { name: "Staff type" }).click();
  await page.getByRole("option", { name: "Nurse" }).click();
  await expect(page.locator(".MuiMenu-root")).toHaveCount(0);
  await dialog.getByLabel("Joined on").fill("2026-01-05");
  await dialog.getByRole("textbox", { name: "Work email (optional)" }).fill(NURSE.email);
  await expectAccessible(page, "Add staff dialog");
  await dialog.getByRole("button", { name: "Add", exact: true }).click();

  await expect(page.getByRole("heading", { name: /Asha Nurse/ })).toBeVisible();
  await expectAccessible(page, "Staff detail");
  // Adding a staff member with a work email sends the invitation at once.
  await expect(page.getByText(/Invitation sent to asha\.nurse@synthetic\.test/)).toBeVisible();
  const first = await newLinkFromEmail(NURSE.email, "activate");
  // Resending replaces the link: the first one stops working.
  await page.getByRole("button", { name: "Resend invitation" }).click();
  await expect(page.getByText(/Invitation emailed to asha\.nurse@synthetic\.test/)).toBeVisible();
  remember("nurse-old-link", first);
  remember("nurse-link", await newLinkFromEmail(NURSE.email, "activate", [first]));
  remember("nurse-staff-url", page.url());
});

test("the nurse activates her account and sees 'no access yet' with a reference", async ({ browser }) => {
  const link = recall("nurse-link");
  const context = await browser.newContext(); // her own browser, nobody signed in
  const page = await context.newPage();
  await page.goto(recall("nurse-old-link"));
  await expect(page.getByText("Invitation link is not valid")).toBeVisible();
  await page.goto(link);
  await expect(page.getByText(/Activate your account/i)).toBeVisible();
  await expectAccessible(page, "Activation page");

  await page.getByLabel("New password").fill("short");
  await page.getByLabel("Confirm password").fill("short");
  await page.getByRole("button", { name: "Activate and sign in" }).click();
  await expect(page.getByText(/at least 12 characters/i)).toBeVisible();

  await page.getByLabel("New password").fill(NURSE_PASSWORD);
  await page.getByLabel("Confirm password").fill(NURSE_PASSWORD);
  await page.getByRole("button", { name: "Activate and sign in" }).click();
  await expect(page.getByText(/don't have access to any area of HIMS yet/i)).toBeVisible();
  const reference = page.getByTestId("reference");
  await expect(reference).not.toHaveText(/Recording/);
  remember("nurse-no-access-reference", (await reference.innerText()).trim());
  await expectAccessible(page, "No access yet page");

  // The link works only once.
  const reuse = await context.newPage();
  await reuse.goto(link);
  await expect(reuse.getByText("Invitation link is not valid")).toBeVisible();
  await context.close();
});

test("the administrator gives the nurse basic access; she then sees the hospital", async ({ browser }) => {
  const admin = await asAdmin(browser);
  await admin.goto(new URL(recall("nurse-staff-url")).pathname);
  await expect(admin.getByText(/Can sign in as asha\.nurse@synthetic\.test/)).toBeVisible();
  await admin.getByRole("tab", { name: "Access" }).click();
  await admin.getByRole("button", { name: "Give access" }).click();
  const dialog = admin.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Role" }).click();
  await admin.getByRole("option", { name: "Basic staff access" }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await dialog.getByRole("radio", { name: "Whole hospital" }).check();
  await dialog.getByRole("textbox", { name: "Reason" }).fill("Joined the cardiac ward");
  await expectAccessible(admin, "Give access dialog");
  await dialog.getByRole("button", { name: "Give access" }).click();
  await expect(dialog).toBeHidden();
  await expect(admin.getByRole("table", { name: "Access" }).getByText("Basic staff access")).toBeVisible();

  const nurse = await (await browser.newContext()).newPage();
  await signIn(nurse, NURSE.email, NURSE_PASSWORD);
  const menu = nurse.getByRole("navigation");
  await expect(menu.getByRole("link", { name: "Facilities", exact: true })).toBeVisible();
  await expect(menu.getByRole("link", { name: "Staff", exact: true })).toHaveCount(0);
  await expect(menu.getByRole("link", { name: "Accounts", exact: true })).toHaveCount(0);
});

test("cover: the nurse's access is lent to a colleague for a week, then ended early", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/");
  await openMenu(page, "Cover");
  await expect(page.getByText("No cover arranged at the moment.")).toBeVisible();
  await expectAccessible(page, "Cover page");

  await page.getByRole("button", { name: "Arrange cover" }).click();
  const dialog = page.getByRole("dialog");
  const pick = async (label: string, search: string, option: RegExp) => {
    await dialog.getByRole("combobox", { name: label }).fill(search);
    await page.getByRole("option", { name: option }).click();
  };
  await pick("Person being covered", "Asha", /Asha Nurse/);
  await pick("Person covering", "E2E Aud", new RegExp(AUDITOR.name));
  await expect(dialog.getByRole("checkbox", { name: /Basic staff access/ })).toBeChecked();
  const nextWeek = localDate(new Date(Date.now() + 7 * 86_400_000));
  await dialog.getByLabel(/Ends on/).fill(nextWeek);
  await dialog.getByRole("textbox", { name: "Reason" }).fill("Annual leave");
  await expectAccessible(page, "Arrange cover dialog");
  await dialog.getByRole("button", { name: "Arrange cover" }).click();
  await expect(page.getByText(/E2E Auditor covers for Asha Nurse until/)).toBeVisible();
  expect(subjectsFor(NURSE.email)).toContain("HIMS: E2E Auditor is covering for you");

  await page.getByRole("button", { name: "End cover by E2E Auditor for Asha Nurse" }).click();
  const end = page.getByRole("dialog");
  await end.getByLabel(/Why is it ending early/).fill("Back early");
  await end.getByRole("button", { name: "End cover now" }).click();
  await expect(end).toBeHidden();
  await page.getByRole("tab", { name: "Past" }).click();
  await expect(page.getByRole("table", { name: "Cover arrangements" }).getByText("Ended early", { exact: true })).toBeVisible();
});

test("you cannot arrange cover that gives yourself access", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/cover");
  await page.getByRole("button", { name: "Arrange cover" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Person being covered" }).fill("Asha");
  await page.getByRole("option", { name: /Asha Nurse/ }).click();
  await dialog.getByRole("combobox", { name: "Person covering" }).fill("E2E Adm");
  await page.getByRole("option", { name: /E2E Admin/ }).click();
  const tomorrow = localDate(new Date(Date.now() + 86_400_000));
  await dialog.getByLabel(/Ends on/).fill(tomorrow);
  await dialog.getByRole("textbox", { name: "Reason" }).fill("Trying to give myself access");
  await dialog.getByRole("button", { name: "Arrange cover" }).click();
  await expect(dialog.getByText(/cannot arrange cover that gives yourself access/)).toBeVisible();
});

test("access review: start one and keep the nurse's access", async ({ browser }) => {
  const page = await asAdmin(browser);
  await page.goto("/");
  await openMenu(page, "Access reviews");
  await expectAccessible(page, "Access reviews");
  await page.getByRole("button", { name: "Start a review" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Start review" }).click();
  await page.getByRole("link", { name: /^Access review / }).first().click();
  await page.getByRole("button", { name: /^Keep Asha Nurse Basic staff access/ }).click();
  await expect(page.getByText("Your own access: another reviewer decides").first()).toBeVisible();
  await expectAccessible(page, "Access review detail");
});

test("rota and leave: a night shift for the nurse, she asks for that day off, the administrator approves", async ({
  browser,
}) => {
  // Spec 4.3 shift schedules and leave (HIMS-STAFF-012).
  const admin = await asAdmin(browser);
  await admin.goto(new URL(recall("nurse-staff-url")).pathname);
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

  const tomorrow = localDate(new Date(Date.now() + 86_400_000));
  await openMenu(admin, "Rota");
  await expect(admin.getByRole("table", { name: "Rota for Cardiology" })).toBeVisible();
  await expect(admin.getByRole("region", { name: "On call now" })).toBeVisible();
  await expectAccessible(admin, "Rota");
  await admin.getByRole("button", { name: "Plan shifts" }).click();
  const plan = admin.getByRole("dialog");
  await plan.getByRole("combobox", { name: "Person" }).click();
  await admin.getByRole("option", { name: "Asha Nurse" }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await plan.getByRole("combobox", { name: "Shift" }).click();
  await admin.getByRole("option", { name: /^Night ·/ }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await plan.getByLabel("First day").fill(tomorrow);
  await expectAccessible(admin, "Plan shifts dialog");
  await plan.getByRole("button", { name: "Plan" }).click();
  await expect(plan).toBeHidden();
  await admin.getByRole("tab", { name: "Shift types" }).click();
  await expect(admin.getByRole("table", { name: "Shift types" })).toContainText("On call (24 hours)");

  const nurse = await (await browser.newContext()).newPage();
  await signIn(nurse, NURSE.email, NURSE_PASSWORD);
  await nurse.getByRole("link", { name: "My schedule" }).click();
  await expect(nurse.getByRole("table", { name: "My coming shifts" })).toContainText("20:00-08:00");
  await expectAccessible(nurse, "My schedule");
  await nurse.getByRole("button", { name: "Ask for leave" }).click();
  const ask = nurse.getByRole("dialog");
  await ask.getByLabel("First day").fill(tomorrow);
  await ask.getByLabel("Last day").fill(tomorrow);
  await expectAccessible(nurse, "Ask for leave dialog");
  await ask.getByRole("button", { name: "Send" }).click();
  await expect(ask).toBeHidden();
  await expect(nurse.getByRole("table", { name: "My leave" })).toContainText("Waiting for a decision");
  expect(subjectsFor(ADMIN.email).some((s) => s.startsWith("Leave to decide: Asha Nurse"))).toBe(true);

  await openMenu(admin, "Leave");
  await admin.getByRole("button", { name: "Approve leave for Asha Nurse" }).click();
  const approve = admin.getByRole("dialog");
  await expect(approve).toContainText("1 planned shift(s) during this leave");
  await approve.getByRole("checkbox", { name: /Cancel those shifts/ }).check();
  await expectAccessible(admin, "Approve leave dialog");
  await approve.getByRole("button", { name: "Approve leave" }).click();
  await expect(approve).toBeHidden();
  await admin.getByRole("tab", { name: "Approved, coming up" }).click();
  await expect(admin.getByRole("table", { name: "Leave" })).toContainText("Asha Nurse");
  await expectAccessible(admin, "Leave");

  await nurse.reload();
  await expect(nurse.getByRole("table", { name: "My leave" })).toContainText("Approved");
  await expect(nurse.getByRole("table", { name: "My coming shifts" })).toContainText("No shifts planned");
  expect(subjectsFor(NURSE.email).some((s) => s.startsWith("Leave approved"))).toBe(true);
});

test("staff group: a clinical privilege, a minimum for a shift, and leave over the balance", async ({ browser }) => {
  // Spec 4.3: HIMS-STAFF-016, HIMS-STAFF-015, HIMS-STAFF-013. The hospital sets every value.
  const admin = await asAdmin(browser);
  await admin.goto("/");
  await openMenu(admin, "Job titles & catalogs");
  await admin.getByRole("tab", { name: "Clinical privileges" }).click();
  await admin.getByRole("button", { name: "Add clinical privilege" }).click();
  const newPrivilege = admin.getByRole("dialog");
  await newPrivilege.getByRole("textbox", { name: "Name" }).fill("Central line insertion");
  await expectAccessible(admin, "Add clinical privilege dialog");
  await newPrivilege.getByRole("button", { name: "Save" }).click();
  await expect(newPrivilege).toBeHidden();

  await admin.goto(new URL(recall("nurse-staff-url")).pathname);
  await admin.getByRole("tab", { name: /^Privileges/ }).click();
  await admin.getByRole("button", { name: "Give a privilege" }).click();
  const give = admin.getByRole("dialog");
  await give.getByRole("combobox", { name: /Privilege/ }).click();
  await admin.getByRole("option", { name: "Central line insertion" }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await expectAccessible(admin, "Give a privilege dialog");
  await give.getByRole("button", { name: "Give" }).click();
  await expect(give).toBeHidden();
  const held = admin.getByRole("table", { name: "Clinical privileges" });
  await expect(held).toContainText("Central line insertion");
  await expect(held).toContainText("Current");
  await expectAccessible(admin, "Clinical privileges");

  await openMenu(admin, "Rota");
  await expect(admin.getByRole("table", { name: "Rota for Cardiology" })).toBeVisible();
  await admin.getByRole("button", { name: "Minimum staffing" }).click();
  const minimums = admin.getByRole("dialog");
  const addMinimum = minimums.getByRole("region", { name: "Add a minimum" });
  await addMinimum.getByRole("combobox", { name: "Shift" }).click();
  await admin.getByRole("option", { name: /^Night ·/ }).click();
  await expect(admin.locator(".MuiMenu-root")).toHaveCount(0);
  await addMinimum.getByLabel("At least").fill("2");
  await addMinimum.getByRole("button", { name: "Add" }).click();
  await expect(minimums.getByRole("table", { name: "Minimum staffing" })).toContainText("Night");
  await expectAccessible(admin, "Minimum staffing dialog");
  await minimums.getByRole("button", { name: "Close" }).click();
  await admin.getByRole("button", { name: "Next week" }).click();
  await expect(admin.getByRole("region", { name: "Staffing gaps" })).toContainText("below the minimum");
  await expectAccessible(admin, "Rota with staffing gaps");

  await openMenu(admin, "Leave");
  await admin.getByRole("tab", { name: "Entitlements" }).click();
  await admin.getByRole("button", { name: "Add an entitlement" }).click();
  const entitlement = admin.getByRole("dialog");
  await entitlement.getByLabel("Days per leave year").fill("1");
  await expectAccessible(admin, "Add an entitlement dialog");
  await entitlement.getByRole("button", { name: "Save" }).click();
  await expect(entitlement).toBeHidden();
  await expect(admin.getByRole("table", { name: "Leave entitlements" })).toContainText("Annual / earned leave");
  await expectAccessible(admin, "Leave entitlements");
  await admin.getByRole("tab", { name: "Balances" }).click();
  await expect(admin.getByRole("table", { name: /^Leave balances/ })).toContainText("Asha Nurse");
  await expectAccessible(admin, "Leave balances");

  const nurse = await (await browser.newContext()).newPage();
  await signIn(nurse, NURSE.email, NURSE_PASSWORD);
  await nurse.getByRole("link", { name: "My schedule" }).click();
  await expect(nurse.getByRole("table", { name: "My leave balance" })).toContainText("Annual / earned leave");
  const first = localDate(new Date(Date.now() + 20 * 86_400_000));
  const last = localDate(new Date(Date.now() + 22 * 86_400_000));
  await nurse.getByRole("button", { name: "Ask for leave" }).click();
  const ask = nurse.getByRole("dialog");
  await ask.getByLabel("First day").fill(first);
  await ask.getByLabel("Last day").fill(last);
  await ask.getByRole("button", { name: "Send" }).click();
  await expect(ask).toBeHidden();

  await admin.getByRole("tab", { name: "To decide" }).click();
  await admin.reload();
  await admin.getByRole("button", { name: "Approve leave for Asha Nurse" }).click();
  const approve = admin.getByRole("dialog");
  await expect(approve).toContainText("over Asha Nurse's balance");
  await expect(approve.getByRole("button", { name: "Approve leave" })).toBeDisabled();
  await approve.getByRole("checkbox", { name: /Approve anyway/ }).check();
  await approve.getByRole("textbox", { name: /Reason/ }).fill("Family emergency");
  await expectAccessible(admin, "Approve over the balance dialog");
  await approve.getByRole("button", { name: "Approve leave" }).click();
  await expect(approve).toBeHidden();
  await nurse.reload();
  await expect(nurse.getByRole("table", { name: "My leave", exact: true })).toContainText("Approved");
});
