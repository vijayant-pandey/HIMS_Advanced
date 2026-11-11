# ADR-034: A free Development environment on a host that needs no payment card

**Status:** Proposed (2026-11-11) · **Items:** HIMS-OPS-020 (analysis), HIMS-OPS-022, -023, -024 ·
**Spec:** 17, 30, 31, 34 · **Puts on hold:** [ADR-027](ADR-027-hosting-on-oracle-cloud.md)

## Context

ADR-027 planned hosting on Oracle Cloud's free offering. Oracle asks every new account for a credit
or debit card for identity checks, and the PO has none available now. The PO asked for a host that
is free to use and asks for no payment.

The analysis ([hosting analysis](../architecture/hosting/hosting-analysis.md)) found that free
hosts without a card exist for a **test** environment, but none gives what real hospital data needs:
backups beyond a few hours, a virus scanner (about 1 GB of memory), durable document storage, legal
agreements (HIPAA BAA, DPDP data processing) and an India region.

## Decision

1. **Stage A (now, no spend):** one hosted environment, **Development** (spec 31.1), with synthetic
   data only, deployed from the `development` branch:
   * first choice **Northflank Sandbox** (always on, a database, scheduled jobs). **Chosen:** the PO
     signed up on 2026-11-11 with no card asked; region **Europe - West (London)** (the free plan
     offers London and US - Central only; Delhi is paid). **Found at set-up:** a Northflank database
     asks for a card, so the database is **Neon** (no card) and Northflank runs only HIMS and its
     timer, if those need no card;
   * otherwise **Render** (free web service) + **Neon** (free PostgreSQL, Singapore) + **GitHub
     Actions** (scheduled jobs every 5 minutes).
   * **Final choice (2026-11-11):** Northflank's database needs a card and its status page showed an open
     security incident, so **Render (Singapore) + Neon (Singapore, direct connection) + cron-job.org**
     calling a token-protected timer address every minute (instead of GitHub Actions: every minute, no
     Actions minutes used, and it keeps the free service awake). Database updates and the first
     administrator are run from the PO's PC. Steps: [Render + Neon guide](../workflows/render-neon-hosting.md).
2. HIMS is made to fit these hosts without changing how it behaves: the screens are served by the
   same server as the API (HIMS-OPS-022), and the scheduled jobs can be started by an outside clock
   (HIMS-OPS-023). Then the environment is set up (HIMS-OPS-024).
3. Every hosted environment runs `python manage.py hosting_check` in its deployment: nothing marked
   "Must fix" may remain. Items marked "Before real data" are accepted on Stage A only.
4. **Stage B (before real patients):** paid hosting chosen with the PO (Oracle once a card is
   available, AWS as in the specification, or another provider with an India region and the needed
   agreements). The remaining hosting-stage tickets are done there.

## Alternatives

* **Wait for a card and use Oracle:** delays every hosted test. Kept as a Stage B option.
* **Only demos from the PC through a tunnel:** the PC must stay on; testers cannot use it for days.
  Kept for short demos.
* **Separate static host for the screens:** HIMS signs in with cookies tied to one address; a
  second address would need cross-site cookies, which weakens CSRF protection. Rejected.

## Consequences

* The free Development environment sleeps (Render) or is small (Northflank); slow first loads are
  expected and are not measured against the spec 18 targets.
* Audit sealing may run every 5 minutes instead of every minute on Plan 2; the hosting check allows
  10 minutes before it reports the scheduler missing.
* QA, Staging and Production branches stay as promotion branches until Stage B.

**Owner:** PO. **Review:** at sign-up (offers change), and when a card becomes available.
