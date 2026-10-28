// Labels typed against the generated API enums: the build fails if the backend adds a value
// that is not listed here.
import type { CredentialType, EmploymentStatus, StaffType } from "../../api/types";

export const STAFF_TYPES: Record<StaffType, string> = {
  doctor: "Doctor",
  nurse: "Nurse",
  pharmacist: "Pharmacist",
  lab_technician: "Laboratory technician",
  radiologist: "Radiologist",
  dietitian: "Dietitian",
  administrator: "Administrator",
  support: "Support staff",
};

export const EMPLOYMENT_STATUSES: Record<EmploymentStatus, string> = {
  active: "Active",
  on_leave: "On leave",
  suspended: "Suspended",
  terminated: "Terminated",
};

export const STATUS_COLOR: Record<EmploymentStatus, "success" | "warning" | "error" | "default"> = {
  active: "success",
  on_leave: "warning",
  suspended: "error",
  terminated: "default",
};

export const CREDENTIAL_TYPES: Record<CredentialType, string> = {
  medical_registration: "Medical council registration",
  nursing_registration: "Nursing council registration",
  pharmacy_registration: "Pharmacy council registration",
  state_license: "State licence (US)",
  npi: "National Provider Identifier (US)",
  dea_registration: "DEA registration (US)",
  other: "Other",
};

export const EXPIRY: Record<string, { label: string; color: "success" | "warning" | "error" | "default" }> = {
  valid: { label: "Valid", color: "success" },
  expiring_soon: { label: "Expires soon", color: "warning" },
  expired: { label: "Expired", color: "error" },
  no_expiry: { label: "No expiry", color: "default" },
};

export const VERIFICATION: Record<string, { label: string; color: "success" | "warning" | "error" }> = {
  verified: { label: "Verified", color: "success" },
  unverified: { label: "Not yet verified", color: "warning" },
  rejected: { label: "Rejected", color: "error" },
};

export function options<T extends string>(labels: Record<T, string>) {
  return (Object.entries(labels) as [T, string][]).map(([value, label]) => ({ value, label }));
}
