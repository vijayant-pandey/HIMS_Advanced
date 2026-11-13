# ADR-037: Patient search: exact numbers first, then names by similar spelling and by sound

**Status:** Proposed (2026-11-13) · **Items:** HIMS-PAT-002 · **Spec:** 4.5, 13.4, 28.6

## Context

The front desk must find a returning patient before registering one (P0 part 01 sections 1 and 2),
or the same person gets two records. P0 asks for one search box: MRN (exact), phone (exact after
normalising), ID number (exact) or name (similar spelling, any order), optionally with age or sex;
at most 50 results showing only the minimum; every search audited. Spec 28.6 asks for "patient
search by approved demographic/search index, with privacy constraints".

Names in Indian and US hospitals are written several ways. PostgreSQL's trigram matching
(`pg_trgm`), measured on 2026-11-13, handles typing mistakes and the start of a name well
("sunitha" and "sun" find Sunita, scores 0.63 and 0.75), but **not** common spelling variants:

| Typed | Patient | Trigram word similarity |
|---|---|---|
| suneeta | Sunita | 0.38 |
| muhammad | Mohammed | 0.25 |
| lakshmi | Laxmi | 0.27 |

Standard Soundex (English names) also misses several of these (Lakshmi / Laxmi).

## Decision

1. **Exact numbers first.** If what was typed has a digit (or `@`), it is tried as an MRN (also an
   earlier MRN kept as an alias after a merge; digits alone match the number part: `123` finds
   MRN-00000123), then a phone number (normalised to international format; the patient's own
   phones only, not relatives'), then an ID number. ID numbers are compared by their keyed
   fingerprint (ADR-036), so the number is never searched in plain text. A previous hospital's
   MRN is tried with each hospital name on record, since its fingerprint includes the issuer. If
   only a number was typed and nobody has it, the answer is "no patient found", not an error.
2. **Names by spelling and by sound.** Otherwise each word typed (any order) must match a word of
   the patient's names, earlier names included, **either** by trigram word similarity (threshold
   0.6, PostgreSQL's default) **or** by an equal **sound key**: the first letter (any vowel counts
   as "a"), then the remaining letters without vowels and without `h`, doubled letters once, after
   `ksh`/`ks` → `x`, `ph` → `f`, `ck`/`q` → `k`, `w` → `v`. Sunita, Suneeta and Sunitha are all
   `snt`; Mohammad and Muhammad `md`; Lakshmi and Laxmi `lxm`. Words in other scripts are kept as
   written (casefolded). A number among the words is an age in years (give or take one).
3. **Stored and indexed.** `patients.search_name` (already there, with earlier names) gets a GIN
   trigram index; a new `patients.search_sounds` array holds the sound keys, with a GIN index.
   Both are refreshed at registration and every name change; the migration fills existing
   patients.
4. **Filters and limits.** Sex and age (give or take a year). P0 also mentions the date of birth;
   it is **not** a filter, because it would travel in the web address and spec 13.3 keeps
   sensitive fields out of addresses (the guard test `test_no_api_takes_a_secret_in_the_address`
   refuses it); the age does the same job. At least 3 letters of a name; at most 50 results, best match first; the response
   says how many matched in all, so the screen asks for more detail.
5. **Audit and privacy.** Every search, in the app and the admin console, writes
   `patient.searched` with the kind of search, the number of results and the filter names, never
   what was typed. Results carry only name, MRN, age and sex, the phone's last 4 digits, the
   facility and what matched. The search goes in the address (`GET /api/v1/patients/?search=`,
   as spec 20 names it); the server's access log and traces already record the path only, never
   the query string (ADR-021).

## Consequences

* Spelling variants and typing mistakes are both found; very short sound keys (`md`) find more
  people, so results are ranked by spelling closeness and capped at 50.
* The sound key is a simple, documented rule, not a full phonetic library: it can be improved
  later with test cases from real front-desk use; any change must refill `search_sounds`
  (a data migration).
* **AWS stage (later):** the load balancer's access logs record full addresses by default; they
  must leave out the query string, or search words would reach them. Recorded with the AWS
  logging item (HIMS-PLAT-019) in the decisions log.
* Not yet: "last visit date and department" in results (needs visits, HIMS-CLIN-001) and hiding
  restricted (VIP/staff) records (HIMS-PAT-006). Duplicate warnings at registration
  (HIMS-PAT-003) will reuse this search.

## Alternatives considered

* **Trigram only:** misses the common variants above.
* **Soundex / Double Metaphone (`fuzzystrmatch`):** built for English names; Lakshmi / Laxmi and
  several Indian spellings still differ, and it adds an extension without solving the problem.
* **A search engine (OpenSearch):** more to run and secure for a need PostgreSQL meets; can be
  revisited for very large hospitals.
* **POST for search (no words in the address):** keeps words out of every log by design, but the
  spec names `GET ...?search=`, and the logs already strip query strings.
