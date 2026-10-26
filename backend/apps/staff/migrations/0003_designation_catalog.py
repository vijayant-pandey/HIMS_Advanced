"""Designation catalog + extended specialty/qualification catalogs (HIMS-STAFF-009).

Starter catalogs drawn from docs/status/Hospital_Departments_and_Doctors_RBAC.MD. Clinical
informatics / HR own them and may extend or deactivate entries; codes are stable identifiers.

Existing free-text designations on staff department assignments are preserved: each value is
matched to a catalog entry by name, or kept as a new "custom" catalog entry.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils.text import slugify

M, N, P, A, AD, S = "medical", "nursing", "pharmacy", "allied_health", "administration", "support"

# (code, name, category, country, seniority 1-10)
DESIGNATIONS = [
    # Doctors - India
    ("in-intern", "Intern (Compulsory Rotating Medical Internship)", M, "IN", 1),
    ("in-junior-resident", "Junior Resident (JR)", M, "IN", 2),
    ("in-medical-officer", "Medical Officer (MO)", M, "IN", 2),
    ("in-casualty-medical-officer", "Casualty Medical Officer (CMO)", M, "IN", 2),
    ("in-resident-medical-officer", "Resident Medical Officer (RMO)", M, "IN", 3),
    ("in-senior-resident", "Senior Resident (SR)", M, "IN", 4),
    ("in-registrar", "Registrar", M, "IN", 4),
    ("in-associate-consultant", "Associate Consultant", M, "IN", 5),
    ("in-assistant-professor", "Assistant Professor", M, "IN", 5),
    ("in-consultant", "Consultant", M, "IN", 6),
    ("in-visiting-consultant", "Visiting Consultant", M, "IN", 6),
    ("in-associate-professor", "Associate Professor", M, "IN", 6),
    ("in-senior-consultant", "Senior Consultant", M, "IN", 7),
    ("in-professor", "Professor", M, "IN", 7),
    ("in-head-of-department", "Head of Department (HOD)", M, "IN", 8),
    ("in-medical-superintendent", "Medical Superintendent", M, "IN", 9),
    ("in-medical-director", "Medical Director", M, "IN", 10),
    # Doctors - United States
    ("us-medical-student", "Medical Student", M, "US", 1),
    ("us-intern", "Intern (PGY-1)", M, "US", 2),
    ("us-resident", "Resident (PGY-2+)", M, "US", 3),
    ("us-chief-resident", "Chief Resident", M, "US", 4),
    ("us-fellow", "Fellow", M, "US", 4),
    ("us-physician-assistant", "Physician Assistant (PA)", M, "US", 5),
    ("us-hospitalist", "Hospitalist", M, "US", 6),
    ("us-attending-physician", "Attending Physician", M, "US", 6),
    ("us-section-chief", "Section / Division Chief", M, "US", 8),
    ("us-department-chair", "Department Chair", M, "US", 9),
    ("us-chief-medical-officer", "Chief Medical Officer (CMO)", M, "US", 10),
    # Doctors - both
    ("locum-physician", "Locum Physician", M, "", 5),
    # Nursing - India
    ("in-anm", "Auxiliary Nurse Midwife (ANM)", N, "IN", 1),
    ("in-staff-nurse", "Staff Nurse", N, "IN", 2),
    ("in-senior-staff-nurse", "Senior Staff Nurse", N, "IN", 3),
    ("in-ward-sister", "Ward Sister / Nursing In-charge", N, "IN", 4),
    ("in-nursing-supervisor", "Nursing Supervisor", N, "IN", 5),
    ("in-assistant-nursing-superintendent", "Assistant Nursing Superintendent", N, "IN", 6),
    ("in-deputy-nursing-superintendent", "Deputy Nursing Superintendent", N, "IN", 7),
    ("in-nursing-superintendent", "Nursing Superintendent", N, "IN", 8),
    # Nursing - United States
    ("us-cna", "Certified Nursing Assistant (CNA)", N, "US", 1),
    ("us-lpn", "Licensed Practical / Vocational Nurse (LPN/LVN)", N, "US", 2),
    ("us-registered-nurse", "Registered Nurse (RN)", N, "US", 3),
    ("us-charge-nurse", "Charge Nurse", N, "US", 4),
    ("us-nurse-practitioner", "Nurse Practitioner (NP)", N, "US", 5),
    ("us-clinical-nurse-specialist", "Clinical Nurse Specialist (CNS)", N, "US", 5),
    ("us-certified-nurse-midwife", "Certified Nurse Midwife (CNM)", N, "US", 5),
    ("us-crna", "Certified Registered Nurse Anesthetist (CRNA)", N, "US", 6),
    ("us-nurse-manager", "Nurse Manager", N, "US", 6),
    ("us-director-of-nursing", "Director of Nursing", N, "US", 8),
    # Nursing - both
    ("nurse-educator", "Nurse Educator", N, "", 5),
    ("chief-nursing-officer", "Chief Nursing Officer (CNO)", N, "", 9),
    # Pharmacy
    ("in-pharmacy-assistant", "Pharmacy Assistant", P, "IN", 1),
    ("us-pharmacy-technician", "Pharmacy Technician (CPhT)", P, "US", 1),
    ("pharmacist", "Pharmacist", P, "", 3),
    ("clinical-pharmacist", "Clinical Pharmacist", P, "", 4),
    ("senior-pharmacist", "Senior Pharmacist", P, "", 5),
    ("chief-pharmacist", "Chief Pharmacist / Director of Pharmacy", P, "", 7),
    # Allied health and technicians
    ("phlebotomist", "Phlebotomist", A, "", 1),
    ("lab-technician", "Laboratory Technician (DMLT / MLT)", A, "", 2),
    ("lab-technologist", "Laboratory Technologist / Medical Laboratory Scientist", A, "", 3),
    ("lab-supervisor", "Laboratory Supervisor", A, "", 5),
    ("blood-bank-technician", "Blood Bank Technician", A, "", 2),
    ("radiographer", "Radiographer / Radiologic Technologist", A, "", 2),
    ("ct-mri-technologist", "CT / MRI Technologist", A, "", 3),
    ("sonographer", "Sonographer", A, "", 3),
    ("chief-radiographer", "Chief Radiographer / Imaging Supervisor", A, "", 5),
    ("in-ot-technician", "OT Technician", A, "IN", 2),
    ("us-surgical-technologist", "Surgical Technologist (CST)", A, "US", 2),
    ("anaesthesia-technician", "Anaesthesia Technician", A, "", 2),
    ("cssd-technician", "CSSD (Sterile Services) Technician", A, "", 1),
    ("dialysis-technician", "Dialysis Technician", A, "", 2),
    ("cath-lab-technician", "Cath Lab Technician", A, "", 3),
    ("ecg-echo-technician", "ECG / ECHO Technician", A, "", 2),
    ("eeg-emg-technician", "EEG / EMG Technician", A, "", 2),
    ("respiratory-therapist", "Respiratory Therapist", A, "", 3),
    ("perfusionist", "Perfusionist", A, "", 4),
    ("physiotherapist", "Physiotherapist / Physical Therapist", A, "", 3),
    ("occupational-therapist", "Occupational Therapist", A, "", 3),
    ("speech-therapist", "Speech Therapist / Audiologist", A, "", 3),
    ("dietitian", "Dietitian", A, "", 3),
    ("optometrist", "Optometrist", A, "", 3),
    ("emergency-medical-technician", "Emergency Medical Technician (EMT / Paramedic)", A, "", 2),
    ("biomedical-engineer", "Biomedical Engineer", A, "", 3),
    ("medical-social-worker", "Medical Social Worker", A, "", 3),
    # Administration and management
    ("front-office-executive", "Front Office / Reception Executive", AD, "", 1),
    ("patient-care-coordinator", "Patient Care Coordinator", AD, "", 2),
    ("billing-executive", "Billing Executive", AD, "", 2),
    ("in-insurance-tpa-executive", "Insurance / TPA Desk Executive", AD, "IN", 2),
    ("us-medical-coder", "Medical Coder (CPC / CCS)", AD, "US", 3),
    ("us-revenue-cycle-specialist", "Revenue Cycle Specialist", AD, "US", 3),
    ("in-medical-records-officer", "Medical Records Officer (MRD)", AD, "IN", 2),
    ("us-him-technician", "Health Information Technician (RHIT)", AD, "US", 3),
    ("hr-executive", "HR Executive", AD, "", 3),
    ("credentialing-officer", "Credentialing Officer", AD, "", 4),
    ("quality-officer", "Quality & Patient Safety Officer", AD, "", 5),
    ("department-manager", "Department Manager", AD, "", 5),
    ("facility-manager", "Facility / Branch Manager", AD, "", 6),
    ("hospital-administrator", "Hospital Administrator", AD, "", 7),
    ("chief-operating-officer", "Chief Operating Officer (COO)", AD, "", 9),
    ("chief-executive-officer", "Chief Executive Officer (CEO)", AD, "", 10),
    # Support services
    ("in-ward-attendant", "Ward Attendant / General Duty Assistant (GDA)", S, "IN", 1),
    ("us-patient-care-technician", "Patient Care Technician (PCT)", S, "US", 1),
    ("housekeeping-staff", "Housekeeping Staff", S, "", 1),
    ("housekeeping-supervisor", "Housekeeping Supervisor", S, "", 3),
    ("patient-transporter", "Patient Transporter / Porter", S, "", 1),
    ("kitchen-staff", "Kitchen / Dietary Staff", S, "", 1),
    ("security-staff", "Security Staff", S, "", 1),
    ("ambulance-driver", "Ambulance Driver", S, "", 1),
]

SPECIALTIES = [
    ("internal-medicine", "Internal Medicine"),
    ("family-medicine", "Family Medicine"),
    ("medical-oncology", "Medical Oncology"),
    ("surgical-oncology", "Surgical Oncology"),
    ("radiation-oncology", "Radiation Oncology"),
    ("hematology", "Hematology"),
    ("neonatology", "Neonatology"),
    ("pediatric-surgery", "Pediatric Surgery"),
    ("cardiothoracic-surgery", "Cardiothoracic and Vascular Surgery"),
    ("interventional-cardiology", "Interventional Cardiology"),
    ("neurosurgery", "Neurosurgery"),
    ("plastic-surgery", "Plastic and Reconstructive Surgery"),
    ("vascular-surgery", "Vascular Surgery"),
    ("rheumatology", "Rheumatology"),
    ("infectious-diseases", "Infectious Diseases"),
    ("geriatrics", "Geriatric Medicine"),
    ("hepatology", "Hepatology"),
    ("pain-medicine", "Pain Medicine"),
    ("palliative-care", "Palliative Care"),
    ("physical-medicine-rehabilitation", "Physical Medicine and Rehabilitation"),
    ("nuclear-medicine", "Nuclear Medicine"),
    ("interventional-radiology", "Interventional Radiology"),
    ("transfusion-medicine", "Transfusion Medicine / Blood Bank"),
    ("microbiology", "Microbiology"),
    ("biochemistry", "Biochemistry"),
    ("forensic-medicine", "Forensic Medicine"),
    ("community-medicine", "Community Medicine / Public Health"),
    ("sports-medicine", "Sports Medicine"),
    ("dentistry", "Dentistry / Oral and Maxillofacial Surgery"),
]

DEG, DIP, FEL, CER = "degree", "diploma", "fellowship", "certification"
QUALIFICATIONS = [
    # India - doctors (postgraduate diplomas are separate from degrees)
    ("in-dnb-broad", "DNB (Broad Specialty)", DIP, "IN"),
    ("in-dnb-super", "DrNB / DNB (Super Specialty)", DIP, "IN"),
    ("in-fnb", "FNB (Fellow of National Board)", FEL, "IN"),
    ("in-dch", "DCH (Diploma in Child Health)", DIP, "IN"),
    ("in-dgo", "DGO (Diploma in Obstetrics & Gynaecology)", DIP, "IN"),
    ("in-da", "DA (Diploma in Anaesthesia)", DIP, "IN"),
    ("in-dmrd", "DMRD (Diploma in Medical Radio-Diagnosis)", DIP, "IN"),
    ("in-dlo", "DLO (Diploma in Otorhinolaryngology)", DIP, "IN"),
    ("in-doms", "DOMS (Diploma in Ophthalmic Medicine & Surgery)", DIP, "IN"),
    ("in-dpm", "DPM (Diploma in Psychological Medicine)", DIP, "IN"),
    ("in-dvl", "DVL (Diploma in Dermatology, Venereology & Leprosy)", DIP, "IN"),
    ("in-mds", "MDS (Master of Dental Surgery)", DEG, "IN"),
    ("in-bams", "BAMS (Ayurveda)", DEG, "IN"),
    ("in-bhms", "BHMS (Homoeopathy)", DEG, "IN"),
    # India - nursing, pharmacy, allied, management
    ("in-anm-cert", "ANM (Auxiliary Nursing & Midwifery)", DIP, "IN"),
    ("in-post-basic-bsc-nursing", "Post Basic B.Sc. Nursing", DEG, "IN"),
    ("in-msc-nursing", "M.Sc. Nursing", DEG, "IN"),
    ("in-dpharm", "D.Pharm", DIP, "IN"),
    ("in-mpharm", "M.Pharm", DEG, "IN"),
    ("in-dmlt", "DMLT (Diploma in Medical Lab Technology)", DIP, "IN"),
    ("in-bsc-mlt", "B.Sc. Medical Lab Technology (BMLT)", DEG, "IN"),
    ("in-bsc-radiology", "B.Sc. Radiology & Imaging Technology", DEG, "IN"),
    ("in-ot-technology", "Diploma / B.Sc. Operation Theatre Technology", DIP, "IN"),
    ("in-bpt", "BPT (Bachelor of Physiotherapy)", DEG, "IN"),
    ("in-mpt", "MPT (Master of Physiotherapy)", DEG, "IN"),
    ("in-mha", "MHA (Master of Hospital Administration)", DEG, "IN"),
    # United States
    ("us-np", "Nurse Practitioner (MSN / DNP, board certified)", DEG, "US"),
    ("us-dnp", "DNP (Doctor of Nursing Practice)", DEG, "US"),
    ("us-adn", "ADN (Associate Degree in Nursing)", DEG, "US"),
    ("us-pa", "Physician Assistant (MPAS, NCCPA certified)", DEG, "US"),
    ("us-cst", "CST (Certified Surgical Technologist)", CER, "US"),
    ("us-arrt", "ARRT certification (Radiologic Technology)", CER, "US"),
    ("us-ascp-mls", "ASCP MLS certification (Medical Laboratory Scientist)", CER, "US"),
    ("us-rrt", "RRT (Registered Respiratory Therapist)", CER, "US"),
    ("us-cpht", "CPhT (Certified Pharmacy Technician)", CER, "US"),
    ("us-cpc", "CPC / CCS (Medical Coding certification)", CER, "US"),
    ("us-rhia-rhit", "RHIA / RHIT (Health Information Management)", CER, "US"),
    # International / both
    ("mrcp", "MRCP (Member of the Royal College of Physicians, UK)", FEL, ""),
    ("frcs", "FRCS (Fellow of the Royal College of Surgeons, UK)", FEL, ""),
    ("bls-acls", "BLS / ACLS life-support certification", CER, ""),
]


def seed_catalogs(apps, schema_editor):
    Designation = apps.get_model("staff", "Designation")
    Specialty = apps.get_model("staff", "Specialty")
    QualificationType = apps.get_model("staff", "QualificationType")
    for code, name, category, country, seniority in DESIGNATIONS:
        Designation.objects.get_or_create(
            code=code,
            defaults={"name": name, "category": category, "country": country, "seniority": seniority},
        )
    for code, name in SPECIALTIES:
        Specialty.objects.get_or_create(code=code, defaults={"name": name})
    for code, name, category, country in QUALIFICATIONS:
        QualificationType.objects.get_or_create(
            code=code, defaults={"name": name, "category": category, "country": country}
        )


def convert_free_text(apps, schema_editor):
    """Map each existing free-text designation to a catalog entry (or a custom one)."""
    Designation = apps.get_model("staff", "Designation")
    Assignment = apps.get_model("staff", "StaffDepartmentAssignment")
    for assignment in Assignment.objects.all():
        text = (assignment.designation or "").strip() or "Unspecified"
        match = Designation.objects.filter(name__iexact=text).first()
        if match is None:
            match = Designation.objects.filter(name__istartswith=text).order_by("country").first()
        if match is None:
            match, _ = Designation.objects.get_or_create(
                code=f"custom-{slugify(text)[:50] or 'unspecified'}",
                defaults={"name": text, "category": "other", "country": "", "seniority": 5},
            )
        assignment.designation_ref = match
        assignment.save(update_fields=["designation_ref"])


class Migration(migrations.Migration):
    dependencies = [("staff", "0002_seed_reference_catalogs")]

    operations = [
        migrations.CreateModel(
            name="Designation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=255)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("medical", "Medical (doctors)"),
                            ("nursing", "Nursing"),
                            ("pharmacy", "Pharmacy"),
                            ("allied_health", "Allied health & technicians"),
                            ("administration", "Administration & management"),
                            ("support", "Support services"),
                            ("other", "Other"),
                        ],
                        max_length=32,
                    ),
                ),
                ("country", models.CharField(blank=True, help_text="Blank when used in both", max_length=2)),
                ("seniority", models.PositiveSmallIntegerField(help_text="1 = entry level ... 10 = leadership")),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "designations",
                "ordering": ["category", "seniority", "name"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("seniority__gte", 1), ("seniority__lte", 10)),
                        name="designation_seniority_range",
                    )
                ],
            },
        ),
        migrations.RunPython(seed_catalogs, migrations.RunPython.noop),
        migrations.AddField(
            model_name="staffdepartmentassignment",
            name="designation_ref",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="staff.designation",
            ),
        ),
        migrations.RunPython(convert_free_text, migrations.RunPython.noop),
        migrations.RemoveField(model_name="staffdepartmentassignment", name="designation"),
        migrations.RenameField(
            model_name="staffdepartmentassignment", old_name="designation_ref", new_name="designation"
        ),
        migrations.AlterField(
            model_name="staffdepartmentassignment",
            name="designation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="+", to="staff.designation"
            ),
        ),
    ]
