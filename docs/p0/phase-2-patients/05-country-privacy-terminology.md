# 05 Country rules, privacy and terminology (P0-G, P0-H)

DRAFT. **This is an engineering proposal, not legal advice.** Spec 26.7: qualified counsel must
confirm the India (DPDP Act 2023 and DPDP Rules 2025, ABDM, Aadhaar rules) and US (HIPAA, state
law) points below **before real patient data is entered**. Each item marked **[LEGAL]** is a
question for them.

## 1. Data held in Phase 2

| Data | Why it is needed | Sensitivity |
|---|---|---|
| Name, DOB/age, sex, contacts, address | Identify the patient, reach them, avoid mix-ups | Restricted (personal) |
| Guardian/next of kin, emergency contact | Minors, emergencies | Restricted |
| ID numbers (masked/encrypted) | Avoid duplicates; link to national IDs later | Restricted |
| Appointments, visits | Run the OPD; reveal which specialty a person sees | Clinical |
| Vitals, allergies, diagnoses, notes, reported medicines | Care | Clinical (PHI) |
| Who opened which chart | Accountability (spec 13.4) | Restricted (audit) |

Not collected in Phase 2: photo (D25), religion/caste, income, biometrics, full Aadhaar (D6),
SSN (D7), race/ethnicity (US: optional later if a payer or report requires it **[PO]**).

## 2. India

| Topic | Proposal | Status |
|---|---|---|
| Privacy notice and consent (DPDP) | At registration, front desk confirms the notice was given (printed/displayed, in the patient's language) and records "agreed to processing for care" (D9). Separate yes/no for SMS and email. Consent withdrawal recorded with date; care records are still kept as legally required | **[LEGAL]** wording, languages, minors (parent's consent), legitimate-use basis for treatment |
| Aadhaar | Never store the full number; only the last 4 digits, typed by staff, as a reference (D6). No Aadhaar-based authentication in HIMS | **[LEGAL]** confirm |
| ABHA (ABDM) | Phase 2 stores an ABHA number/address as "not verified". Creating or verifying ABHA, linking records and consent-based sharing (ABDM milestones) need ABDM sandbox registration and certification: a Phase 6 project | 🔒 PO decision + ABDM registration |
| Phone numbers | Often shared in a family: never used alone to identify a patient (part 01 §3) | — |
| Names | Many patients have one name; family name optional; any script accepted (D26) | — |
| Minors | Under 18: guardian recorded **[DR]**; consent by guardian **[LEGAL]** | **[LEGAL]** |
| Data location | Indian deployment and backups stay in India (separate database already, ADR-003); region chosen with AWS (🔒 AWS) | **[LEGAL]** confirm requirement |
| Breach notification | Incident runbook with DPDP Board / affected people notification steps | **[LEGAL]** before go-live |

## 3. United States

| Topic | Proposal | Status |
|---|---|---|
| HIPAA Privacy Rule | Notice of Privacy Practices acknowledgment recorded at registration (D9); minimum necessary: search results show minimal data, clinical data only for the care relationship (part 04) | **[LEGAL]** |
| HIPAA Security Rule | Already: unique logins, two-factor for privileged roles, automatic sign-out, audit controls incl. chart reads, encryption of identifiers, tamper-evident audit log. Still needed: risk analysis, policies, BAAs with AWS and email/SMS providers | **[LEGAL]** + 🔒 AWS |
| SSN | Not collected (D7) | **[LEGAL]** confirm |
| Sex and gender | Sex at birth required; gender identity and pronouns optional (US Core style) | **[DR]** |
| State laws | Some states have stricter rules (minors' consent, mental health, HIV, substance use). Phase 2 has no special categories; the restricted-record flag is the first tool | **[LEGAL]** list states served |
| Patient right of access | Visit summary print (part 01 §8); full record export is a Phase 6 portal feature | **[LEGAL]** timeline |

## 4. Both countries

- Separate deployment and database per hospital organization: no patient data crosses
  hospitals; no cross-hospital MPI (spec 26.5).
- Logs, traces, emails and URLs never contain clinical data (already enforced; Phase 2 adds tests
  for the new screens).
- Retention: nothing deleted by people; retention periods per country before go-live (D24,
  **[LEGAL]**).
- Restricted records (D23) for VIPs and staff-as-patients.

## 5. Terminology and code systems (P0-H)

| Data | India | US | Source / licence |
|---|---|---|---|
| Diagnoses | ICD-10 (WHO, 2019 edition) | ICD-10-CM (current fiscal year) | WHO ICD-10 licence terms **[LEGAL]**; ICD-10-CM is published by CDC/CMS for public use |
| Vitals | LOINC codes (e.g. 8480-6 systolic BP, 8462-4 diastolic, 8867-4 pulse, 8310-5 temperature, 9279-1 respiratory rate, 59408-5 SpO₂, 8302-2 height, 29463-7 weight, 39156-5 BMI, 72514-3 pain) | same | LOINC: free licence with attribution |
| Units | UCUM (`mm[Hg]`, `Cel`, `kg`, `cm`, `/min`, `%`) | same, shown in °F / lb / in | UCUM: free |
| Allergies | Category + free text in Phase 2; drug allergies coded when the drug catalogue arrives (Phase 4) | same (RxNorm then) | — |
| Clinical findings | SNOMED CT **not** in Phase 2; candidate for Phase 3+ | same | India: national release centre; US: NLM UMLS licence **[LEGAL]** |
| Sex, relationships, languages | Local lists mapped to FHIR value sets | same | — |

Rules (spec 26.8): each coded value stores code system, version and the display text as recorded;
catalogue updates never change past records; retired codes stay readable. FHIR (version and
implementation guides: ABDM's for India, US Core for the US) is chosen in Phase 6 with the
partner; Phase 2 field names are chosen so they map cleanly to FHIR `Patient`, `Appointment`,
`Encounter`, `Observation`, `AllergyIntolerance`, `Condition`.
