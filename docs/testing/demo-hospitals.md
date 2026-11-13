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
