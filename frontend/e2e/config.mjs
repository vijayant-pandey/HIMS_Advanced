// Shared settings for the browser tests (HIMS-QA-001). All people and passwords are synthetic;
// the passwords follow the Synthetic-<Word>-Passw0rd-NNNN pattern the secret scanner allows.
//
// Two separate hospitals, like the real deployments (HIMS-QA-003): India (`npm run e2e`) and the
// United States (`npm run e2e:us`, which sets HIMS_E2E_DEPLOYMENT=us). Each has its own database,
// ports and folders, so the two runs never share anything.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

const DEPLOYMENTS = {
  in: {
    apiPort: 8100,
    appPort: 5180,
    database: "hims_e2e",
    country: "IN",
    timezone: "Asia/Kolkata",
    currency: "INR",
    legalName: "E2E Synthetic Hospital Pvt Ltd",
    displayName: "E2E Synthetic Hospital",
    suffix: "",
  },
  us: {
    apiPort: 8110,
    appPort: 5190,
    database: "hims_e2e_us",
    country: "US",
    timezone: "America/New_York",
    currency: "USD",
    legalName: "E2E Synthetic Medical Center Inc",
    displayName: "E2E Synthetic Medical Center",
    suffix: "-us",
  },
};

const deployment = process.env.HIMS_E2E_DEPLOYMENT === "us" ? "us" : "in";
const chosen = DEPLOYMENTS[deployment];

export const E2E = {
  deployment,
  ...chosen,
  appUrl: `http://localhost:${chosen.appPort}`,
  mailDir: join(here, `.mail${chosen.suffix}`),
  mediaDir: join(here, `.media${chosen.suffix}`),
  stateDir: join(here, `.state${chosen.suffix}`),
};

export const ADMIN = {
  email: "e2e.admin@synthetic.test",
  name: "E2E Admin",
  password: "Synthetic-Admin-Passw0rd-2026",
};

export const AUDITOR = {
  email: "e2e.auditor@synthetic.test",
  name: "E2E Auditor",
  password: "Synthetic-Auditor-Passw0rd-2026",
};

export const NEW_STAFF_PASSWORD = "Synthetic-Nurse-Passw0rd-2026";
