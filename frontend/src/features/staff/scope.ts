import type { CurrentUser, Department } from "../../api/types";

/**
 * HIMS-STAFF-008: where a facility or department grant lets you see staff, in words, e.g.
 * "Cardiology (Main Hospital)". Null for a hospital-wide grant (everyone is shown).
 */
export function staffScope(user: CurrentUser | null | undefined, departments: Department[]): string | null {
  const grants = (user?.grants ?? []).filter((g) => g.permission === "staff.view");
  if (grants.length === 0 || grants.some((g) => g.facility_id === null)) return null;
  const places = grants.map((g) => {
    if (g.department_id) {
      const department = departments.find((d) => d.id === g.department_id);
      return department ? `${department.name} (${department.facility_name})` : "one department";
    }
    const facility = departments.find((d) => d.facility === g.facility_id)?.facility_name;
    return facility ? `all of ${facility}` : "one facility";
  });
  return [...new Set(places)].join(", ");
}
