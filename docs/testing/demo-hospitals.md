# Demo hospitals on your PC (HIMS-QA-004)

There are **5 Indian and 5 US hospitals, each with 3 branches**. Every one has its own database,
exactly like a real customer. Everything in them is invented: hospitals, addresses, people,
licence numbers. "(Demo)" is in every hospital's name.

These are on your PC only. Real hospitals never see the launcher page: each real hospital gets
its own address and sees only itself.

## Make them (once, CMD)

```
cd backend
.venv\Scripts\activate.bat
set HIMS_DEMO_PASSWORD=<choose a password of 12+ characters for all demo accounts>
python manage.py setup_demo_hospitals --password-env HIMS_DEMO_PASSWORD
set HIMS_DEMO_PASSWORD=
```

It takes about a minute per hospital, so about 8 to 10 minutes for all ten. To make only one:
`--only in-sunrise`. To make them again from scratch: `--reset`, which deletes the old demo data
first. A quick, smaller version: `--small`.

After a merge that adds database changes, run the same command with `--reset`. It is demo data,
so nothing real is lost.

Then:

```
cd frontend
npm run dev
```

The launcher lists them under **Demo hospitals: India** and **Demo hospitals: United States**.
Press **Open** on one.

## The hospitals

| Key | Hospital | Branches | App | Server |
|---|---|---|---|---|
| in-sunrise | Sunrise Hospitals (Demo) | Dwarka (Delhi), Noida, Gurugram | :5201 | :8201 |
| in-ganga | Ganga Care Hospitals (Demo) | Lucknow, Varanasi, Prayagraj | :5202 | :8202 |
| in-deccan | Deccan Health (Demo) | Hyderabad, Secunderabad, Warangal | :5203 | :8203 |
| in-westernghats | Western Ghats Hospitals (Demo) | Pune, Mumbai, Nashik | :5204 | :8204 |
| in-baycoast | Bay Coast Medical (Demo) | Chennai, Coimbatore, Madurai | :5205 | :8205 |
| us-lakeside | Lakeside Health (Demo) | Chicago, Evanston, Naperville | :5206 | :8206 |
| us-harborpoint | Harbor Point Medical (Demo) | Boston, Cambridge, Quincy | :5207 | :8207 |
| us-desertbloom | Desert Bloom Health (Demo) | Phoenix, Tempe, Mesa | :5208 | :8208 |
| us-pacificcrest | Pacific Crest Hospitals (Demo) | San Diego, Irvine, Long Beach | :5209 | :8209 |
| us-bluegrass | Bluegrass Regional (Demo) | Louisville, Lexington, Frankfort | :5210 | :8210 |

The list lives in `backend/apps/demo/hospitals.json`. Each one's settings file is
`backend/.env.demo-<key>`; Git ignores these files.

## Sign-in accounts (all use your demo password)

`<key>` is the hospital's key, e.g. `in-sunrise`; `<branch>` is the branch code in lower case,
e.g. `dwk`.

| Account | What it can do |
|---|---|
| `admin@<key>.demo.test` | Hospital administrator: everything |
| `auditor@<key>.demo.test` | Auditor: audit log, access reviews, compliance |
| `hr@<key>.demo.test` | HR: staff, licences, leave, catalogs |
| `admin.<branch>@<key>.demo.test` | Branch administrator (that branch only) |
| `hod.<branch>@<key>.demo.test` | Head of Cardiology at that branch: rota, leave |
| `nurse.<branch>@<key>.demo.test` | A nurse with basic access |
| `beds.<branch>@<key>.demo.test` | Bed manager |
| `equipment.<branch>@<key>.demo.test` | Equipment officer |
| `frontdesk.<branch>@<key>.demo.test` | Front desk of that branch: registers patients (HIMS-PAT-001) |
| `opd.<branch>@<key>.demo.test` | OPD scheduler of that branch: doctors' sessions, doctors away, holidays, extra sessions (HIMS-OPD-001); books, moves and cancels appointments (HIMS-OPD-002) |
| `records@<key>.demo.test` | Medical records officer (whole hospital): registers and corrects patients |
| `support@hims-supplier.demo.test` | **You, the software supplier**: asks for Support access ([how](../workflows/support-access.md)) |

Two-factor setup is switched off in the demo hospitals only
(`HIMS_MFA_REQUIRED_FOR_PRIVILEGED=false` in their settings files), so you can click around
quickly. Real hospitals always require it.

## What is in each hospital

