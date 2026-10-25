# ADR-011: Server-side session authentication for the browser SPA

**Status:** Proposed — needs Security approval. The identity-provider question in spec 36 is still
open. **Owner:** Security + Architecture.

## Decision
- The staff SPA authenticates with Django's database-backed session (`hims_session`: HttpOnly,
  Secure, SameSite=Lax) and is served same-origin with the API via CloudFront/ALB.
- CSRF protection is enforced on every unsafe request, including login. The SPA reads
  `hims_csrftoken` and sends `X-CSRFToken`.
- Sliding idle timeout: 30 minutes by default (`HIMS_SESSION_IDLE_SECONDS`). Clinical governance
  may set a different value per deployment.
- Passwords use Argon2 with a minimum length of 12. Login is rate-limited and gives the same
  answer for an unknown account, a wrong password and an inactive account. Successful and failed
  logins are audited.
- An inactive user fails authentication on the next request, and every grant is evaluated only
  for active users.

## Alternatives
- JWTs in browser storage: exposed to XSS and hard to revoke. Rejected for the clinical UI.
- OIDC/SAML enterprise SSO: likely to be required by hospital customers. It can sit in front of
  this session model (the IdP authenticates, Django issues the session) and is tracked as
  HIMS-IAM-008.

## Follow-ups
MFA for privileged users (HIMS-IAM-005); terminating all sessions on suspension or termination
(HIMS-IAM-006); a reauthentication step-up for sensitive actions (HIMS-IAM-007).
