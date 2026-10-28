import type { CurrentUser } from "../api/types";
import { hasPermission } from "../features/auth/grants";

export interface NavItem {
  to: string;
  label: string;
  permission: string;
}

/** Main menu. Items appear only for users holding the permission (the API still enforces it). */
export const NAV_ITEMS: NavItem[] = [
  { to: "/facilities", label: "Facilities", permission: "facilities.view" },
  { to: "/locations", label: "Locations", permission: "locations.view" },
  { to: "/numbering", label: "Numbering", permission: "numbering.view" },
  { to: "/features", label: "Features", permission: "features.view" },
  { to: "/staff", label: "Staff", permission: "staff.view" },
  { to: "/access", label: "Access", permission: "access.roles.view" },
];

export function visibleNavItems(user: CurrentUser | null | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => hasPermission(user, item.permission));
}
