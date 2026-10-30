# Hospital Departments, Doctors and Role-Based Access (RBAC)

**Status:** Draft v1, 2026-10-26. Catalogs and administrative roles are implemented. The
**clinical access matrix (section 8) is a proposal** that needs clinical-governance approval before
clinical features use it (spec 26.4, P0-D).
**Related:** spec sections 3, 4.2, 4.3, 4.4, 13.2, 26.4 · ADR-015 (scoped RBAC) · ADR-016 (admin console)
· [spec-status.md](spec-status.md)

**Contents**
1. [How access works in HIMS](#1-how-access-works-in-hims)
2. [Hospital structure](#2-hospital-structure)
3. [Doctors: qualifications and what they mean](#3-doctors-qualifications-and-what-they-mean)
4. [Career ladders, junior to senior](#4-career-ladders-junior-to-senior)
5. [Departments and the people in them](#5-departments-and-the-people-in-them)
6. [Professional registration and licences](#6-professional-registration-and-licences)
7. [Roles available today](#7-roles-available-today)
8. [Proposed clinical access matrix](#8-proposed-clinical-access-matrix-needs-clinical-approval)
9. [Separation of duties and safety rules](#9-separation-of-duties-and-safety-rules)
10. [India vs US: key differences](#10-india-vs-us-key-differences)
11. [Decisions needed](#11-decisions-needed)

---

## 1. How access works in HIMS

Four separate ideas. Keeping them separate is required by spec 4.3 ("A doctor's academic degree,
professional designation, specialty and permission to perform a procedure are separate concepts").

| Idea | What it is | Example | Where it lives |
|---|---|---|---|
| **Qualification** | What someone studied | MBBS, MD (Medicine), DNB, RN | Staff → Qualifications (catalog: `qualification_types`) |
| **Credential / licence** | Legal permission to practise, with expiry | State Medical Council registration, US state licence, NPI | Staff → Credentials (verified by HR) |
| **Designation** | Job title on a junior→senior ladder | Senior Resident, Consultant, Charge Nurse | Staff → Department assignment (catalog: `designations`) |
| **Role** | What the person may **do in HIMS** | "Head of department", "HR / credentialing officer" | Role assignments (RBAC) |

**Access comes only from roles.** Having "Consultant" or "MD" on a profile gives **no** access by
itself. An administrator assigns roles. Rules (ADR-015):

- **Default deny:** nothing is allowed unless a role grants it.
- **Scope:** a role is granted for the whole organization, **one facility (branch)**, or **one
  department**. A Cardiology HOD role at Branch A shows only Cardiology at Branch A.
- **Time-bounded:** assignments can expire (locums, visiting consultants, students on rotation).
- **No escalation:** you can only grant permissions you hold yourself.
- **Everything is audited:** grants, revocations and every "permission denied" (with its reference
  number, see HIMS-UI-002).

---

## 2. Hospital structure

```text
Hospital organization (one HIMS deployment, e.g. "Sonia Multispeciality Hospital")
├── Governance: Board / Owner → CEO → COO, Medical Director, Chief Nursing Officer, CFO
├── Facility / branch (e.g. "Main Hospital", "City Clinic")
│   ├── Clinical departments (Cardiology, Oncology, Pediatrics, ...)
│   │   └── Units / wards / OTs / ICUs (beds come with HIMS-FAC-004)
│   ├── Diagnostic departments (Radiology, Laboratory, Blood bank)
│   ├── Support departments (Pharmacy, CSSD, Dietetics, Housekeeping, Biomedical)
│   └── Administrative departments (Front office, Billing, Insurance/TPA, Medical records, HR)
```

| Level | Typical leadership (India) | Typical leadership (US) |
|---|---|---|
| Organization | Managing Director / CEO, Medical Director, Nursing Director | CEO, CMO, CNO, CFO, COO |
| Facility / branch | Medical Superintendent, Facility Manager | Hospital President / Administrator, CMO for site |
| Clinical department | Head of Department (HOD) / Unit Head | Department Chair, Section / Division Chief |
| Nursing in a ward | Ward Sister / Nursing In-charge | Nurse Manager, Charge Nurse |
| Support department | Department Manager / In-charge | Department Director / Manager |

---

## 3. Doctors: qualifications and what they mean

### 3.1 India

| Qualification | Level | What it means in practice | Typical job |
|---|---|---|---|
| **MBBS** | Undergraduate (5.5 yrs incl. internship) | Basic doctor; can practise general medicine | Medical Officer, Casualty MO, RMO, Junior Resident |
| **MD** (e.g. General Medicine, Pediatrics, Anaesthesia, Radiology, Pathology) | Postgraduate, **non-surgical** | Specialist. MD General Medicine = "**Physician**" | Consultant Physician / specialist |
| **MS** (e.g. General Surgery, Orthopaedics, ENT, Ophthalmology, OBG) | Postgraduate, **surgical** | Specialist surgeon | Consultant Surgeon |
| **DNB** (broad specialty) | Postgraduate, National Board | Equivalent to MD/MS | Consultant |
| **Diplomas** (DCH, DGO, DA, DMRD, DLO, DOMS, DPM, DVL) | 2-year PG diploma | Specialist at diploma level | Specialist / Associate Consultant |
| **DM** (Cardiology, Neurology, Nephrology, Gastro, Medical Oncology...) | Super-specialty after MD | Super-specialist physician | Consultant Cardiologist etc. |
| **MCh** (Neurosurgery, CTVS, Urology, Surgical Oncology, Plastic...) | Super-specialty after MS | Super-specialist surgeon | Consultant Neurosurgeon etc. |
| **DrNB / FNB** | Super-specialty / fellowship (National Board) | Equivalent to DM/MCh, or fellowship | Super-specialist |
| **BDS / MDS** | Dental | Dentist / dental specialist | Dental surgeon |
| **BAMS / BHMS** (AYUSH) | Ayurveda / Homoeopathy | Separate system of medicine; limited allopathic practice per state rules | AYUSH Medical Officer |
| **MRCP / FRCS** (UK) | International | Recognised additional qualification | Senior roles |

**"Physician only"** in India usually means MBBS + MD (General Medicine), or MBBS working as a
general physician / Medical Officer, without super-specialty (DM).

### 3.2 United States

| Qualification | What it means | Typical job |
|---|---|---|
| **MD** (Doctor of Medicine) or **DO** (Doctor of Osteopathic Medicine) | Medical degree (after a 4-year college degree) | Starts residency |
| **USMLE / COMLEX** | Licensing exams | Required for a state licence |
| **Residency** (3-7 yrs) | Specialty training (Internal Medicine, General Surgery, Pediatrics...) | Resident → Attending |
| **Board certification** (ABMS / AOA boards) | Specialist certification | Board-certified Attending |
| **Fellowship** (1-3 yrs) | Sub-specialty (Cardiology, Oncology...) | Sub-specialist Attending |
| **NP** (MSN / DNP), **PA** (MPAS) | Advanced practice providers | See patients, prescribe within state scope, often supervised |
| **CRNA** | Nurse anesthetist | Anesthesia care |

**"Physician"** in the US means any MD/DO. A doctor practising general adult medicine is an
**Internist** (Internal Medicine) or **Family Physician**; a hospital-based internist is a
**Hospitalist**.

---

## 4. Career ladders, junior to senior

All titles below are in the HIMS `designations` catalog (seniority 1 = entry ... 10 = leadership).
Hospitals can add their own titles in the admin console (**Designations**).

### 4.1 Doctors

| Seniority | India | US |
|---|---|---|
| 1 | Intern (Compulsory Rotating Internship) | Medical Student |
| 2 | Junior Resident (JR), Medical Officer (MO), Casualty Medical Officer | Intern (PGY-1) |
| 3 | Resident Medical Officer (RMO) | Resident (PGY-2+) |
| 4 | Senior Resident (SR), Registrar | Chief Resident, Fellow |
| 5 | Associate Consultant, Assistant Professor | Physician Assistant (PA) |
| 6 | Consultant, Visiting Consultant, Associate Professor | Attending Physician, Hospitalist |
| 7 | Senior Consultant, Professor | — |
| 8 | Head of Department (HOD) | Section / Division Chief |
| 9 | Medical Superintendent | Department Chair |
| 10 | Medical Director | Chief Medical Officer (CMO) |
| — | Locum Physician (both countries, seniority 5) | |

Teaching hospitals (India) use the academic ladder (Assistant → Associate → Professor); private
hospitals use the consultant ladder. Both are in the catalog.

### 4.2 Nursing

| Seniority | India | US |
|---|---|---|
| 1 | Auxiliary Nurse Midwife (ANM) | Certified Nursing Assistant (CNA) |
| 2 | Staff Nurse (GNM / B.Sc.) | LPN / LVN |
| 3 | Senior Staff Nurse | Registered Nurse (RN) |
| 4 | Ward Sister / Nursing In-charge | Charge Nurse |
| 5 | Nursing Supervisor, Nurse Educator | Nurse Practitioner, Clinical Nurse Specialist, Nurse Midwife, Nurse Educator |
| 6 | Assistant Nursing Superintendent | CRNA, Nurse Manager |
| 7 | Deputy Nursing Superintendent | — |
| 8 | Nursing Superintendent | Director of Nursing |
| 9 | Chief Nursing Officer | Chief Nursing Officer (CNO) |

### 4.3 Pharmacy

| Seniority | India | US |
|---|---|---|
| 1 | Pharmacy Assistant | Pharmacy Technician (CPhT) |
| 3 | Pharmacist (D.Pharm / B.Pharm / Pharm.D) | Pharmacist (PharmD, RPh) |
| 4 | Clinical Pharmacist | Clinical Pharmacist |
| 5 | Senior Pharmacist | Senior Pharmacist |
| 7 | Chief Pharmacist | Director of Pharmacy |

### 4.4 Allied health and technicians (both countries unless marked)

| Seniority | Laboratory | Imaging | Operating theatre / procedures | Therapy & others |
|---|---|---|---|---|
| 1 | Phlebotomist | — | CSSD Technician | — |
| 2 | Lab Technician (DMLT / MLT), Blood Bank Technician | Radiographer / Radiologic Technologist | OT Technician (IN), Surgical Technologist CST (US), Anaesthesia Technician, Dialysis Technician, ECG/ECHO, EEG/EMG Technician | EMT / Paramedic |
| 3 | Lab Technologist / Medical Laboratory Scientist | CT/MRI Technologist, Sonographer | Cath Lab Technician | Physiotherapist, Occupational Therapist, Speech Therapist / Audiologist, Dietitian, Optometrist, Respiratory Therapist, Biomedical Engineer, Medical Social Worker |
| 4 | — | — | Perfusionist | — |
| 5 | Lab Supervisor | Chief Radiographer | — | — |

### 4.5 Administration and support

| Seniority | Administration | Support services |
|---|---|---|
| 1 | Front Office / Reception Executive | Ward Attendant / GDA (IN), Patient Care Technician (US), Housekeeping, Porter, Kitchen, Security, Ambulance Driver |
| 2 | Patient Care Coordinator, Billing Executive, Insurance/TPA Desk (IN), Medical Records Officer (IN) | — |
| 3 | Medical Coder (US), Revenue Cycle Specialist (US), HIM Technician (US), HR Executive | Housekeeping Supervisor |
| 4 | Credentialing Officer | — |
| 5 | Quality & Patient Safety Officer, Department Manager | — |
| 6 | Facility / Branch Manager | — |
| 7 | Hospital Administrator | — |
| 9-10 | COO, CEO | — |

---

## 5. Departments and the people in them

Specialties marked ✓ are in the HIMS `specialties` catalog (52 entries). Departments are created
per branch in the admin console; link them to a specialty through staff assignments.

### 5.1 Medical (non-surgical) departments

| Department | Doctors (India → US) | Nurses | Technicians / allied | Notes |
|---|---|---|---|---|
| General / Internal Medicine ✓ | MBBS MO, MD Medicine (Physician) → Internist, Hospitalist | Staff Nurse / RN | Phlebotomist, ECG tech | Largest OPD/IPD department |
| Cardiology ✓ (+ Interventional ✓) | MD + DM Cardiology → Cardiology fellow / Cardiologist | CCU nurses | Cath lab tech, ECG/ECHO tech | Cath lab is a procedure area |
| Neurology ✓ | MD + DM Neurology → Neurologist | Neuro ward nurses | EEG/EMG tech | Stroke unit |
| Nephrology ✓ | MD + DM Nephrology → Nephrologist | Dialysis nurses | Dialysis technician | Dialysis unit |
| Gastroenterology ✓ / Hepatology ✓ | MD + DM Gastro → Gastroenterologist | Endoscopy nurses | Endoscopy technician | Endoscopy suite |
| Pulmonology ✓ | MD Respiratory Medicine / Pulmonologist | Ward nurses | Respiratory therapist (US), PFT tech | Bronchoscopy |
| Endocrinology ✓ | MD + DM Endo → Endocrinologist | — | Diabetes educator | |
| Medical Oncology ✓ / Hematology ✓ | MD + DM Medical Oncology → Oncologist | Chemo-trained nurses | Pharmacist (chemo mixing) | Day-care chemotherapy |
| Radiation Oncology ✓ | MD Radiotherapy → Radiation Oncologist | — | Radiation therapist, medical physicist | Linac / brachytherapy |
| Pediatrics ✓ / Neonatology ✓ | MD/DCH/DNB Pediatrics, DM Neonatology → Pediatrician, Neonatologist | NICU / PICU nurses | — | NICU, PICU |
| Psychiatry ✓ | MD Psychiatry / DPM → Psychiatrist | Psychiatric nurses | Clinical psychologist, social worker | Extra privacy for records |
| Dermatology ✓ | MD/DVL → Dermatologist | — | — | Mostly OPD |
| Rheumatology ✓, Infectious Diseases ✓, Geriatrics ✓, Palliative Care ✓, Pain Medicine ✓ | Specialists | Ward nurses | — | |
| Physical Medicine & Rehabilitation ✓ / Physiotherapy ✓ | PMR specialist | — | Physiotherapist, OT, speech therapist | |

### 5.2 Surgical departments

| Department | Doctors (India → US) | Nurses | Technicians | Notes |
|---|---|---|---|---|
| General Surgery ✓ | MS General Surgery → General Surgeon | OT nurses, scrub nurses | OT tech / CST, CSSD | |
| Orthopedics ✓ | MS Ortho / DNB → Orthopedic Surgeon | Ortho ward nurses | OT tech, plaster technician | Implants tracking (spec 4.17) |
| Neurosurgery ✓ | MCh Neurosurgery → Neurosurgeon | Neuro ICU nurses | OT tech | |
| Cardiothoracic & Vascular ✓ | MCh CTVS → CT Surgeon | CTICU nurses | Perfusionist, OT tech | Heart-lung machine |
| Urology ✓ | MCh Urology → Urologist | — | OT tech | |
| Surgical Oncology ✓ | MCh Surgical Oncology → Surgical Oncologist | — | OT tech | |
| Plastic Surgery ✓, Pediatric Surgery ✓, Vascular Surgery ✓ | MCh specialists | — | OT tech | |
| Obstetrics & Gynecology ✓ | MS/MD OBG, DGO → OB/GYN | Midwives, labour-room nurses | OT tech | Labour room, maternity ward |
| ENT ✓ | MS ENT / DLO → Otolaryngologist | — | Audiologist | |
| Ophthalmology ✓ | MS Ophth / DOMS → Ophthalmologist | — | Optometrist | |
| Dentistry / Oral & Maxillofacial ✓ | BDS / MDS → Dentist, OMFS | Dental assistant | — | |
| Anesthesiology ✓ | MD/DA/DNB Anaesthesia → Anesthesiologist, CRNA (US) | Recovery (PACU) nurses | Anaesthesia technician | Owns anaesthesia records |

### 5.3 Critical care and emergency

| Department | Doctors | Nurses | Others | Notes |
|---|---|---|---|---|
| Emergency / Casualty ✓ | Casualty MO, Emergency physician (MD/DNB EM) → ER physician | ER nurses, triage nurses | EMT / Paramedic | Treatment before payment clearance (spec 5.1) |
| ICU / Critical Care ✓ (MICU, SICU, CCU, NICU, PICU) | Intensivist (IDCCM/DM Critical Care) | ICU nurses (1:1 / 1:2) | Respiratory therapist (US) | Highest-risk area: double checks |

### 5.4 Diagnostic departments

| Department | Doctors | Technicians | Notes |
|---|---|---|---|
| Radiology ✓ (+ Interventional ✓, Nuclear Medicine ✓) | MD/DMRD Radiology → Radiologist | Radiographer / RT, CT/MRI technologist, sonographer | Radiologist signs reports; PACS integration later |
| Pathology & Laboratory ✓ (Microbiology ✓, Biochemistry ✓) | MD Pathology / Microbiology / Biochemistry → Pathologist | Phlebotomist, lab technician, lab technologist / MLS, lab supervisor | Validates and releases results; critical-result escalation |
| Blood Bank / Transfusion Medicine ✓ | MD Transfusion Medicine / Pathologist | Blood bank technician | Strictly regulated |

### 5.5 Support and administrative departments

| Department | People | Notes |
|---|---|---|
| Pharmacy | Pharmacy assistant / technician, pharmacist, clinical pharmacist, chief pharmacist | Dispensing, controlled drugs, stock |
| CSSD (sterilization) | CSSD technician | Instruments for OT |
| Dietetics & Kitchen | Dietitian, kitchen staff | Diet orders need clinical authorization (spec 4.11) |
| Biomedical Engineering | Biomedical engineer | Equipment maintenance (spec 4.12) |
| Housekeeping | Housekeeping staff, supervisor | Bed cleaning sign-off (spec 4.10) |
| Front Office / Reception | Front office executive, patient care coordinator | Registration, appointments |
| Billing | Billing executive, revenue cycle specialist (US), medical coder (US) | Charges, invoices |
| Insurance desk | TPA / insurance desk executive (IN), revenue cycle (US) | Pre-auth, claims |
| Medical Records (MRD / HIM) | Medical records officer (IN), HIM technician (US) | Record completion, release of information |
| HR & Credentialing | HR executive, credentialing officer | Onboarding, licence verification |
| Quality & Infection Control | Quality officer, infection-control nurse | Audits, incident review (NABH in India, Joint Commission in US) |
| Administration | Department / facility manager, hospital administrator, COO, CEO | |

---

## 6. Professional registration and licences

| Profession | India | US |
|---|---|---|
| Doctors | National Medical Commission (NMC) / State Medical Council registration | State medical licence, DEA registration (controlled drugs), NPI |
| Dentists | Dental Council of India / State Dental Council | State dental licence |
| Nurses | Indian Nursing Council / State Nursing Council | State RN/LPN licence (NCLEX), APRN licence |
| Pharmacists | Pharmacy Council of India / State Pharmacy Council | State pharmacist licence (NAPLEX) |
| Allied health | State paramedical councils (vary by state) | Certifications: ARRT, ASCP, CST, RRT, CPhT |
| Coders / HIM | — | CPC / CCS, RHIA / RHIT |

HIMS stores these under **Staff → Credentials**, with issuing authority, jurisdiction (e.g. `IN-KA`,
`US-CA`) and expiry. **Verification is done by someone else** (HR / credentialing officer), never
by the staff member themselves. Expiry alerts come with HIMS-STAFF-006.

---

## 7. Roles available today

These are **system roles** created automatically for every hospital. They use only features that
exist now. Assign them in the admin console under **Role assignments**.

| Role | Assign at scope | Permissions | Responsibilities | Typical designations |
|---|---|---|---|---|
| **Organization administrator** | Organization | Everything except `audit.view` (organization, facilities, departments, staff, roles, role assignments, admin console) | Sets up the hospital, branches, departments, staff and access | Hospital Administrator, COO, CEO, IT admin |
| **Auditor / compliance officer** | Organization | `audit.view` | Reviews who did what; investigates incidents | Quality officer, compliance officer |
| **Facility (branch) administrator** | One facility | facilities view + manage, departments view + manage, locations view + manage, bed status, numbering view + manage (own facility's series only), features view + manage (own facility's per-facility features only) | Runs one branch: its details, departments, buildings, wards, rooms and beds, its own visit/invoice/claim number series, and which modules are on at the branch | Facility Manager, Medical Superintendent |
| **HR / credentialing officer** | Organization | staff view + manage, credentials verify, facilities + departments view | Onboards staff, records qualifications, verifies licences, sends invitations | HR Executive, Credentialing Officer |
| **Head of department (HOD)** | One department | facilities view, departments view, locations view | Sees their department. Clinical approvals are added with clinical features | HOD, Section Chief, Department Chair |
| **Basic staff access** | Organization or facility | facilities view, departments view, locations view | Minimum access for any employee, so new staff don't see "Permission denied" | Everyone |
| **Bed manager / ward clerk** | One facility | facilities view, locations view, bed status | Marks beds available, under maintenance, blocked or out of service (with a reason). Cannot change the building/ward structure. Reserved/occupied/cleaning come from admissions later (Phase 3) | Ward clerk, bed manager, nursing supervisor, admission desk lead |

**Two-factor sign-in is required** for anyone holding Organization administrator, Auditor, Facility administrator or HR / credentialing officer (they can change settings, people, access, the building/ward/bed structure, the numbering of patients, invoices and claims, which features are on, or read the audit log). Head of department, Basic staff access and Bed manager do not require it today (changing a bed's status is routine ward work), but anyone can turn it on under **Security**. See ADR-018.

**Users with no role** see a "Welcome, your account is active" page with a **reference number**. An auditor can find it in the admin console (**Audit events**, search the reference) as an `access.none_assigned` event.

**To give a new doctor access today:** assign **Basic staff access** (and **Head of department** for
HODs). Clinical access (patients, notes, orders) becomes available when those features are built
and the matrix in section 8 is approved.

Hospitals can also build **custom roles** from the permission list (admin console → Roles).

---

## 8. Proposed clinical access matrix (needs clinical approval)

Planned permissions, by phase. **Proposal only**: clinical governance must confirm or change each
cell before the feature ships (spec 26.4). Legend: ✅ allowed · 👁 view only · ✍ draft only (needs
co-signature) · ⚠ allowed with second-person check · — not allowed. "Own" means patients under the
person's care (treating team / department).

| Permission (phase) | Intern / Student | Junior / Senior Resident, MO | Consultant / Attending | HOD / Chief | Staff Nurse / RN | Ward Sister / Charge Nurse | Pharmacist | Lab tech / technologist | Radiographer / RT | Front office | Billing / Insurance | Medical records |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Register / search patient (P2) | 👁 | ✅ | ✅ | ✅ | 👁 | 👁 | 👁 | 👁 | 👁 | ✅ | 👁 | ✅ |
| View chart (P2) | 👁 own | ✅ own | ✅ own + dept | ✅ dept | ✅ own ward | ✅ ward | 👁 meds only | 👁 orders only | 👁 orders only | — | 👁 billing only | ✅ (release workflow) |
| Write clinical note (P2) | ✍ | ✅ | ✅ | ✅ | ✅ nursing notes | ✅ nursing notes | — | — | — | — | — | — |
| **Sign** note / discharge summary (P2/P3) | — | ✅ (SR) / ✍ (JR, per policy) | ✅ | ✅ | ✅ nursing notes | ✅ | — | — | — | — | — | — |
| Amend a signed note (P2) | — | own only, with reason | own only, with reason | ✅ dept, with reason | own only | own only | — | — | — | — | — | correction workflow only |
| Admit / discharge order (P3) | — | ✅ (as per policy) | ✅ | ✅ | — | — | — | — | — | — | — | — |
| Assign / transfer bed (P3) | — | — | ✅ request | ✅ | — | ✅ | — | — | — | ✅ (bed desk) | — | — |
| Medication order (P4) | ✍ | ✅ | ✅ | ✅ | — | — | — | — | — | — | — | — |
| High-alert / controlled drug order (P4) | — | ⚠ | ✅ | ✅ | — | — | — | — | — | — | — | — |
| Verify order / dispense (P4) | — | — | — | — | — | — | ✅ | — | — | — | — | — |
| Administer dose (eMAR) (P4) | — | — | — | — | ✅ | ✅ | — | — | — | — | — | — |
| High-alert dose administration (P4) | — | — | — | — | ⚠ double check | ⚠ | — | — | — | — | — | — |
| Lab order (P4) | ✍ | ✅ | ✅ | ✅ | ✅ protocol | ✅ protocol | — | — | — | — | — | — |
| Enter lab result (P4) | — | — | — | — | — | — | — | ✅ | — | — | — | — |
| **Validate / release** lab result (P4) | — | — | — | — | — | — | — | technologist ✅ / pathologist ✅ | — | — | — | — |
| Radiology report sign (P4) | — | — | Radiologist ✅ | ✅ | — | — | — | — | performs study only | — | — | — |
| Surgery booking / safety checklist (P4+) | — | ✅ | ✅ | ✅ | ✅ checklist | ✅ | — | — | — | — | — | — |
| Charges / invoices (P5) | — | — | — | 👁 dept | — | — | 👁 pharmacy | — | — | 👁 | ✅ | — |
| Insurance pre-auth / claims (P5) | — | — | ✅ clinical notes for pre-auth | ✅ | — | — | — | — | — | — | ✅ | 👁 |
| Release of information / export (P6) | — | — | — | — | — | — | — | — | — | — | — | ✅ with approval |
| Break-glass emergency access (P2) | — | ✅ with reason | ✅ with reason | ✅ | ✅ with reason | ✅ | — | — | — | — | — | — |

Country notes:
- **US:** NPs and PAs order within state scope of practice (often with a collaborating physician).
  Residents' notes are typically co-signed by the attending. CRNAs administer anesthesia.
- **India:** Interns and JRs work under a named consultant. Controlled-substance (NDPS) orders
  follow hospital and state rules. TPA desk staff handle cashless pre-authorization.

---

## 9. Separation of duties and safety rules

| Rule | Why | Enforced |
|---|---|---|
| The person who makes changes cannot read or change the audit log | Prevents hiding mistakes | ✅ today (admin has no `audit.view`) |
| Nobody verifies their own licence / credential | Prevents self-certification | ✅ today |
| Nobody grants permissions they do not hold | Prevents privilege escalation | ✅ today |
| Nobody revokes their own access | Accountability | ✅ today |
| Prescriber ≠ verifying pharmacist for the same order | Medication safety (spec 4.13) | Planned (P4) |
| High-alert doses need an independent second nurse | Medication safety (spec 4.14) | Planned (P4) |
| Lab result entry ≠ validation where policy requires | Result accuracy (spec 4.15) | Planned (P4) |
| Signed notes are never overwritten; amendments keep the original | Legal record (spec 4.8) | Planned (P2) |
| Break-glass access requires a reason and is reviewed afterwards | Emergency care vs privacy (spec 13.2) | Planned (P2) |
| Every "Permission denied" is recorded with its reference number | Traceability (HIMS-UI-002) | ✅ today |
| Privileged roles must sign in with two-factor (authenticator code); nobody can reset their own two-factor | A stolen password alone cannot change hospital settings or access (spec 13.1) | ✅ today (HIMS-IAM-005) |
| Suspending, terminating or deactivating someone signs them out of every device at once (sessions deleted, recorded as `auth.sessions.ended`) | Access ends the moment employment ends (spec 13.2, 13.5) | ✅ today (HIMS-IAM-006) |
| A signed-in user with no role sees a welcome page; the visit is recorded as `access.none_assigned` with the reference shown on screen | Admins can see who is waiting for access (HIMS-UI-002) | ✅ today |

---

## 10. India vs US: key differences

| Topic | India | US |
|---|---|---|
| Doctor training | MBBS → MD/MS/DNB → DM/MCh/DrNB | College → MD/DO → Residency → Fellowship → Board certification |
| Doctor titles | JR, SR, Registrar, Consultant, HOD, Medical Superintendent | Intern, Resident, Fellow, Attending, Chief, Chair, CMO |
| Advanced practice | Not common outside nursing education | NP, PA, CRNA, CNM widely used |
| Nursing ladder | ANM → GNM/B.Sc. Staff Nurse → Sister → Supervisor → Superintendent | CNA → LPN → RN → Charge → Manager → Director → CNO |
| Support staff | Ward attendant / GDA | Patient Care Technician |
| Theatre staff | OT technician | Surgical technologist (CST) |
| Records | MRD (Medical Records Department) | HIM (Health Information Management) |
| Billing | Billing desk + TPA / insurance desk; government schemes (e.g. Ayushman Bharat) | Revenue cycle, medical coders (ICD-10-CM, CPT), payer claims via clearinghouse |
| Regulators | NMC, INC, PCI, state councils; NABH accreditation | State boards, DEA, CMS; Joint Commission accreditation |
| Privacy law | DPDP Act 2023 | HIPAA |

---

## 11. Decisions needed

| # | Decision | Owner |
|---|---|---|
| 1 | Approve or change the clinical access matrix (section 8), role by role | Medical Director + Nursing Director (clinical governance) |
| 2 | Can Junior Residents / Interns sign notes, or only draft for co-signature? | Medical Director |
| 3 | Which orders need a second-person check (high-alert list)? | Pharmacy & Therapeutics committee |
| 4 | Who may use break-glass, and who reviews it (and how quickly)? | Medical Director + Compliance |
| 5 | Should Head of Department see all patients in the department, or only via treating team? | Medical Director |
| 6 | Hospital-specific titles to add to the designation catalog | HR |
| 7 | Departments to create per branch at go-live | Hospital Administrator |

When these are approved, each clinical feature (Phase 2 onward) adds its permissions to the catalog
(`apps/access_control/catalog.py`) and the matching system roles, and this document is updated.

---

## Update 2026-10-28: managing access in the app (HIMS-IAM-013)
* **Staff → a person → Access** shows their roles (where and until when) and lets an administrator
  with `access.assignments.manage` **give access** (role, whole hospital / one facility / one
  department, optional end date for temporary cover, reason) or **remove** it (reason).
* **Access** page: "Who has access" (everyone's current access, filter by role) and "Roles" (what
  each role can do; create and edit **custom** roles with `access.roles.manage`).
* Safety rules (enforced by the server, in the app and the admin console):
  * **Nobody can give themselves access or remove their own**, so another administrator must do it.
  * You can only give permissions you hold yourself at that place (no privilege escalation).
  * System roles cannot be edited; they follow this document's catalog.
  * Editing a custom role changes access for everyone holding it, on their next request; edits
    are versioned (two people cannot overwrite each other) and audited.

## Update 2026-10-28: the auditor's screen (HIMS-AUD-003)
Auditors (`audit.view`) now have an **Audit log** page in the app: search by the reference number
a staff member reports from a "no access" or error screen, by person, area, event or date; open
an event to see before/after values; download a CSV. Searches and downloads are recorded too.
Administrators still cannot open it.

## Update 2026-10-28: accounts for people who are not staff (HIMS-IAM-015)
New permission **`accounts.manage`**: add sign-in accounts for people who are not on the staff
list (external auditors, IT support), switch accounts off or on, reset two-factor and sign people
out. Organization administrators have it; two-factor sign-in is required. The **Accounts** page
lists everyone who can sign in. The hospital's **last** active administrator can never be
switched off, so the hospital cannot lock itself out.

## Update 2026-10-29: licence documents and expiry alerts (HIMS-STAFF-005/006)
* `staff.view`: see the Licence expiry page and open or download staff documents (every
  opening is in the audit log).
* `staff.manage`: upload documents and archive them (with a reason; nothing is deleted).
* Expiry emails go to HR (holders of `staff.credentials.verify` or `staff.manage`) and to the
  person whose licence it is.

## Update 2026-10-30: department heads and catalogs (HIMS-FAC-007, HIMS-STAFF-010)
* **Head of department** is now recorded on each department (Departments → department → Head).
  It must be someone currently posted there. It is a label, not a permission: give the
  "Head of department (HOD)" role on the Access page for the matching access.
* New permission **`catalogs.manage`** (HR / credentialing officer, organization administrator):
  add, rename and switch off job titles, specialties and qualification types on the
  **Job titles & catalogs** page. Standard entries ship with HIMS; codes never change.

## Update 2026-10-30: access reviews and "My sign-ins" (HIMS-IAM-012, HIMS-IAM-016)
* New permission **`access.reviews.manage`** (organization administrator; two-factor required):
  start a periodic access review, keep or remove each person's access, complete or cancel it.
  Removing access in a review ends it at once (same rule as "Remove" on the Access page).
  **Nobody can decide on their own access**: another reviewer must do it.
* New permission **`access.reviews.view`** (auditor, organization administrator): read reviews
  and download them as CSV evidence. The **auditor** role now has `audit.view` and
  `access.reviews.view`.
* A review is due every 90 days (setting `HIMS_ACCESS_REVIEW_INTERVAL_DAYS`); reviewers get one
  email when it is due and one when the review in progress passes its finish-by date.
* The hospital's **last** organization administrator role can no longer be removed (Access page,
  access review or admin console), in addition to the account not being switchable off.
* Everyone can see their own sign-ins on the **Security** page and sign out other devices; no
  permission is needed for your own account.

## Update 2026-10-30: cover arrangements / delegated access (HIMS-IAM-017)

- **Cover** page (menu → Cover): an administrator lets a colleague work with some or all of a
  person's own access for up to 30 days, e.g. during leave, with a reason. It starts now or on a
  later day and ends by itself. Both people are emailed and see it on their Security page.
- The lent access is a time-limited copy of each role at the same place (whole hospital,
  facility or department), so it follows the same permission rules, and privileged roles still
  need two-factor sign-in. Everything is recorded under the covering person's own name.
- Safety: nobody arranges cover for themselves; you can only lend what you hold yourself; auditor
  access is never lent; lent access cannot be lent on and never counts as a hospital
  administrator; it ends early when the original role is removed or either account is switched off.
- Not yet: clinical delegation (patients, orders, signing) needs clinical governance decisions
  (HIMS-IAM-018); emergency "break-glass" access stays 🔒 CLIN.
- Design: [cover-arrangements.md](../architecture/data-architecture/cover-arrangements.md).
