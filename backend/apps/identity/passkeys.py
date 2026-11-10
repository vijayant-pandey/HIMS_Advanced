"""Passkeys as a second factor (HIMS-IAM-014; spec 13.1 "MFA for privileged users"; ADR-018).

A passkey is a key kept on the person's phone, laptop or security key. The device proves it holds
the key by signing a fresh challenge, after the person unlocks it (fingerprint, face or PIN). It
only works for this hospital's own web address, so a fake sign-in page cannot use it: it resists
phishing in a way a typed code does not.

Rules:
* A passkey is **added to** the authenticator app, not instead of it. The app stays the fallback
  (and the admin console's method), and the backup codes still work. Switching two-factor off or
  an administrator's reset removes the passkeys too.
* Adding or removing one is a sensitive action (confirm it's you) on a session that passed
  two-factor. Up to 10 per person.
* Each check uses a challenge kept in the session for 5 minutes and used once. The device's
  signature counter must go up, so a copied key is refused.
* Only the public key is stored: there is no secret in the database to steal.

The cryptographic checks are done by Duo Labs' ``webauthn`` library (attestation "none": HIMS
does not ask which device maker it is).
"""

import json
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from apps.audit.services import AuditAction, record_audit_event
from common.exceptions import ConflictError, DomainError

from . import mfa
from .models import Passkey, User

MAX_PASSKEYS = 10
CEREMONY_TTL = timedelta(minutes=5)
SESSION_ADDING = "hims_passkey_registration"
SESSION_CHECKING = "hims_passkey_assertion"
LOGIN = "login"
CONFIRM = "confirm"
_TRANSPORTS = {transport.value for transport in AuthenticatorTransport}


class PasskeyNotAccepted(DomainError):
    status_code = 400
    code = "PASSKEY_NOT_ACCEPTED"
    title = "Passkey not accepted"


def _expires() -> str:
    return (timezone.now() + CEREMONY_TTL).isoformat()


def _take(request, key: str) -> dict:
    """The pending ceremony, used once: removed whether or not it then succeeds."""
    pending = request.session.pop(key, None)
    expires_at = parse_datetime(pending["expires_at"]) if pending else None
    if not pending or expires_at is None or expires_at <= timezone.now():
        raise PasskeyNotAccepted("That took too long or was already used. Try again.")
    return pending


def _rp_name() -> str:
    from apps.organizations.models import Organization

    organization = Organization.objects.only("display_name").first()
    return f"{organization.display_name} HIMS" if organization else "HIMS"


def _descriptors(user: User) -> list[PublicKeyCredentialDescriptor]:
    return [
        PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(passkey.credential_id),
            transports=[AuthenticatorTransport(t) for t in passkey.transports if t in _TRANSPORTS],
        )
        for passkey in Passkey.objects.filter(user=user)
    ]


def available(user) -> bool:
    return Passkey.objects.filter(user=user).exists()


# --- Adding one ---------------------------------------------------------------------------------


def begin_registration(request, user: User) -> dict:
    if mfa.confirmed_device(user) is None:
        raise ConflictError(
            "Set up the authenticator app first: a passkey is added to it, not instead of it.",
            code="MFA_NOT_ENABLED",
        )
    if not mfa.session_verified(request):
        raise ConflictError(
            "Sign in again with two-factor before adding a passkey.", code="MFA_NOT_VERIFIED"
        )
    if Passkey.objects.filter(user=user).count() >= MAX_PASSKEYS:
        raise ConflictError(
            f"You have {MAX_PASSKEYS} passkeys, the most allowed. Remove one first.",
            code="TOO_MANY_PASSKEYS",
        )
    options = generate_registration_options(
        rp_id=settings.HIMS_WEBAUTHN_RP_ID,
        rp_name=_rp_name(),
        user_name=user.email,
        user_id=user.pk.bytes,  # an opaque number, never the email
        user_display_name=user.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=_descriptors(user),
    )
    request.session[SESSION_ADDING] = {
        "challenge": bytes_to_base64url(options.challenge),
        "user_id": str(user.pk),
        "expires_at": _expires(),
    }
    return json.loads(options_to_json(options))


