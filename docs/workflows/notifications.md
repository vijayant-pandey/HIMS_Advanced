# Emails and SMS (HIMS-NOTIF-001)

Every email and SMS HIMS sends goes through one **notification service** (spec 4.23):

- It is **logged**: menu → **Messages** (and the admin console → Notifications) shows what was
  sent, to whom, when, and whether it arrived.
- A failure (for example the email provider being down) **never breaks** the action that caused
  it. The message is retried after 5, 15, 60 and 240 minutes, then marked "Failed". An
  administrator can press **Send again now**.
- The stored copy **hides sign-in links and secrets** (`#token=[hidden]`). The real text is kept
  encrypted only until the message is delivered, then erased.
- **Send a test message** on the Messages page checks that email or SMS works.

Who: `notifications.view` (see the log) and `notifications.manage` (send again, test). Both
require two-factor sign-in; hospital administrators have both.

## Today on your PC

Emails and SMS are **printed in the launcher window** (lines start with `🇮🇳 [backend]`). Nothing
leaves your computer.

## Using your Gmail account for real emails

1. In your Google account: **Security → 2-Step Verification** (must be on) → **App passwords** →
   create one called "HIMS". Google shows a 16-letter password. Keep it private.
2. Open `backend\.env` in Notepad and add:
   ```
   DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=true
   EMAIL_HOST_USER=your.address@gmail.com
   EMAIL_HOST_PASSWORD=the-16-letter-app-password
   DJANGO_DEFAULT_FROM_EMAIL=Your Hospital HIMS <your.address@gmail.com>
   ```
   (`backend\.env` is never committed to git. Never put this password anywhere else.)
3. Restart HIMS. Messages → **Send a test message** → your own email address.
4. To go back to the launcher window: remove those lines and restart.

Gmail is fine for testing; for a real hospital use a sending service (Amazon SES on AWS) with the
hospital's own domain, so emails are not marked as spam and limits are higher.

## SMS

Printed in the launcher window (`HIMS_SMS_BACKEND=apps.notifications.backends.ConsoleSmsBackend`).
A real provider is added as a small class with a `send(to, body)` method:

- **India:** a DLT-registered SMS gateway (TRAI rules: registered sender ID and message templates).
- **US:** a provider such as Twilio or Amazon SNS; patients must have agreed to receive texts.

Phone numbers must be in international format (`+919876543210`, `+15555550100`); others are
recorded as "Not sent".

## For developers

```python
from apps.notifications.services import send_email, send_sms

send_email(to=[person.email], subject="…", body="…", category="account",
           template="identity.invitation", related=("user", person.pk))
```

Never put clinical details in an email or SMS (spec 13.3): appointment reminders say only date,
time, doctor and hospital. `retry_notifications` retries due messages by hand (the same job runs
every 5 minutes under Celery beat).
