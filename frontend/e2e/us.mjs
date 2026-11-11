// Selects the US hospital for the browser tests (HIMS-QA-003). Imported first by
// playwright.us.config.ts, before the shared settings in config.mjs are read; the test workers
// and the servers inherit it.
process.env.HIMS_E2E_DEPLOYMENT = "us";