| Area (screen) | Demo records |
|---|---|
| Hospital settings | Letterhead, leave year (April in India, January in the US) |
| Facilities | 3 branches |
| Departments | 12 per branch: services, opening hours, a head |
| Locations | 2 buildings (Main Block; Women and Child Block), 7 floors, 14 wards (emergency, general men/women, ICU, HDU, surgical, private, theatres, recovery, day care, maternity, NICU, children's, PICU), about 48 rooms, about 180 beds per branch |
| Bed board | Beds in every colour: available, maintenance, blocked, out of service |
| Equipment | 15 per branch: some overdue for service, one under repair, with service history |
| Staff | About 45 per branch: doctors, nurses, pharmacists, laboratory, administration; postings, qualifications, licences (some expired or expiring in 7/30/60 days, so Licence expiry has something to show) |
| Job titles and catalogs | 8 clinical privileges; privileges given to the heads of department |
| Rota and leave | Two weeks of morning/evening/night shifts and on-call; leave waiting, approved and refused; minimum staffing for ICU and Emergency |
| Access, Accounts, Cover, Access reviews | The accounts above with their roles, one cover arrangement, one open access review |
| Support access | One finished request and one waiting for the hospital |
| Patients (2026-11-12, HIMS-PAT-001) | 40 invented patients per branch with MRNs, address, a parent for every child, next of kin for some, an invented previous clinic MRN for some, privacy notice and SMS consent; one unknown (unconscious) patient per branch. All registered by that branch's front desk, so the audit log shows who |
| Patient search (2026-11-13, HIMS-PAT-002) | One woman per branch with an earlier family name (still found by it); example searches printed by the rebuild |
| Patient chart (2026-11-14, HIMS-PAT-005) | Per branch: the first child came without a guardian (a teacher brought her; the reason is recorded) and one adult has not had the privacy notice yet, so their charts show alerts; their MRNs are printed as "chart alert" examples; the records officer (`records@...`) sees every chart's History |
| Restricted records (2026-11-14, HIMS-PAT-006) | Per branch one adult's record restricted by medical records (the first branch: a VIP; the others: a member of staff); two emergency accesses to the VIP by the first branch's head of department, one reviewed by medical records and one waiting for review; the VIP's MRN printed as "restricted record" |
| Doctor schedules (2026-11-15, HIMS-OPD-001) | Per branch, in each outpatient department (General Medicine, Cardiology, Orthopaedics, Paediatrics, Obstetrics, General Surgery): the consultant's sessions Mon, Wed, Fri 09:00–13:00 (10-minute slots, 2 extra bookings) and the junior doctor's Tue, Thu 14:00–17:00 (15-minute slots); the cardiologist away 11:00–13:00 next Wednesday, the general physician away three days at a conference, the paediatrician's extra Saturday session (vaccination drive), a holiday (the first branch closed for a day, the others close Orthopaedics for a training day); junior doctors with leave approved on the Leave page show those sessions off |
| Appointments (2026-11-15, HIMS-OPD-002) | Per branch, booked by its front desk: in the cardiologist's first session with free slots in the next two weeks, up to four patients (new and follow-up, short reasons), one more over the slots, one moved to a later slot (linked to the old one), one cancelled at the patient's request; an obstetrics patient whose doctor is then called away for that day, so the Appointments page shows them under To move. Restricted and unknown patients are never booked by the demo |
| OPD queue (2026-11-15, HIMS-OPD-003) | Per branch, today (the day the demo is built): a doctor's session today (an extra session "Demo OPD queue", 08:00–20:00, when no doctor works that day); four patients booked into its first slots, three checked in out of slot order (tokens 1–3) by the front desk and a walk-in (token 4); token 1 seen, token 2 with the doctor, tokens 3 and 4 waiting; the fourth booked patient still to come, or marked did not come when the rebuild runs after their time; the no-show job run once |
| Audit log | Everything above, recorded as it was made |

## Patients and later phases

HIMS has no patient screens yet: patients come with Phase 2 (HIMS-PAT-001). The invented
patients are already prepared: 40 per branch, with names, sex, date of birth, phone, city, blood
group and an allergy. No Aadhaar, ABHA or Social Security numbers. See them now:

```
python manage.py demo_patients --hospital in-sunrise
python manage.py demo_patients --hospital us-lakeside --csv lakeside-patients.csv
```

**Rule for every later task:** each new screen adds its own demo records in
`backend/apps/demo/seed.py`, so the demo hospitals always show everything built so far. For
example, patients and visits come with Phase 2; admissions to these beds with Phase 3;
prescriptions and lab orders with Phase 4; bills with Phase 5.

**Update 2026-11-12 (HIMS-PAT-001):** the invented patients above are now **registered** in each demo hospital (Patients menu), by `frontdesk.<branch>@<key>.demo.test`. Still no Aadhaar, ABHA or Social Security numbers: the only ID number is an invented previous-clinic MRN. US demo phones now carry an area code (`+1 312 555 01xx`, still the fictional 555-01xx range). **After this merge, build the demo hospitals again with `--reset`** (the new tables and patients need it):

```
cd backend
.venv\Scripts\activate.bat
set HIMS_DEMO_PASSWORD=<your demo password>
python manage.py setup_demo_hospitals --password-env HIMS_DEMO_PASSWORD --reset
set HIMS_DEMO_PASSWORD=
```

**Update 2026-11-13 (HIMS-PAT-002, patient search):** in each branch one woman of 25 or more
changed her family name after registering (the front desk corrected it), so her **earlier name
still finds her**. At the end of each hospital the rebuild prints **"Try these on Patients ->
Search"**: an MRN, only its number, another spelling of a first name (e.g. `ee` for `i`), a name in
reverse order, a phone, a previous hospital's MRN and the earlier family name, each with the
patient it finds. Build the demo hospitals again with `--reset` after this merge (the new search
column is filled by `migrate`, but the earlier-name patients come from the rebuild). How to search:
[patient search](../workflows/patient-search.md).

The **hosted Development hospital** (Render + Neon) can get the same records as Sunrise Hospitals
(Demo) with one command from the PC: [Render + Neon, section 8](../workflows/render-neon-hosting.md).

**Update 2026-11-14 (HIMS-PAT-005, patient chart):** in each branch the first child registered
without a guardian (with the reason "brought in by a school teacher; the mother is on her way")
and the third patient, an adult, has no privacy notice recorded yet: their charts show the
alerts "Under 18 with no parent or guardian recorded" and "The privacy notice is not recorded as
given". The rebuild prints both MRNs under "Try these on Patients -> Search" as **chart alert**.
Sign in as `records@<hospital>.demo.test` (medical records officer) to see the **History** tab.
Build the demo hospitals again with `--reset` after this merge. How to use the chart:
[patient chart](../workflows/patient-chart.md).

**Update 2026-11-14 (HIMS-PAT-006, restricted records):** in each branch one adult's record is
restricted (the first branch: a VIP, "a well-known local politician who asked for privacy"; the
others: "a nurse of this hospital"). The first branch's head of department (`hod.<branch>@`) used
emergency access twice on the VIP: one is already reviewed by `records@` (appropriate), one waits
under **Emergency access → To review**. The rebuild prints the VIP's MRN as **restricted record**.
The front desk does not find the VIP by name; the MRN shows only "Restricted record". A hospital
filled before this change (such as the hosted Development hospital) gets the same records with
`python manage.py add_demo_restricted_records` (on Render + Neon: `--hosted-development`;
[Render + Neon section 8](../workflows/render-neon-hosting.md)). How it works:
[restricted records](../workflows/restricted-records.md).

**Update 2026-11-15 (HIMS-OPD-001, doctor schedules):** each branch has the doctors' OPD sessions and
exceptions in the table above and a new account, `opd.<branch>@<key>.demo.test` (OPD scheduler). Look
at **Doctor schedules** as `opd.<branch>@`, `hod.<branch>@` (Cardiology), `admin.<branch>@` (the whole
branch, including holidays for the branch) or `frontdesk.<branch>@` (sees the sessions and free slots,
not why a doctor is away). The rebuild prints what to look at under "Doctor schedules". **After this
merge, build the demo hospitals again with `--reset`** (the new tables, the role and the account need
it). A hospital filled before this change (such as the hosted Development hospital) gets the sessions
and exceptions, without the new account, with `python manage.py add_demo_doctor_schedules` (on Render +
Neon: `--hosted-development`; [Render + Neon section 8](../workflows/render-neon-hosting.md)). How it
works: [doctor schedules](../workflows/doctor-schedules.md).

**Update 2026-11-15, later (HIMS-OPD-002, appointments):** each branch has the appointments in the
table above. Look at **Appointments** as `frontdesk.<branch>@` or `opd.<branch>@` (book, move,
cancel; Cardiology on the day the rebuild prints, and Obstetrics for the To move list), as
`hod.<branch>@` (sees them, books nothing), and at **My schedule** as the cardiologist. The rebuild
prints the days under "Doctor schedules". **After this merge, build the demo hospitals again with
`--reset`.** A hospital filled before this change (such as the hosted Development hospital) gets the
appointments with `python manage.py add_demo_appointments` after `add_demo_doctor_schedules` (on
Render + Neon: `--hosted-development`; [Render + Neon section 8](../workflows/render-neon-hosting.md)).
How it works: [appointments](../workflows/appointments.md).

**Update 2026-11-15, latest (HIMS-OPD-003, the OPD queue):** each branch has today's queue in the
table above. Look at **OPD queue** as `frontdesk.<branch>@` (check in, walk in, Call next, Seen, did
not come) or `hod.<branch>@` (sees it), on the day the rebuild prints under "OPD queue today"; on a
later day choose that day (shown as it was) or add a new day's queue. **After this merge, build the
demo hospitals again with `--reset`.** A hospital filled earlier (such as the hosted Development
hospital) gets today's queue with `python manage.py add_demo_opd_queue` (on Render + Neon:
`--hosted-development`; [Render + Neon section 8](../workflows/render-neon-hosting.md)); it may be
run once a day for that day's queue. How it works: [OPD queue](../workflows/opd-queue.md).
