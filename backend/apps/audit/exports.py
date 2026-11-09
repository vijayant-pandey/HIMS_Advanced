"""Audit events as a CSV file (spec 13.4; HIMS-AUD-003).

Used by the Audit log page's download and the admin console's, so both give the same file.
The caller records the export in the audit log (with its filters) before calling this.
"""

import csv

from django.http import StreamingHttpResponse
from django.utils import timezone

from . import catalog

# Most rows one export may contain; narrow the filters for more (keeps exports reviewable).
EXPORT_LIMIT = 5000


def _cell(value) -> str:
    """Spreadsheet-safe text: a leading = + - @ would otherwise run as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def events_csv_response(rows, *, truncated: bool) -> StreamingHttpResponse:
    """Rows come from ``with_names()`` (names, emails and facility added), newest first."""

    class Echo:
        def write(self, value):
            return value

    writer = csv.writer(Echo())
    header = [
        "When (UTC)",
        "What happened",
        "Action code",
        "Outcome",
        "Who",
        "Email",
        "Facility",
        "Record type",
        "Record id",
        "Reason",
        "Reference number",
        "IP address",
    ]

    def lines():
        yield writer.writerow(header)
        for event in rows:
            yield writer.writerow(
                [
                    _cell(value)
                    for value in (
                        event.occurred_at.isoformat(),
                        catalog.label(event.action),
                        event.action,
                        event.outcome,
                        event.actor_name or event.actor_type,
                        event.actor_email,
                        event.facility_name,
                        event.resource_type,
                        event.resource_id,
                        event.reason,
                        event.request_id,
                        event.ip_address,
                    )
                ]
            )

    stamp = timezone.now().strftime("%Y%m%d-%H%M")
    response = StreamingHttpResponse(lines(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="audit-log-{stamp}.csv"'
    response["X-Export-Truncated"] = "true" if truncated else "false"
    return response
