/** Bed status labels and colours, shared by the Locations page and (later) the bed board. */
export type ChipColor =
  "success" | "warning" | "error" | "info" | "default" | "secondary";

export const BED_STATUS: Record<string, { label: string; color: ChipColor }> = {
  available: { label: "Available", color: "success" },
  reserved: { label: "Reserved", color: "info" },
  occupied: { label: "Occupied", color: "error" },
  cleaning: { label: "Cleaning", color: "secondary" },
  maintenance: { label: "Maintenance", color: "warning" },
  blocked: { label: "Blocked", color: "warning" },
  out_of_service: { label: "Out of service", color: "default" },
};

/** States staff may set by hand. Reserved, occupied and cleaning come from admissions (Phase 3). */
export const SETTABLE_STATUSES = [
  "available",
  "maintenance",
  "blocked",
  "out_of_service",
] as const;
export type SettableStatus = (typeof SETTABLE_STATUSES)[number];

export function isSettable(status: string): boolean {
  return (SETTABLE_STATUSES as readonly string[]).includes(status);
}

export function statusInfo(status: string) {
  return BED_STATUS[status] ?? { label: status, color: "default" as const };
}
