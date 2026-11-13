import type { CurrentUser } from "../api/types";
import { hasPermission } from "../features/auth/grants";

/** Menu text strength and the darkening behind the current page (see AppShell, themes.test.ts). */
export const MENU_TEXT_OPACITY = 0.95;
export const MENU_ACTIVE_SHADE = 0.22;

export interface NavItem {
  to: string;
  label: string;
  /** Holding this permission (or any of these) shows the item. */
  permission: string | readonly string[];
}

/** Main menu. Items appear only for users holding the permission (the API still enforces it). */
export const NAV_ITEMS: NavItem[] = [
  // Patients first: the front desk's main screen (HIMS-PAT-001).
  { to: "/patients", label: "Patients", permission: "patients.search" },
  { to: "/settings", label: "Hospital settings", permission: "organization.view" },
  { to: "/facilities", label: "Facilities", permission: "facilities.view" },
  { to: "/departments", label: "Departments", permission: "departments.view" },
  { to: "/locations", label: "Locations", permission: "locations.view" },
  { to: "/bed-board", label: "Bed board", permission: "locations.view" },
  { to: "/equipment", label: "Equipment", permission: "equipment.view" },
  { to: "/numbering", label: "Numbering", permission: "numbering.view" },
  { to: "/features", label: "Features", permission: "features.view" },
  { to: "/staff", label: "Staff", permission: "staff.view" },
  { to: "/licence-expiry", label: "Licence expiry", permission: "staff.view" },
  { to: "/catalogs", label: "Job titles & catalogs", permission: "staff.view" },
  { to: "/rota", label: "Rota", permission: "rota.view" },
  { to: "/leave", label: "Leave", permission: "leave.approve" },
  { to: "/access", label: "Access", permission: "access.roles.view" },
  { to: "/accounts", label: "Accounts", permission: "access.roles.view" },
  { to: "/access-reviews", label: "Access reviews", permission: "access.reviews.view" },
  { to: "/cover", label: "Cover", permission: "access.roles.view" },
  // The hospital decides, the software supplier asks (HIMS-IAM-021).
  { to: "/support-access", label: "Support access", permission: ["support.access.manage", "support.access.request"] },
  { to: "/notifications", label: "Messages", permission: "notifications.view" },
  { to: "/message-wording", label: "Message wording", permission: "notifications.view" },
  { to: "/compliance", label: "Compliance", permission: "compliance.view" },
  { to: "/audit", label: "Audit log", permission: "audit.view" },
  { to: "/audit/integrity", label: "Audit integrity", permission: "audit.view" },
  { to: "/recovery", label: "Backups", permission: "recovery.view" },
  { to: "/background-jobs", label: "Background jobs", permission: "platform.jobs.view" },
  { to: "/performance", label: "Performance", permission: "platform.performance.view" },
];

/** True when another item lives under this one (e.g. /audit and /audit/integrity), so only the exact page is highlighted. */
export function hasNestedItem(item: NavItem): boolean {
  return NAV_ITEMS.some((other) => other.to.startsWith(`${item.to}/`));
}

export function visibleNavItems(user: CurrentUser | null | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) =>
    (typeof item.permission === "string" ? [item.permission] : item.permission).some((p) => hasPermission(user, p)),
  );
}
