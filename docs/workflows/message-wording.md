# Message wording (HIMS-NOTIF-003)

**Spec:** 4.1 "templates and notification settings", 4.23. Decision record:
[ADR-028](../decisions/ADR-028-message-wording-and-letterhead.md).

A hospital can change the words of every email HIMS sends, without a developer. The standard
wording is always kept and can be used again at any time.

## Using it

Menu → **Message wording**. It lists every message, when it is sent, and whether its wording is
**Standard** or **Changed**.

1. Select a message.
2. Change the **Subject** or **Message**. Placeholders such as `{{name}}` are filled in when the
   message is sent. The list under the box shows which ones this message has.
3. **Preview** shows how it reads, with made-up details. Nothing is saved or sent.
4. **Save**. The next message sent uses the new wording.

**Use the standard wording** puts it back.

The admin console has the same: **Notifications** → **Message templates**, with the same checks. Its
action "Go back to the standard wording" works on several at once.

## The checks

| Refused | Why |
|---|---|
| A placeholder this message does not have, e.g. `{{patient_name}}` | Nobody can pull other data into a message by typing a placeholder |
| Removing one marked **must stay**, e.g. `{{link}}` in the invitation | The message is useless without it |
| Single braces, e.g. `{{name}` | It would be sent as odd text |
| An empty subject or message, or a subject on two lines | |

Text is plain: HIMS does not run the wording as code, so typing into this box cannot run anything.

**Do not type patient details into the wording.** The box goes to everyone who receives the message.

## Who can do what

| Permission | Allows | Held by |
|---|---|---|
| `notifications.view` | Read the wording and preview it | Organization administrator |
| `notifications.templates.manage` | Change it, or go back to the standard | Organization administrator |

Holding `notifications.templates.manage` makes two-factor sign-in mandatory. Saving asks to
[confirm it's you](sensitive-actions.md), because this text reaches everyone, including sign-in
links. Every change is in the audit log with the wording before and after. The HIMS link in a message
cannot be removed where it is marked **must stay**, but an administrator could still add another
link: the audit log shows who did.

## What happens in an upgrade

- Wording left as the standard follows new versions of HIMS.
- Changed wording stays. If it no longer fits (a placeholder was renamed, say), the message goes out
  in the standard wording and a warning is logged. A message is never held back.

## What is not here

- **The test message** on the Messages page: it checks that delivery works and promises to contain
  no personal data, so it is not editable.
- **SMS wording:** no message goes by SMS yet apart from the test. Real SMS comes with the gateway
  (HIMS-NOTIF-002). In India, DLT rules also need each SMS template registered.
- **Per-patient opt-out:** comes with patients and consent in Phase 2 (HIMS-NOTIF-004).
- **Languages:** one wording per message for now.

## Adding a new message (for developers)

Add it to `apps/notifications/message_catalog.py` and send it with `send_message(key, to=…, values=…)`.
It then appears on both screens by itself. Never put patient details in `values`.
