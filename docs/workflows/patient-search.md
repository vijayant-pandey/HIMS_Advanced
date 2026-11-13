# Patient search (HIMS-PAT-002)

Phase 2 → Spec §4.5, §13 → Slice 2A. Rules: [Phase 2 P0 part 01](../p0/phase-2-patients/01-functional-requirements.md)
section 2. How it matches names: [ADR-037](../decisions/ADR-037-patient-search.md). Registering:
[patient registration](patient-registration.md).

**Synthetic data only** until LEGAL closes D6, D7, D9 and D24 and the paid hosting stage is done.

## Who can search

Everyone with **Patients** in the menu: front desk, medical records, hospital administrators and
heads of department. Not the auditor, basic staff or the software supplier's support account.

## Search (screens)

**Patients → Search.** One box; what you type decides how it is matched:

| Type | Example | Finds |
|---|---|---|
| The MRN | `MRN-00000123`, `mrn-00000123` | That patient |
| Only the MRN's number | `123` | MRN-00000123 (not MRN-00001123) |
| A phone number | `98765 43210`, `+91 98765 43210`, `(312) 555-0142` | Every patient who gave that phone (families share phones) |
| An ID number | Aadhaar `2999 9000 0337`, ABHA, passport, a previous hospital's MRN | That patient (the number is never shown in the results) |
| A name | `suneeta`, `laxmi`, `muhammad khan`, `kumar ravi` | Similar spellings and sound-alikes, in any order, earlier names too |
| A name and age | `sunita 45` | Sunitas aged 44 to 46 |

Optional: **Sex** and **Age (years)** (give or take one year) narrow the search. Press **Search**.

* The results show only the name, MRN, age and sex, the phone's last 4 digits, where they were
  registered and **Found by** (MRN, Phone, ID number or Name). Open the record from the MRN.
* More than 50 match: the best 50 are shown with "N patients match; add the age, the sex or more
  of the name".
* Fewer than 3 letters of a name: "Type at least 3 letters of the name, or the MRN, phone number
  or ID number".
* Nobody found: "No patient found", with **Register new patient** for the front desk.
* **Clear** goes back to the newest registrations.

Every search is in the **Audit log** as "Patients searched (MRN, phone, ID number or name)": what
kind of search and how many matched, never the words or numbers typed.

## Admin console

**Patients → Patients**: the search box uses the same search (MRN, phone, ID number or name), at
most 50 results, audited. **Patient identifiers**: search by the MRN or by the whole ID number.

## Try it in a demo hospital

After the merge and the demo rebuild (`--reset`), sign in as
`frontdesk.dwk@in-sunrise.demo.test` (password in your `login.md`) and open **Patients**. The
rebuild prints "Try these on Patients -> Search" for each hospital: an MRN, only its number,
another spelling of a name, a name in reverse order, a phone, a previous hospital's MRN and an
earlier family name (one woman per branch changed her family name). For example, type a first
name from the list with `ee` instead of `i`.

The hosted Development hospital (Render) gets the same demo records with one command:
[Render + Neon, section 8](render-neon-hosting.md#8-demo-records-on-the-hosted-development-hospital-hims-pat-002).
