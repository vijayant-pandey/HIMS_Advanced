// Hospital set-up by the administrator (spec 4.1, 4.2, 4.10, 21 steps 1–3): facility, department,
// the location tree down to beds, and bed status rules. Each screen is checked for accessibility.
import { expect, test } from "@playwright/test";

import { expectAccessible, openMenu, storageFor } from "../helpers";

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
