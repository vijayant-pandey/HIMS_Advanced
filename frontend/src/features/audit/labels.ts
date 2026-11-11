import type { AuditEvent } from "../../api/types";

export const OUTCOME: Record<string, { label: string; color: "success" | "error" | "warning" }> = {
  success: { label: "Done", color: "success" },
  failure: { label: "Failed", color: "error" },
  denied: { label: "Denied", color: "warning" },
};

/** Category codes the server accepts (first part of the event code) with readable names. */
export const CATEGORIES: { value: string; label: string }[] = [
  { value: "auth", label: "Sign-in and security" },
  { value: "user", label: "Accounts" },
  { value: "access", label: "Access and roles" },
  { value: "staff", label: "Staff" },
  { value: "organization", label: "Hospital details" },
  { value: "facility", label: "Facilities" },
  { value: "department", label: "Departments" },
  { value: "location", label: "Locations" },
  { value: "bed", label: "Beds" },
  { value: "numbering", label: "Numbering" },
  { value: "feature", label: "Features" },
  { value: "admin", label: "Admin console changes" },
  { value: "audit", label: "Audit log use" },
  // Added 2026-11-10 (found by HIMS-QA-003): every area the server knows can be chosen; a backend
  // test (apps/audit/tests/test_audit_areas.py) keeps this list in step with apps/audit/catalog.py.
  { value: "rota", label: "Rotas" },
  { value: "leave", label: "Leave" },
  { value: "notification", label: "Emails and SMS" },
  { value: "compliance", label: "Compliance" },
  { value: "recovery", label: "Backups and restore drills" },
  { value: "database", label: "Database access" },
  { value: "outbox", label: "Background jobs" },
  { value: "performance", label: "Performance checks" },
];

export function who(event: AuditEvent): string {
  if (event.actor_name) return `${event.actor_name} (${event.actor_email})`;
  if (event.actor_type === "system") return "System";
  if (event.actor_type === "anonymous") return "Not signed in";
  return event.actor_id ?? "Unknown";
}
