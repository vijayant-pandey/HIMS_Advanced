# Admin console address allow-list

**Ticket:** HIMS-SEC-015 · **Spec:** 13.1 (authentication), 13.4 (monitoring of privileged
access), 17 (hosted deployment) · Related: [ADR-016](../decisions/ADR-016-admin-operations-console.md),
[ADR-022](../decisions/ADR-022-browser-protection-and-client-address.md) (real client address),
[ADR-027](../decisions/ADR-027-hosting-on-oracle-cloud.md) (hosting)

## In one paragraph

The admin console (`/admin/`) can change almost anything, so it now **answers only the addresses
you list** in the server setting `HIMS_ADMIN_ALLOWED_NETWORKS`, such as the hospital's office or
VPN network. Anyone else gets the same **"Not found"** page as when the console is switched off:
before they can try a password, and even with a correct password or a session stolen from
someone who is allowed. Each refused address is counted per day and shown on the Compliance
page (**Console access** tab) and in the console (**Security status**), and the first refusal of the
day is written to the audit log. A firewall rule in front of the server is added at hosting
(HIMS-OPS-020); this setting is the second layer that stays even if that rule is wrong.

## How it works

| Piece | Where |
|---|---|
| The setting | `HIMS_ADMIN_ALLOWED_NETWORKS`: addresses or networks, comma separated, e.g. `10.8.0.0/16,192.0.2.15` |
| The check | `common/admin/allowed_addresses.py`, on **every** console page (sign-in included), before Django's own checks |
| Whose address | The real client address from `common/client_ip.py` (believes `X-Forwarded-For` only from `HIMS_TRUSTED_PROXIES`). One of our own proxies is never enough: then the real sender is unknown |
| Refused | The same "Not found" page as an address that does not exist; `/admin` without the slash is not redirected either, so nothing reveals the console |
| Counted | Table `console_access_blocks`: one row per day and address, at most 500 a day (`apps/compliance/console_access.py`) |
| Audited | "Admin console refused: address not allowed" the first time each address is refused each day, and again the first time a **signed-in** session shows up from it (that session may be in the wrong hands) |
| Reviewed | Compliance page → Console access → **Mark reviewed** (needs `compliance.manage`), or the console's list "Console access blocks" → action "Mark selected as reviewed". Audited |

**Why it is not editable on a screen:** what protects the console must not be changeable through
the console (or the app). The list changes only with the server's settings, like the other
security settings.

## Defaults

| Where | Default | What happens |
|---|---|---|
| Your PC (local settings) | `127.0.0.1,::1` (this computer only) | Same as before: you use the console from this computer |
| Tests | `127.0.0.1,::1` | Tests of refused addresses change the address on purpose |
| Hosted (Development, QA, Staging, Production) | Console **off** (`HIMS_ENABLE_ADMIN` false) | No list needed |
| Hosted with the console **on** | Must be set | The server **refuses to start** without a list, or with `0.0.0.0/0` or `::/0` (every address) |

## Using the console from another computer on your network (optional)

Only if you really need it. In `backend\.env` (and `backend\.env.us` for the US hospital) add, for
example:

```
HIMS_ADMIN_ALLOWED_NETWORKS=127.0.0.1,::1,192.168.1.20
```

Use the other computer's own address, not a whole network, and restart HIMS. The Console access
tab shows the list and whether **your** address is on it. On its own this is not enough: HIMS on
your PC listens only to this computer, and `DJANGO_ALLOWED_HOSTS` must also name this PC's address.
Only do this on a home or office network you trust.

## At hosting (Oracle Cloud, ADR-027)

1. Keep the console off unless it is needed (`HIMS_ENABLE_ADMIN=false`).
2. If it is on: set `HIMS_ADMIN_ALLOWED_NETWORKS` to the VPN or office network, and
   `HIMS_TRUSTED_PROXIES` to the load balancer's network (otherwise every request looks like the
   load balancer and is refused).
3. Add the firewall layer (HIMS-OPS-020): a network security rule or load-balancer rule that only
   lets the same networks reach `/admin/`.
4. After deploying, open the Compliance page → Console access from an allowed computer: it must say
   your address can use the console. From a phone on mobile data, `/admin/` must say "Not found".

## When something is refused

| You see | What it means | What to do |
|---|---|---|
| "Not found" on `/admin/` from a computer that should work | Its address is not on the list, or the proxies setting is wrong | Compliance → Console access shows "your address"; add it, or fix `HIMS_TRUSTED_PROXIES` |
| A few refusals, nobody signed in | Someone tried the address (a scan, or staff working from home) | Mark reviewed with a note |
| A refusal with **Signed in as** a person | That person's console session was used from an address they do not use | Treat as a **security incident**: report it, sign that person out everywhere (Accounts or the console), reset their password |
| Many addresses in one day | Someone is scanning for the console | Report as a security incident; check the firewall rule (HIMS-OPS-020) |

## Tests

- `common/admin/tests/test_console_allow_list.py`: this computer reaches the console and others
  get the same "Not found" as a missing page (also without the slash); a correct password from
  elsewhere signs nobody in; a session used from elsewhere is refused and named; refusals added up
  per day and audited once (again for a signed-in session); ids removed from the recorded page;
  capped; the rest of HIMS unaffected; nothing counted with the console off; behind the load
  balancer the real address decides and a faked header or the proxy itself is not enough; IPv4
  through IPv6; lists that let everyone in or cannot be read are refused; hosted settings refuse
  to start without a proper list.
- `apps/compliance/tests/test_console_access.py`: the Console access status and list, reviewing
  (audited, once, with versions), permissions, the console's list and Security status page.
- Browser tests (`04-audit-and-safety`): the Console access tab in Chrome with the accessibility
  check; the console's new pages open under its protection rules.
