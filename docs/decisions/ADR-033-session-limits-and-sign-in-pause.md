# ADR-033: Session limits background refreshes cannot defeat, and a sign-in pause per account

**Status:** Proposed (2026-11-11) · **Items:** HIMS-SEC-011 (findings F-01, F-02) · **Spec:** 13.1

## Context

The security review of Phase 1 found two gaps in spec 13.1 ("secure session lifecycle, revocation
and expiration"; "login throttling"):

* Django renews the 30-minute idle timeout on every request. Four screens refresh themselves on a
  timer (Bed board, Background jobs, Rota "on call now", the confirm-it's-you status), so a screen
  left open stayed signed in for ever. There was no upper limit on a session's age.
* Wrong passwords were counted per client address only (10 a minute in the app, 5 in the console),
  so guessing one person's password from many addresses was never slowed down.

## Decision

**Sessions.** A middleware (`apps/identity/session_limits.py`) keeps two times in the session:
when the person signed in, and the last request they made. The app marks its timed refreshes with
the header `X-HIMS-Background: 1` (only once the screen already has data, so opening a screen still
counts as use); those do not move the "last request" time. The session ends after
`HIMS_SESSION_IDLE_SECONDS` (default 30 minutes) without use and after `HIMS_SESSION_MAX_SECONDS`
(default 12 hours, a long shift) in any case. Ending closes the sign-in register entry as expired
and writes `auth.sessions.ended` with the reason; the request continues signed out (401), so the
app shows the sign-in page. Hosted settings refuse idle limits outside 5–60 minutes and maximum
lifetimes outside 1–24 hours.

**Sign-in pause per account.** Failed sign-ins are also counted per email (hashed, in the shared
cache) for every email typed, whether or not an account uses it. After `HIMS_SIGN_IN_MAX_FAILURES`
(10) within `HIMS_SIGN_IN_PAUSE_SECONDS` (15 minutes), sign-in with that email answers 429
`SIGN_IN_PAUSED` in the app and the console, with the same answer for unknown emails. A correct
password clears the count.

## Alternatives

* **Idle sign-out only in the browser:** a script can fail or be closed with the tab still signed
  in; the server must decide. Rejected as the only control.
* **Stop the timed refreshes:** the bed board on a wall is exactly where live data matters. Rejected.
* **Lock the account until an administrator unlocks it:** lets anyone lock out any colleague by
  typing wrong passwords. A pause that runs out by itself limits that to 15 minutes. Rejected.

## Consequences

* A wall screen needs a sign-in every 30 minutes of nobody touching it; that is the point.
* Someone can pause a colleague's sign-in for 15 minutes by guessing; the colleague can still reset
  the password. Pauses show as failed sign-ins with reason "paused" in the audit log.
* Hosted environments need the shared cache (Redis) so all server processes count together.

**Owner:** PO. **Review:** with the independent penetration test (HIMS-SEC-021).
