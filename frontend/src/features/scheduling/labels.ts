import type { OpdSession, ScheduleException, ScheduleExceptionKind } from "../../api/types";
import { formatDay } from "../rosters/labels";

export const EXCEPTION_KINDS: { value: ScheduleExceptionKind; label: string; help: string }[] = [
  { value: "leave", label: "Doctor away", help: "All their sessions that day (or those hours) are off." },
  { value: "holiday", label: "Holiday (OPD closed)", help: "Every doctor's sessions in the department or facility." },
  { value: "extra_session", label: "Extra session", help: "One more session on one day, with its own slots." },
];

export const SESSION_STATUS: Record<OpdSession["status"], { label: string; color: "success" | "warning" | "default" }> = {
  open: { label: "Open", color: "success" },
  partly_off: { label: "Partly off", color: "warning" },
  off: { label: "Off", color: "default" },
};

/** "Mon 16 Nov" or "Mon 16 Nov – Wed 18 Nov", and the hours when only part of the day. */
export function exceptionPeriod(item: Pick<ScheduleException, "start_date" | "end_date" | "hours">): string {
  const days =
    item.start_date === item.end_date
      ? formatDay(item.start_date)
      : `${formatDay(item.start_date)} – ${formatDay(item.end_date)}`;
  return item.hours ? `${days}, ${item.hours}` : days;
}

/** "Off: Away" or "11:00-13:00 off: Holiday: Diwali" for one session. */
export function offText(session: OpdSession): string {
  return session.off
    .map((part) => (part.hours === session.hours ? part.reason : `${part.hours} off: ${part.reason}`))
    .join("; ");
}
