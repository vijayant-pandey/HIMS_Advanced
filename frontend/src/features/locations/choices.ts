// Labels for the location choices. Typed against the generated API enums, so the build fails if
// the backend adds or removes a value and this list is not updated.
import type { AgeGroup, BedType, GenderRestriction, RoomType, WardType } from "../../api/types";

export const WARD_TYPES: Record<WardType, string> = {
  general: "General ward",
  private: "Private ward",
  icu: "Intensive care unit (ICU)",
  hdu: "High dependency unit (HDU)",
  nicu: "Neonatal ICU (NICU)",
  picu: "Pediatric ICU (PICU)",
  emergency: "Emergency / casualty",
  maternity: "Maternity / labour",
  isolation: "Isolation ward",
  day_care: "Day care",
  operating_theatre: "Operating theatre complex",
  recovery: "Recovery / PACU",
};

export const ROOM_TYPES: Record<RoomType, string> = {
  general: "General room",
  private: "Private room",
  semi_private: "Semi-private room",
  icu_bay: "ICU bay",
  isolation: "Isolation room",
  operating_room: "Operating room",
  procedure: "Procedure room",
  recovery: "Recovery bay",
  consultation: "Consultation room",
};

export const BED_TYPES: Record<BedType, string> = {
  general: "General",
  semi_private: "Semi-private",
  private: "Private",
  deluxe: "Deluxe / suite",
  icu: "ICU",
  hdu: "HDU",
  nicu: "NICU (cot / incubator)",
  picu: "PICU",
  isolation: "Isolation",
  day_care: "Day care",
  labour: "Labour / delivery",
  recovery: "Recovery",
  emergency_trolley: "Emergency trolley",
};

export const GENDER_RESTRICTIONS: Record<GenderRestriction, string> = {
  any: "Any",
  male: "Male only",
  female: "Female only",
};

export const AGE_GROUPS: Record<AgeGroup, string> = {
  any: "Any age",
  adult: "Adults",
  pediatric: "Children",
  neonatal: "Newborns",
};

export function options<T extends string>(labels: Record<T, string>) {
  return (Object.entries(labels) as [T, string][]).map(([value, label]) => ({ value, label }));
}
