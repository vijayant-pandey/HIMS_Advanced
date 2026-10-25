# Hospital Information Management System (HIMS)

## Solution Architecture & Engineering Blueprint

**Document status:** Architecture baseline for detailed discovery and
implementation planning\
**Target markets:** United States and India from day one\
**Deployment model:** AWS cloud; multiple hospital organizations, each
with multiple branches; dedicated deployment and database per hospital
organization\
**Core stack:** React + TypeScript, Django, Django REST Framework,
PostgreSQL, Redis, Celery\
**Insurance integration:** Stedi for supported US payer workflows, plus
provider adapters for other US and Indian insurers/TPAs\
**Scope:** Full hospital operations, clinical care, ICU, surgery,
diagnostics, pharmacy, insurance, claims, remittance, billing,
reconciliation, patient services, security and interoperability

> **Important:** This is a solution architecture blueprint, not a
> substitute for clinical governance, legal advice, security risk
> assessment, payer onboarding, or country-specific regulatory review.
> Clinical rules and workflows must be validated with qualified hospital
> professionals. Compliance obligations depend on the deployment, legal
> entity, data flows, contracts, and applicable law.

------------------------------------------------------------------------

## Table of Contents

1.  [Executive Summary](#1-executive-summary)
2.  [Product Vision and Architectural
    Principles](#2-product-vision-and-architectural-principles)
3.  [Users and Personas](#3-users-and-personas)
4.  [Functional Scope: Major Domains](#4-functional-scope-major-domains)
5.  [Core Clinical and Operational
    Workflows](#5-core-clinical-and-operational-workflows)
6.  [Technical Architecture](#6-technical-architecture)
7.  [Dedicated Deployment and Database
    Strategy](#7-dedicated-deployment-and-database-strategy)
8.  [Django Backend Architecture and Repository
    Layout](#8-django-backend-architecture-and-repository-layout)
9.  [Database Architecture and Data
    Modeling](#9-database-architecture-and-data-modeling)
10. [Concurrency, Transactions and Data
    Integrity](#10-concurrency-transactions-and-data-integrity)
11. [Insurance, Stedi and Revenue
    Cycle](#11-insurance-stedi-and-revenue-cycle)
12. [Healthcare Interoperability
    Standards](#12-healthcare-interoperability-standards)
13. [Security, Privacy and Regulatory
    Governance](#13-security-privacy-and-regulatory-governance)
14. [Redis, Celery and Asynchronous
    Processing](#14-redis-celery-and-asynchronous-processing)
15. [React Frontend Architecture](#15-react-frontend-architecture)
16. [REST API Design](#16-rest-api-design)
17. [AWS Deployment Architecture](#17-aws-deployment-architecture)
18. [Non-Functional Requirements](#18-non-functional-requirements)
19. [Testing and Quality Strategy](#19-testing-and-quality-strategy)
20. [Implementation Roadmap](#20-implementation-roadmap)
21. [First End-to-End Vertical
    Slice](#21-first-end-to-end-vertical-slice)
22. [Architecture Decisions to
    Record](#22-architecture-decisions-to-record)
23. [Operational Readiness
    Checklist](#23-operational-readiness-checklist)
24. [Reference Links](#24-reference-links)
25. [Specification v2: Purpose and Delivery Standard](#25-specification-v2-purpose-and-delivery-standard)
26. [P0: Required Before Building the Affected Domain](#26-p0-required-before-building-the-affected-domain)
27. [P1: Required Before Production Rollout](#27-p1-required-before-production-rollout)
28. [Artifact A: Detailed Data Architecture](#28-artifact-a-detailed-data-architecture)
29. [Artifact B: API and Integration Contracts](#29-artifact-b-api-and-integration-contracts)
30. [Artifact C: AWS Infrastructure and Operations Design](#30-artifact-c-aws-infrastructure-and-operations-design)
31. [Environment Strategy: Local, Development, QA, Staging and Production](#31-environment-strategy-local-development-qa-staging-and-production)
32. [GitHub Tickets, Branching and Promotion Workflow](#32-github-tickets-branching-and-promotion-workflow)
33. [CI/CD Quality Gates and Release Promotion](#33-cicd-quality-gates-and-release-promotion)
34. [Development Purchases and Cloud Cost Strategy](#34-development-purchases-and-cloud-cost-strategy)
35. [Definition of Done and Production Release Gates](#35-definition-of-done-and-production-release-gates)
36. [Open Architecture Decisions and Approval Register](#36-open-architecture-decisions-and-approval-register)

------------------------------------------------------------------------

## 1. Executive Summary

This is not a basic hospital CRUD application. It is a multi-hospital
Hospital Information Management System (HIMS) intended to manage the
full patient lifecycle---from registration and appointment scheduling to
admission, diagnosis, treatment, medication administration, insurance
claims, discharge, billing, and longitudinal medical history.

The platform should support hospitals in the United States and India.
Country-specific workflows must be configurable and isolated behind
country, payer, regulatory, and integration boundaries rather than mixed
into shared business logic.

### Confirmed architectural direction

-   **Frontend:** React + TypeScript.
-   **Backend:** Django + Django REST Framework (DRF).
-   **Primary database:** PostgreSQL.
-   **Caching and coordination:** Redis.
-   **Background processing:** Celery.
-   **Cloud:** AWS.
-   **Initial architecture style:** Modular monolith with asynchronous
    workers, not microservices everywhere.
-   **Hospital tenancy:** Multiple hospital organizations, each with
    multiple branches.
-   **Isolation model:** Dedicated deployment and dedicated database for
    each hospital organization.
-   **Market scope:** India and the US from day one.
-   **Clinical scope:** Full hospital scope, including ICU, surgery,
    nursing, pharmacy, lab, radiology and diagnostics.
-   **Financial scope:** Full revenue cycle, including eligibility,
    authorization, claims, remittance, denial management, payment
    posting and reconciliation.
-   **US insurance:** Stedi for supported workflows, with other
    payer/clearinghouse adapters as required.
-   **India insurance:** Insurer-, TPA- and government-scheme-specific
    adapters as required.

### Central architectural principle

**Design for clinical safety, data isolation, auditability, and
regulatory compliance before optimizing for feature count.**

In healthcare, a duplicate medication order, incorrect bed assignment,
missing allergy, or claim sent with incorrect patient information can
have consequences far beyond a typical software defect.

------------------------------------------------------------------------

## 2. Product Vision and Architectural Principles

The system is composed of interconnected business domains sharing a
consistent patient identity, clinical record, operational state and
financial foundation.

### 2.1 Logical platform view

```text
                         +----------------------------------+
                         |   HOSPITAL OPERATIONS PLATFORM   |
                         +----------------------------------+
                                         |
                 +-----------------------+-----------------------+
                 |                       |                       |
                 v                       v                       v
       +-------------------+   +-------------------+   +-------------------+
       | Patient & Clinical|   | Inpatient         |   | Medication &      |
       | Care              |   | Operations        |   | Diagnostics       |
       +-------------------+   +-------------------+   +-------------------+
                 |                       |                       |
                 +-----------------------+-----------------------+
                                         |
                                         v
                         +----------------------------------+
                         |     SHARED PLATFORM SERVICES     |
                         | Identity, access, audit, events, |
                         | integrations and observability   |
                         +----------------------------------+
                                         |
             +---------------------------+---------------------------+
             |             |             |             |             |
             v             v             v             v             v
       +----------+  +----------+  +----------+  +----------+  +------------+
       |PostgreSQL|  |  Redis   |  |  Celery  |  |  Object  |  | Integration|
       | source of|  | cache /  |  | workers  |  | storage  |  | gateway    |
       | truth    |  | broker*  |  |          |  |          |  |            |
       +----------+  +----------+  +----------+  +----------+  +------------+

       *Redis is not the authoritative store for clinical or financial state.
```

### 2.2 Architectural principles

1.  **Clinical correctness first.** Critical clinical actions must have
    explicit state transitions, validation, authorization and audit
    trails.
2.  **A patient is not an encounter.** A patient has a longitudinal
    identity; encounters and admissions represent episodes of care.
3.  **An order is not an outcome.** A medication order is distinct from
    dispensing and administration; a lab order is distinct from a
    result.
4.  **Strong consistency for critical writes.** Bed assignment,
    inventory movements, medication administration, signed notes,
    billing and payment posting require well-defined transactional
    guarantees.
5.  **Auditability by design.** Sensitive reads and writes may require
    auditable events, not just ordinary application logs.
6.  **Dedicated hospital isolation.** Each hospital organization gets a
    dedicated deployment and database. Branches are represented within
    that organization's environment.
7.  **Country-specific adapters.** US and Indian payer,
    interoperability, consent, tax and regulatory differences must not
    leak throughout the domain model.
8.  **Modular monolith first.** Keep strong domain boundaries in one
    Django codebase until workload, ownership or reliability needs
    justify service extraction.
9.  **PostgreSQL is authoritative.** Redis is not the source of truth
    for clinical, inventory, billing or financial state.
10. **External systems fail.** Integrations require timeouts,
    idempotency, retry policies, reconciliation and manual exception
    handling.
11. **Security is end-to-end.** Isolation must apply to APIs, background
    jobs, caches, documents, exports, logs and operational tools.
12. **Clinical workflows need clinical owners.** Doctors, nurses,
    pharmacists, lab professionals and administrators must validate
    workflows and acceptance criteria.

### 2.3 Logical subsystems

-   Hospital and facility administration.
-   Patient identity and master patient index.
-   Appointment and queue management.
-   Encounters and electronic health records.
-   Admission, discharge and transfer (ADT).
-   Beds, rooms and ward operations.
-   Nursing, observations and daily care.
-   Medication catalog, prescribing, pharmacy and eMAR/MAR.
-   Laboratory and diagnostic workflows.
-   Radiology, PACS and DICOM integration.
-   Surgery, operating rooms, anesthesia and ICU.
-   Diet, kitchen and meal delivery.
-   Insurance, eligibility and prior authorization.
-   Billing, claims, remittance, payment posting and reconciliation.
-   Procurement, inventory and accounting integration.
-   Patient portal, documents, consent and notifications.
-   Audit, compliance, analytics and reporting.

------------------------------------------------------------------------

## 3. Users and Personas

  -----------------------------------------------------------------------
  User                                Primary responsibilities
  ----------------------------------- -----------------------------------
  Hospital owner / organization       Organization setup, branches,
  administrator                       policies and operational oversight

  Hospital administrator              Departments, staff, configuration
                                      and dashboards

  Medical director / department head  Clinical governance, staff
                                      assignments and approvals

  Doctor / consultant                 Consultations, diagnoses, orders,
                                      treatment plans and discharge

  Nurse / nursing supervisor          Observations, medication
                                      administration, nursing notes and
                                      handovers

  Pharmacist                          Medication verification,
                                      dispensing, stock and controlled
                                      inventory

  Laboratory technician               Specimen collection, processing,
                                      results and validation

  Radiologist                         Imaging workflow, interpretation
                                      and signed reports

  Dietitian / kitchen staff           Diet orders, meal preparation and
                                      delivery

  Bed manager / ward clerk            Bed availability, transfers,
                                      cleaning and admissions

  Insurance / billing team            Eligibility, authorizations,
                                      claims, denials and reconciliation

  Medical records team                Record completion, release of
                                      information and corrections

  Patient / caregiver                 Portal, appointments, reports,
                                      bills and authorized access

  Auditor / compliance officer        Access history, audit review and
                                      policy compliance

  Procurement / inventory staff       Purchasing, receipts, stock
                                      movements and vendor workflows

  Operating-room / anesthesia team    Surgical scheduling, safety checks,
                                      anesthesia and operative records
  -----------------------------------------------------------------------

Roles are starting points. A real hospital may require many additional
roles and tightly scoped permissions.

------------------------------------------------------------------------

## 4. Functional Scope: Major Domains

The following is the target-state functional scope. It should be
delivered incrementally, not all in the first release.

### 4.1 Hospital and branch management

-   Hospital organization, legal entity, branches, facilities and
    locations.
-   Country, state, time zone, currency, locale, tax configuration and
    working hours.
-   Hospital-specific numbering schemes for patient IDs, encounters,
    invoices and claims.
-   Departments, wards, floors, rooms, beds and operating rooms.
-   Hospital logo, templates, consent forms, billing rules and
    notification settings.
-   Group-level reporting where explicitly authorized.
-   Per-organization dedicated deployment and database.
-   Configuration and feature flags by organization, country and
    facility.

### 4.2 Department management

-   General Medicine, Cardiology, Neurology, Pediatrics, Orthopedics,
    Oncology, Surgery, ICU, Emergency, Radiology, Pathology, Pharmacy,
    Physiotherapy and other departments.
-   Department head, staff, services, equipment, operating hours and
    service pricing.
-   Department-specific appointment slots, admission criteria and
    escalation rules.
-   Transfers and interdepartmental consultations.
-   Department-level dashboards and performance reports.

### 4.3 Staff and credential management

-   Doctors, nurses, pharmacists, lab technicians, radiologists,
    administrators and support staff.
-   Qualifications such as MBBS, MD, MS, DM, DNB, specialty, institution
    and graduation year.
-   Professional license/registration number, issuing authority,
    verification status and expiry.
-   Designation, specialty, subspecialty, department assignments and
    clinical privileges.
-   Employment status, joining/leaving dates, shift schedules, leave and
    on-call rotations.
-   Credential document uploads, approval workflow and expiry alerts.

A doctor's academic degree, professional designation, specialty and
permission to perform a procedure are separate concepts. Do not store
them in one text field.

### 4.4 Identity, authentication and access control

-   Hospital administrator onboarding and organization verification.
-   User invitation, account activation, password reset, MFA and session
    management.
-   Role-based and attribute-based access control.
-   Facility-, department-, patient- and encounter-level restrictions.
-   Temporary emergency access with reason and additional auditing.
-   Account suspension, termination, delegated access and periodic
    access reviews.

### 4.5 Patient registration and Master Patient Index (MPI)

-   Demographics, contact details, address and emergency contacts.
-   Guardian, parent, caregiver and next-of-kin relationships.
-   Identity document references under country-specific rules.
-   Patient identifiers, medical record number (MRN), external
    identifiers and portal account.
-   Duplicate patient detection and controlled record merging.
-   Name changes, demographic corrections and identity verification.
-   Consent, communication preferences and language.
-   History, prior admissions, allergies, diagnoses, medications and
    procedures.

Use a generated internal UUID as the immutable database identity. MRN is
a hospital-facing identifier and should not be the primary database key.

### 4.6 Appointments and outpatient department (OPD)

-   Doctor availability, appointment calendars, specialty and service
    selection.
-   Booking, rescheduling, cancellation and waitlists.
-   Walk-in registration and token/queue management.
-   Check-in, consultation start, completion and no-show tracking.
-   Telemedicine support where required.
-   Pre-visit insurance eligibility checks.
-   Reminders through email, SMS and supported messaging providers.
-   Follow-up appointments and referral management.

### 4.7 Encounter and admission management

An encounter represents an episode of care; it is not the same thing as
the patient record.

Support:

-   Outpatient, inpatient, emergency, observation, day-care and
    telehealth encounters.
-   Admission request, approval and admitting consultant.
-   Admission diagnosis, reason for admission, expected length of stay
    and initial care plan.
-   Responsible doctor, attending team, admitting department and current
    location.
-   Admission, transfer, discharge and readmission history.
-   Patient status board showing active admissions and pending tasks.
-   Leave of absence, against-medical-advice discharge and death
    workflows where applicable.

### 4.8 Electronic Health Record (EHR/EMR)

-   Presenting complaints and history of present illness.
-   Medical, surgical, family, social and medication history.
-   Allergies and adverse drug reactions.
-   Vitals, examinations, clinical notes and progress notes.
-   Diagnoses, problem lists, care plans and referrals.
-   Procedure notes, operative notes and anesthesia records.
-   Consultations, discharge summaries and follow-up instructions.
-   Signed, amended, corrected and addended records.
-   Longitudinal medical timeline across encounters.
-   Clinical templates by specialty with appropriate mandatory fields.

Do not silently overwrite signed clinical notes. Corrections should
preserve the original version, author, timestamp, reason and amended
version.

### 4.9 Nursing and daily patient care

-   Shift handover, nursing assessments and nursing care plans.
-   Scheduled observations and vital-sign charts.
-   Pain scores, fluid intake/output, weight and relevant monitoring.
-   Daily doctor rounds and progress updates.
-   Fall-risk, pressure-injury and other configured risk assessments.
-   Wound care, catheter care, mobility assistance and hygiene tasks.
-   Procedure preparation, patient transport and escalation.
-   Nursing task lists, overdue tasks and shift-specific
    responsibilities.
-   Clinical observation escalation based on hospital-defined
    thresholds.

Every observation should record who entered it, when it was measured,
value, unit, method where applicable, and correction history.

### 4.10 Bed, room and ward management

Model the hierarchy:

`Hospital → Facility → Building → Floor → Ward/Unit → Room → Bed`

Capabilities:

-   Bed inventory and types: general, private, semi-private, ICU, NICU,
    isolation and others.
-   Real-time availability board.
-   Bed reservations and admission allocation.
-   Occupied, reserved, cleaning, maintenance, blocked and
    out-of-service states.
-   Admission, transfer and discharge coordination.
-   Gender, age, specialty, infection-control and isolation constraints.
-   Bed turnover, housekeeping requests and cleaning sign-off.
-   Bed charges, room-category changes and utilization reporting.
-   Transfer history with start/end times and responsible staff.
-   Prevention of concurrent active assignments to the same bed.

Bed allocation is a time-bounded assignment, not just a string on an
admission.

### 4.11 Diet, kitchen and food management

-   Dietitian assessment and approved diet plan.
-   Normal, diabetic, renal, cardiac, liquid, soft, fasting/NPO and
    hospital-configured diets.
-   Food allergies, intolerances, religious/cultural preferences and
    texture restrictions.
-   Breakfast, lunch, dinner and scheduled snacks.
-   Patient-specific meal orders tied to active admission.
-   Menu planning, recipes, ingredients, kitchen inventory and
    procurement.
-   Meal preparation, tray identification, ward delivery and
    confirmation.
-   Meal refused, missed, withheld or modified, including reason.
-   Intake monitoring where clinically indicated.
-   Diet changes after doctor or dietitian order.
-   Kitchen workload and meal cost reports.

Do not treat a generic dietary preference as a clinically authorized
diet order. Clinical restrictions require appropriate authorization.

### 4.12 Housekeeping, equipment and transport

-   Room and bed cleaning workflows.
-   Disinfection and isolation-room clearance.
-   Equipment inventory, maintenance and calibration.
-   Wheelchair, stretcher and patient transport requests.
-   Internal service requests and escalation.
-   Oxygen equipment and other resource allocation according to hospital
    procedures.

### 4.13 Pharmacy and medication management

-   Drug catalog: generic name, brand, strength, dosage form, route and
    units.
-   Prescriptions and medication orders linked to patient and encounter.
-   Dose, frequency, route, duration, start/end times and administration
    instructions.
-   Allergy checking, duplicate therapy and clinically appropriate
    interaction checks.
-   Prescriber verification and pharmacist review.
-   Medication dispensing and patient-specific supply.
-   Lot/batch numbers, expiry dates, manufacturer and supplier.
-   Stock transfers, purchase orders, goods receipts and returns.
-   Inventory reservations, dispensing, returns, wastage and
    adjustments.
-   Ward stock, emergency stock, controlled-drug handling and
    reconciliation.
-   Substitution rules and formulary restrictions.
-   Expiry alerts, low-stock alerts and recall handling.
-   Pharmacy billing and dispensing history.

### 4.14 Medication Administration Record (MAR/eMAR)

Keep the prescription and actual administration event separate.

If a doctor orders a medicine three times a day, record each scheduled
administration and whether it was administered, withheld, refused,
delayed, omitted or not applicable.

Record:

-   Patient, encounter, medication order and scheduled dose.
-   Actual administered dose, route, time and administering
    professional.
-   Relevant pre-administration checks and observations.
-   Reason for missed, delayed or withheld dose.
-   Medication barcode verification where deployed.
-   High-alert medication and independent double-check workflows when
    required.
-   PRN medication indication, administration and reassessment.
-   Corrections and late documentation without erasing the original
    event.

### 4.15 Laboratory Information System (LIS integration)

-   Lab test catalog, panels, specimen requirements and reference
    ranges.
-   Test orders, collection labels, accession numbers and specimen
    tracking.
-   Collection, receipt, rejection, processing and completion states.
-   Instrument integration and quality-control workflows.
-   Result entry, validation, critical-result escalation and
    acknowledgment.
-   Corrected reports with version history.
-   Lab turnaround-time monitoring.
-   Billing, insurance coding and external laboratory integration.

### 4.16 Radiology and imaging

-   Imaging orders, scheduling and modality worklists.
-   CT, MRI, X-ray, ultrasound and other modalities.
-   Contrast and procedure preparation documentation.
-   Image storage and retrieval through PACS.
-   DICOM integration and imaging metadata.
-   Radiologist reporting, preliminary/final status and critical
    findings.
-   Report correction and finalization history.
-   Image/report access permissions and retention policies.

### 4.17 Procedures, surgery, anesthesia and ICU

-   Procedure requests and approvals.
-   Operating-room scheduling and resource allocation.
-   Preoperative assessments, consent and safety checklists.
-   Anesthesia records, intraoperative documentation and recovery.
-   Implant, device and consumable tracking.
-   ICU bed management, observations, ventilator-related documentation
    and care plans.
-   Critical event documentation and clinical escalation.
-   Postoperative orders, follow-up and transfer to the ward.

These workflows must be developed with clinical experts and validated
against the hospital's actual procedures.

### 4.18 Insurance and payer management

Build a provider-side insurance subsystem supporting multiple policies,
payers and country-specific rules.

-   Payer, insurer, plan and network configuration.
-   Policyholder/subscriber and dependent relationships.
-   Member ID, group number, policy number and effective dates.
-   Primary, secondary and other coverage coordination.
-   Eligibility and benefit verification.
-   Coverage limitations, copays, deductibles and coinsurance.
-   Referral and prior-authorization requirements.
-   Preauthorization requests, documents, approvals and denials.
-   Admission notifications and continuing-stay authorizations.
-   Estimated coverage versus actual adjudication.
-   Claim generation, submission, acknowledgment and status tracking.
-   Denial management, appeals, resubmissions and corrected claims.
-   Remittance advice, payment posting and reconciliation.
-   Patient responsibility and final settlement.

Eligibility verification is not a guarantee of payment. Authorization,
medical necessity, benefit limits, network status, coding and final
adjudication can affect the result.

### 4.19 Billing and revenue cycle management

-   Service catalog and configurable price lists.
-   Consultation, bed, procedure, laboratory, imaging, pharmacy and
    miscellaneous charges.
-   Charge capture linked to services actually delivered.
-   Packages, discounts, deposits, refunds and credit notes.
-   Interim inpatient bills and final discharge bills.
-   Insurance-covered, insurer-pending and patient-payable balances.
-   Tax and invoice rules appropriate to country and entity.
-   Receipts, payment methods, refunds and cash reconciliation.
-   Outstanding balances, write-offs and bad-debt workflows.
-   Financial reporting, revenue reconciliation and audit trails.

Do not store only one `paid` flag on an invoice. Use invoice lines,
payments, allocations, refunds, adjustments and payer remittances
because one invoice may be settled by several parties over time.

### 4.20 Procurement, inventory and accounting

-   Suppliers, purchase requisitions, purchase orders and approvals.
-   Goods receipt and supplier invoices.
-   Central warehouse, department stores and pharmacy stores.
-   Inventory movements, stock valuation and consumption.
-   Equipment and fixed-asset registers.
-   Vendor payments and outstanding liabilities.
-   General ledger integration, cost centers and financial exports.
-   Budgeting and departmental expense reports.

Accounting rules should be reconciled with qualified finance
professionals; the HIMS should not invent accounting rules
independently.

### 4.21 Patient and caregiver portal

-   Registration, secure sign-in and identity verification.
-   Appointments and follow-up scheduling.
-   Access to released reports, prescriptions and discharge summaries.
-   Bills, receipts and payment history.
-   Insurance information and pre-visit forms.
-   Consent management, communication preferences and authorized
    caregivers.
-   Secure messaging and service requests where supported.

### 4.22 Medical records, documents and consent

-   Scanned documents, referrals, external reports and signed forms.
-   Versioning, document categorization, retention and authorized
    release.
-   Electronic signatures and signature verification where legally
    supported.
-   Consent for treatment, procedures, data sharing and portal access.
-   Release-of-information workflow.
-   Patient-requested corrections and access to records.

### 4.23 Notifications and task orchestration

-   Admission and discharge notifications.
-   Medication due alerts and overdue nursing tasks.
-   Critical lab results and escalation acknowledgments.
-   Insurance authorization expiry and claim-status changes.
-   Bed-cleaning and equipment-maintenance tasks.
-   Staff credential expiration.
-   Email, SMS and supported messaging integrations.
-   Notification delivery status, retries and escalation rules.

### 4.24 Reporting and operational analytics

-   Occupancy, admissions, transfers and discharge trends.
-   Average length of stay and bed turnover.
-   Appointment waiting time and doctor utilization.
-   Medication errors, missed administrations and inventory expiry.
-   Laboratory turnaround times and critical-result acknowledgment.
-   Insurance eligibility failures, authorization delays and claim
    denials.
-   Revenue, outstanding receivables and payment reconciliation.
-   Patient safety, clinical quality and compliance indicators.

### 4.25 Audit, compliance and governance

-   Who viewed, created, changed, signed, exported or disclosed a
    record.
-   Before/after values for sensitive changes where appropriate.
-   Break-glass access, reason, approver where required and subsequent
    review.
-   Login history, failed access attempts and privileged actions.
-   Consent and data-sharing records.
-   Retention, legal holds, export controls and deletion restrictions.
-   Security incident investigation and audit-log export.

------------------------------------------------------------------------

## 5. Core Clinical and Operational Workflows

Feature lists are not sufficient. The complexity comes from making
modules interact correctly.

### 5.1 Patient admission to discharge

```text
[Patient Registration / MPI]
              |
              v
[Appointment or Emergency Visit]
              |
              v
     [Clinical Assessment]
              |
              v
          +------------------+
          | Admission needed?|
          +------------------+
             | Yes      | No
             v          v
    [Admission Request] [OPD Treatment / Follow-up]
             |
             v
       [Bed Allocation]
             |
             v
 [Insurance / Financial Clearance]
             |
             v
     [Admission Confirmed]
             |
             v
    [Doctor Orders and Care Plan]
             |
             v
 [Nursing, Medication, Diet, Lab and Imaging]
             |
             v
 [Daily Review and Discharge Readiness]
             |
             v
 [Discharge Orders and Summary]
             |
             v
  [Final Bill and Claim Preparation]
             |
             v
   [Bed Cleaning and Release]
             |
             v
 [Follow-up and Longitudinal Record]
```

This is conceptual, not a rule that every admission must wait for
insurance clearance. Emergency and urgent-care policies must support
treatment before administrative clearance when required by law and
clinical policy.

Key engineering rules:

-   A patient may have many encounters but should not receive a new
    identity for every visit.
-   An admission has a lifecycle and responsible clinical team.
-   Bed assignment is a time-bounded allocation, not just a string on
    the admission.
-   Discharge coordinates clinical, operational and financial workflows.
-   The patient's medical record persists after discharge.
-   Billing or insurance integration failure must not erase or corrupt
    clinical records.

### 5.2 Medication order to administration

```text
[Doctor creates medication order]
                 |
                 v
       [Clinical validation]
                 |
                 v
[Pharmacist review, if required]
                 |
                 v
 [Dispensing / Medication supply]
                 |
                 v
          [MAR schedule]
                 |
                 v
          [Due-dose task]
                 |
                 v
[Patient and medication verification]
                 |
                 v
       +---------------------------+
       | Is administration suitable?|
       +---------------------------+
             | Yes          | No
             v              v
  [Record administered dose] [Record withheld / refused / omitted]
             |              |
             v              v
   [Monitor patient response] [Escalate if required]
             |              |
             +------+-------+
                    |
                    v
           [Medication history]
```

An order does not mean a medicine was dispensed or administered. Those
are distinct clinical events.

### 5.3 Insurance eligibility and claim lifecycle

```text
+------------------------------------+
| Capture payer and policy details   |
+------------------------------------+
                  |
                  v
+------------------------------------+
| Eligibility request                |
+------------------------------------+
                  |
                  v
+------------------------------------+
| Payer / clearinghouse response     |
+------------------------------------+
                  |
                  v
+------------------------------------+
| Store raw response and normalized  |
| result                             |
+------------------------------------+
                  |
                  v
+------------------------------------+
| Review coverage and benefit details|
+------------------------------------+
                  |
                  v
+------------------------------------+
| Authorization workflow, if needed  |
+------------------------------------+
                  |
                  v
+------------------------------------+
| Deliver and document services      |
+------------------------------------+
                  |
                  v
+------------------------------------+
| Capture billable charges            |
+------------------------------------+
                  |
                  v
+------------------------------------+
| Generate and validate claim        |<--------------------------+
+------------------------------------+                           |
                  |                                              |
                  v                                              |
+------------------------------------+                           |
| Submit claim                       |                           |
+------------------------------------+                           |
                  |                                              |
                  v                                              |
+------------------------------------+                           |
| Acknowledgment and adjudication    |                           |
+------------------------------------+                           |
                  |                                              |
                  v                                              |
          +------------------+                                   |
          | Claim outcome?    |                                   |
          +------------------+                                   |
             |            |                                       |
      Paid / partial    Denied                                    |
             |            |                                       |
             v            v                                       |
+---------------------+  +-----------------------------+           |
| Post remittance and |  | Investigate, appeal or      |-----------+
| reconcile           |  | correct                     |
+---------------------+  +-----------------------------+
             |
             v
+-------------------------------+
| Close remaining balances      |
+-------------------------------+
```

Eligibility is not a payment guarantee. Authorization, medical
necessity, benefit limits, network status, coding and adjudication can
affect the outcome.

------------------------------------------------------------------------

## 6. Technical Architecture

### 6.1 Recommended architecture style

Start with a **modular monolith and asynchronous workers**, not a large
collection of microservices.

A modular monolith is one deployable Django backend with strong
business-domain boundaries. Split domains into services later when real
workload, team structure or operational needs justify it.

Benefits:

-   Transactional consistency for admissions, beds, medication orders
    and billing.
-   Easier development and debugging.
-   Fewer infrastructure dependencies.
-   Clear domain boundaries without HTTP calls for every internal
    operation.
-   Option to extract insurance integration, notifications, reporting or
    other domains later.

A modular monolith does not mean one enormous `models.py`, a universal
service class or unrestricted APIs. Module boundaries must be enforced
from the beginning.

### 6.2 Technology stack

  --------------------------------------------------------------------------
  Layer                   Recommendation             Reason
  ----------------------- -------------------------- -----------------------
  Frontend                React + TypeScript         Maintainable, type-safe
                                                     clinical workspaces

  UI                      Consistent component       Accessible forms,
                          library such as MUI        tables, dialogs and
                                                     dashboards

  Server state            TanStack Query             Fetching, caching,
                                                     mutations and
                                                     invalidation

  Forms                   React Hook Form + schema   Large, validated
                          validation                 clinical forms

  Backend                 Django + DRF               Mature ORM,
                                                     authentication, admin
                                                     and API ecosystem

  Database                PostgreSQL                 ACID transactions,
                                                     constraints, indexing
                                                     and relational
                                                     integrity

  Async processing        Celery                     Scheduled jobs, retries
                                                     and background work

  Broker                  Redis initially; evaluate  Simpler initial
                          RabbitMQ or managed        deployment versus
                          messaging as needed        durability/routing
                                                     needs

  Cache                   Redis                      Reference data,
                                                     short-lived caches and
                                                     rate-limit counters

  Documents               S3-compatible object       Durable storage without
                          storage                    large binaries in SQL

  API documentation       OpenAPI / drf-spectacular  Contract-driven
                                                     development

  Deployment              Docker + AWS managed       Repeatable builds and
                          services                   controlled scaling

  Observability           OpenTelemetry-compatible   Production debugging
                          tracing, structured logs   
                          and metrics                
  --------------------------------------------------------------------------

### 6.3 Logical component view

```text
[React + TypeScript Portals]
                |
                v
      [CDN / WAF / Load Balancer]
                |
                v
       [Django REST Framework API]
                |
       +--------+-------------------+
       |                            |
       v                            v
[Business Domain Modules]    [Shared Platform Services]
 Patients, encounters,        Identity, access control,
 admissions, beds, nursing,   tenant context, audit,
 medications, diagnostics,    idempotency, integration
 billing, insurance           gateway and outbox
       |                            |
       +-------------+--------------+
                     |
                     v
              [PostgreSQL]
          business data + outbox
                     |
                     v
            [Outbox Dispatcher]
                     |
                     v
               [Celery Broker]
                     |
                     v
              [Celery Workers]
                |           |
                v           v
         [PostgreSQL] [Insurance / Lab /
                        Messaging APIs]

[Django API] ----> [Redis: cache / coordination]
[Django API] ----> [S3: documents / reports]
[API and workers] -> [Logs / Metrics / Traces]
```

### 6.4 Why not microservices initially?

Microservices introduce distributed transactions, service discovery,
network failures, duplicated operational concerns, eventual consistency
and more complicated deployments. A modular Django backend is a safer
starting point for a new product unless team or scale constraints demand
otherwise.

------------------------------------------------------------------------

## 7. Dedicated Deployment and Database Strategy

The selected tenancy model is **multiple hospital organizations, each
with multiple branches, with a dedicated deployment and database for
each organization**.

This differs from a shared-schema, multi-tenant database. It provides
stronger isolation and more flexible per-customer recovery and
configuration, but it increases operational complexity and cost.

### 7.1 Organization and branch hierarchy

``` text
Hospital Organization A
  ├── Dedicated AWS deployment A
  ├── Dedicated PostgreSQL database/cluster A
  ├── Facility A1
  ├── Facility A2
  └── Facility A3

Hospital Organization B
  ├── Dedicated AWS deployment B
  ├── Dedicated PostgreSQL database/cluster B
  ├── Facility B1
  └── Facility B2
```

An organization may own several branches. Branches share the
organization's database and deployment unless a future isolation
requirement justifies per-branch separation.

### 7.2 Recommended deployment control plane

Operate a central, tightly restricted **control plane** that manages
customer provisioning but does not become a shared repository of patient
clinical records.

Control-plane responsibilities:

-   Customer organization onboarding and subscription/entitlement state.
-   Deployment and database provisioning.
-   Per-customer configuration and feature flags.
-   Deployment version tracking and upgrade orchestration.
-   Health checks and operational status.
-   Secrets references, not plaintext secrets.
-   Customer support access requests and approval workflow.
-   Usage and infrastructure-cost reporting using appropriately
    minimized metadata.

Keep patient clinical data inside each hospital's dedicated data plane.
The control plane should not silently gain access to patient records.

### 7.3 Per-hospital data plane

Each hospital deployment should have its own:

-   Django API service and application configuration.
-   Celery worker pools and task queues.
-   PostgreSQL database or dedicated PostgreSQL cluster, according to
    the agreed isolation level.
-   Redis instance or isolated Redis deployment.
-   S3 bucket or strongly isolated storage prefix/access boundary,
    preferably customer-specific buckets where appropriate.
-   Encryption keys and secret references.
-   Logs, metrics and alerting boundaries.
-   Backup and restore procedures.
-   Domain/subdomain and TLS configuration.
-   Integration credentials and network policy.

A dedicated database does not automatically mean a dedicated database
server. Decide whether each hospital needs a dedicated RDS
instance/cluster or a logically dedicated database on a shared managed
cluster based on threat model, contractual commitments, load, cost and
recovery requirements. If the requirement is strict infrastructure-level
isolation, use dedicated instances/clusters as well.

### 7.4 Isolation requirements

-   Authenticate users and resolve the correct hospital environment
    before serving business requests.
-   Never select a database using an untrusted client-provided
    organization ID alone.
-   Validate facility membership and authorization inside the hospital
    environment.
-   Isolate cache keys, task queues, object storage, logs, metrics and
    exports.
-   Keep credentials unique per deployment.
-   Prevent cross-customer access through support tooling and deployment
    automation.
-   Test customer provisioning, deprovisioning, upgrades, backups and
    restores.
-   Define how a hospital's data is exported and securely retired at
    contract termination.
-   Establish a documented process for emergency support access and
    audit it.

### 7.5 Trade-offs

**Advantages**

-   Stronger blast-radius reduction.
-   Independent backup, restore and maintenance windows.
-   Easier customer-specific configuration and integration credentials.
-   Easier alignment with contractual isolation requirements.

**Costs and complexity**

-   Higher infrastructure cost.
-   More deployments, databases, secrets and alerts to manage.
-   Database schema upgrades must be orchestrated across customers.
-   Central reporting across hospitals requires an explicit, authorized
    data pipeline.
-   Disaster recovery and fleet-wide patching require automation.

### 7.6 Cross-hospital reporting

Do not query each hospital's production database directly from a
universal reporting UI. If group reporting is needed, create a governed
analytics pipeline that exports only approved data to a separately
secured analytics environment. Define data minimization, aggregation,
authorization, residency and retention requirements first.

------------------------------------------------------------------------

## 8. Django Backend Architecture and Repository Layout

Organize by business domain, not by a generic `core` app that eventually
contains everything.

``` text
hims/
├── backend/
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── local.py
│   │   │   ├── test.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   ├── celery.py
│   │   └── asgi.py
│   ├── apps/
│   │   ├── organizations/
│   │   ├── identity/
│   │   ├── access_control/
│   │   ├── facilities/
│   │   ├── staff/
│   │   ├── patients/
│   │   ├── appointments/
│   │   ├── encounters/
│   │   ├── admissions/
│   │   ├── beds/
│   │   ├── clinical_records/
│   │   ├── nursing/
│   │   ├── medication_catalog/
│   │   ├── prescriptions/
│   │   ├── medication_administration/
│   │   ├── pharmacy/
│   │   ├── laboratory/
│   │   ├── radiology/
│   │   ├── procedures/
│   │   ├── diet_kitchen/
│   │   ├── insurance/
│   │   ├── billing/
│   │   ├── inventory/
│   │   ├── documents/
│   │   ├── notifications/
│   │   ├── audit/
│   │   ├── reporting/
│   │   └── integrations/
│   ├── common/
│   │   ├── permissions/
│   │   ├── exceptions/
│   │   ├── idempotency/
│   │   ├── outbox/
│   │   └── utilities/
│   ├── tests/
│   ├── manage.py
│   └── requirements/
├── frontend/
│   └── src/
│       ├── app/
│       ├── api/
│       ├── features/
│       │   ├── patients/
│       │   ├── admissions/
│       │   ├── beds/
│       │   ├── medication/
│       │   ├── insurance/
│       │   └── billing/
│       ├── components/
│       ├── layouts/
│       ├── routes/
│       └── types/
├── infrastructure/
│   ├── docker/
│   ├── terraform/
│   └── deployment/
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── security/
│   ├── workflows/
│   └── decisions/
├── docker-compose.yml
└── README.md
```

This is a starting structure, not a requirement to create every app on
day one. Introduce modules as their actual domain boundaries emerge.

### 8.1 Suggested internal app pattern

``` text
patients/
├── models.py
├── selectors.py       # Read/query operations
├── services.py        # Business transactions
├── api/
│   ├── serializers.py
│   ├── views.py
│   ├── permissions.py
│   └── urls.py
├── tasks.py
├── admin.py
├── tests/
└── migrations/
```

Keep business invariants in the domain/service layer and database
constraints. Do not rely on React validation or Django admin forms to
protect critical rules because API clients and background workers can
bypass those interfaces.

------------------------------------------------------------------------

## 9. Database Architecture and Data Modeling

PostgreSQL is the recommended primary database. SQLite may be useful for
isolated tests or prototypes, but PostgreSQL should be used in
development and production to expose real transaction, locking, indexing
and concurrency behavior early.

### 9.1 Conceptual entity relationships

```text
Relationship notation: 1:N = one-to-many; 0:1 = optional one; N:1 = many-to-one.

[ORGANIZATION]
  +-- 1:N --> [FACILITY] -- 1:N --> [DEPARTMENT] -- 1:N --> [STAFF_MEMBERSHIP]
  +-- 1:N --> [STAFF_MEMBERSHIP] -- 1:N --> [STAFF_CREDENTIAL]
  +-- 1:N --> [PATIENT] -- 1:N --> [ENCOUNTER]
  |                              |-- 0:1 --> [ADMISSION]
  |                              |              |-- 1:N --> [BED_ASSIGNMENT] <-- N:1 -- [BED]
  |                              |              +-- 1:N --> [DIET_ORDER] -- 1:N --> [MEAL_DELIVERY]
  |                              |-- 1:N --> [CLINICAL_NOTE]
  |                              |-- 1:N --> [MEDICATION_ORDER] -- 1:N --> [MEDICATION_ADMINISTRATION]
  |                              |-- 1:N --> [LAB_ORDER] -- 1:N --> [LAB_RESULT]
  |                              +-- 1:N --> [CHARGE] -- 1:N --> [CLAIM_LINE] <-- N:1 -- [CLAIM]
  |                                                                                   |
  |                                                                                   +-- 1:N --> [CLAIM_EVENT]
  +-- (other organization-owned records)

[FACILITY] -- 1:N --> [DEPARTMENT]
[PATIENT]  -- 1:N --> [INSURANCE_POLICY]

Notes:
- A patient can have many encounters and many insurance policies.
- An encounter may have zero or one associated admission in this conceptual view.
- An admission can have many time-bounded bed assignments and diet orders.
- A bed can have many historical assignments, but must not have conflicting active assignments.
- A charge can be represented on one or more claim lines according to the billing model.
- The production ERD needs explicit foreign keys, relationship constraints, history tables,
  authorization records, documents, workflow states and financial transactions.
```

This is a conceptual ERD. Production design will require more entities
for many-to-many relationships, histories, authorizations, documents,
workflow states and financial transactions.

### 9.2 Suggested table groups

  -----------------------------------------------------------------------
  Domain                              Representative tables
  ----------------------------------- -----------------------------------
  Organization                        `organizations`, `facilities`,
                                      `departments`, `wards`, `rooms`,
                                      `beds`

  Identity                            `users`, `staff_memberships`,
                                      `roles`, `permissions`,
                                      `staff_credentials`

  Patient                             `patients`, `patient_identifiers`,
                                      `patient_contacts`,
                                      `patient_relationships`,
                                      `patient_merges`

  Clinical                            `encounters`, `diagnoses`,
                                      `allergies`, `clinical_notes`,
                                      `observations`, `care_plans`

  Inpatient                           `admissions`, `bed_assignments`,
                                      `patient_transfers`,
                                      `nursing_tasks`, `handover_records`

  Medication                          `medications`, `medication_orders`,
                                      `dispense_records`,
                                      `administration_events`

  Laboratory                          `lab_orders`, `specimens`,
                                      `lab_results`, `diagnostic_reports`

  Diet                                `diet_orders`, `menus`,
                                      `meal_orders`, `meal_deliveries`

  Insurance                           `payers`, `insurance_policies`,
                                      `eligibility_checks`,
                                      `authorizations`, `claims`,
                                      `claim_events`

  Billing                             `invoices`, `invoice_lines`,
                                      `payments`, `payment_allocations`,
                                      `refunds`, `remittances`

  Platform                            `audit_events`, `consents`,
                                      `documents`, `outbox_events`,
                                      `idempotency_records`
  -----------------------------------------------------------------------

### 9.3 Key modeling decisions

**Patient identity versus encounter**

A patient is a person in the system. An encounter is a particular
episode of care. An admission is an inpatient episode associated with an
encounter or a defined episode-of-care model. Do not store all history
in one JSON field on `Patient`.

**Clinical facts versus clinical events**

A current allergy list is useful for fast access, but retain who
recorded an allergy, when it was recorded, verification state and
subsequent corrections/resolution.

**Current state versus historical state**

The patient's current ward should be easy to query, but transfer history
must be retained. The same applies to staff assignments, medication
orders, authorization status and policy coverage.

**Reference catalogs versus transactions**

A medication catalog describes the drug. A prescription orders it for a
patient. A dispense record describes supply. A medication administration
records what actually happened. Each has a separate lifecycle.

**Relational integrity**

Use foreign keys, uniqueness constraints, check constraints, appropriate
indexes and transactional service methods. Use `PROTECT` or restricted
deletion for clinically significant historical data rather than casual
cascading deletes.

**Avoid premature JSON modeling**

JSONB is useful for flexible metadata, external API payload snapshots
and variable document structures. Core patient identity, admission
status, medication orders, claims, invoices and inventory movements
should remain relationally modeled.

### 9.4 Doctor and qualification data model

A doctor may have multiple qualifications, credentials and department
assignments.

``` text
StaffMember
    id
    organization_id
    user_id
    employee_number
    employment_status

StaffDepartmentAssignment
    staff_id
    department_id
    designation
    specialty_id
    valid_from
    valid_until

StaffQualification
    staff_id
    qualification_type
    institution
    year_awarded
    verification_status

StaffCredential
    staff_id
    credential_type
    registration_number
    issuing_authority
    valid_from
    expires_at
    verification_status
```

Use a controlled qualification catalog. A professional registration and
scope of practice need country-specific verification rules.

------------------------------------------------------------------------

## 10. Concurrency, Transactions and Data Integrity

### 10.1 Bed allocation race condition

Two admission clerks may attempt to allocate the same bed
simultaneously. Both can read `AVAILABLE` before either saves the
assignment. Without concurrency controls, both requests might succeed.

Use a database transaction, lock the bed row, verify its state and
create the assignment atomically. Also enforce an appropriate database
constraint preventing overlapping active assignments.

Illustrative Django example:

``` python
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.beds.models import Bed
from apps.admissions.models import BedAssignment


@transaction.atomic
def allocate_bed(*, bed_id, admission):
    bed = Bed.objects.select_for_update().get(
        id=bed_id,
        organization_id=admission.organization_id,
    )

    if bed.status != Bed.Status.AVAILABLE:
        raise ValidationError("Bed is not available.")

    if BedAssignment.objects.filter(
        bed=bed,
        ended_at__isnull=True,
    ).exists():
        raise ValidationError("Bed already has an active assignment.")

    assignment = BedAssignment.objects.create(
        organization_id=admission.organization_id,
        bed=bed,
        admission=admission,
    )

    bed.status = Bed.Status.OCCUPIED
    bed.save(update_fields=["status"])

    return assignment
```

This is illustrative, not production-complete. Also validate admission
state, facility compatibility, isolation requirements, cancellation and
transfer workflows. Enforce active-assignment rules in the database as
well as application logic.

### 10.2 Other race conditions

  -----------------------------------------------------------------------
  Operation                           Protection
  ----------------------------------- -----------------------------------
  Double bed allocation               Row locking + database constraints

  Duplicate patient registration      Identifier uniqueness + duplicate
                                      detection workflow

  Double pharmacy dispensing          Transactional stock reservation and
                                      deduction

  Overselling medication inventory    Row locking or conditional atomic
                                      updates

  Duplicate insurance request         Idempotency key and stored request
                                      state

  Duplicate claim submission          Stable claim identity, submission
                                      version and idempotency controls

  Duplicate payment posting           Provider transaction ID uniqueness
                                      and reconciliation

  Concurrent clinical edits           Optimistic concurrency/version
                                      checks

  Duplicate Celery execution          Idempotent handlers and unique
                                      business-event identifiers
  -----------------------------------------------------------------------

`transaction.atomic()` only provides database transaction boundaries. It
does not make an external HTTP call, email or Redis operation part of
the same PostgreSQL transaction.

------------------------------------------------------------------------

## 11. Insurance, Stedi and Revenue Cycle

### 11.1 Integration gateway

Stedi is a useful choice for the US revenue-cycle integration layer. Its
documented APIs support real-time eligibility and benefit checks using
X12 270/271 transactions, along with claim submission, claim status and
remittance-related workflows. Availability depends on supported
endpoints, payer/network participation and onboarding.

Official references:

-   [Stedi healthcare API
    documentation](https://www.stedi.com/docs/healthcare)
-   [Stedi eligibility API
    reference](https://www.stedi.com/docs/healthcare/api-reference/post-eligibility-check)

Do not call Stedi directly from React, and do not scatter
provider-specific payloads throughout Django views.

``` text
Insurance Domain
    |
    └── Insurance Integration Service
          |
          ├── Stedi Adapter (US)
          ├── Other US Payer/Clearinghouse Adapters
          ├── Indian Insurer / TPA Adapters
          └── Government Scheme Adapters
```

Conceptual provider-neutral contract:

``` python
class InsuranceProvider:
    def check_eligibility(self, request_data):
        raise NotImplementedError

    def request_authorization(self, request_data):
        raise NotImplementedError

    def submit_claim(self, claim_data):
        raise NotImplementedError

    def check_claim_status(self, claim_reference):
        raise NotImplementedError
```

Not every provider supports every operation. Model each adapter's
capabilities explicitly.

### 11.2 Suggested eligibility data model

``` text
InsurancePolicy
    id
    organization_id
    patient_id
    payer_id
    member_id
    policy_number
    subscriber_relationship
    effective_from
    effective_until
    priority
    status

EligibilityCheck
    id
    organization_id
    policy_id
    encounter_id
    provider_name
    external_reference
    request_hash
    status
    checked_at
    coverage_effective_from
    coverage_effective_until

EligibilityResponse
    id
    eligibility_check_id
    normalized_result
    encrypted_raw_payload_reference
    received_at
    parser_version
```

Separate normalized fields used by workflows from the original response.
Retain the original response in restricted storage according to
applicable retention and operational requirements.

Statuses should distinguish:

-   Pending.
-   Active coverage confirmed.
-   Inactive coverage confirmed.
-   Payer returned an error.
-   Information insufficient.
-   Provider unavailable or timeout.
-   Manual review required.

Do not map every unsuccessful request to `INACTIVE`. A timeout is not
evidence that coverage is inactive.

### 11.3 Eligibility workflow

1.  Frontend submits a request to Django.
2.  Django verifies authorization, tenant, patient, encounter and
    selected policy.
3.  Application creates a durable eligibility-check record.
4.  It calls the selected provider using server-side credentials.
5.  It validates and normalizes the response.
6.  It persists the result, external reference and appropriate audit
    event.
7.  It presents coverage details and any required manual review.
8.  If the provider is unavailable, it displays pending/unavailable
    rather than silently assuming coverage.

A synchronous request may be appropriate for an interactive workflow.
For batches or long-running work, use Celery and return a job identifier
for status polling.

Protect eligibility requests against accidental duplication. If a
request times out after the payer has processed it, reconcile the
outcome instead of blindly repeating an operation.

**US-specific network caution:** Stedi documents additional CMS/HETS
requirements, including originating network-IP traceability for relevant
eligibility checks. Its documentation states that CMS requests can be
blocked when the originating IP or forwarded upstream IP is outside the
United States. Design connectivity and deployment topology for the
particular payer workflow; do not assume one global outbound gateway
works for every payer.

### 11.4 US and India insurance workflows

  -----------------------------------------------------------------------
  Capability              United States           India
  ----------------------- ----------------------- -----------------------
  Eligibility             X12 270/271 through     Insurer/TPA-specific
                          supported payer         interfaces and
                          networks                workflows

  Claim submission        Relevant X12 837 claim  Insurer/TPA-specific
                          types, as supported     formats, portals or
                                                  APIs

  Authorization           Payer-specific          Cashless
                          preauthorization        preauthorization and
                                                  scheme-specific
                                                  approvals

  Remittance              X12 835 and related     Insurer/TPA settlement
                          workflows where         and remittance
                          supported               workflows

  Patient responsibility  Deductible, copay,      Deductibles,
                          coinsurance and         copayments, exclusions
                          uncovered services      and policy-specific
                                                  rules

  Government programs     Medicare, Medicaid and  Relevant government
                          other applicable        schemes, including
                          programs                applicable Ayushman
                                                  Bharat workflows
  -----------------------------------------------------------------------

This is a capability overview, not a universal mapping of every insurer.
Exact integrations depend on target hospitals, payer/network enrollment
and contractual arrangements.

### 11.5 Full revenue-cycle workflow

-   Capture and validate coverage.
-   Perform eligibility and benefits verification.
-   Obtain referrals and prior authorizations where required.
-   Record services and capture billable charges.
-   Validate coding and required documentation.
-   Generate claims and perform pre-submission edits.
-   Submit claims and record acknowledgments.
-   Track adjudication and payer requests.
-   Receive remittance advice and post payments.
-   Allocate payments across claim lines and patient balances.
-   Handle denials, corrections, appeals and resubmissions.
-   Reconcile payer deposits, remittances, invoices and ledger entries.
-   Close or escalate remaining balances under approved policies.

Do not assume that claim submission equals acceptance, acceptance equals
adjudication, or adjudication equals payment. Each is a separate state.

------------------------------------------------------------------------

## 12. Healthcare Interoperability Standards

Design interoperability into the data model even if the first release
uses only a few external integrations.

### 12.1 HL7 FHIR

FHIR provides standardized healthcare resources for exchanging patient,
practitioner, encounter, observation, medication, diagnostic and
financial information.

Official reference: [HL7 FHIR](https://hl7.org/fhir/)

  -----------------------------------------------------------------------
  Internal domain                     FHIR resource to evaluate
  ----------------------------------- -----------------------------------
  Patient                             `Patient`

  Hospital and departments            `Organization`, `Location`

  Doctor and clinical staff           `Practitioner`, `PractitionerRole`

  Appointment                         `Appointment`

  Visit and admission                 `Encounter`

  Clinical notes and reports          `Composition`, `DocumentReference`,
                                      `DiagnosticReport`

  Vitals and laboratory values        `Observation`

  Medication catalog and orders       `Medication`, `MedicationRequest`

  Medication administration           `MedicationAdministration`

  Allergy                             `AllergyIntolerance`

  Procedures                          `Procedure`

  Insurance and claims                `Coverage`, `Claim`,
                                      `ExplanationOfBenefit`
  -----------------------------------------------------------------------

FHIR is an interoperability layer, not a reason to replace the
transactional data model wholesale with JSON documents. Choose the
version and implementation guide based on partner requirements.

### 12.2 India: ABDM

For Indian hospitals, assess integration with the Ayushman Bharat
Digital Mission (ABDM), including ABHA-related workflows, applicable EHR
standards, consent-based health-information exchange, sandbox validation
and security requirements.

Official portal: [Ayushman Bharat Digital Mission](https://abdm.gov.in/)

Government material describes consent-based exchange and security
validation for participating digital health applications. Confirm
current technical specifications and participation requirements before
implementation.

### 12.3 US interoperability and compliance

For US deployments, assess the applicable HIPAA Privacy, Security and
Breach Notification Rules, plus relevant state laws, contractual
obligations and payer-specific requirements.

Official reference: [US HHS HIPAA](https://www.hhs.gov/hipaa/index.html)

HIPAA security expectations include access control, authentication,
audit controls and transmission security. Do not claim HIPAA compliance
merely because the system uses encryption or is hosted on AWS.
Compliance requires risk assessment, policies, safeguards, contracts
where required and ongoing operational controls.

------------------------------------------------------------------------

## 13. Security, Privacy and Regulatory Governance

For both countries, create a regulatory requirements matrix with
qualified healthcare counsel and compliance specialists. Evaluate the
Indian Digital Personal Data Protection Act, 2023 and DPDP Rules, 2025,
applicable ABDM requirements, and US HIPAA obligations against the
actual services, data flows and business relationships.

The DPDP Rules were notified in November 2025. Confirm commencement
provisions and other applicable requirements for the deployment rather
than assuming every provision has the same effective date.

### 13.1 Authentication

-   MFA for privileged users and appropriate clinical access.
-   Secure session/token lifecycle, revocation and expiration.
-   Login throttling and secure account recovery.
-   Protection against account enumeration.
-   Reauthentication for sensitive actions where justified.

### 13.2 Authorization

-   Role-based access control plus patient, facility, department and
    encounter context.
-   Least-privilege access and explicit denial by default.
-   Separate permissions for viewing, editing, signing, dispensing,
    approving and exporting.
-   Emergency access with justification, audit and retrospective review.
-   Periodic permission review and prompt termination of access when
    employment ends.

### 13.3 Data protection

-   TLS in transit and encryption at rest.
-   Managed encryption keys and rotation.
-   Restricted document storage with short-lived authorized access.
-   Minimize sensitive data in logs, traces, URLs and notifications.
-   Backups, restoration testing and controlled data exports.
-   Secret management; never commit credentials to source control.
-   Data minimization and retention policies by data type and
    jurisdiction.

### 13.4 Auditability

-   Append-oriented audit records for sensitive operations.
-   Actor, tenant, action, target, timestamp, outcome and relevant
    change metadata.
-   Restricted audit access, tamper detection and monitoring of
    privileged access.
-   Documented retention, incident response and legal-hold procedures.

Application logs help diagnose errors. Clinical audit logs establish who
accessed or changed a record and what happened. Sensitive events may
include viewing a patient record, exporting a report, changing an
allergy, amending a signed note, overriding a medication check or
changing insurance data.

Do not put passwords, tokens, unnecessary clinical details or full
insurance payloads in general-purpose application logs. Audit data
itself requires access controls and retention policies.

### 13.5 Security test cases

-   A user from Hospital A requests a patient ID belonging to Hospital
    B.
-   A doctor accesses a patient outside the authorized scope.
-   A nurse attempts to modify a signed doctor's note.
-   A pharmacist attempts to dispense more stock than is available.
-   A terminated employee reuses an old session.
-   A user downloads a document by guessing another document's URL.
-   A Celery job runs with missing or stale customer context.
-   A report export includes patients outside the authorized facility.
-   An integration logs a secret or sensitive patient data during an
    exception.
-   A database restore recovers records but fails to restore required
    audit relationships.

Treat these as testable acceptance criteria, not merely a checklist.

------------------------------------------------------------------------

## 14. Redis, Celery and Asynchronous Processing

### 14.1 Suitable background tasks

-   Insurance verification and batch eligibility processing.
-   Claim submission and status reconciliation.
-   Email, SMS and appointment reminders.
-   Scheduled medication and nursing task generation.
-   Document rendering and report exports.
-   Large analytics jobs.
-   Integration polling and external-system synchronization.
-   Credential and insurance-expiry alerts.
-   Nightly reconciliation and inventory notifications.

### 14.2 Recommended execution pattern

```text
[Django API]
     |
     v
+-----------------------------------------+
| Single PostgreSQL transaction           |
| 1. Write the business state              |
| 2. Insert the outbox event               |
+-----------------------------------------+
     |
     v
[Committed business data + outbox row]
     |
     v
[Outbox Dispatcher reads unpublished rows]
     |
     v
[Publish durable work item to Celery Broker]
     |
     v
[Celery Worker executes background task]
     |
     v
[Call external API / perform job]
     |
     v
[Persist result and status in PostgreSQL]
     |
     +----> [Retry or reconcile when required]
```

For important workflows, use the **transactional outbox pattern**. If a
database update and task publication are performed separately, the
database update could succeed while task publication fails. Persisting
an outbox record in the same PostgreSQL transaction allows a dispatcher
to retry publication after a crash.

The outbox is not necessary for every low-risk notification. It is
valuable for important integration events, claims, financial operations
and workflows where silently losing a task is unacceptable.

### 14.3 Celery reliability rules

-   Assume a task may execute more than once.
-   Make tasks idempotent.
-   Use bounded retries with exponential backoff and jitter.
-   Distinguish retryable errors from permanent validation failures.
-   Set connection and task timeouts.
-   Use unique operation identifiers.
-   Store task state in durable business records; do not depend solely
    on Celery's result backend.
-   Route long-running jobs to dedicated queues.
-   Monitor queue depth, task age, retries and exhausted-retry cases.
-   Never perform irreversible clinical actions merely because a
    scheduled task ran.

Redis is suitable as the initial broker for many workloads. If stronger
durable message retention or different routing semantics are required,
evaluate RabbitMQ or a managed messaging service. Broker choice should
follow the required failure and recovery guarantees.

Redis should not be the sole store for medication administration, bed
assignments, signed reports, claims or payments.

------------------------------------------------------------------------

## 15. React Frontend Architecture

Organize the frontend around how each hospital role works, rather than
exposing one massive navigation menu to everyone.

### 15.1 Role-specific workspaces

  -----------------------------------------------------------------------
  Workspace                           Key capabilities
  ----------------------------------- -----------------------------------
  Hospital admin                      Staff, departments, facilities,
                                      permissions and KPIs

  Doctor                              Patient timeline, notes, diagnoses,
                                      orders, results and discharge

  Nurse                               Ward board, vitals, medication due
                                      list, care tasks and handover

  Pharmacy                            Orders, verification, dispensing,
                                      batches, stock and expiry

  Lab / Radiology                     Worklists, specimen/study tracking,
                                      results and reporting

  Billing / Insurance                 Eligibility, authorizations, charge
                                      review, claims and settlement

  Patient portal                      Appointments, released reports,
                                      bills, consent and follow-up
  -----------------------------------------------------------------------

### 15.2 Frontend engineering decisions

-   Use TypeScript and typed API contracts.
-   Use a shared design system but allow workflows to differ by role.
-   Keep server state in TanStack Query or an equivalent data-fetching
    library.
-   Use React Hook Form with schema-based validation for large forms.
-   Provide searchable worklists, filters, pagination and
    keyboard-friendly workflows.
-   Use optimistic updates only where rollback and conflict handling are
    safe.
-   Use WebSockets or server-sent events for selected live dashboards,
    with polling fallback.
-   Never treat hidden UI buttons as security controls; backend
    authorization is mandatory.
-   Prevent stale clinical forms from silently overwriting changes made
    by another clinician.
-   Build accessible forms and readable clinical displays.

### 15.3 Patient chart design

The patient chart should be the central clinical workspace, with a
stable header containing identity confirmation, allergies and important
warnings, followed by encounter-specific views:

-   Overview and patient summary.
-   Timeline and encounter history.
-   Clinical notes and diagnoses.
-   Medications and medication administration.
-   Vitals and observations.
-   Laboratory and imaging results.
-   Procedures and care plans.
-   Documents and consent.
-   Insurance and billing, subject to permissions.

The user should not have to open six different screens to understand a
patient's current admission.

------------------------------------------------------------------------

## 16. REST API Design

Use a versioned REST API, initially under `/api/v1/`, with consistent
pagination, validation, authorization and error formats.

  --------------------------------------------------------------------------------------------
  Area                                Endpoint
  ----------------------------------- --------------------------------------------------------
  Hospital setup                      `POST /api/v1/organizations/`

  Departments                         `POST /api/v1/departments/`

  Doctor onboarding                   `POST /api/v1/staff/`

  Patient registration                `POST /api/v1/patients/`

  Patient search                      `GET /api/v1/patients/?search=`

  Appointments                        `POST /api/v1/appointments/`

  Admission                           `POST /api/v1/admissions/`

  Bed availability                    `GET /api/v1/beds/availability/`

  Bed assignment                      `POST /api/v1/admissions/{id}/bed-assignments/`

  Clinical notes                      `POST /api/v1/encounters/{id}/notes/`

  Medication orders                   `POST /api/v1/encounters/{id}/medication-orders/`

  Medication administration           `POST /api/v1/medication-orders/{id}/administrations/`

  Lab orders                          `POST /api/v1/encounters/{id}/lab-orders/`

  Diet orders                         `POST /api/v1/admissions/{id}/diet-orders/`

  Insurance verification              `POST /api/v1/insurance/eligibility-checks/`

  Claim submission                    `POST /api/v1/claims/{id}/submissions/`

  Discharge                           `POST /api/v1/admissions/{id}/discharge/`

  Audit review                        `GET /api/v1/audit-events/`
  --------------------------------------------------------------------------------------------

Use action endpoints for business operations such as signing a note,
assigning a bed, administering a dose or submitting a claim. These are
not ordinary field updates: each operation should validate current
state, enforce authorization, execute the transition and record the
result.

For every write endpoint, define:

1.  Authentication and authorization requirements.
2.  Request schema and validation rules.
3.  Allowed source states and resulting state.
4.  Transaction boundaries and concurrency controls.
5.  Idempotency behavior.
6.  Audit events.
7.  Error responses and retry guidance.
8.  Required downstream events or integrations.

For example, `POST /api/v1/admissions/{id}/discharge/` should not simply
set `status="DISCHARGED"`. It should validate the discharge workflow,
capture required clinical documentation, record the authorized action
and coordinate outstanding operational tasks.

------------------------------------------------------------------------

## 17. AWS Deployment Architecture

Start with a manageable AWS deployment that can scale without
introducing unnecessary infrastructure.

```text
[Hospital Staff / Patient Portal]
                 |
                 v
          [CloudFront + WAF]
                 |
                 v
       [Application Load Balancer]
                 |
                 v
         [Django API Containers]
           |       |       \
           |       |        +--> [CloudWatch: logs / metrics / traces]
           |       +-----------> [ElastiCache Redis]
           +-------------------> [S3: documents and reports]
           |
           v
   [Amazon RDS PostgreSQL]
       |              ^
       |              |
       |              +--------------------------------+
       |                                               |
       +--> [Automated backups / point-in-time recovery]|
       |                                               |
       v                                               |
 [Outbox Dispatcher]                                  |
       |                                               |
       v                                               |
  [Celery Broker]                                     |
       |                                               |
       v                                               |
  [Celery Workers] -----------------------------------+
       |                 |
       |                 +--> [S3: generated reports]
       +--------------------> [Insurance / Lab / Messaging APIs]
       +--------------------> [CloudWatch: logs / metrics / traces]

Each hospital organization has its own dedicated deployment and
 database boundary. Branches share that organization's environment.
```

### 17.1 Suggested AWS services

  -----------------------------------------------------------------------
  Need                                AWS service
  ----------------------------------- -----------------------------------
  Frontend hosting                    S3 + CloudFront, or an appropriate
                                      managed frontend platform

  API and workers                     ECS with Fargate

  Relational database                 Amazon RDS for PostgreSQL

  Redis                               Amazon ElastiCache

  Documents and reports               Amazon S3

  Encryption keys                     AWS KMS

  Credentials and API keys            AWS Secrets Manager

  Application metrics                 Amazon CloudWatch

  Distributed tracing                 OpenTelemetry-compatible tracing
                                      and AWS observability services

  DNS and TLS                         Route 53 and AWS Certificate
                                      Manager

  Infrastructure as code              Terraform

  CI/CD                               GitHub Actions with OIDC (see
                                      sections 30.3, 32 and 33)
  -----------------------------------------------------------------------

### 17.2 Environment separation

-   Separate Development, QA, Staging and Production environments (see
    section 31).
-   Different credentials and restricted access for each environment.
-   Avoid copying production patient data into development.
-   Use infrastructure as code and reviewed changes.
-   Automate deployment, health checks and rollback.
-   Use controlled database migration jobs.
-   Restrict production shell and database access.
-   Record and review privileged operations.

### 17.3 Reliability and disaster recovery

Define measurable targets for:

-   API availability and response latency.
-   Recovery time objective (RTO) and recovery point objective (RPO).
-   Backup frequency, retention and restoration testing.
-   Database failover behavior.
-   Celery queue recovery after worker or broker failure.
-   External integration timeout and outage handling.
-   Disaster recovery and incident escalation.
-   Capacity planning and load testing.

A backup is not a recovery strategy until it has been restored
successfully and critical relationships, files, clinical records and
audit history have been verified.

### 17.4 Per-customer deployment automation

Since each hospital gets a dedicated deployment/database, automate:

1.  Customer onboarding and configuration.
2.  AWS infrastructure provisioning.
3.  Database creation and credential generation.
4.  S3 storage and encryption setup.
5.  Application deployment.
6.  Database migrations.
7.  Health and smoke tests.
8.  Monitoring, alerting and backup verification.
9.  Customer-specific domain/TLS configuration.
10. Version tracking and controlled upgrades.

Do not rely on manual console steps for every customer. Fleet-wide
patching and migration orchestration will otherwise become a major
operational risk.

------------------------------------------------------------------------

## 18. Non-Functional Requirements

The following are starting targets to validate with hospitals, not
universal healthcare standards.

  -----------------------------------------------------------------------
  Area                                Initial engineering target
  ----------------------------------- -----------------------------------
  Availability                        Define an initial 99.9% target for
                                      agreed critical services, then
                                      validate

  Interactive API latency             Target p95 below 300--500 ms for
                                      ordinary reads under expected load

  Data consistency                    Strong transactional consistency
                                      for critical clinical and financial
                                      writes

  Security                            Least privilege, encryption,
                                      auditability and tested isolation

  Scalability                         Horizontal API and worker scaling
                                      with database capacity planning

  Recovery                            Explicit, tested RTO/RPO for each
                                      critical subsystem

  Interoperability                    Versioned, validated integration
                                      contracts

  Accessibility                       Accessible forms, keyboard
                                      navigation and readable clinical
                                      interfaces

  Observability                       Correlated request IDs, structured
                                      logs, metrics, traces and
                                      actionable alerts

  Maintainability                     Domain ownership, automated tests,
                                      documented contracts and controlled
                                      migrations
  -----------------------------------------------------------------------

A real-time bed board may tolerate a short delay in a secondary
dashboard, but the bed-allocation transaction cannot tolerate
conflicting assignments. A delayed analytics report may be acceptable,
whereas silently losing a medication administration event is not.

------------------------------------------------------------------------

## 19. Testing and Quality Strategy

A system of this size cannot be validated through manual browser testing
alone.

### 19.1 Backend testing

-   Model and database constraint tests.
-   Unit tests for clinical and financial business rules.
-   API permission tests for every relevant role.
-   Tenant/deployment-isolation tests across resources.
-   Transaction and concurrency tests using PostgreSQL.
-   Workflow transition tests.
-   Celery retry and duplicate-execution tests.
-   Insurance adapter contract tests.
-   Migration and recovery tests.
-   Security tests for file access, injection, authentication and
    authorization.

### 19.2 Frontend testing

-   Component and form-validation tests.
-   Role-specific navigation and permission tests.
-   Patient search and chart workflows.
-   Medication ordering and administration flows.
-   Bed assignment and transfer workflows.
-   Insurance response handling and failure states.
-   Accessibility checks.
-   End-to-end tests using Playwright or an equivalent tool.

### 19.3 Clinical and operational validation

Work with doctors, nurses, pharmacists, laboratory staff, insurance
specialists and hospital administrators to validate real workflows.
Clinical experts must determine clinical rules, required approvals and
escalation thresholds; engineering implements and tests them.

Use synthetic patients and simulated payer responses during development.
Production payer testing must follow the provider's authorized testing
procedures.

------------------------------------------------------------------------

## 20. Implementation Roadmap

Do not attempt to build all functional areas at once. Deliver controlled
phases, establishing the shared foundation before expanding into
clinical and financial workflows.

### Phase 1 --- Foundation and hospital onboarding

-   Django, DRF, React, TypeScript, PostgreSQL, Redis and Celery.
-   Hospital organization and facility configuration.
-   Authentication, staff, departments, credentials and access policies.
-   Dedicated customer provisioning model and infrastructure automation.
-   Audit infrastructure, CI/CD, observability and deployment
    environments.
-   API conventions, migrations and testing.

**Exit criterion:** A hospital can be configured, staff can be onboarded
and isolation is demonstrably enforced.

### Phase 2 --- Patient administration and outpatient care

-   Patient registration and duplicate detection.
-   Patient search and longitudinal history.
-   Appointments, consultations, encounters and clinical notes.
-   Diagnoses, allergies, vitals and basic reports.

**Exit criterion:** The hospital can manage patients and outpatient
visits end to end.

### Phase 3 --- Inpatient and nursing operations

-   Admission and discharge workflows.
-   Ward, room and bed allocation.
-   Patient transfers and nursing assessments.
-   Daily care tasks, vital charts and clinical handovers.
-   Diet orders, meal delivery and housekeeping.

**Exit criterion:** Inpatient stays, bed movements and daily care are
traceable.

### Phase 4 --- Medication, pharmacy and diagnostics

-   Medication catalog, prescriptions and pharmacy inventory.
-   Medication administration records.
-   Lab orders, specimen tracking and results.
-   Imaging and report workflows.
-   Medication safety checks and stock reconciliation.

**Exit criterion:** Orders, dispensing, administration and diagnostic
results remain distinct and auditable.

### Phase 5 --- Insurance and revenue cycle

-   US payer configuration and Stedi integration.
-   Eligibility verification and authorization workflows.
-   Charges, invoices, payments and reconciliation.
-   Claim generation, submission, status tracking and denial management.
-   Indian insurer/TPA and applicable government scheme integrations.

**Exit criterion:** The hospital can reconcile services, payer
obligations and patient balances.

### Phase 6 --- Enterprise integrations and rollout

-   Patient portal and advanced reporting.
-   FHIR, ABDM and external EHR integrations as required.
-   PACS/LIS and device integrations.
-   Performance, security and recovery testing.
-   Hospital user acceptance testing, training and controlled rollout.

**Exit criterion:** The product passes agreed operational, clinical,
security and recovery acceptance tests.

Duration depends on team size, existing infrastructure, integrations and
clinical validation requirements. Do not promise an enterprise-ready
HIMS within an arbitrary short deadline.

------------------------------------------------------------------------

## 21. First End-to-End Vertical Slice

For the initial development milestone, implement this end-to-end
journey:

1.  A hospital administrator creates and configures a hospital.
2.  The administrator creates departments and facilities.
3.  The administrator invites a doctor and records qualifications,
    designation and credentials.
4.  The doctor receives access limited to the authorized hospital and
    department.
5.  Reception registers a patient and generates an MRN.
6.  The patient books an appointment or arrives as a walk-in.
7.  The doctor records the encounter, diagnosis and clinical notes.
8.  The doctor creates an admission request.
9.  Authorized staff allocate a bed without a race condition.
10. The inpatient team records vitals, medication orders, administration
    events and daily care.
11. The laboratory records results and the treating team reviews them.
12. The doctor initiates discharge, and the system creates the necessary
    clinical and operational records.
13. Billing produces a bill while insurance verification runs through
    the appropriate integration.
14. The patient record and audit history remain available after
    discharge.

This slice exercises multiple domains and exposes important modeling
mistakes before every module is implemented.

------------------------------------------------------------------------

## 22. Architecture Decisions to Record

Record each significant choice in an Architecture Decision Record (ADR),
including context, alternatives, decision, consequences, owner and
review date.

### ADR-001: Modular monolith before microservices

**Decision:** Start with Django modular monolith and Celery workers.\
**Reason:** Strong transactions, simpler deployment and fewer
distributed failure modes.\
**Revisit when:** Domain ownership, independent scaling or reliability
needs justify service extraction.

### ADR-002: PostgreSQL as authoritative transactional database

**Decision:** Use PostgreSQL for production and development.\
**Reason:** ACID transactions, relational integrity, indexing and
concurrency controls.

### ADR-003: Dedicated deployment/database per hospital organization

**Decision:** Each hospital organization receives a dedicated deployment
and database; branches share that organization's environment by
default.\
**Reason:** Stronger isolation, independent recovery and
customer-specific configuration.\
**Trade-off:** More infrastructure, migration and operational
automation.

### ADR-004: Redis is not the source of truth

**Decision:** Redis is for cache, short-lived coordination and broker
use where appropriate.\
**Reason:** Clinical and financial state must remain durable in
PostgreSQL.

### ADR-005: Transactional outbox for critical asynchronous workflows

**Decision:** Use an outbox where losing an event would affect important
business or integration workflows.\
**Reason:** Avoid the dual-write failure between database commit and
task publication.

### ADR-006: Provider-neutral insurance integration layer

**Decision:** Normalize payer workflows behind provider adapters.\
**Reason:** US and Indian insurers expose different capabilities and
formats; provider-specific schemas should not permeate core domains.

### ADR-007: Interoperability as an explicit boundary

**Decision:** Map internal domain models to selected FHIR/HL7/ABDM
requirements through dedicated adapters.\
**Reason:** Standards facilitate exchange but do not replace
transactional domain modeling.

### ADR-008: Clinical records and financial records require auditability

**Decision:** Signed records, medication administration, financial
postings and sensitive access events have controlled history and
correction workflows.\
**Reason:** Traceability and safety.

------------------------------------------------------------------------

## 23. Operational Readiness Checklist

### Product and clinical governance

-   [ ] Named clinical owners for each clinical workflow.
-   [ ] Validated admission, transfer and discharge policies.
-   [ ] Validated medication, nursing, ICU and surgery workflows.
-   [ ] Agreed laboratory and critical-result escalation procedures.
-   [ ] Approved role and privilege matrix.
-   [ ] Defined patient identity and duplicate-merge policy.

### Architecture and data

-   [ ] Dedicated customer provisioning is automated.
-   [ ] Database schemas and migrations are version-controlled.
-   [ ] Critical database constraints are implemented.
-   [ ] Idempotency and concurrency controls are tested.
-   [ ] Outbox and retry behavior are tested for critical workflows.
-   [ ] Data retention and correction policies are defined.
-   [ ] Cross-hospital analytics is explicitly governed.

### Security and compliance

-   [ ] Threat model and risk assessment completed.
-   [ ] Authentication and MFA policies established.
-   [ ] Authorization and isolation tests pass.
-   [ ] Encryption and key-management policies reviewed.
-   [ ] Audit event catalog and retention policies defined.
-   [ ] Incident response and breach procedures documented.
-   [ ] Applicable US and Indian regulatory obligations reviewed.
-   [ ] Contracts and business associate/data-processing arrangements
    reviewed where applicable.

### AWS and operations

-   [ ] Separate Development, QA, Staging and Production environments
    (section 31).
-   [ ] Infrastructure as code is reviewed and tested.
-   [ ] Secrets are stored in a managed secret store.
-   [ ] Backups and point-in-time recovery configured as appropriate.
-   [ ] Restore drills completed.
-   [ ] RTO/RPO agreed and tested.
-   [ ] Metrics, logs, traces and actionable alerts are configured.
-   [ ] Capacity and load tests completed.
-   [ ] Deployment rollback and migration recovery plans exist.
-   [ ] Customer-specific integration credentials are isolated.

### Insurance and revenue cycle

-   [ ] Payer and network enrollment requirements identified.
-   [ ] Eligibility outcomes distinguish inactive coverage from errors
    and timeouts.
-   [ ] Authorization requirements and exception workflows defined.
-   [ ] Claim validation and submission lifecycle modeled.
-   [ ] Remittance and payment-posting workflows tested.
-   [ ] Denial, appeal, corrected-claim and reconciliation processes
    validated.
-   [ ] US and Indian adapter capabilities documented separately.
-   [ ] Financial reconciliation signed off by qualified finance
    stakeholders.

### Go-live readiness

-   [ ] User acceptance testing completed.
-   [ ] Clinical workflow training completed.
-   [ ] Data migration and reconciliation validated.
-   [ ] Support escalation and incident ownership defined.
-   [ ] Recovery and downtime procedures documented.
-   [ ] Rollout plan, rollback criteria and success metrics approved.

------------------------------------------------------------------------

## 24. Reference Links

These links are starting points for official technical and regulatory
documentation. Verify the current version and applicability during
implementation.

### Insurance and healthcare interoperability

-   [Stedi healthcare API
    documentation](https://www.stedi.com/docs/healthcare)
-   [Stedi eligibility API
    reference](https://www.stedi.com/docs/healthcare/api-reference/post-eligibility-check)
-   [HL7 FHIR](https://hl7.org/fhir/)
-   [Ayushman Bharat Digital Mission (ABDM)](https://abdm.gov.in/)

### US privacy and security

-   [US HHS HIPAA](https://www.hhs.gov/hipaa/index.html)

### Core engineering stack

-   [Django documentation](https://docs.djangoproject.com/)
-   [Django REST Framework
    documentation](https://www.django-rest-framework.org/)
-   [PostgreSQL documentation](https://www.postgresql.org/docs/)
-   [Celery documentation](https://docs.celeryq.dev/)
-   [Redis documentation](https://redis.io/docs/)
-   [React documentation](https://react.dev/)
-   [TypeScript documentation](https://www.typescriptlang.org/docs/)
-   [AWS documentation](https://docs.aws.amazon.com/)
-   [Amazon RDS for
    PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)
-   [Amazon ECS](https://docs.aws.amazon.com/ecs/)
-   [Amazon S3](https://docs.aws.amazon.com/s3/)

------------------------------------------------------------------------

## Final Recommendation

Build the HIMS as a secure, tenant-aware, modular Django platform with
PostgreSQL at the center, a typed React frontend, and carefully
controlled asynchronous workflows. Use dedicated deployment and database
boundaries for each hospital organization, while modeling its branches
within that environment. Keep US and Indian insurance, interoperability
and regulatory requirements behind explicit configuration and
integration boundaries.

Make clinical state transitions, patient identity, medication history,
bed allocation, billing, reconciliation and auditability correct before
expanding the feature set. Automate customer provisioning, migrations,
backups, monitoring and recovery from the beginning, because a
dedicated-deployment model becomes operationally expensive without
automation.

This is the foundation for growing from an initial hospital rollout into
a robust multi-hospital HIMS without requiring a complete architectural
rewrite.

---

# Specification v2 — Detailed Implementation and Delivery Architecture

The sections below extend the existing blueprint. The original sections 1–24 remain the baseline functional and technical architecture. These additions make the design more actionable for implementation, validation, operations and release management.

## 25. Specification v2: Purpose and Delivery Standard

### 25.1 What this document is and is not

This document is the master architecture specification for planning and implementation. It defines architecture principles, domain responsibilities, implementation standards, delivery controls and required supporting artifacts. It does not replace module-level requirements, approved clinical protocols, complete table-by-table data dictionaries, provider-specific payer onboarding instructions, or jurisdiction-specific legal review. Those are governed deliverables created under the standards in this document.

A production-grade HIMS is not considered ready merely because screens and APIs work. It must demonstrate correct business invariants under normal operation, concurrent requests, retries, permissions failures, dependency outages, partial failures, restore operations and release/rollback scenarios.

### 25.2 Normative terms

- **MUST**: required for a safe and acceptable implementation unless an approved architecture decision record (ADR) explicitly documents a justified exception.
- **SHOULD**: expected by default; deviations require a documented reason and owner.
- **MAY**: optional capability.
- **P0**: must be resolved before implementing the affected domain or before the corresponding high-risk capability is enabled.
- **P1**: must be resolved before production rollout or before the relevant scale/availability requirement is claimed as satisfied.

### 25.3 Requirements traceability

Every requirement must have a stable identifier and traceability to implementation and verification. Suggested identifiers:

- `HIMS-FR-<DOMAIN>-NNN`: functional requirement.
- `HIMS-NFR-<CATEGORY>-NNN`: non-functional requirement.
- `HIMS-SEC-NNN`: security requirement.
- `HIMS-INT-<PROVIDER>-NNN`: integration requirement.
- `HIMS-OPS-NNN`: operational requirement.
- `HIMS-CLIN-NNN`: clinically validated workflow requirement.
- `HIMS-ADR-NNN`: architecture decision record.

Each requirement should link to one or more GitHub Issues, pull requests, automated tests, manual test cases and release evidence. A requirement is not considered done solely because a developer reports that the code is complete.

### 25.4 Mandatory requirements record

For every requirement, record:

| Field | Meaning |
|---|---|
| ID and title | Stable identifier and short description |
| Business/clinical reason | Why it is needed and who owns the decision |
| Actors | Roles and service identities allowed to perform it |
| Preconditions | Required patient, encounter, admission or financial state |
| Main success path | Expected workflow and persisted outcome |
| Alternate/failure paths | Timeout, unavailable resource, invalid input, denial and cancellation behavior |
| Data effects | Tables/events/documents created or changed |
| Security classification | Data sensitivity and access restrictions |
| Audit requirement | What must be logged and at what granularity |
| Idempotency/concurrency | Duplicate-request and race-condition behavior |
| Integration dependencies | External systems and failure semantics |
| Acceptance criteria | Observable, testable conditions |
| Test evidence | Automated tests, manual evidence and reviewer |
| Release risk | Clinical, privacy, financial, operational and rollback impact |

### 25.5 Quality attributes must be testable

Do not use vague statements such as “secure,” “fast,” “highly available” or “scalable” as acceptance criteria. Convert them into measurable tests. Examples: an unauthorized cross-customer API request returns a denial and creates an auditable security event; a concurrent bed-assignment test never creates more than one active assignment; a backup restore meets the approved RTO/RPO; and a failed payer timeout is never normalized as confirmed inactive insurance.

---

## 26. P0: Required Before Building the Affected Domain

P0 design work should be completed just ahead of implementation of the domain it governs. Do not block all early engineering until every future module is fully specified, but do not build critical data models or clinical workflows on unreviewed assumptions.

### 26.1 P0-A: Functional requirements and acceptance criteria

For each module in sections 4 and 5, create a functional specification containing:

1. Actors and permission boundaries.
2. Main workflow and exception paths.
3. Business rules and clinical/financial rules with named owners.
4. State transitions and invalid transitions.
5. Required fields, code sets, defaults and validation messages.
6. Side effects: audit records, notifications, integrations and financial entries.
7. Concurrency, idempotency and retry behavior.
8. Data retention, correction and amendment rules.
9. Screen-level expectations and API-level acceptance criteria.
10. Positive, negative, boundary, permissions and failure tests.

Examples that must be specified before the relevant workflow ships:

- Admission request when no compatible bed is available.
- Emergency admission while payer verification is unavailable.
- Bed transfer where the destination is unavailable, blocked or incompatible.
- Medication order change after one or more doses have already been administered.
- Medication marked as administered in error and the permitted correction process.
- Critical lab result that cannot reach the ordering clinician.
- Discharge initiation when documentation or reconciliation is incomplete.
- Claim rejected at submission versus denied after adjudication.
- Payment received with no matching remittance or with an amount that does not reconcile.

Clinical protocols, medication thresholds, surgical checklists and critical-result rules must be approved by clinical governance, not invented solely by engineering.

### 26.2 P0-B: Detailed database design

Before implementing a domain's write paths, its physical schema must define:

- Table, column, data type, nullability, default and sensitivity class.
- Primary/foreign keys, unique constraints, check constraints and deletion behavior.
- Relationship cardinality and lifecycle ownership.
- Required indexes tied to expected query patterns.
- State/status enumerations and their transition constraints.
- History/version model and correction semantics.
- Data retention and archival policy.
- Data owner and source of truth.
- Migration strategy and compatibility with the prior release.

Use foreign keys and relational constraints for core business relationships. JSONB may carry flexible external payloads or versioned metadata, but must not be used to avoid modeling core patient, clinical, admission, inventory or financial relationships.

### 26.3 P0-C: State machines and workflow ownership

For each stateful entity, create a transition table with the following columns: entity, current state, requested action, guard/precondition, authorized actor, transaction, next state, audit event, emitted event, retry behavior and compensating/recovery action.

Minimum state machines are required for:

- Patient identity merge and correction.
- Appointment and encounter lifecycle.
- Admission, transfer, discharge and cancellation.
- Bed reservation, allocation, occupied, cleaning, maintenance and release.
- Clinical note draft, signed, amended and corrected.
- Medication order, pharmacy review, dispensing, scheduled administration and administration outcome.
- Lab order, specimen lifecycle, validated result and corrected result.
- Imaging order, study status, preliminary report, final report and addendum.
- Surgery request, scheduling, pre-op, in progress, recovery and completion/cancellation.
- Insurance eligibility, authorization, claim submission, acknowledgment, adjudication, denial and appeal.
- Invoice, charge adjustment, payment, refund, remittance posting and reconciliation.
- Purchase order, receiving, stock transfer, inventory adjustment and recall.

No API should permit arbitrary state changes by updating a `status` property without calling the domain operation that enforces these rules.

### 26.4 P0-D: Role and permission matrix

Create a versioned permission matrix covering at least:

- Read/search clinical records.
- Create/edit draft clinical records.
- Sign, amend and correct clinical records.
- Record diagnoses, medication orders and medication administrations.
- Verify and dispense medication.
- Enter, validate and release lab/radiology reports.
- Allocate/transfer/release a bed.
- Create/approve diet orders and confirm meal delivery.
- Create/adjust charges, issue invoices, receive payments and post remittances.
- Submit/modify claims and appeal denials.
- View/download/export documents.
- Manage users, roles, credentials and configuration.
- View audit history and perform emergency access.

For each action, define role, facility/department/patient scope, relationship to the patient, record sensitivity, approval requirements and break-glass behavior. Use least privilege. Frontend hiding is not authorization; enforce permissions in the backend and, where appropriate, at database/storage boundaries.

### 26.5 P0-E: Customer provisioning and tenant isolation

The chosen model is one deployment and database per hospital organization, with multiple branches in that organization. The control plane manages provisioning and deployment metadata; it must not become a universal clinical-record database.

Before the first customer deployment, specify and test:

- How the tenant is resolved from an authenticated domain, identity and membership.
- How a hospital and branches are provisioned automatically.
- How a customer receives isolated database credentials, Redis configuration, S3 access and integration secrets.
- Whether production customers receive dedicated AWS accounts in addition to dedicated stacks/databases.
- How backups, restore requests, maintenance and software upgrades are isolated per customer.
- How support access is requested, approved, time-limited and audited.
- How data export, contract termination and destruction/retention obligations work.
- How central operational reporting minimizes customer metadata and prevents PHI leakage.

Do not perform cross-database joins across hospital deployments. Cross-hospital information sharing must use an explicitly authorized, standards-based and auditable integration. Patient identities in different hospital deployments are separate by default; do not create a global cross-customer MPI unless a legitimate, lawful and consent-governed use case has been approved.

### 26.6 P0-F: US and India integration contracts

For each integration, maintain a provider capability matrix and a technical contract. The matrix must identify supported operations, enrollment requirements, geographic/network restrictions, test environment availability, request limits, rate limits, identifiers, error meanings, retry policy, idempotency support, status polling/webhooks, retention rules and operational owner.

For US insurance, validate Stedi endpoint and payer support for the actual hospital contracts and intended workflows. Do not assume that every payer or transaction type is supported by the same API. For India, identify specific insurers, TPAs and government programs rather than designing against an imaginary universal interface.

Normalize the domain response while preserving the source-specific response in restricted storage when retention is justified. Distinguish a valid negative response from transport errors, invalid input, insufficient information and unknown/pending outcomes. Retry only when the failure is retryable and the operation's duplicate semantics are understood.

### 26.7 P0-G: Country/regulatory and data-flow assessment

Before selecting a production region or transmitting real data, document:

- Legal entities and roles (hospital, HIMS provider, payer, processor/service provider, etc.).
- Types of personal and sensitive data processed.
- Purpose, legal basis/consent mechanism as applicable, and allowed recipients.
- Data region, backup region, logs/telemetry region and cross-border flows.
- Retention, access, correction, export, deletion and legal-hold policies.
- Incident and breach notification responsibilities.
- Vendor, subprocessor and contractual requirements.
- Applicable federal, state, national and sector-specific obligations.

Have qualified counsel/compliance specialists validate the applicability of US HIPAA and other relevant US requirements, India's DPDP framework, applicable ABDM requirements, and other state/country/contract-specific requirements. Product architecture alone does not certify compliance.

### 26.8 P0-H: Terminology and interoperability baseline

Before importing clinical codes or sharing data, decide the supported terminology/code systems and their licensed/source-update processes. Specify the FHIR version and implementation guides only after confirming partner requirements. Define mappings for diagnoses, procedures, medications, lab tests, units, observations, patient identifiers, coverage and claims. Support versioning and unknown/deprecated codes; never silently remap historical clinical data when a terminology catalog changes.

Interoperability scope must explicitly cover applicable FHIR, HL7 messaging, DICOM/PACS, laboratory interfaces and applicable US transaction formats and ABDM interfaces. The standards boundary should have adapter tests and conformance evidence.

### 26.9 P0-I: API contracts and database migration discipline

Every write endpoint needs authorization requirements, request/response schema, state guards, transaction boundaries, concurrency protection, idempotency behavior, audit event, error codes and integration side effects.

Database migrations must be reviewed and tested against representative data volume. Prefer expand-and-contract changes: add backward-compatible schema first, deploy compatible code, backfill safely, switch reads/writes, and remove old schema only after all application versions no longer depend on it. Do not combine an irreversible data rewrite with a routine application rollout without an explicit recovery plan.

### 26.10 P0 exit criteria

A domain is cleared for implementation when the requirements and principal workflows have an owner, schema design is reviewed, access rules are written, state transitions and failure cases are documented, API contracts are agreed where frontend/backend work is parallel, and acceptance tests are identifiable. A high-risk domain cannot move to production merely because its P0 design documents exist; it must also pass the relevant validation and release gates.

---

## 27. P1: Required Before Production Rollout

### 27.1 Resilience and disaster recovery

Define RTO and RPO by workload rather than applying one optimistic number to the whole system. At minimum, assess patient/clinical records, medication administration, admission/bed operations, billing/payment records, documents, audit logs and analytics separately.

The recovery plan must cover:

- Database backups and point-in-time restore where supported/configured.
- Object storage versioning, retention and recovery.
- Database failover and application reconnection.
- Redis loss and cache rebuild; persistent business state must not depend on Redis recovery.
- Celery broker/worker recovery, outbox replay and idempotent task reprocessing.
- Secret/key recovery and controlled rotation.
- Region-level recovery if required by business and regulatory assessment.
- Restore drills in an isolated environment and verified reconciliation afterward.
- Clinical downtime operations and safe reconciliation of actions recorded during downtime.

A successful backup job does not prove recoverability. Maintain evidence that restores have been tested and critical relationships, audit data and documents are intact.

### 27.2 Observability and operational runbooks

Every critical path must emit structured logs, metrics and traces with a correlation/request ID, without logging unnecessary PHI or credentials. Capture per-customer deployment identity, service version, external provider, operation type and sanitized outcome so issues can be diagnosed without leaking clinical payloads.

Define actionable alerts and runbooks for:

- API error/latency spikes and capacity exhaustion.
- PostgreSQL connection saturation, replication/failover or storage alerts.
- Celery queue depth, oldest task age, retry storms and exhausted retries.
- Repeated payer timeouts, invalid responses and failed claim acknowledgments.
- Unreconciled payments/remittances and inventory imbalance.
- S3/document access failures.
- Security alerts and suspected unauthorized access.
- Failed deployments, migrations and health checks.
- Failed backup or restore verification.

Each runbook needs an owner, impact assessment, first checks, safe mitigations, escalation, communication plan, recovery verification and post-incident review criteria.

### 27.3 Performance, load and capacity validation

Create a workload model based on expected hospitals, branches, users, concurrent clinicians, patient counts, daily admissions, medication administrations, diagnostic orders, claim batches, document volume and retention. Test realistic query patterns and payload sizes.

Required test categories:

- Patient search and longitudinal chart loads.
- Admission/bed allocation concurrency.
- Medication due lists and administration writes.
- Lab worklists and result retrieval.
- Claim generation, batch submission and reconciliation.
- Report/export jobs under concurrent usage.
- Database pool exhaustion and slow-query analysis.
- Queue backlog recovery after a dependency outage.
- Large document upload/download and authorization checks.

Do not partition every table in advance. Start with measured indexing and query plans; partition high-volume tables only when volume, retention/deletion needs or measured performance justify the added operational cost.

### 27.4 Clinical validation and operational readiness

A production pilot requires named clinical owners, workflow training, approved clinical configuration, user acceptance testing, patient identity reconciliation, documented support coverage, downtime procedures, recovery drills and a controlled rollout/rollback plan. The clinical owner must sign off on clinically consequential logic and escalation behavior.

### 27.5 P1 exit criteria

Before production go-live, evidence must exist for applicable security review, successful isolation tests, backup restoration, approved RTO/RPO, monitored operational runbooks, payer/provider contract testing, clinical UAT, load testing, incident response readiness and a documented go/no-go decision.

---

## 28. Artifact A: Detailed Data Architecture

Artifact A is the detailed data architecture deliverable. It belongs in `docs/architecture/data-architecture/` and must be versioned with the code. The high-level ERD in section 9 is not a substitute for this artifact.

### 28.1 Required deliverables

1. Domain-by-domain logical ERD.
2. Physical ERD with all tables and relationship cardinalities.
3. Data dictionary, including type, nullability, default, allowed values, source and sensitivity.
4. Index and uniqueness specification tied to query patterns.
5. Data lifecycle, retention, archive and correction rules.
6. Transaction boundaries and concurrency rules.
7. Data classification and access matrix.
8. Historical/version model for clinical and financial facts.
9. Migration and backfill playbook.
10. Terminology/catalog ownership and update process.
11. Data-flow lineage to external providers and analytics sinks.
12. Representative seed/synthetic data strategy.

### 28.2 Data modeling standards

- Use UUID primary keys for distributed-friendly internal identifiers unless a specific domain requires another proven strategy. Do not expose predictable sequential IDs as the only authorization control.
- Use explicit business identifiers (MRN, claim number, invoice number, accession number) separately from database keys.
- Scope patient-facing identifiers to the organization/facility and make uniqueness rules explicit. Never assume an MRN is globally unique across independent hospital deployments.
- Store instants in UTC; retain the applicable facility/time-zone context for clinical and operational display. Date-only values (such as birth date where date-only semantics apply) should not be converted into misleading timestamps.
- Use decimal/numeric types for money, not binary floating point. Store currency explicitly and define rounding policy by country, payer and financial operation.
- Store quantities with explicit units and unit catalogs. Do not compare or aggregate incompatible units silently.
- Use controlled catalogs and codes for clinically significant values. Display labels may change; historical coded values and the source/version must remain traceable.
- Use created/updated metadata for operational records and an explicit actor/recorded-at/effective-at model where clinical or financial semantics require it.
- Do not use a generic `deleted=true` mechanism to erase signed clinical or financial facts. Use status/correction/reversal/void workflows governed by retention policies.
- Make source of truth explicit when data comes from a payer, lab, PACS, pharmacy supplier or another EHR.
- Do not use cross-database foreign keys between customer deployments. Cross-customer exchange requires an authorized external contract or data pipeline.

### 28.3 Domain ownership and sources of truth

| Data | Authoritative owner | Notes |
|---|---|---|
| Organization, branch and department configuration | Organization/facility domain | Changes must be audited and permission-controlled |
| Staff credentials | Staff/credential domain | Verification and expiry are separate from user login status |
| Patient identity | Patient/MPI domain within each customer deployment | Merge/correction requires a controlled workflow |
| Encounter/admission state | Encounter/ADT domain | Must not be independently duplicated in UI or reporting tables |
| Bed occupancy | Bed assignment domain | Current occupancy is derived or maintained consistently from assignment events |
| Medication order | Prescribing domain | Not proof of dispensing or administration |
| Dispensing/stock movement | Pharmacy/inventory domain | Stock ledger is the source for inventory balance reconciliation |
| Medication administration | eMAR/MAR domain | Immutable clinical event with controlled correction |
| Lab result | Lab domain or validated source integration | Preserve corrected-result lineage and source identifiers |
| Imaging report | Radiology domain; images usually in PACS | HIMS holds metadata/report and secured links, not necessarily all DICOM files |
| Eligibility outcome | Insurance domain | Source response and normalized meaning must both be traceable where retained |
| Claim lifecycle | Claims domain | Submission attempts and adjudication events have their own records |
| Charges/invoices/payments | Billing/finance domain | Use ledger-like movements, allocations and reversals |
| Audit event | Audit domain | Separate security boundary and retention rules |

### 28.4 Suggested minimum financial model

Do not represent the full revenue cycle as a single invoice and a boolean paid flag. At minimum, specify:

- `Charge`: source service, encounter/admission, quantity, price snapshot, code, date of service and status.
- `Invoice` and `InvoiceLine`: issue status, currency, price/tax snapshots, totals and patient responsibility calculations.
- `Claim`: payer, patient/coverage references, claim type, current lifecycle state and business identity.
- `ClaimSubmission`: each submission attempt/version, payload reference/hash, provider reference, timestamp and response.
- `ClaimEvent`: acknowledgment, rejection, adjudication, denial, appeal or status change.
- `Remittance`: payer remittance identity, source reference and received totals.
- `RemittanceLine`: claim/service-line allocation, allowed amount, paid amount, adjustment codes and patient responsibility as returned.
- `Payment`: actual incoming/outgoing financial transaction and unique provider/bank reference.
- `PaymentAllocation`: allocations to invoices/claims/patient balances.
- `Adjustment` and `Refund`: reason, approval, source transaction and reversal linkage.
- `ReconciliationRun` and `ReconciliationException`: source totals, matched/unmatched records, difference and resolution.

Use immutable postings or controlled reversal entries for financial corrections. Never silently edit a posted payment to make reconciliation appear successful.

### 28.5 Suggested clinical history model

Clinical notes, diagnostic reports and signed documents should keep their author, signing identity, timestamps, state, version and amendment/correction reason. A correction should create a new version or linked amendment rather than erase the signed original. For observations, preserve effective measurement time, recorded time, source, unit, value, status and correction history.

### 28.6 Index and query design

For each high-volume query, record the access pattern and index that supports it. Expected examples include:

- Patient exact match by organization-scoped identifier.
- Patient search by approved demographic/search index, with privacy constraints.
- Active encounters/admissions by facility and state.
- Beds by facility/ward/status and compatible type.
- Due medication administrations by unit, scheduled time and status.
- Lab worklists by facility, status, priority and requested time.
- Claims by payer, state, submission date and customer-specific claim identity.
- Audit events by actor, resource, action and timestamp.

Validate indexes with production-like data volume and query plans. Avoid indexing every column: indexes increase write cost and storage. Add partitioning only after measuring volume/retention requirements.

### 28.7 Database migration rules

- Generate migrations in development and review them in pull requests.
- Run `makemigrations --check` and migration tests in CI.
- Test migrations with a representative dataset size and the previous application version.
- Use a dedicated release migration job with a lock; do not have every web container migrate on startup.
- Use expand-and-contract changes for zero/low downtime deployments.
- Back up and verify recovery before risky data transformations.
- For backfills, provide progress, checkpoints, idempotency, rate limiting and restart behavior.
- Record the schema version deployed per customer and verify drift before rollout.

### 28.8 Artifact A acceptance criteria

Artifact A is accepted when all implemented P0 domains have reviewed physical schemas, data dictionaries, constraints, source-of-truth ownership, sensitive-data classification, indexes for critical query patterns, retention/correction rules, migration procedures and automated tests for critical invariants.

---

## 29. Artifact B: API and Integration Contracts

Artifact B defines stable contracts between React, Django domain modules, background workers and external providers. It belongs in `docs/architecture/api-and-integrations/` and should be represented using versioned OpenAPI documents plus provider-specific integration notes.

### 29.1 API baseline

- Prefix external REST APIs with `/api/v1/` until an explicitly managed major version change is required.
- Use resource nouns and explicit action endpoints for business transitions.
- Define pagination, filtering, ordering and maximum page sizes consistently.
- Use a consistent error format based on RFC 9457 Problem Details or a documented equivalent.
- Generate and propagate a request/correlation ID through API requests, worker messages and external calls.
- Apply authentication and object-level authorization at every endpoint.
- Validate all foreign-key references against the active customer's database and allowed facility scope.
- Never expose provider credentials or raw secrets to the frontend.
- Avoid putting PHI or tokens in URLs, analytics, traces and client-side error reports.
- Generate and validate OpenAPI schema in CI to catch accidental contract changes.

### 29.2 Example error response

```json
{
  "type": "https://api.example.invalid/problems/bed-not-available",
  "title": "Bed not available",
  "status": 409,
  "detail": "The selected bed is no longer available.",
  "code": "BED_NOT_AVAILABLE",
  "request_id": "server-generated-correlation-id"
}
```

The example domain is intentionally reserved; use the actual product domain when configured. Do not return internal exception messages or sensitive data in public errors.

### 29.3 Idempotency and concurrency contract

For operations where duplicate submission can create financial or clinical harm, define idempotency semantics explicitly. Examples include claim submission, payment posting, external eligibility calls where supported, inventory issue, dispensing and other non-repeatable operations.

A write request may accept an `Idempotency-Key` header. Persist the key scoped to customer, actor/client, operation and request fingerprint, with a documented retention window. A repeated key with the same request should return the stored outcome; reusing a key with a different payload should return a conflict. Do not assume an external provider honors the same idempotency key unless documented by that provider.

For concurrent edits, use version fields or ETags/`If-Match` for resources where stale writes are dangerous. Return a conflict instead of silently overwriting another clinician's edits.

### 29.4 Synchronous versus asynchronous API behavior

Use synchronous responses for operations that are short, deterministic and safe within the request latency budget. For long-running or provider-dependent work, persist an operation record and return `202 Accepted` with an operation/status URL. The client should poll or subscribe for status. The operation record must survive worker restarts and must not rely solely on the Celery result backend.

### 29.5 Endpoint contract template

Every endpoint specification should include:

```text
Endpoint ID:
Method and path:
Business purpose:
Actor/permission required:
Customer/facility scope:
Request schema:
Response schema:
Validation rules:
Allowed current states:
Resulting state:
Idempotency key behavior:
Concurrency control:
Database transaction:
Audit event:
Outbox/domain event:
External calls:
Timeout and retry policy:
Expected error codes:
Rate/volume assumptions:
Metrics and alerts:
Automated test cases:
Backward-compatibility policy:
```

### 29.6 Provider adapter contract

Each insurance, laboratory, imaging or messaging adapter should document:

- Provider and supported capabilities.
- API/transaction version and endpoint allowlist.
- Authentication and key rotation procedure.
- Network/IP and enrollment prerequisites.
- Request/response schema and field mappings.
- Provider identifiers and correlation rules.
- Rate limits, timeouts and retryable errors.
- Idempotency/reconciliation strategy.
- Polling, webhook signature validation and replay protection.
- Normalized status mapping and unknown-status behavior.
- Raw payload retention and redaction rules.
- Sandbox fixtures and contract tests.
- Operations owner, support contact and escalation process.

Never convert unknown provider statuses into a successful, paid, eligible or inactive state. Preserve them as an explicit unknown/manual-review outcome until properly interpreted.

### 29.7 Domain event envelope

For internal asynchronous events, define a versioned envelope such as:

```json
{
  "event_id": "uuid",
  "event_type": "claim.submission.requested",
  "event_version": 1,
  "occurred_at": "2026-01-01T12:00:00Z",
  "customer_id": "customer-reference",
  "facility_id": "facility-reference",
  "aggregate_type": "claim",
  "aggregate_id": "claim-reference",
  "correlation_id": "request-correlation-id",
  "causation_id": "prior-event-or-request-reference",
  "payload": {
    "submission_id": "claim-submission-reference"
  }
}
```

Values are examples only. Keep event payloads minimal and avoid including unnecessary PHI. Store durable outbox state transactionally with the aggregate change. Consumers must deduplicate by `event_id` or a suitable business key and tolerate reordering where ordering is not guaranteed.

### 29.8 Webhooks

For inbound webhooks:

- Verify provider signatures using documented mechanisms.
- Validate timestamp/replay windows where supported.
- Store provider event ID and reject or deduplicate repeats.
- Acknowledge quickly after durable receipt; process business logic asynchronously where appropriate.
- Do not trust the payload as authorization to access arbitrary records.
- Reconcile webhook events with a provider status API when payloads are incomplete or contradictory.
- Monitor signature failures and repeated delivery without logging sensitive payloads.

### 29.9 Artifact B acceptance criteria

Artifact B is accepted when the implemented API surface has OpenAPI contracts, permission requirements, standard error semantics, concurrency/idempotency rules, contract tests, provider capability documentation, webhook/retry behavior and versioning rules. Breaking changes must be detected in CI or reviewed through an explicit versioning process.

---

## 30. Artifact C: AWS Infrastructure and Operations Design

Artifact C is the deployable infrastructure and operating model. It belongs in `infrastructure/` and `docs/architecture/aws/`. Infrastructure should be declarative, reviewed, reproducible and testable.

### 30.1 AWS account strategy

Use AWS Organizations for governed multi-account operations where feasible. A reasonable target is:

```text
AWS Organization / Management
  |
  +-- Security / Log Archive accounts (where justified)
  +-- Shared Tooling / CI account (optional)
  +-- Non-production accounts
  |     +-- Development
  |     +-- QA
  |     +-- Staging
  +-- Production accounts
        +-- Customer A production stack and database
        +-- Customer B production stack and database
        +-- ...
```

This diagram shows a possible account design, not a requirement that every hospital must immediately receive a separate AWS account. The isolation requirement confirmed for the product is dedicated deployment and database per hospital organization. Decide whether a dedicated customer AWS account is also required based on the threat model, contract, risk review, operational model and cost. Strongest isolation generally comes from a separate customer account; isolated services/databases within a guarded account can cost less but provide a different boundary.

Do not place access keys in GitHub code or static repository variables. Prefer short-lived AWS credentials through GitHub Actions OIDC roles with tightly scoped permissions, where supported and configured. Keep deployment roles separated by environment; the CI role for Development must not be able to modify Production.

### 30.2 Network and service topology

Target shape for a production customer deployment:

```text
Internet / Hospital Users
          |
          v
  Route 53 + TLS
          |
          v
  CloudFront / WAF (as required)
          |
          v
  Public ALB (public subnets)
          |
          v
  ECS Fargate API tasks (private subnets)
          |             |                 |
          v             v                 v
   RDS PostgreSQL  ElastiCache Redis   S3 via IAM/API
   (private)       (private)           (private access policy)
          |
          v
 Automated backups / PITR / restore verification

Separate private worker tasks:
Celery Worker -> broker/queue -> PostgreSQL / approved external APIs
```

Minimum network principles:

- RDS and Redis must not be publicly reachable.
- Place application and worker tasks in private subnets where possible.
- Restrict security groups to the smallest required inbound/outbound paths.
- Use egress controls and private service endpoints where cost and use cases justify them.
- Define outbound routing for payer-specific IP/network requirements. Do not assume a general NAT egress path satisfies every US payer/network requirement.
- Separate management access from application access.
- Restrict and audit database access; prefer managed identity/short-lived access tooling where supported.

### 30.3 Recommended AWS service mapping

| Capability | Initial recommendation | Design note |
|---|---|---|
| Web UI | S3 + CloudFront or a managed frontend platform | Keep static frontend independent from API release where useful |
| Django API | ECS on Fargate | Avoid managing Kubernetes until needed |
| Celery workers | Separate ECS services/task definitions by queue | Scale critical/background workload independently |
| PostgreSQL | RDS for PostgreSQL | Decide instance/cluster isolation based on customer boundary and availability requirements |
| Redis | ElastiCache | Isolate per customer and environment; do not store authoritative business state here |
| Documents | S3 | Block public access, use least-privilege policies, versioning/retention where required |
| Encryption | KMS | Define key ownership, rotation and recovery |
| Secrets | Secrets Manager | Separate secrets per customer and environment |
| DNS and certificates | Route 53 and ACM | Automate customer domain/certificate lifecycle |
| WAF | AWS WAF where applicable | Managed rules plus application-specific rate/abuse controls |
| Monitoring | CloudWatch + tracing/metrics stack | Add cost and PHI-safe logging policy |
| IaC | Terraform | Pin providers/modules and review plans before apply |
| CI/CD | GitHub Actions with OIDC where supported | Environment-scoped deployment roles and approval controls |

Final service selection depends on region availability, contractual obligations, payer integration networking and cost estimates.

### 30.4 Infrastructure-as-code structure

Suggested layout:

```text
infrastructure/
  terraform/
    modules/
      network/
      ecs-service/
      rds-postgres/
      redis/
      object-storage/
      kms/
      secrets/
      monitoring/
      customer-environment/
    environments/
      development/
      qa/
      staging/
      production/
    customers/
      customer-a/
      customer-b/
  docker/
  scripts/
  runbooks/
```

Do not copy/paste separate hand-maintained Terraform stacks for every hospital. Reuse reviewed modules, feed per-customer configuration through controlled inputs, isolate Terraform state and protect production state access. Keep secrets out of state wherever possible; if a provider must store sensitive state, apply encryption, restricted access and lifecycle controls.

### 30.5 Database lifecycle and migrations

- Provision database resources with encryption, private networking, backups and monitoring enabled.
- Use separate credentials per application role where appropriate (runtime, migration, read-only reporting, support/break-glass).
- Apply schema migrations through a dedicated release job, not every API container at startup.
- Lock migration execution to prevent concurrent customer migration jobs.
- Track the deployed application version and schema version per customer.
- Roll forward using backward-compatible migrations whenever possible.
- Use a tested restore/rollback plan for migrations that change or transform data.
- Do not assume application rollback reverses database changes.

### 30.6 Document and object-storage controls

- Block public access.
- Scope access by customer, document classification and permitted operation.
- Use short-lived signed URLs only after server-side authorization, with appropriate expiry.
- Consider versioning, Object Lock or retention controls only when the legal/operational requirement is understood and lifecycle behavior is tested.
- Scan uploads where appropriate, validate file types and size limits, and store metadata separately from the binary.
- Log access events without putting document contents or sensitive filenames into general logs.

### 30.7 AWS operating cost controls

Cloud cost is driven by region, uptime, instance sizing, database HA, data volume, network egress, NAT gateways, load balancers, WAF, log retention, backups and the number of dedicated customer deployments. Obtain a region-specific estimate from the [AWS Pricing Calculator](https://calculator.aws/) and set AWS Budgets alerts before creating long-running resources.

- Turn off temporary non-production resources when not in use, if the operating model permits.
- Keep local development independent from production cloud resources.
- Use realistic but smaller non-production capacity; preserve architectural parity rather than identical production scale.
- Set log retention and storage lifecycle policies deliberately.
- Measure per-customer costs from the first deployment.
- Test backup and recovery without leaving duplicate expensive resources running unnecessarily.

### 30.8 Artifact C acceptance criteria

Artifact C is accepted when a new customer environment can be provisioned from reviewed code, the network and secrets are isolated, migrations and deployments are repeatable, backup/restore is demonstrated, alarms and runbooks exist, and an environment can be upgraded or recovered without manual undocumented steps.

---

## 31. Environment Strategy: Local, Development, QA, Staging and Production

The delivery model consists of a developer's local environment plus four managed environments: Development, QA, Staging and Production. Local is not counted as one of the shared managed environments.

### 31.1 Environment purpose and rules

| Environment | Purpose | Data | Deployment behavior | Release authority |
|---|---|---|---|---|
| Local | Fast developer feedback and debugging | Synthetic/fake data only by default | Developer starts services locally | Developer |
| Development | Integration environment for merged work | Synthetic/test data | Automatically deploy a passing `develop` build | Engineering owner |
| QA | Dedicated functional, regression and integration testing | Controlled synthetic/test data | Promote an immutable release candidate | QA owner |
| Staging | Production-like pre-production validation/UAT | Synthetic or formally approved de-identified data; never casually copy PHI | Promote the same artifact proven in QA | Release manager / QA / product or clinical owner as defined |
| Production | Real hospital operations | Real data under approved policies | Deploy only the approved artifact that passed staging | Authorized production approver |

### 31.2 Staging must be production-like, not a copy of live patient data

“Exact copy of production” should mean the same application artifact, deployment topology, network controls, configuration model, database engine/version, integration contracts, migration mechanism and observability—not an uncontrolled copy of the production database or secrets.

Staging should be as close to production as is operationally practical, but its scale can be smaller when capacity and performance tests are separately designed. Use synthetic data or an approved de-identification process. Do not copy production patient data, insurance responses, documents, credentials or tokens into staging without explicit legal, security and operational approval.

The environments should have different credentials, database instances, encryption/access boundaries and external-provider credentials. A staging job must never be able to write to Production.

### 31.3 Local development without AWS

Local development should be self-contained and reproducible. Use:

- Python and a project-defined virtual environment.
- Node.js version pinned by the repository (for example `.nvmrc` or an equivalent version file).
- Docker Compose for PostgreSQL, Redis, local object-storage emulation if needed and development dependencies.
- Django API and Celery workers running locally or as disposable containers.
- Synthetic patient, encounter, medication, lab and claim fixtures.
- Mock insurance/payer adapters or provider sandbox endpoints where authorized.

A developer must be able to run unit and most integration tests without a paid AWS environment. Use a local S3-compatible emulator or an adapter/fake in tests; use actual AWS for cloud-specific integration, IAM, networking, storage policy and deployment validation in managed environments.

### 31.4 Configuration management

Keep configuration external to code. Maintain a documented schema for settings such as database connection, feature flags, country, timezone, integration endpoint and environment mode. Store credentials in a secret manager, not checked into Git. Use separate secret sets per environment and per customer.

Do not allow a production endpoint or credential to be loaded accidentally by local/test settings. Add a startup guard that refuses dangerous combinations, such as a local environment targeting a production database.

### 31.5 Environment promotion policy

The required business flow is:

1. Ticket is implemented on a short-lived branch and merged to Development after review/checks.
2. The change is deployed to the Development environment and verified.
3. A release candidate is promoted to QA; QA tests and records a pass/fail result.
4. The QA-approved artifact is promoted to Staging; staging/UAT validates release readiness.
5. The approved staging artifact is promoted to Production only after all gates pass.

**Important implementation detail:** promote the same built artifact (ideally the exact immutable container image digest), rather than rebuilding different binaries for QA, Staging and Production. Environment-specific configuration and secrets may differ; the application artifact must not. This materially reduces “it passed in staging but a different build reached production” risk.

If QA or Staging finds a defect, fix it through a ticket and pull request. Create a new release candidate, rerun the required checks, and restart promotion from the earliest affected gate. Do not patch a production server manually.

---

## 32. GitHub Tickets, Branching and Promotion Workflow

Use a GitHub Organization to own the repository and permissions rather than tying business-critical intellectual property to one developer's personal account. Use GitHub Issues and GitHub Projects for ticketing, backlog, dependencies, milestones and delivery tracking. A separate Jira subscription is not mandatory if GitHub Projects satisfies the team's workflow.

### 32.1 Ticket hierarchy

Recommended hierarchy:

- **Epic:** major business domain or delivery objective, e.g. Patient Identity, Medication Administration, Claims and Remittance, Customer Provisioning.
- **Feature:** user-visible or system capability within an epic.
- **Story/task:** a small, reviewable unit of behavior or engineering work.
- **Bug:** behavior differing from approved requirements.
- **Security/privacy issue:** reported and access-restricted as appropriate; never put real PHI or secrets in a public issue.
- **Tech debt/ADR:** changes needed to keep the platform maintainable or alter an approved architecture decision.

Do not create one giant ticket for “build hospital management system.” Decompose by domain, workflow and acceptance criterion. Make tickets small enough to review and test without losing the end-to-end business context.

### 32.2 Required ticket template

Each feature/bug should contain:

```text
Title:
Ticket ID:
Epic / domain:
Business or clinical reason:
User story / intended behavior:
In scope:
Out of scope:
Actors and required permissions:
Preconditions:
Acceptance criteria (Given / When / Then):
Validation and edge cases:
Data model / migration impact:
API / event / integration impact:
Audit and privacy impact:
Idempotency / concurrency impact:
Failure and retry behavior:
Observability / metrics impact:
Testing plan:
Rollback / recovery considerations:
Dependencies / blockers:
Risk level (clinical, privacy, financial, operational):
Approver / domain owner:
Definition of Done:
```

Tickets must not contain actual patient data, production credentials, access tokens or unredacted insurance payloads. Refer to synthetic examples or secure incident systems instead.

### 32.3 GitHub Project status workflow

Suggested statuses:

`Backlog -> Ready -> In Progress -> Code Review -> Ready for Development -> In Development Validation -> QA Ready -> QA In Progress -> QA Passed -> Staging/UAT -> Ready for Production -> Released`

Use `Blocked` as a distinct status or field with an explicit reason and owner. Status labels should represent actual work state, not merely the branch name. Track priority, domain, risk, owner, sprint/milestone, target release and dependencies as fields where useful.

### 32.4 Branch model

Recommended simple release-oriented model:

- `main`: production release history and approved production version.
- `develop`: integration branch; passing merges deploy to the Development environment.
- `feature/HIMS-123-short-description`: short-lived feature branch from `develop`.
- `bugfix/HIMS-456-short-description`: ordinary defect branch from the appropriate integration/release branch.
- `release/1.2.0` (or equivalent): temporary stabilization branch for a release candidate when needed.
- `hotfix/HIMS-789-short-description`: controlled emergency fix from the production release baseline, then merged/backported to `develop`.

For a small team, the process can be simpler, but `main` and deployment credentials must remain protected. Avoid having developers push directly to protected branches.

### 32.5 Pull-request rules

- Every change links to one or more GitHub Issues/tickets.
- At least one reviewer approves meaningful changes; high-risk clinical, security and financial changes require the designated domain/security/finance reviewer according to policy.
- All required automated checks pass.
- Discussions are resolved.
- Database migrations, API changes, permissions and audit behavior are explicitly included in review when applicable.
- No secrets, patient data or generated real clinical documents are committed.
- Use CODEOWNERS for security, infrastructure, clinical rules, finance and integration adapters where practical.
- Block force-push/deletion of protected branches and require PRs for changes.

### 32.6 Ticket-to-release sequence

```text
GitHub Issue / Ticket
          |
          v
Feature branch from develop
          |
          v
Local implementation + tests
          |
          v
Pull Request to develop
          |
          v
CI: lint, types, unit, integration, security checks
          |
          v
Review + required approvals
          |
          v
Merge to develop
          |
          v
Auto-deploy Development -> smoke/integration validation
          |
          v
Cut release candidate from a known commit
          |
          v
Build once -> immutable image/artifact + commit/SBOM metadata
          |
          v
Promote same artifact to QA -> QA sign-off
          |
          v
Promote same artifact to Staging -> UAT/release approval
          |
          v
Promote same artifact to Production -> smoke checks/monitoring
          |
          v
Close tickets against deployed release and record evidence
```

The user-facing order remains Development → QA → Staging → Production. The implementation should treat each environment as a deployment target, not necessarily a separate long-lived code branch. Long-lived `qa`, `staging` and `production` branches often drift and make it harder to prove that the exact tested artifact reached production.

### 32.7 Defect found at a later gate

- **Development defect:** fix the ticket/branch, rerun CI and redeploy Development.
- **QA defect:** create a defect ticket, fix it through PR, build a new release candidate, and rerun impacted CI and QA suites.
- **Staging defect:** do not promote the previous candidate; fix the release candidate, repeat affected QA tests, then redeploy Staging and repeat acceptance.
- **Production incident:** follow incident severity policy. Roll back to a known-good compatible application artifact if safe. Database changes require backward-compatible migration strategy or a tested forward fix; application rollback alone may not restore schema/data.

### 32.8 Branch protection and GitHub plan note

Configure branch rules/rulesets for PR review, status checks, conversation resolution and restricted pushes. GitHub plan features differ, especially for environments and deployment approvals in private repositories. Before paying, verify the current entitlement for the exact repository owner/plan. Current GitHub documentation says private-repository environment secrets/deployment environment support require an eligible paid plan, while required-reviewer/wait-timer protections are restricted on Free/Pro/Team to public repositories; review current docs because product entitlements can change. Links: [GitHub pricing](https://github.com/pricing), [protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

---

## 33. CI/CD Quality Gates and Release Promotion

### 33.1 Pull-request CI gates

Recommended pipeline stages:

1. Formatting and linting for Python, JavaScript and TypeScript.
2. Python type checks where adopted, frontend type-check and build.
3. Django system checks and migration consistency checks.
4. Unit tests for services and pure domain rules.
5. Integration tests against PostgreSQL and Redis test services.
6. API permission and customer-isolation tests.
7. Concurrency tests for beds, inventory and financial posting where changed.
8. Dependency vulnerability scan and secret scanning.
9. Static analysis/security checks appropriate to the repository and plan.
10. Build container and verify it starts with production-like settings.
11. Contract tests for APIs/events and mock/sandbox external adapters.

Not every pull request needs the full expensive end-to-end suite, but critical safety checks must run before merge. Use a fast PR suite and a broader scheduled/release suite.

### 33.2 Environment gates

| Gate | Required evidence | Failure behavior |
|---|---|---|
| Development | Deployment healthy, smoke tests, migrations, integration logs reviewed | Block release candidate or fix ticket |
| QA | Test plan passed, regression passed, contract/integration tests passed, no unresolved release-blocking defects | Candidate rejected; fix and rerun |
| Staging | Production-like smoke tests, UAT approval, migration/recovery plan reviewed, environment-specific configuration validated | No production promotion |
| Production | Explicit release approval, backups/recovery posture confirmed, change window/communication complete, safe migration path and rollback/forward plan | Stop or roll back application where safe; incident process if already released |

### 33.3 Build once, promote many

Build the container from a known source commit one time. Tag it for traceability but use the immutable digest as the deployment identity. Promote that exact image digest through Development/QA/Staging/Production. Do not run a separate build for each environment, since dependency resolution or build-time differences can create different artifacts.

Record per deployment:

- Git commit SHA and release tag.
- Container image digest and build provenance.
- Dependency lockfile/SBOM reference where adopted.
- Database migration version.
- Deployment actor/workflow run.
- Environment/customer deployment identifier.
- Test and approval evidence.
- Resulting health/smoke-check outcome.

### 33.4 Database migration gate

Use a dedicated migration job with narrowly scoped credentials. The pipeline must fail if a migration is invalid or a required check fails. Separate schema changes that require sequencing from normal feature changes. Follow expand-and-contract migration patterns so the currently deployed version and newly deploying version can coexist during rollout where needed.

Do not automatically reverse a schema migration in production unless that rollback has been explicitly designed and tested. In many cases, a forward repair is safer than trying to reverse transformed clinical or financial data.

### 33.5 Production rollout controls

- Restrict deployment permission to authorized release operators/workflows.
- Use an explicit release approval appropriate to the repository plan and governance needs.
- Prefer gradual rollout/health checks when the hosting architecture supports it.
- Run smoke tests after deployment without creating or altering real patient records unintentionally.
- Monitor errors, latency, database health, worker lag and critical business signals after deployment.
- Define a rollback threshold and who can invoke rollback.
- Record release notes and notify affected stakeholders.
- Keep the prior known-good artifact available.

### 33.6 Practical GitHub Actions structure

```text
.github/
  ISSUE_TEMPLATE/
    feature_request.md
    bug_report.md
    security_issue.md
  pull_request_template.md
  CODEOWNERS
  workflows/
    pull-request-ci.yml
    deploy-development.yml
    promote-qa.yml
    promote-staging.yml
    promote-production.yml
    dependency-review.yml
    scheduled-security-tests.yml
```

Use reusable workflows where helpful, pin third-party actions to reviewed versions/commit SHAs, grant least-privilege `GITHUB_TOKEN` permissions and do not expose cloud secrets to untrusted pull-request code. Prefer AWS OIDC federation with narrow IAM roles rather than long-lived AWS access keys, where supported.

---

## 34. Development Purchases and Cloud Cost Strategy

### 34.1 Do you need to purchase AWS immediately?

**No. AWS is not required for the initial development phase.** You can build most of the system on your local machine before purchasing or deploying cloud infrastructure.

Local development can run:

- Django/DRF and Celery.
- PostgreSQL through a local installation or Docker Compose.
- Redis through Docker Compose.
- React/TypeScript and frontend tooling.
- Local file storage or an S3-compatible emulator/fake adapter.
- Synthetic clinical, insurance and billing fixtures.
- Mock provider adapters and contract tests.

This lets you build models, APIs, UI, business rules, permissions and most tests without AWS running continuously. AWS becomes necessary when you are validating the real AWS infrastructure, IAM/networking, cloud storage policies, managed database behavior, deployment pipeline, cloud observability, customer environments or external-provider network constraints.

Do not send real patient information through unapproved local services or test fixtures. Use synthetic data unless the environment and handling have been explicitly approved.

### 34.2 What you likely need to pay for

| Item | Required immediately? | Guidance |
|---|---|---|
| Development workstation | Already available if hardware is sufficient | More RAM/SSD helps; no dedicated server is needed to begin |
| Python, Node.js, Git | No purchase | Use supported versions pinned by the repository |
| PostgreSQL and Redis | Usually no purchase for local use | Run locally or through containers; review distribution/service terms where applicable |
| Docker | Depends on use and licensing terms | Review Docker Desktop licensing for your organization; alternatives include supported local container runtimes or direct installs |
| GitHub repository | No, basic private repository hosting is available on Free | Use an organization-owned repository for business ownership and access control |
| GitHub Issues and Projects | Usually no separate purchase needed for basic planning | Verify current limits/features against the plan |
| GitHub Team / other paid GitHub plan | Maybe | Consider when you need organization features, private deployment-environment secrets or controls available only on the relevant plan; check current plan limits before buying |
| AWS account | Not needed for local feature development | Use a controlled non-production account when beginning cloud infrastructure validation |
| AWS managed services | Not required at the beginning | Pay when running shared Development/QA/Staging or Production workloads; shut down temporary resources where safe |
| Stedi or payer connectivity | Not needed for mocked local development | Contract, sandbox, enrollment and transaction charges/access depend on provider and customer arrangement; confirm directly |
| Domain name/TLS | Not needed for local development | Buy/configure when a hosted environment or customer-facing pilot needs a domain |
| Monitoring/security products | Not all at once | Start with CI security scans, cloud-native logs/metrics, alerting and documented incident processes; add paid tools as needs justify |
| Licensed clinical content | Before the affected domain ships | Drug-interaction knowledge base (US and India vendors differ), CPT (AMA-licensed), DRG grouper for US inpatient claims; SNOMED CT, LOINC and RxNorm are free but carry license/affiliate obligations |
| Messaging providers | Before notifications ship | SMS (India requires DLT template/entity registration), email (e.g. Amazon SES), WhatsApp Business where used |
| Compliance and assurance | Before production | Penetration testing, security/compliance attestation customers require (e.g. SOC 2/HITRUST in the US), legal review, cyber insurance |
| AWS Business Associate Addendum | Before any PHI reaches AWS (US) | No fee; accept via AWS Artifact and use only HIPAA-eligible services for PHI |
| Engineering, clinical and QA staff | Throughout | Usually the dominant cost; budget explicitly alongside infrastructure |

A HIMS is a commercial healthcare product. Before production, budget for security review, legal/compliance review, external testing, payer/provider onboarding, backups/monitoring, support coverage and recovery exercises—not just compute resources.

### 34.3 AWS account and free usage

AWS offer terms can change. The current official AWS Free Tier documentation says new accounts can receive $100 in credits and may earn up to another $100 by completing eligible activities; a Free account plan is described as suitable for experimenting for up to six months, subject to its terms and service restrictions. This does not mean every managed service or production architecture is free. Confirm account-specific eligibility and terms in the AWS console and official documentation: [AWS Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html).

Use [AWS Pricing Calculator](https://calculator.aws/) to estimate each planned environment. Include database storage/compute and HA configuration, Redis, running ECS tasks, load balancers, NAT/data transfer, WAF, logs, backups, object storage, KMS usage, monitoring and the number of dedicated hospital deployments. Region and availability choices materially change cost. Set budget alerts before creating resources.

### 34.4 Recommended cost-conscious rollout

**Stage A — Local-first (no cloud spend required):** Build foundations and domain modules with local services, synthetic data, mock integrations and automated CI.

**Stage B — Shared non-production AWS:** Provision Development first. Add QA and Staging when needed for team/hospital validation. These can be smaller than production while keeping the same infrastructure pattern. Keep environments isolated and shut down nonessential resources when appropriate.

**Stage C — Customer pilot:** Add a dedicated deployment and database for the first pilot hospital, with monitoring, backups, secrets isolation, data-flow review, access controls and a restore drill.

**Stage D — Production fleet:** Automate per-customer provisioning, upgrades, backup verification, per-customer cost reporting and security isolation before onboarding many hospital organizations.

Avoid provisioning four full-size, always-on environments plus one stack per hospital before the application has a validated workload model. Conversely, do not declare production-ready by testing only locally; cloud integration, identity/network policies, backups, deployment and recovery must be tested in managed environments.

---

## 35. Definition of Done and Production Release Gates

### 35.1 Definition of Done for a ticket

A ticket is complete only when all applicable items are true:

- [ ] Acceptance criteria are met and demonstrated.
- [ ] Code is reviewed and merged through the approved pull-request process.
- [ ] Unit/integration/API tests are added or updated.
- [ ] Permissions and customer/facility isolation are tested.
- [ ] Data migrations are reviewed and tested where applicable.
- [ ] Audit, logging and monitoring effects are considered.
- [ ] Idempotency, concurrency and retry behavior are covered where required.
- [ ] API contracts and documentation are updated.
- [ ] No secrets or sensitive real data are committed.
- [ ] The change is deployed to the required target environment and verified.
- [ ] QA evidence is attached for a release-bound change.
- [ ] Security, clinical, finance or interoperability approvals are obtained when the ticket requires them.
- [ ] Rollback/forward-recovery implications are documented.

### 35.2 Release go/no-go checklist

A release cannot progress to production unless all applicable gates are satisfied:

- [ ] Source commit and immutable artifact are identified.
- [ ] Required CI/security checks pass.
- [ ] Open release-blocking defects are resolved or formally accepted by the appropriate authority.
- [ ] QA regression and integration results are approved.
- [ ] Staging/UAT sign-off is recorded.
- [ ] Database migration compatibility has been reviewed.
- [ ] Backup and recovery posture is acceptable for the change.
- [ ] Environment configuration and secrets are verified without exposing them.
- [ ] Monitoring and alert thresholds are ready.
- [ ] Release owner and incident responder are available.
- [ ] Rollback or forward-fix strategy is recorded.
- [ ] Customer/hospital communication and downtime requirements are addressed.
- [ ] Clinical/financial approvals are present for high-risk changes.

### 35.3 Never bypass these controls casually

Do not merge directly to protected branches, deploy an unreviewed commit to Production, patch running servers manually, disable authorization to make a test pass, copy production patient data into Staging without approval, or use a successful HTTP response as proof that a financial/clinical operation was committed correctly.

Emergency hotfixes may use a shortened route only under a documented incident policy with after-the-fact review, testing and backport to the normal development branch.

---

## 36. Open Architecture Decisions and Approval Register

Record a decision owner and due date for every open item. Recommended items to close during discovery:

| Decision | Questions to resolve | Owner(s) |
|---|---|---|
| AWS account isolation | Separate customer account for every hospital, or isolated customer stacks in shared accounts? | Architecture + Security + Finance |
| AWS regions/data residency | Which region(s) for each country/customer, including backups and logs? | Security + Legal/Compliance + Operations |
| GitHub plan | Which plan supports private repos, required checks, environment secrets, approvals and team access needed for the release process? | Engineering lead / organization owner |
| Source control ownership | Which GitHub Organization owns repositories, billing and access? | Business owner + Engineering lead |
| Identity provider | Native authentication versus enterprise SSO/identity integration? | Security + Product |
| Clinical data standards | Which terminology systems and FHIR versions/implementation guides are required by initial customers? | Clinical informatics + Integration lead |
| Insurance scope | Which concrete US payers/Stedi operations and Indian insurers/TPAs/programs are in initial rollout? | Revenue cycle + Integration lead |
| Imaging/lab integration | Which PACS, modalities, LIS and instrument vendors are in scope? | Clinical operations + Integration lead |
| Downtime operations | What paper/offline process and reconciliation are approved by each hospital? | Clinical governance + Operations |
| RTO/RPO | What are acceptable recovery targets by clinical/financial domain? | Operations + Clinical leadership + Business owner |
| Audit/retention | Which events and records are retained for how long under which jurisdiction/policy? | Compliance + Security + Records management |
| Clinical sign-off | Who approves medication, ICU, surgery and critical-result rules? | Medical director / clinical governance |
| Finance sign-off | Who approves billing, coding, remittance and reconciliation rules? | Finance/revenue-cycle owner |
| Production access | Who can deploy, approve, view sensitive logs and access databases? | Security + Operations |
| Production approval mechanism | GitHub Enterprise environment required-reviewers, or an alternative auditable approval gate on GitHub Team? (see 32.8) | Engineering lead + Security |
| Celery broker | Redis (current default) versus Amazon SQS or RabbitMQ for production durability (see ADR-010 in `docs/decisions/`) | Architecture + Operations |
| Session/authentication model | Server-side session cookies versus tokens for the browser SPA (see ADR-011) | Security + Architecture |
| Customer isolation tiers | Dedicated database on a shared cluster versus dedicated instance/account per customer, and per-customer unit economics | Architecture + Finance + Security |
| Licensed clinical content | Which drug-knowledge, CPT, DRG and terminology licenses are needed per market? | Clinical informatics + Finance |

Do not leave these as undocumented assumptions. Each decision must have a recorded answer, rationale, trade-offs and revisit criteria.

---

## Version 2 Closing Recommendation

Treat the original blueprint as the product-wide map and this v2 specification as the implementation and delivery control layer. The next engineering work should be split into traceable tickets and supported by Artifact A (Detailed Data Architecture), Artifact B (API and Integration Contracts) and Artifact C (AWS Infrastructure and Operations Design).

Start locally without requiring AWS for every developer. Put source code, tickets, pull requests, architecture decisions, tests and release evidence in the company's GitHub Organization. Stand up the managed Development, QA, Staging and Production environments incrementally. Promote the same immutable application artifact through each gate, use synthetic/de-identified test data outside Production, and prohibit production deployment until technical, clinical, security, operational and financial release criteria are satisfied.

This approach avoids both extremes: it does not force expensive infrastructure before it is useful, and it does not treat a successful local demo as proof of production readiness.

