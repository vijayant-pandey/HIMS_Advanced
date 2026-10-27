export const DOCUMENT_TYPES = [
  { value: "mrn", label: "Patient record number (MRN)" },
  { value: "encounter", label: "Encounter / visit number" },
  { value: "invoice", label: "Invoice number" },
  { value: "claim", label: "Insurance claim number" },
] as const;

export const PERIODS = [
  { value: "none", label: "Never restarts" },
  { value: "calendar_year", label: "Every calendar year (January)" },
  { value: "financial_year", label: "Every financial year" },
  { value: "month", label: "Every month" },
] as const;

export const SEPARATORS = [
  { value: "-", label: "Dash  ( - )" },
  { value: "/", label: "Slash  ( / )" },
  { value: "", label: "None" },
] as const;

export const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function periodLabel(period: string, startMonth: number): string {
  if (period === "financial_year") return `Every financial year (from ${MONTHS[startMonth - 1]})`;
  return PERIODS.find((p) => p.value === period)?.label ?? period;
}
