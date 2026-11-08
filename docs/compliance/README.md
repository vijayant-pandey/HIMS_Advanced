# Compliance pack (spec 13, 23, 26.7, 27.5; HIMS-COMP-001 to 005)

**DRAFT prepared by engineering, not legal advice.** It organises the work and gives a lawyer
something concrete to review. Spec 12.3 and 26.7: software and documents do not make a hospital
compliant. Compliance also needs the hospital's own policies, training, contracts and qualified
counsel. **No real patient data before counsel signs off.**

**2026-11-08:** legal reviewed the pack and approved it **for now** (relayed by the PO); it will be
revisited if required. See the [decisions log](../status/decisions-log.md).

## What HIPAA is, and India's equivalent

| | United States | India |
|---|---|---|
| Main privacy law | **HIPAA** Privacy, Security and Breach Notification Rules | **DPDP Act 2023 and DPDP Rules 2025** (notified November 2025) |
| Cyber incident rules | Part of HIPAA | **CERT-In Directions of 28 April 2022** (IT Act section 70B) |
| Health data exchange | State and federal rules, plus payer contracts | **ABDM Health Data Management Policy**, if the hospital joins ABDM |
| Older data rules | State laws | **IT Act section 43A and SPDI Rules 2011** (counsel confirms their status as DPDP commences) |
| Identity numbers | SSN (not collected by default) | **Aadhaar Act 2016** and UIDAI rules |
| Medical records | State retention laws | Medical council regulations and state rules |

The DPDP Rules commence in stages: most duties (including breach notice and log retention) apply
**18 months after publication, around May 2027**. HIMS is built to meet them from day one.

## The documents

| Document | What it is | For |
|---|---|---|
| [requirements-matrix.md](requirements-matrix.md) | Every requirement, with citation and what HIMS does (generated) | Counsel, compliance officer |
| [risk-register.md](risk-register.md) | Starting risks with scores (generated) | Compliance officer |
| [threat-model.md](threat-model.md) | How HIMS could be attacked and what stops it | Security reviewer |
| [hipaa-security.md](hipaa-security.md) | HIPAA safeguards and risk analysis worksheet | US deployment |
| [india-dpdp-cert-in.md](india-dpdp-cert-in.md) | DPDP, CERT-In, ABDM, Aadhaar assessment | India deployment |
| [incident-response-runbook.md](incident-response-runbook.md) | What to do, hour by hour, in an incident | Everyone on the incident team |
| [retention-schedule.md](retention-schedule.md) | How long each kind of record is kept | Counsel, medical records |
| [policies.md](policies.md) | Access control, encryption and key management policies to adopt | Hospital management |
| [vendors.md](vendors.md) | Vendors and the contracts each needs | Hospital management |

## In the app

Menu → **Compliance** (permissions `compliance.view`, `compliance.manage`; both need two-factor):

- **Requirements:** the ones for this hospital's country, with status, owner, evidence and review
  date. "Verified" requires written evidence.
- **Risks:** the live register; accepting a risk requires a reason.
- **Incidents:** the log, with legal deadlines worked out from when the incident was noticed, and
  emails to the compliance team on reporting, 24 hours before each deadline and when overdue.

**Anyone signed in** can report an incident from the **Security** page; only compliance staff read
the log. New role: **Compliance / security officer**. Auditors can read the registers. Every change
is in the audit log; the admin console has the same registers with the same rules.

Keep the catalogue and documents together: change `backend/apps/compliance/catalog.py`, then run
`python manage.py compliance_docs`. A test fails if they differ.

## How facts were checked (2026-11-04)

| Fact | Checked against |
|---|---|
| DPDP breach notice (without delay; detailed report in 72 hours), one-year logs, 18-month commencement | Published summaries of the Rules: [Khaitan & Co](https://www.khaitanco.com/sites/default/files/2025-11/ERGO%20-%20Digital%20Personal%20%20Data%20Protection%20Rules%20-%2015%20November%202025.pdf), [BDO India](https://www.bdo.in/getmedia/87552494-85d2-4edb-95da-0f118fdb3052/The-DPDP-Rules_BDO-India_2025.pdf), [Mondaq](https://www.mondaq.com/india/data-protection/1708164/digital-personal-data-protection-rules-2025-notified) |
| CERT-In 6-hour reporting, 180-day logs in India | Published summaries: [PSA Legal](https://psalegal.com/new-cert-in-directions-overview-and-implications/), [ManageEngine](https://www.manageengine.com/log-management/cyber-security/cert-in-compliance-for-indian-enterprises.html) |
| HIPAA 60-day notices, 500-person thresholds | [HHS Breach Notification Rule](https://www.hhs.gov/hipaa/for-professionals/breach-notification/index.html), [45 CFR 164.408](https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-D/section-164.408) |

**Not independently confirmed; counsel must check:** section and rule numbers in the matrix (taken
from engineering knowledge and secondary sources), the 6-year HIPAA documentation rule, Indian
medical-record retention periods (sources conflict), UIDAI's rules on storing Aadhaar numbers, and
the ABDM policy's requirements.

## Open items for the hospital

Name a security official and a DPDP contact · confirm legal basis for treatment data · sign vendor
contracts · adopt the policies · train staff · run an incident drill · set retention periods.
