# ADR-018: Two-factor sign-in with authenticator apps (TOTP)

**Status:** Proposed — needs Security approval. **Owner:** Security. **Ticket:** HIMS-IAM-005.
**Spec:** 4.4 (MFA), 13.1 ("MFA for privileged users"), 13.3 (encryption at rest, key rotation),
13.4 (audit).

## Decision
- **Method:** time-based one-time passwords (RFC 6238; HMAC-SHA1, 6 digits, 30 s), the standard
  supported by Google/Microsoft Authenticator, Authy and similar apps. One step of clock drift is
  tolerated; an accepted code cannot be reused (`last_used_step`). SMS codes are not used (weaker,
  and India requires DLT registration for SMS).
- **Who must use it:** anyone holding a permission in
  `access_control.catalog.MFA_REQUIRED_PERMISSIONS` (admin console, organization/facility
  management, staff management and credential verification, role and role-assignment management,
  audit log). Hospitals may require it for everyone (`HIMS_MFA_REQUIRED_FOR_ALL`). Other users
  may opt in. Clinical permissions are added to the list when clinical governance decides
  (RBAC document).
- **Enforcement:** a privileged user whose session has not passed two-factor can only reach the
  Security endpoints (`/api/v1/auth/mfa/...`, `/auth/me/`, logout); every other API call returns
  403 `MFA_SETUP_REQUIRED`, and the admin console refuses access. The React app sends such users
  straight to the Security page.
- **Sign-in:** two steps. The password step returns 202 `mfa_required` and stores a pending
  challenge in the anonymous session (5 minutes, 5 wrong codes, then start again). The code step
  signs the person in and marks the session as two-factor-verified. The admin console login form
  has an "Authenticator code" field.
- **Recovery:** 10 one-time backup codes at setup (SHA-256 fingerprints stored, never the codes).
  Regenerating needs a current code. Turning two-factor off needs a code and is impossible for
  roles that require it. An administrator can reset someone else's two-factor (lost phone), which
  also signs that person out everywhere; nobody can reset their own.
- **Secret storage:** the authenticator secret is encrypted with Fernet keys from
  `HIMS_FIELD_ENCRYPTION_KEYS` (newest first, so keys can rotate). Managed environments must supply
  keys from the secret manager, one set per environment and customer; production refuses to start
  without them, and refuses to start with privileged two-factor switched off. Developer machines
  and tests derive a local key from `DJANGO_SECRET_KEY`.
- **Audit:** `auth.mfa.enabled`, `.disabled`, `.reset`, `.verified`, `.failed`,
  `.recovery_code_used`, `.recovery_codes_regenerated`, plus `auth.login` with `{"mfa": true}`.

## Alternatives
- WebAuthn / passkeys: stronger and phishing-resistant, but needs device support and more UI
  work. Planned as an addition, not a replacement (HIMS-IAM-014).
- Enterprise SSO with the identity provider's MFA (HIMS-IAM-008): when a hospital uses SSO,
  its IdP's MFA can satisfy this requirement.

## Consequences
- Existing privileged accounts are asked to set up two-factor at their next sign-in.
- Losing both the phone and the backup codes needs an administrator reset (by design).
- Step-up re-authentication for individual sensitive actions remains HIMS-IAM-007.
  (Update 2026-11-05: done, see [ADR-023](ADR-023-confirm-before-sensitive-actions.md).)

## Update 2026-10-28 (HIMS-ORG-004)
Hospitals can now also require two-factor for everyone themselves, on the Features page
("Two-factor sign-in for all staff", ADR-019). The setting is audited and needs a reason. The
server setting `HIMS_MFA_REQUIRED_FOR_ALL` still works and takes precedence.

## Update (2026-11-10, HIMS-IAM-014: passkeys built)

Passkeys are built as planned above: **an addition, not a replacement.**

- A passkey can be added only once the authenticator app is on, and only on a session that passed
  two-factor, after "confirm it's you". The app, the backup codes and the admin console's code stay.
  Switching two-factor off, or an administrator's reset, removes the passkeys.
- A passkey answers the second sign-in step and "confirm it's you" (always with the password). Wrong
  tries count with wrong codes.
- Checks use Duo Labs' `webauthn` library rather than code of our own: the format and signature rules
  are subtle, and a maintained, widely used implementation is the safer choice for sign-in.
  Attestation "none": HIMS does not ask which maker the device is from.
- Only the public key is stored; challenges are single-use and expire after 5 minutes; the device's
  counter must rise; the site is `HIMS_WEBAUTHN_RP_ID`, which follows `HIMS_APP_BASE_URL`.
- Not done: passkey sign-in to the admin console (it would need scripts on the console's sign-in page),
  and signing in with a passkey alone, without a password. Both can follow if the hospitals ask.
