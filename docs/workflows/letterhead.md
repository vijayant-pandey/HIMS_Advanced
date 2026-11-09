# Hospital logo and letterhead (HIMS-ORG-006)

**Spec:** 4.1 "hospital logo, templates". Decision record:
[ADR-028](../decisions/ADR-028-message-wording-and-letterhead.md).

## Setting it up

Menu → **Hospital settings** → **Letterhead** (needs `organization.manage`).

- **Upload logo:** a PNG or JPG picture, up to 2 MB.
- **Edit letterhead:** address, phone, email, website, registration or tax number, and a last line
  such as a helpline. All optional.
- **Print a sample** shows how it looks on paper.

The admin console has the same fields: **Organizations** → open the hospital → **Letterhead on
printouts and emails**.

There is one letterhead for the whole hospital. A letterhead per branch can be added if hospitals
ask for it.

## Where it appears

| Where | What happens |
|---|---|
| **Printouts** | Today the [equipment register](equipment-register.md). Later screens that print use the same `PrintLetterhead` component: put it at the top and mark controls with `HIDE_WHEN_PRINTING`. Phase 2 visit summaries are the next user |
| **Emails** | The plain text gets the hospital's details at the end. An HTML copy has the logo at the top and clickable links |
| **SMS** | Stays plain: there is no room for a letterhead |

With nothing set up, emails go out exactly as they did before: plain text only.

## Safety

- **Only PNG and JPG**, read from the first bytes of the file, not its name. **SVG is refused**
  because an SVG file can carry scripts.
- The file is stored under a random name and has no public address. Only people who are signed in
  can open it. Emails carry the logo inside the message.
- The delivery log (**Messages**) keeps the message only, not the letterhead.
- If the logo file cannot be read, the email still goes, without the logo.
- Text is escaped in the HTML copy, so nothing typed into a message or the letterhead can become
  markup.
- Every change to the logo or details is in the audit log.

## On your PC

Emails print in the launcher window as text. The encoded logo is left out on purpose, so the
sign-in link stays easy to find. A line says that an HTML copy goes too.
