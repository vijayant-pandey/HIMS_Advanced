# Minimum staffing per shift (HIMS-STAFF-015)

**Spec:** 4.3 shift schedules. **Approval:** clinical governance said "fine for now" on 2026-11-08,
on the basis that the hospital sets the numbers itself
([decisions log](../status/decisions-log.md), item 5). HIMS has **no staffing ratios of its own**.

## Setting it up

Menu → **Rota** → choose the department → **Minimum staffing**. Add one row per rule:

| Field | Meaning |
|---|---|
| **Shift** | Which kind of shift |
| **Who counts** | Anyone, or one kind of staff (nurses, doctors…). A department can have both |
| **Days** | Every day, Monday to Friday, or Saturday and Sunday |
| **At least** | The fewest people the hospital wants on it |

Two rows cannot count the same people on the same days: "every day" cannot sit beside "Monday to
Friday" for the same shift and people. Switch a rule off rather than removing it. Heads of
department can set the numbers for their own department (`rota.manage`).

## What happens

- **A warning on the Rota page** lists this week's shifts below the minimum, from today on.
- **One email a day at most**, to the department's planners, about gaps in the next 7 days. **Each gap
  is told once**, so an unfilled shift does not repeat every morning. The wording can be changed
  under [Message wording](message-wording.md). It says "1 of 2 nurse planned" and names nobody.
- **Planning is never blocked.** A planner may know better, and a rota must always be plannable.

Only scheduled shifts count. A shift cancelled for approved leave stops counting, so approving leave
can open a gap; the warning then shows it. A gap in the past is not shown, because it cannot be
filled.

## On your PC

The daily job runs where Celery beat is running. To check it by hand:

```
python manage.py send_staffing_gap_alerts
```

Safe to run any number of times.

## Admin console

- **Staffing requirements:** the same rows, plus a **Staffing gaps** button listing every gap in the
  next two weeks, department by department.
- **Staffing gap alerts:** read-only list of what has been emailed.

If the Rotas feature is off for a facility, its rules cannot be added and no emails go.

## Not included

No nurse-to-patient ratios: those need patients and bed occupancy, which arrive in Phase 3.

## Tables

`staffing_requirements` and `staffing_gap_alerts`: see the
[data dictionary](../architecture/data-architecture/data-dictionary.md).
