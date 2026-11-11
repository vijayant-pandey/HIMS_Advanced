// Starts a throw-away HIMS backend for the browser tests (HIMS-QA-001). Started by
// playwright.config.ts; not meant to be run by hand.
//
// 1. Recreates the empty database `hims_e2e` (`hims_e2e_us` for the US hospital; the command
//    refuses any name not starting with hims_e2e).
// 2. Migrates it and provisions a synthetic hospital (India, or the US with HIMS_E2E_DEPLOYMENT=us:
//    HIMS-QA-003) with an administrator and an auditor.
// 3. Runs the API on port 8100 (US: 8110; the normal local hospitals use 8000/8001, so they are
//    untouched).
//
// Database server: E2E_DATABASE_URL if set, otherwise the server from backend/.env; either way the
// database name is replaced by the test database's. Emails are written to e2e/.mail, uploads to
// e2e/.media (US: .mail-us, .media-us).
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { ADMIN, AUDITOR, E2E } from "./config.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const backend = join(here, "..", "..", "backend");

function python() {
  if (process.env.HIMS_E2E_PYTHON) return process.env.HIMS_E2E_PYTHON;
  for (const candidate of [join(backend, ".venv", "Scripts", "python.exe"), join(backend, ".venv", "bin", "python")]) {
    if (existsSync(candidate)) return candidate;
  }
  return "python";
}

function databaseUrl() {
  let server = process.env.E2E_DATABASE_URL;
  if (!server) {
    const file = join(backend, ".env");
    // The owner's URL when the app has its own limited user (HIMS-OPS-007): creating the
    // throw-away database needs the owner's rights.
    const text = existsSync(file) ? readFileSync(file, "utf8") : "";
    const line = text.match(/^HIMS_MIGRATION_DATABASE_URL=(.+)$/m) || text.match(/^DATABASE_URL=(.+)$/m);
    if (!line) throw new Error("Set E2E_DATABASE_URL, e.g. postgres://user:pass@localhost:5432/hims_e2e");
    server = line[1].trim();
  }
  const url = new URL(server);
  url.pathname = `/${E2E.database}`;
  return url.toString();
}

for (const dir of [E2E.mailDir, E2E.mediaDir]) {
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
}

const env = {
  ...process.env,
  HIMS_ENV_FILE: "__no_env_file__", // never the developer's own settings or secrets
  DJANGO_SETTINGS_MODULE: "config.settings.local",
  DJANGO_DEBUG: "false",
  DJANGO_SECRET_KEY: "e2e-only-not-secret-0000000000000000000000000000",
  HIMS_ENVIRONMENT: "local",
  HIMS_DATABASE_ENVIRONMENT: "local",
  HIMS_DEPLOYMENT_ID: "e2e",
  DATABASE_URL: databaseUrl(),
  REDIS_URL: "",
  CELERY_BROKER_URL: "memory://",
  HIMS_APP_BASE_URL: E2E.appUrl,
  DJANGO_ALLOWED_HOSTS: "localhost,127.0.0.1",
  DJANGO_CSRF_TRUSTED_ORIGINS: E2E.appUrl,
  DJANGO_EMAIL_BACKEND: "django.core.mail.backends.filebased.EmailBackend",
  HIMS_EMAIL_FILE_PATH: E2E.mailDir,
  HIMS_MEDIA_ROOT: E2E.mediaDir,
  HIMS_THROTTLE_LOGIN: "1000/min",
  HIMS_THROTTLE_ANON: "1000/min",
  HIMS_THROTTLE_PASSWORD_RESET: "1000/min",
  HIMS_MFA_REQUIRED_FOR_PRIVILEGED: "true",
  HIMS_TRACING_EXPORTER: "none",
  // A slow machine must not be asked in the middle of other tests; 04-audit-and-safety tests the asking.
  HIMS_CONFIRM_IDENTITY_MINUTES: "60",
  E2E_ADMIN_PASSWORD: ADMIN.password,
  E2E_AUDITOR_PASSWORD: AUDITOR.password,
};

function run(args) {
  const result = spawnSync(python(), ["manage.py", ...args], { cwd: backend, env, stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

run(["reset_e2e_database"]);
run(["migrate", "--no-input", "-v", "0"]);
run([
  "provision_organization",
  `--legal-name=${E2E.legalName}`,
  `--display-name=${E2E.displayName}`,
  `--country=${E2E.country}`,
  `--timezone=${E2E.timezone}`,
  `--currency=${E2E.currency}`,
  `--admin-email=${ADMIN.email}`,
  `--admin-name=${ADMIN.name}`,
  "--admin-password-env=E2E_ADMIN_PASSWORD",
  `--auditor-email=${AUDITOR.email}`,
  `--auditor-name=${AUDITOR.name}`,
  "--auditor-password-env=E2E_AUDITOR_PASSWORD",
]);

const server = spawn(python(), ["manage.py", "runserver", "--insecure", `127.0.0.1:${E2E.apiPort}`, "--noreload"], {
  cwd: backend,
  env,
  stdio: "inherit",
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill());
server.on("exit", (code) => process.exit(code ?? 0));
