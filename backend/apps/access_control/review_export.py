"""An access review as a CSV file, with every decision (evidence for auditors; HIMS-IAM-012).

Used by the app's download and the admin console's, so both give the same file and both are
audited the same way.
"""

import csv

from django.http import HttpResponse

from apps.audit.services import AuditAction, record_audit_event


def _cell(value) -> str:
    """Spreadsheet-safe text: a leading = + - @ would otherwise run as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def _iso(value) -> str:
    return value.isoformat() if value else ""


def review_csv_response(review, *, request) -> HttpResponse:
    items = list(review.items.select_related("decided_by"))
    record_audit_event(
        action=AuditAction.ACCESS_REVIEW_EXPORTED,
        resource_type="access_review",
        resource_id=review.pk,
        request=request,
        metadata={"rows": len(items)},
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="access-review-{review.created_at:%Y%m%d}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        [
            "Review",
            "Review status",
            "Person",
            "Email",
            "Account could sign in",
            "Last signed in (UTC)",
            "Role",
            "Where",
            "Access given (UTC)",
            "Access ends (UTC)",
            "Decision",
            "Decided by",
            "Decided at (UTC)",
            "Comment",
        ]
    )
    for item in items:
        writer.writerow(
            [
                _cell(value)
                for value in (
                    review.title,
                    review.get_status_display(),
                    item.person_name,
                    item.person_email,
                    "yes" if item.account_active else "no",
                    _iso(item.last_signed_in_at),
                    item.role_name,
                    item.scope,
                    _iso(item.granted_at),
                    _iso(item.access_ends_at),
                    item.get_decision_display(),
                    item.decided_by.display_name if item.decided_by else "",
                    _iso(item.decided_at),
                    item.comment,
                )
            ]
        )
    return response
