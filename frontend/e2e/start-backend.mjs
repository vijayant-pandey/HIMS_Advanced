// Starts a throw-away HIMS backend for the browser tests (HIMS-QA-001). Started by
// playwright.config.ts; not meant to be run by hand.
//
// 1. Recreates the empty database `hims_e2e` (the command refuses any other name).
// 2. Migrates it and provisions a synthetic hospital with an administrator and an auditor.
// 3. Runs the API on port 8100 (the normal local hospitals use 8000/8001, so they are untouched).
//
// Database server: E2E_DATABASE_URL if set, otherwise the server from backend/.env with the
// database name replaced by hims_e2e. Emails are written to e2e/.mail, uploads to e2e/.media.
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
  if (process.env.E2E_DATABASE_URL) return process.env.E2E_DATABASE_URL;
  const file = join(backend, ".env");
  const line = existsSync(file) && readFileSync(file, "utf8").match(/^DATABASE_URL=(.+)$/m);
  if (!line) throw new Error("Set E2E_DATABASE_URL, e.g. postgres://user:pass@localhost:5432/hims_e2e");
  const url = new URL(line[1].trim());
  url.pathname = "/hims_e2e";
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
  "--legal-name=E2E Synthetic Hospital Pvt Ltd",
  "--display-name=E2E Synthetic Hospital",
  "--country=IN",
  "--timezone=Asia/Kolkata",
  "--currency=INR",
  `--admin-email=${ADMIN.email}`,
  `--admin-name=${ADMIN.name}`,
  "--admin-password-env=E2E_ADMIN_PASSWORD",
  `--auditor-email=${AUDITOR.email}`,
  `--auditor-name=${AUDITOR.name}`,
  "--auditor-password-env=E2E_AUDITOR_PASSWORD",
]);

const server = spawn(python(), ["manage.py", "runserver", `127.0.0.1:${E2E.apiPort}`, "--noreload"], {
  cwd: backend,
  env,
  stdio: "inherit",
});
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill());
server.on("exit", (code) => process.exit(code ?? 0));