def finish_registration(request, user: User, *, name: str, credential: dict) -> Passkey:
    pending = _take(request, SESSION_ADDING)
    if pending["user_id"] != str(user.pk):
        raise PasskeyNotAccepted("That took too long or was already used. Try again.")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=settings.HIMS_WEBAUTHN_RP_ID,
            expected_origin=settings.HIMS_WEBAUTHN_ORIGINS,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError):
        raise PasskeyNotAccepted(
            "The passkey could not be added. Try again, or use another device."
        ) from None
    transports = (credential.get("response") or {}).get("transports") or []
    try:
        with transaction.atomic():
            passkey = Passkey.objects.create(
                user=user,
                name=name.strip()[:60] or "Passkey",
                credential_id=bytes_to_base64url(verified.credential_id),
                public_key=verified.credential_public_key,
                sign_count=verified.sign_count,
                transports=[t for t in transports if t in _TRANSPORTS][:8],
                backed_up=verified.credential_backed_up,
            )
    except IntegrityError:
        raise ConflictError("This passkey is already added.", code="PASSKEY_EXISTS") from None
    record_audit_event(
        action=AuditAction.AUTH_PASSKEY_ADDED,
        resource_type="user",
        resource_id=user.pk,
        actor=user,
        request=request,
        metadata={"passkey_id": str(passkey.pk), "backed_up": passkey.backed_up},
    )
    return passkey


# --- Using one ----------------------------------------------------------------------------------


def begin_assertion(request, user: User, purpose: str) -> dict:
    descriptors = _descriptors(user)
    if not descriptors:
        raise ConflictError("You have no passkey yet.", code="NO_PASSKEY")
    options = generate_authentication_options(
        rp_id=settings.HIMS_WEBAUTHN_RP_ID,
        allow_credentials=descriptors,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    request.session[SESSION_CHECKING] = {
        "challenge": bytes_to_base64url(options.challenge),
        "user_id": str(user.pk),
        "purpose": purpose,
        "expires_at": _expires(),
    }
    return json.loads(options_to_json(options))


def check_assertion(request, user: User, purpose: str, credential: dict) -> Passkey:
    """The device signed this session's challenge with one of the person's passkeys. Call inside
    a transaction: the passkey row is locked while its counter is moved on."""
    pending = _take(request, SESSION_CHECKING)
    if pending["user_id"] != str(user.pk) or pending["purpose"] != purpose:
        raise PasskeyNotAccepted("That took too long or was already used. Try again.")
    credential_id = credential.get("id") if isinstance(credential, dict) else None
    passkey = (
        Passkey.objects.select_for_update().filter(user=user, credential_id=credential_id).first()
        if isinstance(credential_id, str)
        else None
    )
    if passkey is None:
        raise PasskeyNotAccepted("That passkey is not one of yours here.")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(pending["challenge"]),
            expected_rp_id=settings.HIMS_WEBAUTHN_RP_ID,
            expected_origin=settings.HIMS_WEBAUTHN_ORIGINS,
            credential_public_key=bytes(passkey.public_key),
            credential_current_sign_count=passkey.sign_count,
        )
    except (WebAuthnException, ValueError, KeyError, TypeError):
        raise PasskeyNotAccepted("The passkey was not accepted. Try again.") from None
    counter = verified.new_sign_count
    passkey.sign_count = counter
    passkey.last_used_at = timezone.now()
    passkey.save(update_fields=["sign_count", "last_used_at"])
    return passkey


def verify_login(request, credential: dict) -> User:
    """Second sign-in step with a passkey instead of a code: same expiry and the same count of
    wrong tries as codes."""
    user, pending = mfa.pending_challenge(request)
    try:
        with transaction.atomic():
            check_assertion(request, user, LOGIN, credential)
    except PasskeyNotAccepted:
        mfa.count_failed_attempt(request, user, pending, method="passkey")
        raise
    mfa.finish_challenge(request, user, method="passkey")
    return user


# --- Removing one -------------------------------------------------------------------------------


@transaction.atomic
def remove(*, actor, passkey_id, owner=None, request=None) -> None:
    """The person removes their own (``owner``), or an administrator removes a lost one."""
    rows = Passkey.objects.select_for_update().filter(pk=passkey_id)
    if owner is not None:
        rows = rows.filter(user=owner)
    passkey = rows.first()
    if passkey is None:
        raise ConflictError("No such passkey.", code="NO_PASSKEY")
    user_id = passkey.user_id
    passkey.delete()
    record_audit_event(
        action=AuditAction.AUTH_PASSKEY_REMOVED,
        resource_type="user",
        resource_id=user_id,
        actor=actor,
        request=request,
        metadata={"passkey_id": str(passkey_id), "by_owner": owner is not None},
    )
