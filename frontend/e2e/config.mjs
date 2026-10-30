// Shared settings for the browser tests (HIMS-QA-001). All people and passwords are synthetic;
// the passwords follow the Synthetic-<Word>-Passw0rd-NNNN pattern the secret scanner allows.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

export const E2E = {
  apiPort: 8100,
  appPort: 5180,
  appUrl: "http://localhost:5180",
  mailDir: join(here, ".mail"),
  mediaDir: join(here, ".media"),
  stateDir: join(here, ".state"),
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
