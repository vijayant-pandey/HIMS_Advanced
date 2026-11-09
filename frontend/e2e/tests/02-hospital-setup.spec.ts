// Hospital set-up by the administrator (spec 4.1, 4.2, 4.10, 4.12, 4.23, 21 steps 1–3): facility,
// department, the location tree down to beds, bed status rules, equipment, letterhead and message
// wording. Each screen is checked for accessibility.
import { expect, test } from "@playwright/test";

import { expectAccessible, openMenu, storageFor } from "../helpers";

const ONE_PIXEL_PNG =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

test.use({ storageState: storageFor("admin") });
test.describe.configure({ mode: "serial" });

test("create a facility; a duplicate code is refused", async ({ page }) => {
  await page.goto("/");
  await openMenu(page, "Facilities");
  await expect(page.getByRole("heading", { name: "Facilities" })).toBeVisible();
  await expectAccessible(page, "Facilities");

  const fill = async (code: string, name: string) => {
    await page.getByRole("button", { name: "New facility" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("textbox", { name: "Code", exact: true }).fill(code);
    await dialog.getByRole("textbox", { name: "Name", exact: true }).fill(name);
    await dialog.getByLabel("State / region").fill("Maharashtra");
    await dialog.getByLabel("City").fill("Pune");
    await dialog.getByLabel("Address line 1").fill("1 Synthetic Road");
    await dialog.getByLabel("Postal code").fill("411001");
    await dialog.getByLabel("Time zone (IANA)").fill("Asia/Kolkata");
    await expectAccessible(page, "New facility dialog");
    await dialog.getByRole("button", { name: "Create" }).click();
    return dialog;
  };

  const dialog = await fill("TST1", "Test Branch One");
  await expect(dialog).toBeHidden();
  const table = page.getByRole("table", { name: "Facilities" });
  await expect(table.getByText("Test Branch One")).toBeVisible();

  const duplicate = await fill("TST1", "Copy");
  await expect(duplicate.getByText(/already/i)).toBeVisible();
  await duplicate.getByRole("button", { name: "Cancel" }).click();
});

test("add a department to the facility", async ({ page }) => {
  await page.goto("/departments");
  await expect(page.getByRole("heading", { name: "Departments" })).toBeVisible();
  await page.getByRole("button", { name: "Add department" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Facility" }).click();
  await page.getByRole("option", { name: "Test Branch One" }).click();
  await dialog.getByRole("textbox", { name: "Name", exact: true }).fill("Cardiology");
  await dialog.getByRole("textbox", { name: "Code", exact: true }).fill("CARD");
  await expectAccessible(page, "Add department dialog");
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("link", { name: "Cardiology" }).or(page.getByText("Cardiology")).first()).toBeVisible();
  await expectAccessible(page, "Departments");
});

test("build building → floor → ward → room → beds, then put a bed into maintenance", async ({ page }) => {
  await page.goto("/locations");
  await expect(page.getByRole("heading", { name: "Locations" })).toBeVisible();
  // With one facility the screen picks it by itself; otherwise choose it.
  const chooser = page.getByRole("combobox", { name: "Facility" });
  if (await chooser.count()) {
    await chooser.click();
    await page.getByRole("option", { name: "Test Branch One" }).click();
  }

  const save = async (button: string) => {
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: button, exact: true }).click();
    await expect(dialog).toBeHidden();
  };

  await page.getByRole("button", { name: "Add building" }).click();
  await page.getByRole("dialog").getByRole("textbox", { name: "Code", exact: true }).fill("MB");
  await page.getByRole("dialog").getByRole("textbox", { name: "Name", exact: true }).fill("Main Block");
  await save("Save");

  await page.getByRole("button", { name: /Add floor/ }).first().click();
  await page.getByRole("dialog").getByLabel("Level").fill("0");
  await page.getByRole("dialog").getByRole("textbox", { name: "Name", exact: true }).fill("Ground floor");
  await save("Save");

  await page.getByRole("button", { name: /Add ward/ }).first().click();
  await page.getByRole("dialog").getByRole("textbox", { name: "Code", exact: true }).fill("W1");
  await page.getByRole("dialog").getByRole("textbox", { name: "Name", exact: true }).fill("Cardiac Ward");
  await save("Save");

  await page.getByRole("button", { name: /Add room/ }).first().click();
  await page.getByRole("dialog").getByRole("textbox", { name: "Code", exact: true }).fill("101");
  await page.getByRole("dialog").getByRole("textbox", { name: "Name", exact: true }).fill("Room 101");
  await save("Save");

  await page.getByRole("button", { name: /Add beds/ }).first().click();
  const beds = page.getByRole("dialog");
  await beds.getByLabel("Prefix").fill("b");
  await beds.getByLabel("Start at").fill("1");
  await beds.getByLabel("How many").fill("3");
  await expectAccessible(page, "Add beds dialog");
  await save("Add beds");
  await expect(page.getByRole("button", { name: "Bed B01, Available" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Bed B03, Available" })).toBeVisible();
  await expectAccessible(page, "Locations with beds");

  // A bed taken out of use needs a reason (spec 4.10).
  await page.getByRole("button", { name: "Bed B02, Available" }).click();
  const status = page.getByRole("dialog");
  await status.getByRole("combobox", { name: "Status" }).click();
  await page.getByRole("option", { name: "Maintenance" }).click();
  // Let the list finish its closing animation before checking contrast.
  await expect(page.locator(".MuiMenu-root")).toHaveCount(0);
  // Without a reason the change cannot be saved.
  await expect(status.getByRole("button", { name: "Save" })).toBeDisabled();
  await expectAccessible(page, "Bed status dialog");
  await status.getByLabel(/Reason/).fill("Broken side rail");
  await status.getByRole("button", { name: "Save" }).click();
  await expect(status).toBeHidden();
  await expect(page.getByRole("button", { name: /Bed B02, Maintenance/ })).toBeVisible();
});

test("bed board: the ward's beds, why one is unavailable and its history; put it back", async ({ page }) => {
  // HIMS-FAC-008 (spec 4.10 availability board, 15.1 ward board). No patients yet.
  await page.goto("/");
  await openMenu(page, "Bed board");
  await expect(page.getByRole("heading", { name: "Bed board", level: 1 })).toBeVisible();
  const chooser = page.getByRole("combobox", { name: "Facility" });
  if (await chooser.count()) {
    await chooser.click();
    await page.getByRole("option", { name: "Test Branch One" }).click();
  }
  const ward = page.getByRole("region", { name: "Cardiac Ward" });
  await expect(ward.getByText("2 available · 1 maintenance")).toBeVisible();
  await expectAccessible(page, "Bed board");

  await ward.getByRole("button", { name: /Bed B02.*Room 101.*Maintenance/ }).click();
  const dialog = page.getByRole("dialog");
  const history = dialog.getByRole("list", { name: "Status history" });
  await expect(history.getByText("Available → Maintenance: Broken side rail")).toBeVisible();
  await expectAccessible(page, "Bed board: bed details");
  await dialog.getByRole("combobox", { name: "Status" }).click();
  await page.getByRole("option", { name: "Available" }).click();
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(ward.getByText("3 available")).toBeVisible();
});

test("letterhead: upload a logo, a wrong file is refused, details show on the page", async ({ page }) => {
  // HIMS-ORG-006 (spec 4.1). It stays on for the later tests, so the activation emails they read
  // are real letterhead emails.
  await page.goto("/");
  await openMenu(page, "Hospital settings");
  const section = page.getByRole("region", { name: "Letterhead" });
  const logoFile = section.getByLabel("Logo file");
  await logoFile.setInputFiles({
    name: "logo.svg",
    mimeType: "image/svg+xml",
    buffer: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"></svg>'),
  });
  await expect(section.getByText("The logo must be a PNG or JPG picture.")).toBeVisible();

  await logoFile.setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: Buffer.from(ONE_PIXEL_PNG, "base64") });
  await expect(section.getByRole("button", { name: "Remove logo" })).toBeVisible();
  const logo = section.locator("img");
  await expect(logo).toBeVisible();
  await expect.poll(() => logo.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(1);

  await section.getByRole("button", { name: "Edit letterhead" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Address").fill("1 Synthetic Road, Pune");
  await dialog.getByLabel("Phone").fill("+91 20 0000 0000");
  await expectAccessible(page, "Edit letterhead dialog");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(section.getByText("1 Synthetic Road, Pune")).toBeVisible();
  await expectAccessible(page, "Hospital settings with letterhead");
});

test("equipment register: add, record a visit, status needs a reason, prints with the letterhead", async ({ page }) => {
  // HIMS-FAC-009 (spec 4.12).
  await page.goto("/");
  await openMenu(page, "Equipment");
  await expect(page.getByRole("heading", { name: "Equipment", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Add equipment" }).click();
  const add = page.getByRole("dialog");
  const chooser = add.getByRole("combobox", { name: "Facility" });
  if (await chooser.count()) {
    await chooser.click();
    await page.getByRole("option", { name: "Test Branch One" }).click();
  }
  await add.getByLabel("Asset tag").fill("icu-vent-01");
  await add.getByRole("textbox", { name: "Name", exact: false }).first().fill("Ventilator");
  await add.getByRole("combobox", { name: "Ward" }).click();
  await page.getByRole("option", { name: "Cardiac Ward" }).click();
  await expect(page.locator(".MuiMenu-root")).toHaveCount(0);
  await add.getByRole("combobox", { name: "Room" }).click();
  await page.getByRole("option", { name: "Room 101" }).click();
  await expect(page.locator(".MuiMenu-root")).toHaveCount(0);
  await expectAccessible(page, "Add equipment dialog");
  await add.getByRole("button", { name: "Add", exact: true }).click();
  await expect(add).toBeHidden();

  const table = page.getByRole("table", { name: "Equipment" });
  await expect(table.getByText("Cardiac Ward · Room 101")).toBeVisible();
  await expectAccessible(page, "Equipment");

  await table.getByRole("button", { name: "ICU-VENT-01" }).click();
  const details = page.getByRole("dialog");
  await details.getByRole("button", { name: "Record a visit" }).click();
  const visit = page.getByRole("dialog", { name: /Record a visit/ });
  await visit.getByLabel("Done by").fill("Acme Biomed");
  await visit.getByLabel("Next one due").fill(`${new Date().getFullYear() + 1}-12-31`);
  await expectAccessible(page, "Record a visit dialog");
  await visit.getByRole("button", { name: "Save" }).click();
  await expect(visit).toBeHidden();
  const visits = page.getByRole("list", { name: "Visits" });
  await expect(visits.getByText(/Service on .*Acme Biomed/)).toBeVisible();

  await page.getByRole("button", { name: "Change status" }).click();
  const status = page.getByRole("dialog", { name: /Status of/ });
  await status.getByRole("combobox", { name: "Status" }).click();
  await page.getByRole("option", { name: "Under maintenance" }).click();
  await expect(page.locator(".MuiMenu-root")).toHaveCount(0);
  await expect(status.getByRole("button", { name: "Save" })).toBeDisabled();
  await status.getByLabel(/Reason/).fill("Battery fault");
  await status.getByRole("button", { name: "Save" }).click();
  await expect(status).toBeHidden();
  await expect(page.getByRole("dialog").getByText("Battery fault")).toBeVisible();
  await expectAccessible(page, "Equipment details");
  await page.getByRole("button", { name: "Close" }).click();

  // On paper: the letterhead and the register, without the menu or the buttons.
  await page.emulateMedia({ media: "print" });
  const letterhead = page.getByTestId("print-letterhead");
  await expect(letterhead).toBeVisible();
  await expect(letterhead.getByText("1 Synthetic Road, Pune")).toBeVisible();
  await expect(letterhead.locator("img")).toBeVisible();
  await expect(page.getByRole("navigation")).toBeHidden();
  await expect(page.getByRole("button", { name: "Add equipment" })).toBeHidden();
  await expect(table.getByText("Ventilator")).toBeVisible();
  await page.emulateMedia({ media: "screen" });
  await expect(letterhead).toBeHidden();
});

test("message wording: wrong wording refused, a change is previewed and saved, the standard comes back", async ({ page }) => {
  // HIMS-NOTIF-003 (spec 4.1, 4.23).
  await page.goto("/");
  await openMenu(page, "Message wording");
  await expect(page.getByRole("heading", { name: "Message wording", level: 1 })).toBeVisible();
  await expectAccessible(page, "Message wording");
  const row = page.getByRole("row", { name: /Account invitation/ });
  await expect(row.getByText("Standard")).toBeVisible();

  await row.getByRole("button", { name: "Account invitation" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/The activation link \(must stay\)/)).toBeVisible();
  await expectAccessible(page, "Message wording dialog");
  const message = dialog.getByRole("textbox", { name: "Message" });
  await message.fill("Welcome {{name}}, there is no link here.");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog.getByText(/must keep \{\{link\}\}/)).toBeVisible();

  await message.fill("Welcome {{name}}. Please open {{link}}");
  await dialog.getByRole("button", { name: "Preview" }).click();
  await expect(dialog.getByRole("region", { name: "Preview" }).getByText(/Welcome Asha Verma/)).toBeVisible();
  await expectAccessible(page, "Message wording preview");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(row.getByText("Changed")).toBeVisible();

  await row.getByRole("button", { name: "Account invitation" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Use the standard wording" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(row.getByText("Standard")).toBeVisible();
});

test("numbering, features and hospital settings screens open and are accessible", async ({ page }) => {
  for (const [menu, heading] of [
    ["Numbering", "Numbering"],
    ["Features", "Features"],
    ["Hospital settings", "Hospital settings"],
  ] as const) {
    await page.goto("/");
    await openMenu(page, menu);
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await expectAccessible(page, menu);
  }
});
