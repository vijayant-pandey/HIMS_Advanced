# Passkeys as a second factor (HIMS-IAM-014)

**Spec:** 13.1 ("MFA for privileged users"). Decision record: [ADR-018](../decisions/ADR-018-two-factor-sign-in.md)
(update of 2026-11-10).

## What a passkey is

A passkey is a key kept on your phone, laptop or a security key. To use it, you unlock the device the
way you normally do (fingerprint, face or PIN) instead of typing a 6-digit code.

It is safer than a code: **a passkey only works on this hospital's own HIMS address.** If someone
sends you a fake sign-in page, your device simply will not offer the passkey there, while a code
could be typed into the fake page.

## How HIMS uses them

- A passkey is **added to** two-factor sign-in, **not instead of it.** You set up the authenticator
  app first (Security page). The app and your backup codes keep working, so a lost device never
  locks you out.
- **Signing in:** after your password, choose **Use a passkey**, or type the code as before.
- **Confirm it's you** (before sensitive actions): your password, then **Confirm with a passkey
  instead of the code**. A passkey never replaces the password.
- **Admin console:** still asks for the authenticator code. Its sign-in page has no passkey button.
- Up to **10 passkeys** each, e.g. your phone and your work laptop.

## Adding one

1. Sign in with two-factor. Menu → your name → **Security**.
2. Under **Passkeys**, type a name you will recognise, e.g. "Work laptop", and press **Add a passkey**.
3. Confirm it's you if asked (password and code).
4. Your device asks you to unlock it. Done: the passkey appears in the list.

## Removing one

- **Yourself:** Security → Passkeys → **Remove** (confirm it's you if asked).
- **A lost or stolen device:** an administrator removes it in the admin console → **Passkeys** →
  choose it → **Remove selected passkeys** (confirm it's you). The person keeps their code.
- **Switching two-factor off**, or an administrator's **reset two-factor**, removes all the person's
  passkeys too.

Every passkey added, used, refused and removed is in the audit log.

## Safety details

| What | Why |
|---|---|
| Only the **public** key is stored | There is no secret in the HIMS database to steal; the private key never leaves the device |
| Each check signs a fresh, single-use challenge that expires after 5 minutes | An old answer cannot be replayed |
| The device's counter must go up each time | A copied key is refused |
| Checked for this site's address and name only | A passkey made for another site is refused |
| Wrong tries count with wrong codes: five end the sign-in | Same limit as codes |
| The person's internal number, not their email, is given to the device as their ID | Nothing personal stored on the device beyond the name shown to them |

The cryptographic checks use Duo Labs' `webauthn` library (version 3.0.1, with its helpers `cbor2`,
`pyasn1`, `pyasn1-modules` and `pyOpenSSL`), added through the hash-locked lockfile
([adding a library](dependencies.md)).

## Settings

Passkeys belong to a web address. Both settings follow `HIMS_APP_BASE_URL`, so usually nothing needs
setting:

| Setting | Default | Meaning |
|---|---|---|
| `HIMS_WEBAUTHN_RP_ID` | The host name of `HIMS_APP_BASE_URL`, e.g. `localhost` or `hims.hospital.example` | The site a passkey belongs to |
| `HIMS_WEBAUTHN_ORIGINS` | The full address of `HIMS_APP_BASE_URL`, e.g. `http://localhost:5175` | Where the browser may answer from |

**Changing the hospital's web address later makes existing passkeys stop working** (they belong to
the old address). People then use their code and add a new passkey. Plan this before hosting
(HIMS-OPS-020).

Browsers allow passkeys only on `https://` addresses, or on `localhost` on your own PC.

## On your PC

- Windows Hello (PIN, fingerprint or face) works as a passkey in Chrome and Edge.
- A phone can be used too: Chrome shows a QR code to scan.
- The India and US hospitals on your PC run on different addresses, so each needs its own passkey.
