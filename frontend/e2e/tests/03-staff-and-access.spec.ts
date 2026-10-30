// Staff onboarding and access (spec 4.3, 4.4, 13.2, 21 steps 4–5): add a staff member, invite
// them, they activate in their own browser and see "no access yet" with a reference number; the
// administrator gives a role; cover is arranged. Uses two browsers like two real people.
import { type Browser, type Page, expect, test } from "@playwright/test";

import { AUDITOR, NEW_STAFF_PASSWORD } from "../config.mjs";
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
  const nextWeek = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
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
  const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
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

