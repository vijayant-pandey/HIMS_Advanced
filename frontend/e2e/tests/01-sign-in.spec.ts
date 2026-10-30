// Sign-in safety (spec 13.1, 13.5): wrong password and wrong code are refused; the menu shows
// only what each role may use.
import { expect, test } from "@playwright/test";

import { ADMIN, AUDITOR } from "../config.mjs";
import { expectAccessible, recall, signIn, storageFor } from "../helpers";

test("sign-in page is accessible and refuses a wrong password", async ({ page }) => {
  await page.goto("/login");
  await expectAccessible(page, "sign-in page");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password", { exact: true }).fill("Synthetic-Wrong-Passw0rd-0000");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("a wrong two-factor code is refused, the right one lets the person in", async ({ page }) => {
  await signIn(page, ADMIN.email, ADMIN.password);
  await page.getByLabel("Authentication code").fill("000000");
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("navigation")).toHaveCount(0);

  await signIn(page, ADMIN.email, ADMIN.password, recall("admin-secret"));
  await expect(page.getByRole("navigation")).toBeVisible();
});

test.describe("menus follow the role", () => {
  test.describe("administrator", () => {
    test.use({ storageState: storageFor("admin") });
    test("sees setup screens but not the audit log", async ({ page }) => {
      await page.goto("/");
      const menu = page.getByRole("navigation");
      for (const item of ["Facilities", "Departments", "Locations", "Staff", "Access", "Accounts", "Cover"]) {
        await expect(menu.getByRole("link", { name: item, exact: true })).toBeVisible();
      }
      await expect(menu.getByRole("link", { name: "Audit log", exact: true })).toHaveCount(0);
      await expectAccessible(page, "home page (administrator)");
    });
  });

  test.describe("auditor", () => {
    test.use({ storageState: storageFor("auditor") });
    test("sees the audit screens only", async ({ page }) => {
      await page.goto("/");
      const menu = page.getByRole("navigation");
      for (const item of ["Audit log", "Audit integrity", "Access reviews"]) {
        await expect(menu.getByRole("link", { name: item, exact: true })).toBeVisible();
      }
      for (const item of ["Facilities", "Staff", "Accounts"]) {
        await expect(menu.getByRole("link", { name: item, exact: true })).toHaveCount(0);
      }
    });
  });
});

test("signed out people are sent to the sign-in page", async ({ page }) => {
  await page.goto("/staff");
  await expect(page).toHaveURL(/\/login/);
  expect(AUDITOR.email).toContain("@synthetic.test");
});
