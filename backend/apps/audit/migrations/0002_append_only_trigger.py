"""Make audit_events append-only at the database level (ADR-013).

Application code cannot update or delete audit rows even through raw SQL or a compromised
code path. TRUNCATE is controlled by role grants instead: the runtime database role must not
hold TRUNCATE on audit_events (HIMS-OPS-007), while test tooling may still reset the table.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION audit_events_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (% rejected)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_append_only
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_reject_mutation();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
DROP FUNCTION IF EXISTS audit_events_reject_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
