"""Opening staff documents becomes its own permission (HIMS-STAFF-008).

Until now ``staff.view`` also opened licence and qualification files. Every role that has
``staff.view`` today, including a hospital's own roles, gets ``staff.documents.view`` too, so
nobody loses access. Roles given ``staff.view`` from now on (e.g. head of department) see the
staff directory but not the files.
"""

from django.db import migrations

DOCUMENTS = "staff.documents.view"


def keep_document_access(apps, schema_editor):
    Permission = apps.get_model("access_control", "Permission")
    RolePermission = apps.get_model("access_control", "RolePermission")
    documents, _ = Permission.objects.get_or_create(
        codename=DOCUMENTS,
        defaults={
            "description": "Open staff licence and qualification documents (the uploaded files)"
        },
    )
    for row in RolePermission.objects.filter(permission__codename="staff.view"):
        RolePermission.objects.get_or_create(role_id=row.role_id, permission=documents)


class Migration(migrations.Migration):
    dependencies = [("access_control", "0004_access_delegations")]

    operations = [migrations.RunPython(keep_document_access, migrations.RunPython.noop)]
