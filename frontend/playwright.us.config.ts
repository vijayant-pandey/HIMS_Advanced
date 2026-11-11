/**
 * Browser tests for the US hospital (spec 19.2; HIMS-QA-003): `npm run e2e:us`.
 *
 * India and the US are separate deployments with separate databases (ADR-003), so the US gets its
 * own throw-away hospital (database hims_e2e_us, API port 8110, app port 5190) and its own tests
 * in e2e/us. Everything else is the shared configuration.
 */
import "./e2e/us.mjs"; // must stay first: chooses the US settings before they are read
import config from "./playwright.config";

export default config;
