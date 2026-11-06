# Dates and time zones (HIMS-STAFF-011)

## The rule

- **Moments** (when something happened, when a sign-in ends) are stored in **UTC** and shown on
  each person's own clock by the screens.
- **Calendar dates** that people act on (a licence's expiry, the last day of a posting, a review's
  finish-by date, a day searched for in the audit log) are dates **at the hospital**.

So "today" is never the UTC date. In India UTC is still on yesterday until 5:30 am; in the US it is
already tomorrow from the evening. Before this fix, a licence that expired yesterday showed as
"expiring soon, 0 days left" until 5:30 am in India, and its "expired" email was a day late.

## Which clock

| What | Clock |
|---|---|
| Licence and qualification expiry, expiry alerts, the Licence expiry page | Hospital (Hospital settings → Default time zone) |
| Access reviews: finish-by date, next due date, reminders | Hospital |
| Audit log search "from day / to day" | Hospital |
| Blocked-content reports grouped per day (Compliance page) | Hospital |
| Times in emails (cover, invitations, incident deadlines); the zone is named, e.g. IST | Hospital |
| A posting's last day, department head checks, who counts as posted in a department | That department's facility |
| Numbering (restart per year or month) | The issuing facility, else the hospital |
| Staff counts on the Departments list (spans facilities) | Hospital |
| Default dates in the screens' date fields | The computer the person is using |

The hospital's time zone can be changed on **Hospital settings**; each facility's on **Facilities**.

## For developers

- Backend: use `apps.organizations.dates`: `hospital_today(facility=None)`,
  `hospital_date(instant, facility=None)` and `hospital_time(instant)` for emails (format with
  `%Z` so the zone is named). Pass the facility when the date belongs to one.
- Never `timezone.localdate()`, `timezone.localtime()`, `date.today()` or `datetime.today()`:
  `TIME_ZONE` is UTC, so they give the UTC date.
- Screens and browser tests: use `localDate()` from `src/components/dates.ts`, never
  `new Date().toISOString().slice(0, 10)` (the UTC date).
- A test (`test_nothing_works_out_today_on_the_utc_clock`) fails if any of these come back.
- Tests that need a fixed moment patch `django.utils.timezone.now`; see
  `apps/organizations/tests/test_hospital_dates.py`. A model field with `default=timezone.now`
  keeps the real clock, so set it explicitly in such tests.

No database change.
