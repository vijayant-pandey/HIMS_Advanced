"""Check the audit log for tampering now (HIMS-SEC-010).

Seals pending events, then recomputes the whole chain. The result is stored and shown on the
Audit integrity screen; auditors are emailed if problems are found. Exits with status 1 when
problems are found, so it can be used in scripts and monitoring.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.audit.integrity import run_integrity_check
from apps.audit.models import AuditIntegrityCheck


class Command(BaseCommand):
    help = "Check that no audit event was changed or removed (tamper evidence)."

    def handle(self, *args, **options):
        check = run_integrity_check(trigger=AuditIntegrityCheck.Trigger.COMMAND)
        summary = (
            f"Sealed {check.events_sealed} new event(s); checked {check.entries_checked} "
            f"link(s); chain head {check.chain_head[:16] or '-'}."
        )
        if check.outcome == AuditIntegrityCheck.Outcome.PASSED:
            self.stdout.write(self.style.SUCCESS(f"PASSED. {summary}"))
            return
        for problem in check.problems:
            where = problem.get("sequence") or problem.get("event_id") or ""
            self.stderr.write(f"- {problem['kind']} {where}: {problem['text']}")
        raise CommandError(f"FAILED: {check.problem_count} problem(s). {summary}")
