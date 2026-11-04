# Incident response runbook (spec 13.4, 23, 27.5; HIMS-COMP-004)

DRAFT for counsel and the hospital to adopt. Print it: the system may be down during an incident.
Fill in the contacts **before** go-live and practise once.

| Role | Person | Phone |
|---|---|---|
| Incident lead (compliance / security officer) | | |
| Hospital management | | |
| Technical lead | | |
| Legal counsel | | |
| Hosting / vendor support | | |

## Anyone who sees a problem

Report at once: **Security page → Report a security incident**. If HIMS is down, phone the incident
lead. Do not switch off or wipe anything, do not delete emails or files, and do not discuss it outside
the team. No patient details in the report.

## The legal clocks (working defaults; counsel confirms what applies)

The clocks start when the incident is **noticed**. HIMS adds these automatically and shows them under
Compliance → Incidents.

| Country | Notice | Deadline |
|---|---|---|
| India | **CERT-In** report (listed cyber incidents) | **6 hours** |
| India | Data Protection Board, first notice | Without delay (HIMS shows 24 hours) |
| India | Data Protection Board, detailed report | **72 hours**, unless the Board allows longer |
| India | Affected people | Without delay (HIMS shows 24 hours) |
| US | Affected people | Without unreasonable delay, **60 days** at most |
| US | HHS, 500 or more people | With the notice to people, **60 days** at most |
| US | HHS, fewer than 500 people | Within **60 days after the calendar year ends** |
| US | Media, more than 500 residents of a state or area | **60 days** at most |

The DPDP duties commence around May 2027; counsel confirms what applies before then. US state laws
may add shorter deadlines.

## Steps

**1. First hour: confirm and contain.** The incident lead opens the incident, sets severity and notes
facts. Contain without destroying evidence: end sessions (Accounts → Sign out of all devices), switch
accounts off, revoke access, change keys. Open Audit log and run **Audit integrity → Check now**. Keep
logs and save copies.

**2. First hours: decide on notices.** Is personal or patient data involved? Tick it and enter the
number of people (deadlines update). In India, send the CERT-In report within 6 hours of noticing,
even with partial facts. Call counsel. Record each notice in HIMS with its reference, or mark it "not
required" with counsel's reason.

**3. Next days: investigate and fix.** Find the cause, what was reached and who is affected. HIPAA
requires a four-factor risk assessment to decide whether an incident is a reportable breach; counsel
leads this. Fix the cause and add it to the risk register.

**4. Tell people, as counsel advises:** what happened, what data, what we did, what they should do, and
who to contact. Never by a message that itself exposes data.

**5. Close and learn.** Write the closure summary (HIMS refuses to close while a notice is pending).
Review within two weeks: what went well, what to change. Update this runbook and the risks.

## Severity guide

| Level | Example |
|---|---|
| Critical | Patient data exposed or altered at scale; ransomware; systems down |
| High | Confirmed unauthorised access to patient or staff data; privileged account compromised |
| Medium | Lost encrypted device; malware contained; suspicious access under investigation |
| Low | Phishing email reported, nothing clicked; a policy mistake with no exposure |

## If HIMS itself reports a problem

An **Audit integrity** alert means audit records may have been altered: treat it as High until proven
otherwise, do not repair anything, and keep the database as it is. Details:
[audit-integrity.md](../architecture/data-architecture/audit-integrity.md).

## Practice

Run a drill before go-live and yearly (spec 27.5): a fake incident, one full pass with the clock
running. Record it as evidence for `ALL-INCIDENT-DRILL` on the Compliance page.
