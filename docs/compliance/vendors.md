# Vendors and contracts (spec 13, 23, 26.7; HIMS-COMP-004)

DRAFT. Fill in as vendors are chosen. Personal or patient data must not reach a vendor before the contract is signed.
US: a Business Associate Agreement (BAA). India: a data processing contract under DPDP section 8(2).

| Service | Vendor | Personal data? | Contract needed | Status |
|---|---|---|---|---|
| Hosting, database, backups, file storage | AWS (later stage) | Yes, all | BAA (US) / data processing terms (India) | Not chosen for production |
| Email | Gmail for testing only; a sending service such as Amazon SES for production | Names, addresses, links | BAA / processing terms. **Gmail personal accounts are not for real patients** | Testing only |
| SMS | India: DLT-registered gateway; US: e.g. Twilio or Amazon SNS | Phone numbers, short text | BAA / processing terms | Not chosen |
| Source code and CI | GitHub | No patient data; synthetic only | Standard terms | In use |
| HIMS provider (software support) | | Yes, if support can reach production | BAA / processing terms; access requested, time-limited and audited (spec 26.5) | To agree |
| Drug database, lab, PACS, insurers/TPAs, Stedi, ABDM | Later phases | Yes | Per integration (spec 26.6) | Later |

For each vendor record: legal name, data location, what data, security evidence (e.g. SOC 2, ISO 27001), contract date
and renewal, breach-notice duty to the hospital, and a named contact.
