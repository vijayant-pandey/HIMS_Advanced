import type { CurrentUser } from "../api/types";
import { hasPermission } from "../features/auth/grants";

export interface NavItem {
  to: string;
  label: string;
  permission: string;
}

/** Main menu. Items appear only for users holding the permission (the API still enforces it). */
export const NAV_ITEMS: NavItem[] = [
  { to: "/settings", label: "Hospital settings", permission: "organization.view" },
  { to: "/facilities", label: "Facilities", permission: "facilities.view" },
  { to: "/departments", label: "Departments", permission: "departments.view" },
  { to: "/locations", label: "Locations", permission: "locations.view" },
  { to: "/numbering", label: "Numbering", permission: "numbering.view" },
  { to: "/features", label: "Features", permission: "features.view" },
  { to: "/staff", label: "Staff", permission: "staff.view" },
  { to: "/licence-expiry", label: "Licence expiry", permission: "staff.view" },
  { to: "/catalogs", label: "Job titles & catalogs", permission: "staff.view" },
  { to: "/access", label: "Access", permission: "access.roles.view" },
  { to: "/accounts", label: "Accounts", permission: "access.roles.view" },
  { to: "/access-reviews", label: "Access reviews", permission: "access.reviews.view" },
  { to: "/cover", label: "Cover", permission: "access.roles.view" },
  { to: "/audit", label: "Audit log", permission: "audit.view" },
  { to: "/audit/integrity", label: "Audit integrity", permission: "audit.view" },
];

/** True when another item lives under this one (e.g. /audit and /audit/integrity), so only the exact page is highlighted. */
export function hasNestedItem(item: NavItem): boolean {
  return NAV_ITEMS.some((other) => other.to.startsWith(`${item.to}/`));
}

export function visibleNavItems(user: CurrentUser | null | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => hasPermission(user, item.permission));
}
