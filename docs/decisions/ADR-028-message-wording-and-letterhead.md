# ADR-028: Editable message wording with fixed placeholders; letterhead added at delivery

**Status:** Proposed (2026-11-09) · **Items:** HIMS-NOTIF-003, HIMS-ORG-006 · **Spec:** 4.1, 4.23, 13.3

## Context

Spec 4.1 asks for hospital logo, templates and notification settings. Every email's text used to be
written in code at the place that sent it. Hospitals need to change the wording and show their own
letterhead, and this text goes out to everyone, including sign-in links.

## Decision

**1. Wording is plain text with a fixed list of placeholders per message; no template engine.**
Each message is declared in `message_catalog.py` with its standard wording and its variables.
Replacing `{{name}}` is a single pass over the text. A template language such as Django's would let
whoever edits the wording reach into objects and run logic, which is a known route to data exposure.
Optional parts, such as a note, are values that may be empty.

**2. A row per message; blank means "use the standard".** Wording left as the standard follows
upgrades. If stored wording no longer fits the catalog, the standard is used and a warning logged:
a sign-in link is never held back by a typing mistake.

**3. Changing wording is a separate permission and a sensitive action.** It reaches everyone, so it
needs its own permission, two-factor sign-in and a recent "confirm it's you", and it is audited with
the wording before and after.

**4. The letterhead is added at delivery, not stored in the message.** The delivery log keeps the
message alone, retries use the current letterhead, and the stored copy's secret handling
(HIMS-NOTIF-001) does not change. With no letterhead set up, the email is plain text exactly as
before.

**5. The logo travels inside the email (CID).** Mail programs block pictures loaded from elsewhere,
and HIMS does not serve files to people who are not signed in. PNG and JPG only; SVG can carry
scripts.

## Consequences

- Each sender passes values rather than sentences; the existing wording moved to the catalog
  unchanged.
- An administrator can still add a misleading link to a message. Separate permission, confirmation
  and the audit log are the controls; checking link targets is not attempted.
- New messages cost one catalog entry and appear on both screens by themselves.
- Conditional wording is limited to optional values. That is deliberate.
