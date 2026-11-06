/**
 * A calendar date (YYYY-MM-DD) on this computer's clock, for date fields.
 *
 * Not `toISOString().slice(0, 10)`: that is the UTC date, which in India is still yesterday
 * until 5:30 am (HIMS-STAFF-011).
 */
export function localDate(date: Date = new Date()): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}
