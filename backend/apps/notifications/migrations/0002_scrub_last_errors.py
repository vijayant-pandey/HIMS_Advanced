"""Clean error texts kept before HIMS-SEC-019: a provider may have repeated the refused message,
sign-in link included, in its error. Data only; nothing to undo."""

from django.db import migrations


def scrub_last_errors(apps, schema_editor):
    from apps.notifications.services import _error_text_from
    from common import crypto

    Notification = apps.get_model("notifications", "Notification")
    for row in Notification.objects.exclude(last_error="").iterator():
        name, _, detail = row.last_error.partition(": ")
        try:
            body = crypto.decrypt(row.body_encrypted) if row.body_encrypted else row.body
        except crypto.DecryptionError:
            body = None  # cannot tell which parts were secret: keep only the kind of error
        cleaned = _error_text_from(name, detail, row.body, body)
        if cleaned != row.last_error:
            Notification.objects.filter(pk=row.pk).update(last_error=cleaned)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_notifications")]

    operations = [migrations.RunPython(scrub_last_errors, migrations.RunPython.noop)]
