"""Every audit area the server knows can be chosen in the app's Audit log "Area" list.

HIMS-QA-003 found eight areas (rotas, leave, messages, compliance, backups, database access,
background jobs, performance) that the server could filter by but the app did not offer, so an
auditor could not narrow a search to them. The app's list lives in the frontend; this test reads
it so the two cannot drift apart again.
"""

import re
from pathlib import Path

from django.conf import settings

from apps.audit.catalog import CATEGORIES

APP_LIST = Path(settings.BASE_DIR).parent / "frontend/src/features/audit/labels.ts"


def test_every_audit_area_is_in_the_apps_area_list():
    text = APP_LIST.read_text(encoding="utf-8")
    block = text.split("export const CATEGORIES", 1)[1].split("];", 1)[0]
    offered = set(re.findall(r'value: "([a-z_]+)"', block))
    assert offered == set(CATEGORIES)
