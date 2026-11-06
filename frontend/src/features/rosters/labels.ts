import type { LeaveRequest, LeaveType } from "../../api/types";

export const LEAVE_TYPES: { value: LeaveType; label: string }[] = [
  { value: "annual", label: "Annual / earned leave" },
  { value: "casual", label: "Casual leave" },
  { value: "sick", label: "Sick leave" },
  { value: "maternity", label: "Maternity leave" },
  { value: "paternity", label: "Paternity leave" },
  { value: "study", label: "Study or conference leave" },
  { value: "compensatory", label: "Compensatory off" },
  { value: "unpaid", label: "Unpaid leave" },
  { value: "other", label: "Other" },
];

export const LEAVE_STATUS: Record<
  LeaveRequest["status"],
  { label: string; color: "warning" | "success" | "default" | "error" }
> = {
  requested: { label: "Waiting for a decision", color: "warning" },
  approved: { label: "Approved", color: "success" },
  rejected: { label: "Refused", color: "error" },
  cancelled: { label: "Cancelled", color: "default" },
};

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" });

/** "Mon 9 Nov" for a YYYY-MM-DD date (read as a calendar day, not a moment). */
export const formatDay = (value: string) => dayFormat.format(new Date(`${value}T12:00:00`));



/** "08:00" from the server's "08:00:00". */
export const clock = (value: string) => value.slice(0, 5);

export function leavePeriod(leave: Pick<LeaveRequest, "start_date" | "end_date" | "days">): string {
  if (leave.start_date === leave.end_date) return formatDay(leave.start_date);
  return `${formatDay(leave.start_date)} – ${formatDay(leave.end_date)} (${leave.days} days)`;
}

/** Monday of the week holding this YYYY-MM-DD date. */
export function mondayOf(value: string): string {
  const day = new Date(`${value}T12:00:00`);
  day.setDate(day.getDate() - ((day.getDay() + 6) % 7));
  return isoDay(day);
}

export function addDays(value: string, days: number): string {
  const day = new Date(`${value}T12:00:00`);
  day.setDate(day.getDate() + days);
  return isoDay(day);
}

function isoDay(day: Date): string {
  const month = String(day.getMonth() + 1).padStart(2, "0");
  return `${day.getFullYear()}-${month}-${String(day.getDate()).padStart(2, "0")}`;
}
