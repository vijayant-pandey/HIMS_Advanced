"""Standard shift types every hospital starts with (HIMS-STAFF-012). Hospitals rename, switch
off or add their own on the Rota page or in the admin console; codes never change."""

from datetime import time

from django.db import migrations

STANDARD = [
    ("morning", "Morning", "shift", time(8), time(14)),
    ("evening", "Evening", "shift", time(14), time(20)),
    ("night", "Night", "shift", time(20), time(8)),
    ("day-12h", "Day (12 hours)", "shift", time(7), time(19)),
    ("night-12h", "Night (12 hours)", "shift", time(19), time(7)),
    ("general", "General (office hours)", "shift", time(9), time(17)),
    ("on-call-24h", "On call (24 hours)", "on_call", time(8), time(8)),
    ("on-call-night", "On call (night)", "on_call", time(20), time(8)),
]


def add_standard(apps, schema_editor):
    ShiftType = apps.get_model("rosters", "ShiftType")
    for code, name, kind, start, end in STANDARD:
        ShiftType.objects.get_or_create(
            code=code, defaults={"name": name, "kind": kind, "start_time": start, "end_time": end}
        )


class Migration(migrations.Migration):
    dependencies = [("rosters", "0001_initial")]

    operations = [migrations.RunPython(add_standard, migrations.RunPython.noop)]
