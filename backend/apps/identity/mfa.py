"""Two-factor sign-in with authenticator apps (HIMS-IAM-005; spec 4.4, 13.1, 13.3, 13.4).

* Codes are time-based one-time passwords (TOTP, RFC 6238: HMAC-SHA1, 6 digits, 30 seconds),
  which every common authenticator app supports. One step of clock drift is tolerated either way,
  and a code that was already accepted cannot be used again.
* The shared secret is stored encrypted (common.crypto). Ten one-time recovery codes are issued
  at setup; only their SHA-256 fingerprints are stored.
* Users holding a privileged permission (catalog.MFA_REQUIRED_PERMISSIONS) must use two-factor;
  until they have set it up, the API and admin console only allow them to set it up.
* Sign-in with two-factor is two steps: password (``begin_challenge``) then code
  (``verify_challenge``). The pending state lives in the anonymous session for 5 minutes and
  allows 5 wrong codes.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote, urlencode

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.access_control.catalog import MFA_REQUIRED_PERMISSIONS
from apps.access_control.selectors import list_grants
from apps.audit.models import AuditEvent
from apps.audit.services import AuditAction, record_audit_event
from common.crypto import decrypt, encrypt
from common.exceptions import ConflictError, DomainError

from .models import MfaDevice, MfaRecoveryCode, User, UserSession

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i look-alikes
SESSION_VERIFIED_KEY = "hims_mfa_verified"
SESSION_PENDING_KEY = "hims_mfa_pending"
CHALLENGE_TTL = timedelta(minutes=5)
CHALLENGE_MAX_ATTEMPTS = 5


class InvalidMfaCode(DomainError):
    status_code = 400
    code = "MFA_CODE_INVALID"
    title = "Code not accepted"


class MfaChallengeExpired(DomainError):
    status_code = 400
    code = "MFA_CHALLENGE_EXPIRED"
    title = "Sign-in expired"


class MfaRequired(DomainError):
    status_code = 403
    code = "MFA_SETUP_REQUIRED"
    title = "Two-factor sign-in required"


# --- TOTP (RFC 6238) ----------------------------------------------------------------------


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp(secret_b32: str, step: int, digits: int = DIGITS) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def matching_step(secret_b32: str, code: str, *, now: float | None = None) -> int | None:
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    step = current_step(now)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if hmac.compare_digest(totp(secret_b32, candidate), code):
            return candidate
    return None


def provisioning_uri(secret_b32: str, *, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode(
        {"secret": secret_b32, "issuer": issuer, "digits": DIGITS, "period": STEP_SECONDS}
    )
    return f"otpauth://totp/{label}?{query}"


# --- Policy -------------------------------------------------------------------------------


def confirmed_device(user) -> MfaDevice | None:
    device = MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).first()
    return device


def is_required(user, request=None) -> bool:
    if settings.HIMS_MFA_REQUIRED_FOR_ALL:
        return True
    from apps.features.catalog import F
    from apps.features.services import is_enabled

    # The hospital can require it for everyone on its Features page (HIMS-ORG-004).
    if is_enabled(F.TWO_FACTOR_FOR_EVERYONE, request=request):
        return True
    if not settings.HIMS_MFA_REQUIRED_FOR_PRIVILEGED:
        return False
    return any(grant["permission"] in MFA_REQUIRED_PERMISSIONS for grant in list_grants(user))


def session_verified(request) -> bool:
    session = getattr(request, "session", None)
    return bool(session is not None and session.get(SESSION_VERIFIED_KEY))


def ensure_satisfied(request) -> None:
    """Raise MfaRequired unless the signed-in user may continue without (more) two-factor."""
    user = request.user
    if not getattr(user, "is_authenticated", False):
        return
    if session_verified(request) or not is_required(user, request):
        return
    raise MfaRequired(
        "Your role requires two-factor sign-in. Set it up under Security to continue."
        if confirmed_device(user) is None
        else "Sign in again with your authenticator code to continue."
    )


def status(user, request=None) -> dict:
    device = confirmed_device(user)
    return {
        "enabled": device is not None,
        "required": is_required(user, request),
        "verified": session_verified(request) if request is not None else False,
        "recovery_codes_remaining": MfaRecoveryCode.objects.filter(
            user=user, used_at__isnull=True
        ).count()
        if device
        else 0,
    }


# --- Setup ------------------------------------------------------------------------------


def _issuer() -> str:
    from apps.organizations.models import Organization

    organization = Organization.objects.only("display_name").first()
    return f"HIMS ({organization.display_name})" if organization else "HIMS"


@transaction.atomic
def begin_setup(user: User) -> dict:
    """Create (or replace) an unconfirmed authenticator and return what the app needs."""
    if confirmed_device(user) is not None:
        raise ConflictError(
            "Two-factor sign-in is already on. Turn it off first to set up a new phone.",
            code="MFA_ALREADY_ENABLED",
        )
    secret = new_secret()
    MfaDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret_encrypted": encrypt(secret),
            "confirmed_at": None,
            "last_used_step": None,
        },
    )
    return {
        "secret": secret,
        "otpauth_uri": provisioning_uri(secret, account=user.email, issuer=_issuer()),
    }


def _new_recovery_codes(user: User) -> list[str]:
    MfaRecoveryCode.objects.filter(user=user).delete()
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    MfaRecoveryCode.objects.bulk_create(
        MfaRecoveryCode(user=user, code_hash=_fingerprint(code)) for code in codes
    )
    return codes


def _fingerprint(code: str) -> str:
    normalized = "".join(ch for ch in code.lower() if ch.isalnum())
    return hashlib.sha256(normalized.encode()).hexdigest()


@transaction.atomic
def confirm_setup(*, user: User, code: str, request=None) -> list[str]:
    """Check the first code from the app, switch two-factor on, return the recovery codes."""
    device = MfaDevice.objects.select_for_update().filter(user=user).first()
    if device is None or device.confirmed_at is not None:
        raise ConflictError("Start two-factor setup first.", code="MFA_SETUP_NOT_STARTED")
    step = matching_step(decrypt(device.secret_encrypted), code)
    if step is None:
        raise InvalidMfaCode("That code did not match. Check the time on your phone and try again.")
    device.confirmed_at = timezone.now()
    device.last_used_step = step
    device.last_used_at = device.confirmed_at
    device.save(update_fields=["confirmed_at", "last_used_step", "last_used_at"])
    codes = _new_recovery_codes(user)
    if request is not None:
        request.session[SESSION_VERIFIED_KEY] = True
    record_audit_event(
        action=AuditAction.AUTH_MFA_ENABLED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
    )
    return codes


@transaction.atomic
def regenerate_recovery_codes(*, user: User, code: str, request=None) -> list[str]:
    _check_code(user, code, allow_recovery=False)
    codes = _new_recovery_codes(user)
    record_audit_event(
        action=AuditAction.AUTH_MFA_RECOVERY_CODES_REGENERATED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
    )
    return codes


@transaction.atomic
def disable(*, user: User, code: str, request=None) -> None:
    if is_required(user):
        raise ConflictError(
            "Your role requires two-factor sign-in, so it cannot be turned off.",
            code="MFA_REQUIRED_FOR_ROLE",
        )
    _check_code(user, code, allow_recovery=True)
    _remove(user)
    record_audit_event(
        action=AuditAction.AUTH_MFA_DISABLED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
    )


@transaction.atomic
def admin_reset(*, user: User, actor, request=None) -> None:
    """For a lost phone: remove two-factor and sign the person out everywhere. The person sets
    it up again at their next sign-in. Administrators cannot reset their own."""
    if actor is not None and actor.pk == user.pk:
        raise ConflictError(
            "You cannot reset your own two-factor sign-in. Ask another administrator.",
            code="SELF_MFA_RESET",
        )
    from .sessions import end_user_sessions

    _remove(user)
    end_user_sessions(
        user, reason=UserSession.EndReason.SIGNED_OUT_BY_ADMIN, actor=actor, request=request
    )
    record_audit_event(
        action=AuditAction.AUTH_MFA_RESET,
        resource_type="user",
        resource_id=user.pk,
        actor=actor,
        request=request,
    )


def _remove(user: User) -> None:
    MfaDevice.objects.filter(user=user).delete()
    MfaRecoveryCode.objects.filter(user=user).delete()


def _check_code(user: User, code: str, *, allow_recovery: bool) -> str:
    """Accept a current authenticator code (or, if allowed, an unused recovery code).

    Returns "totp" or "recovery_code"; raises InvalidMfaCode otherwise.
    """
    device = (
        MfaDevice.objects.select_for_update().filter(user=user, confirmed_at__isnull=False).first()
    )
    if device is None:
        raise ConflictError(
            "Two-factor sign-in is not on for this account.", code="MFA_NOT_ENABLED"
        )
    step = matching_step(decrypt(device.secret_encrypted), code)
    if step is not None and (device.last_used_step is None or step > device.last_used_step):
        device.last_used_step = step
        device.last_used_at = timezone.now()
        device.save(update_fields=["last_used_step", "last_used_at"])
        return "totp"
    if allow_recovery:
        recovery = (
            MfaRecoveryCode.objects.select_for_update()
            .filter(user=user, code_hash=_fingerprint(code), used_at__isnull=True)
            .first()
        )
        if recovery is not None:
            recovery.used_at = timezone.now()
            recovery.save(update_fields=["used_at"])
            return "recovery_code"
    raise InvalidMfaCode("That code was not accepted. Use the newest code from your app.")


# --- Sign-in challenge --------------------------------------------------------------------


def begin_challenge(request, user: User) -> None:
    """Password was correct and the user has two-factor on: remember who is signing in."""
    request.session[SESSION_PENDING_KEY] = {
        "user_id": str(user.pk),
        "expires_at": (timezone.now() + CHALLENGE_TTL).isoformat(),
        "attempts": 0,
    }


def verify_challenge(request, code: str) -> User:
    """Second sign-in step. Returns the user on success (the caller then logs them in)."""
    pending = request.session.get(SESSION_PENDING_KEY)
    expires_at = parse_datetime(pending["expires_at"]) if pending else None
    if not pending or expires_at is None or expires_at <= timezone.now():
        request.session.pop(SESSION_PENDING_KEY, None)
        raise MfaChallengeExpired("Your sign-in expired. Enter your email and password again.")

    user = User.objects.filter(pk=pending["user_id"], is_active=True).first()
    if user is None:
        request.session.pop(SESSION_PENDING_KEY, None)
        raise MfaChallengeExpired("Your sign-in expired. Enter your email and password again.")

    try:
        with transaction.atomic():
            method = _check_code(user, code, allow_recovery=True)
    except InvalidMfaCode:
        pending["attempts"] += 1
        record_audit_event(
            action=AuditAction.AUTH_MFA_FAILED,
            resource_type="user",
            resource_id=user.pk,
            request=request,
            outcome=AuditEvent.Outcome.FAILURE,
            metadata={"attempt": pending["attempts"]},
        )
        if pending["attempts"] >= CHALLENGE_MAX_ATTEMPTS:
            request.session.pop(SESSION_PENDING_KEY, None)
            raise MfaChallengeExpired(
                "Too many wrong codes. Enter your email and password again."
            ) from None
        request.session[SESSION_PENDING_KEY] = pending
        raise

    request.session.pop(SESSION_PENDING_KEY, None)
    record_audit_event(
        action=AuditAction.AUTH_MFA_RECOVERY_CODE_USED
        if method == "recovery_code"
        else AuditAction.AUTH_MFA_VERIFIED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
        metadata={"method": method},
    )
    return user


def mark_session_verified(request, verified: bool) -> None:
    request.session[SESSION_VERIFIED_KEY] = verified
