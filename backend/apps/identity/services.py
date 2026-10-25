from django.db import transaction

from apps.audit.services import AuditAction, record_audit_event
from common.exceptions import ConflictError

from .models import User


@transaction.atomic
def create_user(
    *, email: str, display_name: str, password: str | None = None, actor=None, request=None
) -> User:
    """Create a login identity. Without a password the account cannot sign in until the
    invitation/activation flow sets one (HIMS-IAM-003)."""
    if User.objects.filter(email__iexact=email.strip()).exists():
        raise ConflictError("A user with this email already exists.", code="USER_EMAIL_EXISTS")
    user = User.objects.create_user(email=email, display_name=display_name, password=password)
    record_audit_event(
        action=AuditAction.USER_CREATED,
        resource_type="user",
        resource_id=user.pk,
        actor=actor,
        request=request,
        metadata={"has_password": bool(password)},
    )
    return user
