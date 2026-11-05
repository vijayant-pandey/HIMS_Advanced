# ADR-023: Confirm before sensitive actions

**Status:** Proposed. **Owner:** Engineering lead. **Ticket:** HIMS-IAM-007.
**Spec:** 13.1 ("reauthentication for sensitive actions where justified"), 13.4 (auditability), 23
(threat model). How-to and the full list: [sensitive-actions.md](../workflows/sensitive-actions.md).

## Decision

- **Enforced by the server, per session.** Views declare `sensitive_actions`; the default permission
  class checks them after the normal permission check. The time of the last confirmation is kept in
  the session, so it ends with the session and needs no new table.
- **Password plus second factor.** A person with two-factor must give both, and a code cannot be used
  twice. Password alone would let someone who only knows the password act from a stolen session.
- **A time window, 15 minutes by default.** Asking for every action trains people to type passwords
  without thinking; a long window protects little. Signing in counts as confirming.
- **The app handles it in one place.** The API client catches `REAUTH_REQUIRED`, shows one dialog and
  repeats the same request. No screen needs its own handling, and future screens are covered.
  Downloads are plain links, which cannot react to a refusal, so they confirm first.
- **The admin console has the same rule,** through a mixin and its own page. It redirects before
  anything is saved and the person repeats the action: re-sending a console form automatically would
  mean storing its contents across the redirect.
- **Five wrong tries end the session.** A per-session count is enough, because getting a new session
  needs the password.
- **The session key is not rotated on confirming.** The sign-in register tracks sessions by key, and
  the key was already rotated at sign-in. The window limits what a stolen session can do.
- **A hospital can turn it off** with a reason (Features, audited). It defaults to on.

## Rejected
- **Separate short-lived confirmation tokens.** More moving parts than a session value, with no
  benefit while the session cookie is the only credential.
- **Asking inside each service function.** Services also run from background jobs, which have no
  person to ask.

## Consequences
- Every list of "what asks" is a judgment call. A test pins the list, so changes are deliberate.
- A long batch of decisions can be interrupted once by the dialog, without losing work.
- Single sign-on (HIMS-IAM-008) will need its own way to confirm, since those people have no HIMS
  password.
- Clinical actions such as emergency access and signing need their own design: HIMS-IAM-011 and
  HIMS-IAM-020, in Phase 2.
