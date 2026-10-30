// First sign-in of the administrator and the auditor: two-factor is required for both roles, so
// each sets it up exactly as a person would (spec 4.4, 13.1). Their signed-in sessions are saved
// for the other tests.
import { expect, test as setup } from "@playwright/test";

import { ADMIN, AUDITOR } from "../config.mjs";
import { freshCode, remember, signIn, storageFor } from "../helpers";

for (const [role, person] of [
  ["admin", ADMIN],
  ["auditor", AUDITOR],
] as const) {
  setup(`${role}: first sign-in sets up two-factor`, async ({ page }) => {
    await signIn(page, person.email, person.password);
    await expect(page.getByText(/two-factor sign-in is required before you can continue/i)).toBeVisible();

    await page.getByRole("button", { name: "Set up two-factor sign-in" }).click();
    const secret = (await page.getByTestId("manual-key").innerText()).replace(/\s/g, "");
    expect(secret).toMatch(/^[A-Z2-7]{16,}$/);
    remember(`${role}-secret`, secret);

    await page.getByLabel("6-digit code").fill(await freshCode(secret));
    await page.getByRole("button", { name: "Turn on" }).click();
    await expect(page.getByText(/Save these backup codes now/)).toBeVisible();
    await page.getByRole("button", { name: "I've saved them" }).click();

    await expect(page.getByRole("navigation")).toBeVisible();
    await page.context().storageState({ path: storageFor(role) });
  });
}
