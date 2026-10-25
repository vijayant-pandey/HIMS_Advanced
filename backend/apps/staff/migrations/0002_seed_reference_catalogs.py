"""Starter specialty and qualification catalogs.

A minimal starting set so onboarding can begin. Clinical informatics owns these catalogs and
must review/extend them per market before go-live (spec 26.8). Codes are stable identifiers;
names may be corrected later without changing historical meaning.
"""

from django.db import migrations

SPECIALTIES = [
    ("general-medicine", "General Medicine"),
    ("cardiology", "Cardiology"),
    ("neurology", "Neurology"),
    ("pediatrics", "Pediatrics"),
    ("orthopedics", "Orthopedics"),
    ("oncology", "Oncology"),
    ("general-surgery", "General Surgery"),
    ("anesthesiology", "Anesthesiology"),
    ("critical-care", "Critical Care Medicine"),
    ("emergency-medicine", "Emergency Medicine"),
    ("radiology", "Radiology"),
    ("pathology", "Pathology"),
    ("obstetrics-gynecology", "Obstetrics and Gynecology"),
    ("nephrology", "Nephrology"),
    ("gastroenterology", "Gastroenterology"),
    ("pulmonology", "Pulmonology"),
    ("psychiatry", "Psychiatry"),
    ("dermatology", "Dermatology"),
    ("ophthalmology", "Ophthalmology"),
    ("otorhinolaryngology", "Otorhinolaryngology (ENT)"),
    ("urology", "Urology"),
    ("endocrinology", "Endocrinology"),
    ("physiotherapy", "Physiotherapy"),
]

# (code, name, category, country)
QUALIFICATIONS = [
    ("in-mbbs", "MBBS", "degree", "IN"),
    ("in-md", "MD (Doctor of Medicine, postgraduate)", "degree", "IN"),
    ("in-ms", "MS (Master of Surgery)", "degree", "IN"),
    ("in-dm", "DM (Doctorate of Medicine)", "degree", "IN"),
    ("in-mch", "MCh (Master of Chirurgiae)", "degree", "IN"),
    ("in-dnb", "DNB (Diplomate of National Board)", "diploma", "IN"),
    ("in-bds", "BDS", "degree", "IN"),
    ("in-bsc-nursing", "B.Sc. Nursing", "degree", "IN"),
    ("in-gnm", "GNM (General Nursing and Midwifery)", "diploma", "IN"),
    ("in-bpharm", "B.Pharm", "degree", "IN"),
    ("in-pharmd", "Pharm.D", "degree", "IN"),
    ("us-md", "MD (Doctor of Medicine)", "degree", "US"),
    ("us-do", "DO (Doctor of Osteopathic Medicine)", "degree", "US"),
    ("us-bsn", "BSN (Bachelor of Science in Nursing)", "degree", "US"),
    ("us-msn", "MSN (Master of Science in Nursing)", "degree", "US"),
    ("us-pharmd", "PharmD", "degree", "US"),
    ("us-board-certification", "Specialty board certification", "certification", "US"),
]


def seed(apps, schema_editor):
    Specialty = apps.get_model("staff", "Specialty")
    QualificationType = apps.get_model("staff", "QualificationType")
    for code, name in SPECIALTIES:
        Specialty.objects.get_or_create(code=code, defaults={"name": name})
    for code, name, category, country in QUALIFICATIONS:
        QualificationType.objects.get_or_create(
            code=code, defaults={"name": name, "category": category, "country": country}
        )


class Migration(migrations.Migration):
    dependencies = [("staff", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
