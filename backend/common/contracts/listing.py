"""The API endpoints list shown in the app and the console (HIMS-DOC-001).

Read from the code on first use and kept for the life of the process (under a second to build).
"""

from apps.access_control.catalog import PERMISSIONS

from . import generator, inventory, reach

AREA_LABELS = generator.AREAS


def endpoint_rows() -> list[dict]:
    roles = generator.roles_by_permission()
    rows = []
    for endpoint in inventory.endpoints():
        found = reach.for_endpoint(endpoint)
        rows.append(
            {
                "method": endpoint.method,
                "path": endpoint.path,
                "area": endpoint.app_label,
                "area_label": AREA_LABELS.get(endpoint.app_label, endpoint.app_label),
                "summary": endpoint.summary,
                "access": endpoint.access,
                "permission": endpoint.permission,
                "permission_label": PERMISSIONS.get(endpoint.permission, ""),
                "roles": roles.get(endpoint.permission, []) if endpoint.permission else [],
                "scope": endpoint.scope,
                "confirm_identity": endpoint.confirm_identity,
                "idempotency": endpoint.idempotency,
                "audit_actions": list(found.audit_actions),
                "requirements": list(endpoint.requirements),
            }
        )
    return rows


def summary(rows: list[dict]) -> dict:
    return {
        "total": len(rows),
        "public": sum(1 for row in rows if row["access"] == inventory.PUBLIC),
        "signed_in": sum(1 for row in rows if row["access"] == inventory.SIGNED_IN),
        "permission": sum(1 for row in rows if row["access"] == inventory.PERMISSION),
        "confirm_identity": sum(1 for row in rows if row["confirm_identity"]),
        "idempotent": sum(1 for row in rows if row["idempotency"]),
        "audited_writes": sum(1 for row in rows if row["method"] != "GET" and row["audit_actions"]),
        "writes": sum(1 for row in rows if row["method"] != "GET"),
    }
