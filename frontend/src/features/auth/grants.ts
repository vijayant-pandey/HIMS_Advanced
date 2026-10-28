import type { CurrentUser } from "../../api/types";

/**
 * Navigation hints only. Hiding a control is never a security boundary; the API enforces
 * every permission (spec 15.2, 26.4).
 */
export function hasPermission(user: CurrentUser | null | undefined, permission: string): boolean {
  return !!user?.grants?.some((grant) => grant.permission === permission);
}

export function hasOrganizationWidePermission(
  user: CurrentUser | null | undefined,
  permission: string,
): boolean {
  return !!user?.grants?.some(
    (grant) => grant.permission === permission && grant.facility_id === null,
  );
}

/** True when a grant covers this facility (an organization-wide grant covers every facility). */
export function hasPermissionAt(
  user: CurrentUser | null | undefined,
  permission: string,
  facilityId: string | null | undefined,
): boolean {
  return !!user?.grants?.some(
    (grant) =>
      grant.permission === permission &&
      (grant.facility_id === null || grant.facility_id === facilityId),
  );
}
