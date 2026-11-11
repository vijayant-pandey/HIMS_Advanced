"""Start the scheduled jobs over HTTPS from an outside timer (spec 14; HIMS-OPS-024).

Some free hosts run one web service and nothing else: no worker, no scheduler, no shell, no timer
of their own (Render's free plan; ADR-034). A free timer service then calls this address every
minute, which runs the due jobs exactly as ``run_scheduled_jobs`` does (common/outbox/scheduler.py)
and also keeps a sleeping free service awake.

* Off unless ``HIMS_SCHEDULER_TOKEN`` is set; then 404, as if the address did not exist.
* The caller must send the token in ``X-HIMS-Scheduler-Token``; a wrong one is refused (403) and
  recorded as an access denial (the general rule audits signed-in refusals only; a wrong value
  here means a probe or a misconfigured timer), and the address is rate limited per caller.
* No sign-in, no cookies, so no CSRF; the answer holds counts only.
"""

import hmac

from django.conf import settings
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.throttling import ScopedThrottle

from . import scheduler

SCHEDULER_HEADER = "X-HIMS-Scheduler-Token"


class ScheduledRunSerializer(serializers.Serializer):
    busy = serializers.BooleanField(help_text="Another run was still going; nothing started.")
    ran = serializers.IntegerField()
    failed = serializers.IntegerField()


class ScheduledJobsTriggerView(APIView):
    """Run the scheduled jobs that are due, for an outside timer calling every minute."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "scheduler"

    @extend_schema(request=None, responses=ScheduledRunSerializer)
    def post(self, request):
        expected = settings.HIMS_SCHEDULER_TOKEN
        if not expected:
            raise Http404
        given = request.headers.get(SCHEDULER_HEADER, "")
        if not hmac.compare_digest(given.encode(), expected.encode()):
            from apps.audit.models import AuditEvent
            from apps.audit.services import AuditAction, record_audit_event

            record_audit_event(
                action=AuditAction.ACCESS_DENIED,
                resource_type="scheduled_jobs",
                request=request,
                outcome=AuditEvent.Outcome.DENIED,
                metadata={"view": type(self).__name__, "method": request.method},
            )
            raise PermissionDenied("Not allowed.")
        result = scheduler.run_due()
        failed = sum(1 for item in result["ran"] if item["error"])
        return Response(
            ScheduledRunSerializer(
                {"busy": result["busy"], "ran": len(result["ran"]), "failed": failed}
            ).data
        )
