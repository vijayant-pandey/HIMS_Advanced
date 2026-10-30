// Helpers for the browser tests (HIMS-QA-001).
import AxeBuilder from "@axe-core/playwright";
import { type Page, expect } from "@playwright/test";
import { createHmac } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { E2E } from "./config.mjs";

// --- Two-factor codes (RFC 6238, the same as an authenticator app) -------------------------

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.replace(/[\s=]/g, "").toUpperCase()) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  }
  const bytes = bits.match(/.{8}/g) ?? [];
  return Buffer.from(bytes.map((byte) => parseInt(byte, 2)));
}

function codeAt(secret: string, step: number): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const digest = createHmac("sha1", base32(secret)).update(counter).digest();
  const offset = digest[digest.length - 1]! & 15;
  const value = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return String(value).padStart(6, "0");
}

const usedStepFile = (secret: string) => join(E2E.stateDir, `step-${secret.slice(0, 8)}.txt`);

/**
 * A code that has not been used yet. The server refuses a code twice (replay protection), so if
 * this 30-second step was already used, wait for the next one.
 */
export async function freshCode(secret: string): Promise<string> {
  mkdirSync(E2E.stateDir, { recursive: true });
  const file = usedStepFile(secret);
  const lastUsed = existsSync(file) ? Number(readFileSync(file, "utf8")) : -1;
  let step = Math.floor(Date.now() / 30_000);
  while (step <= lastUsed) {
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    step = Math.floor(Date.now() / 30_000);
  }
  writeFileSync(file, String(step));
  return codeAt(secret, step);
}

// --- Saved state shared between test files ---------------------------------------------------

export function remember(name: string, value: string): void {
  mkdirSync(E2E.stateDir, { recursive: true });
  writeFileSync(join(E2E.stateDir, `${name}.txt`), value);
}

export function recall(name: string): string {
  return readFileSync(join(E2E.stateDir, `${name}.txt`), "utf8");
}

export const storageFor = (role: string) => join(E2E.stateDir, `${role}.json`);

// --- Emails (written to files by the backend) --------------------------------------------------

type LinkKind = "activate" | "reset-password";

/** The separate messages in the email folder (Django writes one or more per file). */
function messagesTo(email: string): string[] {
  if (!existsSync(E2E.mailDir)) return [];
  return readdirSync(E2E.mailDir)
    .flatMap((name) => readFileSync(join(E2E.mailDir, name), "utf8").split(/^-{70,}$/m))
    .filter((message) => message.includes(`To: ${email}`));
}

/** Every link of this kind (`activate` or `reset-password`) emailed to `email` so far. */
export function linksFromEmails(email: string, kind: LinkKind): string[] {
  const pattern = new RegExp(`https?://\\S+/${kind}#token=[^\\s"<]+`, "g");
  return messagesTo(email).flatMap((message) => message.match(pattern) ?? []);
}

/**
 * Wait for a link of this kind to `email` that is not in `known`, i.e. the one just sent.
 * (Email files can share a timestamp, so "newest file" is not reliable.)
 */
export async function newLinkFromEmail(email: string, kind: LinkKind, known: string[] = []): Promise<string> {
  for (let attempt = 0; attempt < 40; attempt++) {
    const fresh = linksFromEmails(email, kind).filter((link) => !known.includes(link));
    if (fresh.length === 1) return fresh[0]!;
    if (fresh.length > 1) throw new Error(`${fresh.length} new ${kind} emails for ${email}; expected one`);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`No new ${kind} email for ${email}`);
}

/** Every email subject sent to `email` so far. */
export function subjectsFor(email: string): string[] {
  return messagesTo(email).flatMap((message) => {
    const subject = message.match(/^Subject: (.+)$/m);
    return subject ? [subject[1]!.trim()] : [];
  });
}

// --- Signing in --------------------------------------------------------------------------------

export async function signIn(page: Page, email: string, password: string, secret?: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  if (secret) {
    await page.getByLabel("Authentication code").fill(await freshCode(secret));
    await page.getByRole("button", { name: "Verify and sign in" }).click();
  }
}

/** Open a screen from the top menu. */
export async function openMenu(page: Page, label: string): Promise<void> {
  await page.getByRole("navigation").getByRole("link", { name: label, exact: true }).click();
}

// --- Accessibility (spec 18 "accessible forms, keyboard navigation"; spec 19.2) ------------------

/**
 * No serious or critical WCAG 2.1 A/AA problems on the page as it is now. Minor and moderate
 * findings do not fail the run.
 */
export async function expectAccessible(page: Page, screen: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const summary = blocking.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help}: ${v.nodes.length} element(s): ` +
      v.nodes
        .slice(0, 3)
        .map((n) => `${n.target.join(" ")} [${(n.failureSummary ?? "").replace(/\s+/g, " ").slice(0, 200)}]`)
        .join(" | "),
  );
  expect(summary, `Accessibility problems on ${screen}`).toEqual([]);
}
