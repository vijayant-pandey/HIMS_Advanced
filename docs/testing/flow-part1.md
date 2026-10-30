# HIMS manual test guide: Flow Part 1 (everything built in Phase 1)

**Who this is for:** the product owner, testing HIMS by hand in a web browser. No coding knowledge is needed.
**What it covers:** every screen and every admin console page built so far (Phase 1, up to PR #20: "My sign-ins" and access reviews).
**How long it takes:** about 3 to 4 hours for India. The US check (Part 21) takes about 45 minutes more. You can stop after any part and continue later.

> **Important: use made-up data only.** Use invented people, invented emails (ending in
> `@test.local`) and sample PDF files. Never use real patient or real staff documents on this
> computer.

---

## Contents

0. [How to use this guide](#0-how-to-use-this-guide)
1. [What has been built (and what has not)](#1-what-has-been-built-and-what-has-not)
2. [What you need before starting](#2-what-you-need-before-starting)
3. [Start HIMS](#3-start-hims)
4. [Set up your browsers (how many and why)](#4-set-up-your-browsers-how-many-and-why)
5. [Part 1: first sign-in as administrator and two-factor](#part-1-first-sign-in-as-administrator-and-two-factor)
6. [Part 2: hospital settings](#part-2-hospital-settings)
7. [Part 3: facilities (branches)](#part-3-facilities-branches)
8. [Part 4: departments](#part-4-departments)
9. [Part 5: locations and beds](#part-5-locations-and-beds)
10. [Part 6: numbering](#part-6-numbering)
11. [Part 7: job titles and catalogs](#part-7-job-titles-and-catalogs)
12. [Part 8: staff, postings, qualifications, licences, documents](#part-8-staff-postings-qualifications-licences-documents)
13. [Part 9: invite a staff member and let them sign in (second browser)](#part-9-invite-a-staff-member-and-let-them-sign-in-second-browser)
14. [Part 10: department page (head, opening hours, services)](#part-10-department-page-head-opening-hours-services)
15. [Part 11: roles and access](#part-11-roles-and-access)
16. [Part 12: accounts (including people who are not staff)](#part-12-accounts-including-people-who-are-not-staff)
17. [Part 13: licence expiry and alert emails](#part-13-licence-expiry-and-alert-emails)
18. [Part 14: features (turning parts of HIMS on and off)](#part-14-features-turning-parts-of-hims-on-and-off)
19. [Part 15: security page, "My sign-ins" and forgot password](#part-15-security-page-my-sign-ins-and-forgot-password)
20. [Part 16: access reviews](#part-16-access-reviews)
21. [Part 17: audit log (as the auditor)](#part-17-audit-log-as-the-auditor)
22. [Part 18: the admin console (Django admin) tour](#part-18-the-admin-console-django-admin-tour)
23. [Part 19: leaving staff (termination)](#part-19-leaving-staff-termination)
24. [Part 20: safety checks (things that must be refused)](#part-20-safety-checks-things-that-must-be-refused)
25. [Part 21: repeat the key steps for the US hospital](#part-21-repeat-the-key-steps-for-the-us-hospital)
26. [Stop HIMS](#stop-hims)
27. [Troubleshooting](#troubleshooting)
28. [How to report a problem](#how-to-report-a-problem)
29. [Results sheet](#results-sheet)

---

## 0. How to use this guide

- Do the parts **in order**. Later parts use what you created earlier. For example, a department
  head must be a staff member posted in that department.
- Each step says **Do** (what to click or type) and **Expect** (what you should see).
- If what you see matches **Expect**, tick the box: change `[ ]` to `[x]`, or tick it on a
  printout. If it does not match, write it down (see [How to report a problem](#how-to-report-a-problem)).
- Words in **bold** are exact button or menu names on the screen.
- **Write down** every name and code you create on paper. Later steps ask for them.

### Words used in this guide

| Word | Meaning |
|---|---|
| **App** | The HIMS website staff use, e.g. http://localhost:5175 (India). |
| **Admin console** | The Django admin "back office", e.g. http://localhost:8000/admin/. It can control everything. Every change there is recorded. |
| **Launcher window** | The black CMD window where you typed `npm run dev`. HIMS "emails" are printed there (see below). |
| **Facility** | A branch or building of the hospital (e.g. "Main Hospital", "City Clinic"). |
| **Two-factor** | After your password, HIMS asks for a 6-digit code from an app on your phone. |
| **Audit log** | The permanent history of who did what, when. Nobody can change or delete it. |

### About emails on this computer

HIMS does **not** really send emails on your computer. Every email (invitations, password reset
links, licence alerts, review reminders) is **printed in the launcher window** instead. When a step
says "open the link from the email", look in the launcher window for lines that start with
`🇮🇳 [backend]` and find the link that starts with `http://localhost:5175/...#token=`. To use it:

1. Select the whole link with the mouse (it can be long; make sure you get all of it, up to
   the end of the token).
2. Press `Ctrl+C` to copy it. (In CMD you can also select and press `Enter`.)
3. Paste it into the address bar of the **right browser window** (the guide tells you which one),
   then press `Enter`.

---

## 1. What has been built (and what has not)

**Built in Phase 1 (you test all of this):**

| Area | What you can do |
|---|---|
| Sign-in and security | Sign in, two-factor codes, backup codes, forgot password, account activation by invitation, "My sign-ins", automatic sign-out after 30 minutes without activity |
| Hospital setup | Hospital settings, facilities (branches), departments with head, services and opening hours |
| Locations and beds | Buildings, floors, wards, rooms, beds, bed status (maintenance, blocked, out of service) |
| Numbering | How patient record (MRN), visit, invoice and claim numbers will look |
| Features | Turn parts of HIMS on or off for the hospital or one facility |
| Staff | Staff list, postings to departments, qualifications, licences, documents, verification, licence expiry alerts, job titles catalog |
| Access | Roles, giving and removing access, custom roles, accounts (including people who are not staff), access reviews, cover arrangements (lend someone's access to a colleague for a limited time) |
| Audit | Audit log for auditors: search, details, CSV download; **Audit integrity**: proof that no audit record was changed or removed (tamper check) |
| Admin console | Every item above can also be managed in the Django admin console, and every change is audited |

**Not built yet (do not look for it):** patients, appointments, doctors' notes, pharmacy, lab,
billing, insurance. They come in Phases 2 to 6. Some of them already appear on the **Features**
page as "Coming in Phase X". That is expected.

---

## 2. What you need before starting

- [ ] **The latest code is merged and migrated.** PR #20 (My sign-ins + access reviews) is merged
      into `development`, you ran `git pull origin development`, and you ran the migrate steps for
      **India and US**. If PR #20 is not merged yet, skip Part 15 step 15.2 and Part 16.
- [ ] **Your passwords:** open `login.md` (in the HIMS folder; it is only on your computer). It
      has the admin and auditor emails and passwords for India and US.
- [ ] **Your phone** with an authenticator app installed: **Google Authenticator**, **Microsoft
      Authenticator** or **Authy** (free, from the Play Store or App Store). You will add **3
      accounts** to it during the test (India admin, India auditor, one test staff member).
- [ ] **Two browsers on the computer:** Google Chrome and Microsoft Edge (Edge comes with Windows).
- [ ] **Two small sample files** to upload as "certificates": any PDF, JPG or PNG under 10 MB
      (for example a screenshot saved as PNG). Save them on the Desktop as `sample-certificate.pdf`
      or `.png` and `sample-licence.pdf` or `.png`.
- [ ] **Paper and pen**, or a notes file, to write down names, codes and reference numbers.

---

## 3. Start HIMS

1. Press the **Windows** key, type `cmd`, press `Enter`. A black window opens. This is the
   **launcher window**. Keep it open the whole time.
2. Type these two lines (press `Enter` after each):
   ```cmd
   cd C:\Users\vpand\OneDrive\Desktop\HIMS\frontend
   npm run dev
   ```
3. **Expect:** your browser opens **http://localhost:5173** showing hospital cards:
   🇮🇳 **IN Hospitals**, 🇺🇸 **US Hospitals**, and 🇪🇺 European Hospitals ("Coming later").
4. Click **IN Hospitals**. Wait about 10 to 20 seconds.
5. **Expect:** the India app opens at **http://localhost:5175** with the **Sign in to HIMS** page.

| | 🇮🇳 India | 🇺🇸 US |
|---|---|---|
| App | http://localhost:5175 | http://localhost:5174 |
| Admin console | http://localhost:8000/admin/ | http://localhost:8001/admin/ |
| API documentation (optional) | http://localhost:8000/api/docs/ | http://localhost:8001/api/docs/ |

> The admin console only works while that hospital is started from the launcher.

---

## 4. Set up your browsers (how many and why)

A browser window remembers **one signed-in person per hospital**. To test two or three people at
the same time (for example the administrator **and** a new nurse), each person needs a separate
window that shares nothing with the others:

| Window | How to open it | Who signs in there | Used in |
|---|---|---|---|
| **Window A**: Chrome, normal | Open Chrome as usual | **You, as India administrator** | Almost every part |
| **Window B**: Chrome **Incognito** | In Chrome press `Ctrl+Shift+N` | **The test staff member** (a new person you create) | Parts 9, 10, 11, 15, 16, 19 |
| **Window C**: Microsoft **Edge** | Start menu → Edge | **The auditor**, and later "your second device" | Parts 15, 16, 17 |

Tips:
- Put the windows side by side: drag one to the left edge of the screen and one to the right.
- **Closing all Incognito windows signs that person out.** That's fine; just sign in again.
- India and US can be open in the same window at the same time (different addresses).
- If you are inactive for **30 minutes**, HIMS signs you out automatically. This is a security
  rule, not a bug. Just sign in again.

---

## Part 1: first sign-in as administrator and two-factor

**Window A** (Chrome).

### 1.1 Sign in
- [ ] **Do:** go to http://localhost:5175. Type the India **admin email** and **password** from
      `login.md`. Click **Sign in**.
- [ ] **Expect (two-factor not set up yet):** you are taken to the **Security** page with the
      warning "Your role can change important hospital settings, so two-factor sign-in is required
      before you can continue." Go to 1.2.
- [ ] **Expect (two-factor already set up earlier):** a **Two-factor sign-in** box asks for the
      code. Open your authenticator app, type the 6-digit code for HIMS India admin, click
      **Verify and sign in**. Go to 1.4.

### 1.2 Set up two-factor (only the first time)
- [ ] **Do:** click **Set up two-factor sign-in**.
- [ ] **Expect:** a QR code and a text key appear.
- [ ] **Do:** on your phone, open the authenticator app → **+** / **Add account** → **Scan a QR
      code** → point the phone at the screen.
- [ ] **Expect:** the app shows a new entry with a 6-digit code that changes every 30 seconds.
      Rename it on the phone to **"HIMS India admin"** if you can.
- [ ] **Do:** type the current 6-digit code into **6-digit code** and click **Turn on**.
- [ ] **Expect:** "Save these backup codes now. They are shown only once."
- [ ] **Do:** click **Download .txt**. Save the file somewhere private, then click **I've saved them**.
- [ ] **Expect:** you are taken into HIMS. A menu bar at the top shows the pages you can use.

### 1.3 Wrong code is refused
- [ ] **Do:** click **Sign out** (top right). Sign in again with email and password. When asked
      for the code, type `000000` and click **Verify and sign in**.
- [ ] **Expect:** an error saying the code is wrong. You are **not** signed in.
- [ ] **Do:** type the real code from the app → **Verify and sign in**.
- [ ] **Expect:** you are signed in.

### 1.4 Look around the menu
- [ ] **Expect:** the top menu shows: **Hospital settings, Facilities, Departments, Locations,
      Numbering, Features, Staff, Licence expiry, Job titles & catalogs, Access, Accounts, Access
      reviews**, plus your name/Security and **Sign out**. (**Audit log** is **not** shown to the
      administrator. That is correct: only the auditor sees it.)
- [ ] **Do:** find the **Theme** picker and change the theme.
- [ ] **Expect:** the colours change. Change it back if you like.

### 1.5 Sign in to the admin console
- [ ] **Do:** open a **new tab** in Window A and go to http://localhost:8000/admin/.
- [ ] **Expect:** "HIMS operations console" sign-in page with **Email**, **Password** and
      **Authenticator code**.
- [ ] **Do:** type the admin email, password and the current 6-digit code. Click **Log in**.
- [ ] **Expect:** "Administration (every change is audited)" with sections such as
      **Access_Control, Beds, Facilities, Features, Identity, Numbering, Organizations, Staff**.
      There is **no Audit** section for the administrator.
- [ ] **Do:** try once more in a fresh window with the right password but **no** code (optional).
- [ ] **Expect:** "Enter the code from your authenticator app."

Keep this tab open. You'll use it to compare the app with the admin console.

---

## Part 2: hospital settings

**Window A**, app tab.

- [ ] **Do:** click **Hospital settings**.
- [ ] **Expect:** the hospital name, legal name, default time zone, country (India), currency
      (INR) and status. A note says country and currency cannot be changed here.
- [ ] **Do:** click **Edit**. Change **Name shown in HIMS** to `My Hospital TEST`. Click **Save**.
- [ ] **Expect:** the new name is shown on the page and in the top bar.
- [ ] **Check in the admin console:** admin tab → **Organizations** → **Organizations** → click
      the hospital.
- [ ] **Expect:** the display name is `My Hospital TEST`.
- [ ] **Do:** in the app, change the name back to the original and **Save**.

---

## Part 3: facilities (branches)

**Window A**, app.

### 3.1 Create a facility
- [ ] **Do:** click **Facilities** → **New facility**. Fill in:
      Code `TST1`, Name `Test Branch One`, Type **Hospital**, Country **India**, State / region
      `Maharashtra`, City `Pune`, Address line 1 `1 Test Road`, Postal code `411001`, Time zone
      (IANA) `Asia/Kolkata` (Phone and Address line 2 are optional). Click **Create**.
- [ ] **Expect:** `Test Branch One` appears in the list with status Active and 0 departments.

### 3.2 Duplicate code is refused
- [ ] **Do:** **New facility** again with Code `TST1`, Name `Copy` (fill the other required
      fields as before). **Create**.
- [ ] **Expect:** an error next to Code saying it is already used. Click **Cancel**.

### 3.3 Edit
- [ ] **Do:** click **Edit** on `Test Branch One`. Change the name to `Test Branch One (Pune)`. **Save**.
- [ ] **Expect:** the new name in the list. The code cannot be changed.

### 3.4 Admin console
- [ ] **Do:** admin tab → **Facilities** → **Facilitys** (spelled that way).
- [ ] **Expect:** `TST1 Test Branch One (Pune)` is listed. There is **no Delete** button
      anywhere (records are switched to Inactive, never deleted).

---

## Part 4: departments

**Window A**, app.

### 4.1 Add departments
- [ ] **Do:** **Departments** → **Add department**. Facility **Test Branch One (Pune)**, Name
      `Cardiology`, Code `CARD`, Type **Clinical**. Click **Add**.
- [ ] **Do:** add a second one: Name `Radiology`, Code `RAD`, Type **Diagnostic**.
- [ ] **Expect:** both are in the list with Head "—", Staff 0, Wards 0.

### 4.2 Filter
- [ ] **Do:** use the **Facility** filter to choose `Test Branch One (Pune)`, then the
      **Status** filter.
- [ ] **Expect:** the list changes to match.

### 4.3 Edit and switch off
- [ ] **Do:** **Edit** `Radiology` → Status **Inactive** → **Save**.
- [ ] **Expect:** Radiology shows as Inactive. (A department with active staff postings or
      active wards cannot be switched off; you will see that rule in Part 20.)
- [ ] **Do:** switch Radiology back to **Active**.

The department **page** (head, hours, services) is tested in Part 10, after you have staff.

---

## Part 5: locations and beds

**Window A**, app.

### 5.1 Build the location tree
- [ ] **Do:** **Locations** → choose **Facility** `Test Branch One (Pune)` → **Add building**:
      Code `MB`, Name `Main Block` → **Save**.
- [ ] **Do:** under Main Block → **Add floor**: Level `0`, Name `Ground floor` → **Save**.
- [ ] **Do:** under Ground floor → **Add ward**: Code `W1`, Name `Cardiac Ward`, Type
      **General ward**, Department **Cardiology** → **Save**.
- [ ] **Do:** under Cardiac Ward → **Add room**: Code `101`, Name `Room 101`, Type **General
      room** → **Save**.
- [ ] **Do:** under Room 101 → **Add beds**: Prefix `b`, Start at `1`, How many `4`, Bed type
      **General** → **Add beds**.
- [ ] **Expect:** 4 beds (B1 to B4), all **Available**. The summary "Beds in this facility"
      counts them.

### 5.2 Limits
- [ ] **Do:** **Add beds** again with Start at `1` and How many `2`.
- [ ] **Expect:** refused, because those bed codes already exist. **Cancel**.
- [ ] **Do:** try How many `61`.
- [ ] **Expect:** not allowed (maximum 60 at a time).

### 5.3 Bed status
- [ ] **Do:** click bed **B2** → Status **Maintenance**, leave Reason empty → **Save**.
- [ ] **Expect:** refused: "Say why the bed is unavailable".
- [ ] **Do:** Reason `Broken side rail` → **Save**.
- [ ] **Expect:** B2 shows Maintenance with the reason.
- [ ] **Do:** open B2 again and look at the status list.
- [ ] **Expect:** you can only choose Available, Maintenance, Blocked or Out of service.
      Reserved, Occupied and Cleaning are **not** offered: they will be set by admissions and
      housekeeping in later phases.
- [ ] **Do:** set B2 back to **Available**.

### 5.4 Edit and hide inactive
- [ ] **Do:** **Edit** Room 101 → untick **Active** → **Save**.
- [ ] **Expect:** a warning about deactivating. The room shows as inactive. **Hide inactive** hides it.
- [ ] **Do:** make Room 101 **Active** again.

### 5.5 Admin console
- [ ] **Do:** admin tab → **Facilities** → **Buildings**, **Floors**, **Wards**, **Rooms**, and
      **Beds** → **Beds**.
- [ ] **Expect:** everything you made is listed.

---

## Part 6: numbering

**Window A**, app.

- [ ] **Do:** **Numbering**.
- [ ] **Expect:** schemes for **Patient record number (MRN)**, **Encounter / visit number**,
      **Invoice number** and **Insurance claim number**, each with "The first number will look
      like" or next number. **Issued numbers** says "None yet" (patients come in Phase 2).
- [ ] **Do:** **Edit** the Invoice scheme. Change **Prefix** (e.g. `INV`) and **Digits in the
      running number** (e.g. `6`).
- [ ] **Expect:** the preview "The first number will look like" changes **while you type**.
      Click **Save**.
- [ ] **Do:** try **Digits** `2`.
- [ ] **Expect:** refused ("Use between 3 and 12 digits").
- [ ] **Do:** **Continue from…** on the MRN scheme → type a number such as `5000` (as if you are
      moving from an old system) → **Save**.
- [ ] **Expect:** the next number is 5000. Then try a **smaller** number than the current one.
- [ ] **Expect:** refused (numbers are never reused).
- [ ] **Do (optional):** add a **Facility series** for Encounter numbers for `Test Branch One
      (Pune)` with **Include the facility code** ticked.
- [ ] **Expect:** the preview shows the facility code, e.g. `ENC-TST1-2026-0000001`.
- [ ] **Admin console:** **Numbering** → **Numbering schemes** lists the same schemes.

---

## Part 7: job titles and catalogs

**Window A**, app.

- [ ] **Do:** **Job titles & catalogs**.
- [ ] **Expect:** tabs **Job titles**, **Specialties**, **Qualification types**. Entries are
      marked **Standard** (come with HIMS).
- [ ] **Do:** on **Job titles** → **Add job title**: Name `Cath Lab Technician`, Category
      **Allied health & technicians**, Country **India**, Seniority `4` → **Save**.
- [ ] **Expect:** it appears marked **Added by hospital**. Tick **Only added by this hospital**:
      only your entry shows.
- [ ] **Do:** add the same name again.
- [ ] **Expect:** refused (name already used).
- [ ] **Do:** **Edit** it → rename to `Cath Lab Technologist` → **Save**.
- [ ] **Expect:** the name changes. The code below the name stays the same.
- [ ] **Do:** **Specialties** tab → **Add specialty** `Interventional Cardiology`.
- [ ] **Do:** use **Search** to find `cardio`.
- [ ] **Expect:** the matching rows only.
- [ ] **Do:** switch off the **In use** switch for `Cath Lab Technologist`, then switch it on again.
- [ ] **Expect:** the row fades while off and returns when on. (When off, it disappears from
      drop-downs when adding new postings, but stays on old records.)
- [ ] **Admin console:** **Staff** → **Designations** shows your job title, with "Is custom" ticked.

---

## Part 8: staff, postings, qualifications, licences, documents

**Window A**, app. You will create **two** test staff members:

| Person | Use |
|---|---|
| **Asha Nurse** (with an email) | Will sign in in Window B |
| **Ravi Doctor** (no email) | Cardiology head, documents, licence expiry |

### 8.1 Add staff
- [ ] **Do:** **Staff** → **Add staff member**: First name `Ravi`, Last name `Doctor`, Employee
      number `T-1001`, Staff type **Doctor**, Joined on (any recent date), Work email **empty** → **Add**.
- [ ] **Expect:** Ravi's page opens. The **Access** area says "No sign-in account (no email recorded)."
- [ ] **Do:** back to **Staff** → **Add staff member**: `Asha`, `Nurse`, `T-1002`, **Nurse**,
      joined date, Work email `asha.nurse@test.local` → **Add**.
- [ ] **Expect:** Asha's page says "Not activated yet. Send an invitation to asha.nurse@test.local."
- [ ] **Do:** add someone with the same employee number `T-1001`.
- [ ] **Expect:** refused.

### 8.2 Staff list
- [ ] **Do:** **Staff** → search `Ravi`, then try the **Status** filter.
- [ ] **Expect:** filtering works. **View** opens the person.

### 8.3 Department posting (Ravi)
- [ ] **Do:** Ravi's page → **Departments** tab → **Add posting**: Department **Cardiology**
      (Test Branch One), Designation e.g. **Consultant**, Specialty **Interventional
      Cardiology**, Starts on today, tick **Main department** → **Save**.
- [ ] **Expect:** the posting is listed.
- [ ] **Do:** also give **Asha** a posting: Department **Cardiology**, Designation a nursing
      title (e.g. **Staff Nurse**), starts today.

### 8.4 Qualification and document (Ravi)
- [ ] **Do:** Ravi → **Qualifications** tab → **Add qualification**: Qualification **MBBS**
      (or similar), Institution `Test Medical College`, Year `2010` → **Save**.
- [ ] **Expect:** listed as **not verified**.
- [ ] **Do:** in that row → **Upload** → choose `sample-certificate` from the Desktop → **Upload**.
- [ ] **Expect:** the document is listed. Clicking it opens or downloads the file.
- [ ] **Do:** try uploading a file over 10 MB, or a `.docx` file (optional).
- [ ] **Expect:** refused.
- [ ] **Do:** **Verify** → Result **Verified against the original document**, Note `Checked
      original on <date>` → **Save**.
- [ ] **Expect:** status **Verified** with your name and the date.

### 8.5 Licence that expires soon (Ravi)
- [ ] **Do:** Ravi → **Licences** tab → **Add licence**: Type **Medical council
      registration**, Registration number `MCI-TEST-123`, Issued by `Test Medical Council`,
      Valid from (last year), **Expires on = 20 days from today** → **Save**.
- [ ] **Expect:** the licence is listed with its expiry date. A banner on Ravi's page warns it
      expires soon.
- [ ] **Do:** **Upload** `sample-licence` for this licence.
- [ ] **Do:** upload a **second** file for the same licence, then **Archive** the first one with
      Reason `Wrong file`.
- [ ] **Expect:** the archived file is no longer shown as current, but it is **not deleted**.

### 8.6 Edit staff
- [ ] **Do:** Ravi → **Edit** → change Employment status to **On leave** → **Save**, then back
      to **Active**.
- [ ] **Expect:** the status changes each time.

### 8.7 Admin console
- [ ] **Do:** admin tab → **Staff** → **Staff members** → Ravi.
- [ ] **Expect:** his qualifications, licences and postings are shown. **Staff documents** lists
      the uploaded files (the archived one marked archived).

---

## Part 9: invite a staff member and let them sign in (second browser)

Now you need **Window A** (you, admin) and **Window B** (Chrome Incognito, `Ctrl+Shift+N`) for Asha.

### 9.1 Send the invitation
- [ ] **Window A:** Asha's page → **Send invitation**.
- [ ] **Expect:** "Invitation sent to asha.nurse@test.local; the link works until …" (72 hours).
- [ ] **Launcher window:** find the email that was just printed (lines start with `🇮🇳 [backend]`)
      and the link `http://localhost:5175/activate#token=...`. Copy the **whole** link.

### 9.2 Activate (Window B)
- [ ] **Window B:** paste the link → `Enter`.
- [ ] **Expect:** "Activate your account" with "Welcome, Asha…".
- [ ] **Do:** type a short password such as `abc123`.
- [ ] **Expect:** refused (at least 12 characters).
- [ ] **Do:** type a strong made-up password (12+ characters, e.g. `Test-Nurse-Pass-2026!`) twice
      → **Activate and sign in**. Write it down.
- [ ] **Expect:** Asha is signed in, but sees **"Your account is active, but you don't have
      access to any area of HIMS yet."** with a **Reference** number. Write the reference down.
      (She has no role yet. That is correct: everyone starts with no access.)
- [ ] **Do:** paste the same invitation link again in Window B.
- [ ] **Expect:** the link no longer works (it can be used only once).

### 9.3 Give Asha access (Window A)
- [ ] **Window A:** Asha's page → **Access** tab (or the Access section) → **Give access**:
      Role **Basic staff access**, **One facility** → `Test Branch One (Pune)`, Reason `Joined
      Cardiology ward` → **Give access**.
- [ ] **Expect:** the role is listed with "Given by" you.
- [ ] **Window B:** click **I've been given access, check again**.
- [ ] **Expect:** Asha now sees only a few menu items (Facilities, Departments, Locations).
      She can **look** but has **no** Add or Edit buttons.

### 9.4 Make Asha an HR officer (two-factor becomes required)
- [ ] **Window A:** Asha → **Give access**: Role **HR / credentialing officer**, **Whole
      hospital**, Reason `Testing HR role` → **Give access**.
- [ ] **Window B:** refresh the page (`F5`).
- [ ] **Expect:** Asha is sent to the **Security** page: two-factor is now **required** for her role.
- [ ] **Do (Window B):** **Set up two-factor sign-in** → scan with your phone (name it **"HIMS
      Asha test"**) → type the code → **Turn on** → **Download .txt** (or note them) → **I've saved them**.
- [ ] **Expect:** Asha now sees **Staff**, **Licence expiry**, **Job titles & catalogs** and can
      add staff, but **not** Access, Accounts or Hospital settings.
- [ ] **Window A:** Asha → **Qualifications** → **Add qualification** (e.g. **GNM** / any nursing
      qualification, Institution `Test Nursing School`, Year `2018`).
- [ ] **Window B:** refresh → **Staff** → open **Asha Nurse** (herself) → **Qualifications**.
- [ ] **Expect:** there is **no Verify** button on her own qualification (nobody verifies their
      own papers). On **Ravi's** page she would see **Verify** for unverified items.

---

## Part 10: department page (head, opening hours, services)

**Window A**, app.

### 10.1 Department head
- [ ] **Do:** **Departments** → click the name **Cardiology**.
- [ ] **Expect:** the department page with **Head of department**, **Opening hours** and
      **Services offered**.
- [ ] **Do:** Head → **Change**.
- [ ] **Expect:** the choice lists only **staff currently posted in Cardiology** (Ravi Doctor,
      Asha Nurse). Nobody else.
- [ ] **Do:** choose **Ravi Doctor** → **Save**.
- [ ] **Expect:** Head shows Ravi. On the **Departments** list, the **Head** column shows Ravi.

### 10.2 Opening hours
- [ ] **Do:** **Edit hours**. For **Monday** add a session `09:00`–`13:00` and another
      `14:00`–`18:00`. Click **Copy Monday to Tuesday–Friday**. Leave Saturday and Sunday empty → **Save**.
- [ ] **Expect:** Monday to Friday show two sessions. Saturday and Sunday show closed.
- [ ] **Do:** **Edit hours** → on Monday add `12:00`–`15:00` (overlaps) → **Save**.
- [ ] **Expect:** refused (sessions overlap). Remove that session and **Cancel**.
- [ ] **Do:** **Edit hours** → turn on **Open 24 hours, every day** → **Save**.
- [ ] **Expect:** "Open 24 hours, every day". Turn it off again if you like.

### 10.3 Services
- [ ] **Do:** **Add service**: `ECG`, Description `Resting 12-lead ECG` → **Save**. Add `Echo`.
- [ ] **Do:** add `ecg` again (lower case).
- [ ] **Expect:** refused (same name).
- [ ] **Do:** **Edit** `Echo` → switch it off → **Save**.
- [ ] **Expect:** Echo shows as inactive (never deleted). The note says prices come with billing.

### 10.4 Admin console
- [ ] **Do:** admin tab → **Facilities** → **Departments** → Cardiology.
- [ ] **Expect:** Head, Open 24 hours, and sections for **services** and **hours** at the bottom.
      The facility and code cannot be changed here.

---

## Part 11: roles and access

**Window A**, app.

### 11.1 Roles
- [ ] **Do:** **Access**.
- [ ] **Expect:** a list of roles. **System** roles (Organization administrator, Auditor,
      Facility administrator, HR / credentialing officer, Head of department, Basic staff
      access, Bed manager) show their permissions. System roles cannot be edited.
- [ ] **Do:** click a role to see **Who has access** (person, where, given by, until).

### 11.2 Custom role
- [ ] **Do:** **New custom role**: Name `Ward Viewer`, Code `ward-viewer`, Description `Can see
      wards and beds`. Tick only the permissions to view facilities, departments and locations → **Save**.
- [ ] **Expect:** `Ward Viewer` is listed as **Custom**.
- [ ] **Do:** **Edit** it → add **Put beds into or out of maintenance…** → **Save**.
- [ ] **Expect:** saved, and the change is recorded.

### 11.3 Give and remove access with an end date
- [ ] **Do:** open **Staff** → **Asha Nurse** → **Give access**: Role **Ward Viewer**, **One
      department** → Test Branch One → **Cardiology**, **Ends on** = a date next week, Reason
      `Temporary cover` → **Give access**.
- [ ] **Expect:** listed with an "Until" date.
- [ ] **Do:** **Remove** that access → Reason `Cover finished` → **Remove access**.
- [ ] **Expect:** it disappears from current access. Tick **Show removed and expired** to see it
      again, marked removed.

### 11.4 You cannot change your own access
- [ ] **Do:** **Accounts** → open **your own** admin account.
- [ ] **Expect:** "You cannot change your own access; ask another administrator." No Give or
      Remove buttons.

---

## Part 12: accounts (including people who are not staff)

**Window A**, app.

### 12.1 Accounts list
- [ ] **Do:** **Accounts**.
- [ ] **Expect:** everyone who can sign in: you (admin), the auditor, Asha. Columns show Type,
      Access, **Two-factor** on/off, and Last sign-in. Use the tabs **Everyone / Not staff /
      Staff / Switched off** and **Search by name or email**.

### 12.2 Add an account for someone who is not staff
- [ ] **Do:** **Add account**: Full name `External Auditor Test`, Email
      `ext.auditor@test.local`, Reason `Yearly external audit` → **Add and send invitation**.
- [ ] **Expect:** a new account (type "Not staff"). "The account has no access until you give it
      a role on its page." An invitation email is printed in the launcher window. (You don't need
      to use it.)

### 12.3 Switch an account off and on (with Window B)
- [ ] **Window B:** make sure Asha is signed in and on any page.
- [ ] **Window A:** **Accounts** → open **Asha Nurse** → **Switch account off** → Reason
      `Testing switch off` → confirm.
- [ ] **Window B:** refresh (`F5`).
- [ ] **Expect:** Asha is signed out immediately. Signing in again fails.
- [ ] **Window A:** **Switch account back on** → Reason `Test finished`.
- [ ] **Window B:** sign in as Asha (password + her code from the phone).
- [ ] **Expect:** works again.

### 12.4 Sign someone out of all devices
- [ ] **Window A:** Asha's account → **Sign out of all devices** → confirm.
- [ ] **Window B:** refresh.
- [ ] **Expect:** Asha is signed out. Sign her in again.

### 12.5 Reset two-factor (lost phone)
- [ ] **Window A:** Asha's account → **Reset two-factor (lost phone)** → Reason `Lost phone test`.
- [ ] **Window B:** refresh, sign in as Asha with only the password.
- [ ] **Expect:** Asha must set up two-factor again (scan a **new** QR code). Do it. On the phone,
      delete the old "HIMS Asha test" entry and keep the new one.

### 12.6 Cover arrangements: lend Asha's access while she is away (needs PR #23)
Asha is the HR officer (Part 9.4). Pretend she goes on leave and **External Auditor Test**
(12.2) covers for her. ("External auditor" is only the test name; any account works.)

- [ ] **Window A:** menu → **Cover**.
- [ ] **Expect:** "No cover arranged at the moment."
- [ ] **Do:** **Arrange cover**. **Person being covered** = type `Asha` → pick **Asha Nurse**.
      **Person covering** = type `Exte` → pick **External Auditor Test**.
- [ ] **Expect:** under **Access to lend**, Asha's roles appear, all ticked (e.g. **HR /
      credentialing officer**).
- [ ] **Do:** **Ends on** = a date 7 days from today. **Reason** = `Annual leave test` →
      **Arrange cover**.
- [ ] **Expect:** green message "External Auditor Test covers for Asha Nurse until …". The table
      shows the row with **Active now** and the lent role.
- [ ] **Launcher window (India):** two emails: "HIMS: you are covering for Asha Nurse" and
      "HIMS: External Auditor Test is covering for you".
- [ ] **Do:** **Accounts** → open **External Auditor Test**.
- [ ] **Expect:** the access list shows **HR / credentialing officer** with a **Cover for Asha
      Nurse** label and an end date 7 days away.
- [ ] **Window B (Asha):** **Security** page (top right menu).
- [ ] **Expect:** a **Cover arrangements** box: "External Auditor Test covers for you", with the
      dates and the role.
- [ ] **Do (Window A):** **Arrange cover** again with the same two people and dates.
- [ ] **Expect:** refused: "… already covers for … in this period."
- [ ] **Do:** **Arrange cover** → open the **Ends on** calendar.
- [ ] **Expect:** days more than 30 days ahead cannot be picked ("At most 30 days"). The server
      refuses longer cover too. Press **Cancel**.
- [ ] **Do:** in the table → **End now** → reason `Back early` → **End cover now**.
- [ ] **Expect:** the row moves to the **Past** tab with **Ended early** and your reason; the
      role is crossed out ("removed: Cover ended early …"). Two more emails ("cover arrangement
      ended"). On External Auditor Test's account, switch on **Show removed and expired**: the role
      shows **Removed**.
- [ ] **Do (optional):** arrange cover again, then switch **External Auditor Test**'s account off
      (Accounts) and back on.
- [ ] **Expect:** the cover is **Ended early**, reason "…'s account was switched off."
- [ ] **Admin console (Window A, admin tab):** **Access control → Access delegations**.
- [ ] **Expect:** both arrangements, with who, when, status and the access lent. **Add access
      delegation** works like the Cover page (lends everything that can be lent). The action
      **End selected cover now** ends one. Nothing can be deleted.

---

## Part 13: licence expiry and alert emails

**Window A**, app.

- [ ] **Do:** **Licence expiry**.
- [ ] **Expect:** Ravi's licence `MCI-TEST-123` is listed (expires in about 20 days), with
      verification status and "Last alert".
- [ ] **Do:** change **Expiring within** to a small number (e.g. 7 days).
- [ ] **Expect:** Ravi's licence disappears (20 days is more than 7). Set it back to 60.
- [ ] **Do:** tick **Include expired**.

**Send the alert emails by hand.** On a real server this runs every day automatically.

1. Open a **new** CMD window (Windows key → `cmd`).
2. Type, one line at a time:
   ```cmd
   cd C:\Users\vpand\OneDrive\Desktop\HIMS\backend
   .venv\Scripts\activate.bat
   set HIMS_ENV_FILE=
   python manage.py send_credential_expiry_alerts
   ```
- [ ] **Expect:** "Sent alerts for 1 licence(s)." The emails are printed **in this CMD window**
      (an email to HR people listing Ravi's licence). Ravi gets no personal email, because he has
      no email address.
- [ ] **Do:** run the same command again.
- [ ] **Expect:** "Sent alerts for 0 licence(s)." The same alert is never sent twice.
- [ ] **App:** refresh **Licence expiry**.
- [ ] **Expect:** "Last alert" now shows the 30-day stage.
- [ ] **Admin console:** **Staff** → **Credential expiry alerts** shows the alert.

Keep this CMD window open for Part 16.

---

## Part 14: features (turning parts of HIMS on and off)

**Window A**, app.

- [ ] **Do:** **Features**.
- [ ] **Expect:** grouped features. Live ones: **Forgot-password emails**, **Two-factor sign-in
      for all staff**, **Locations and beds**. The rest say "Coming in Phase …" and cannot be changed.

### 14.1 Turn off Locations for one facility
- [ ] **Do:** **Settings for** → choose `Test Branch One (Pune)` → **Change** on **Locations and
      beds** → **Off**, Reason `Testing` → **Save**.
- [ ] **Expect:** that facility shows Off, while the hospital setting stays On.
- [ ] **Do:** **Locations** → choose `Test Branch One (Pune)`.
- [ ] **Expect:** a message that Locations is turned off for this facility.
- [ ] **Do:** turn it back to **Same as the hospital**. Reason `Test finished`.

### 14.2 Turn off forgot-password emails
- [ ] **Do:** **Whole hospital** → **Forgot-password emails** → **Off**, Reason `Testing`.
- [ ] **Window B:** sign out Asha, then look at the sign-in page.
- [ ] **Expect:** the **Forgot password?** link is gone (or says the hospital does not reset
      passwords by email).
- [ ] **Window A:** turn it **On** again (Reason `Test finished`). Window B: refresh. The link is back.

> Do **not** switch on "Two-factor sign-in for all staff" unless you want everyone (including
> Ravi-type accounts) to need an authenticator. If you test it, the screen warns you first.
> Switch it off again afterwards.

- [ ] **Admin console:** **Features** → **Feature flags** shows each change, with the reason.

---

## Part 15: security page, "My sign-ins" and forgot password

### 15.1 Backup codes
- [ ] **Window A:** click your name or **Security: two-factor sign-in** → **Security**.
- [ ] **Expect:** Two-factor **On**, "Required for your role", **Backup codes left: 10**.
- [ ] **Do:** sign out → sign in with password → when asked for the code, use **Use a backup
      code** and type one code from your saved .txt file.
- [ ] **Expect:** you are signed in. **Security** now shows 9 backup codes left. The same backup
      code never works twice.
- [ ] **Do:** **Get new backup codes** (needs a current 6-digit code) → save the new file.

### 15.2 My sign-ins (needs PR #20)
- [ ] **Window C (Edge):** go to http://localhost:5175 and sign in as **the India admin** (same as
      Window A; use the phone code). You are now signed in on "two devices".
- [ ] **Window A:** **Security** → section **My sign-ins**.
- [ ] **Expect:** two rows, e.g. "Chrome on Windows" marked **This device**, and "Edge on
      Windows" with a **Sign out** button. Each row shows when it signed in and the IP address
      (127.0.0.1 on your computer).
- [ ] **Do (Window A):** click **Sign out** on the Edge row.
- [ ] **Window C:** refresh.
- [ ] **Expect:** Edge is signed out. Window A is still signed in.
- [ ] **Do:** sign in again in Window C. Then in Window A click **Sign out all other devices**.
- [ ] **Expect:** "Signed out 1 other device." Window C is signed out after refresh. The list says
      "You are not signed in anywhere else."

### 15.3 Forgot password (Asha)
- [ ] **Window B:** sign out Asha. On the sign-in page click **Forgot password?** → email
      `asha.nurse@test.local` → **Send reset link**.
- [ ] **Expect:** a message that **if** the email belongs to an active account, a link was sent.
      (It says the same for unknown emails, so outsiders cannot discover who has an account.)
- [ ] **Do:** also try `nobody@test.local`.
- [ ] **Expect:** the same message, and **no** email in the launcher window.
- [ ] **Launcher window:** copy the reset link `http://localhost:5175/reset-password#token=...`.
- [ ] **Window B:** open it → choose a new password (12+ characters) twice → **Change password**.
- [ ] **Expect:** "Your password was changed. For your safety, every device that was signed in
      has been signed out." Sign in with the new password and Asha's code. Write the new password down.
- [ ] **Do:** open the same reset link again.
- [ ] **Expect:** it no longer works (one use only; it expires after 60 minutes anyway).

---

## Part 16: access reviews

(Needs PR #20.) An access review means "every few months, someone checks who has which access and
removes what is no longer needed". **Nobody may decide on their own access**, so you need two
reviewers. Asha will be the second reviewer.

### 16.1 Prepare a second reviewer
- [ ] **Window A:** **Access** → **New custom role**: Name `Access reviewer`, Code
      `access-reviewer`, permissions: **See periodic access reviews…** and **Run periodic access
      reviews…** → **Save**.
- [ ] **Do:** **Staff** → Asha → **Give access**: Role **Access reviewer**, **Whole hospital**,
      Reason `Second reviewer for test` → **Give access**.
- [ ] **Window B:** refresh.
- [ ] **Expect:** Asha now sees **Access reviews** in her menu.

### 16.2 Start a review (Window A)
- [ ] **Do:** **Access reviews**.
- [ ] **Expect:** a blue or yellow box: "Next review due by …" (every 90 days) or "A review is due",
      and the list says "No access review has been done yet."
- [ ] **Do:** **Start a review** → keep the name (e.g. "Access review October 2026"), leave
      **Finish by** empty → **Start review**.
- [ ] **Expect:** a new review **In progress**, "0 of N" decided.
- [ ] **Do:** try **Start a review** again.
- [ ] **Expect:** the button is gone (only one review at a time).

### 16.3 Decide (Window A)
- [ ] **Do:** click the review name.
- [ ] **Expect:** one row per person and role and place: you, the auditor, Asha (Basic staff,
      HR officer, Access reviewer) and the external auditor if you gave them a role. Columns
      show last sign-in and, if relevant, **Account switched off**.
- [ ] **Expect:** your **own** rows say "Your own access: another reviewer decides" and have no buttons.
- [ ] **Do:** on Asha's **Basic staff access** row → **Keep**.
- [ ] **Expect:** decision **Keep**, with your name and date.
- [ ] **Do:** on Asha's **HR / credentialing officer** row → **Remove** → leave the reason empty.
- [ ] **Expect:** **Remove access now** cannot be clicked until you type a reason. Type
      `HR role was only for testing` → **Remove access now**.
- [ ] **Expect:** decision **Removed**. Go to **Staff** → Asha → Access: the HR role is gone
      (shown only with **Show removed and expired**).
- [ ] **Do:** tick the boxes of the remaining rows that are not yours (e.g. the auditor's and
      Asha's Access reviewer row) → **Keep selected (n)**.
- [ ] **Expect:** all chosen rows become **Keep**. **Complete review** is still greyed out because
      your own rows are undecided.
- [ ] **Do:** use the **Decision** filter (e.g. "Not reviewed yet") and **Search**.

### 16.4 The second reviewer decides your rows (Window B)
- [ ] **Window B (Asha):** **Access reviews** → open the review.
- [ ] **Expect:** Asha's own rows say "Your own access: another reviewer decides". Your (admin)
      rows have **Keep** / **Remove** buttons.
- [ ] **Do:** **Keep** each of your (admin) rows.
- [ ] **Expect:** nothing is left "Not reviewed yet".

### 16.5 Complete and download (Window A)
- [ ] **Window A:** refresh the review → **Complete review** → Summary `All checked` → **Complete review**.
- [ ] **Expect:** status **Completed**, with your name and the date. Keep/Remove buttons are gone
      (locked). On the **Access reviews** list, the box now shows the next due date (90 days from today).
- [ ] **Do:** **Download (CSV)** → open the file in Excel.
- [ ] **Expect:** one line per row, with decision, who decided, when, and the comment, including
      "HR role was only for testing".

### 16.6 Reminder emails (optional)
In the CMD window from Part 13:
```cmd
python manage.py send_access_review_reminders
```
- [ ] **Expect:** "Sent 0 reminder(s)." (A review was just completed, so none is due.)

### 16.7 Admin console
- [ ] **Do:** admin tab → **Access_Control** → **Access reviews**, **Access review items**,
      **Access review reminders**.
- [ ] **Expect:** your review and all its rows. The items page has actions **Keep selected
      access** and **Remove selected access now**. They follow the same rules as the app: your own
      rows are refused.
- [ ] **Do:** **Access reviews** → **Add access review**: Title `Console review`, Due on next week → **Save**.
- [ ] **Expect:** a new review is created with a snapshot of current access.
- [ ] **Do:** select it → action **Cancel selected reviews** → **Go**.
- [ ] **Expect:** status Cancelled.

---

## Part 17: audit log (as the auditor)

**Window C** (Edge). Sign out the admin there first, if signed in.

### 17.1 Auditor sign-in and two-factor
- [ ] **Do:** http://localhost:5175 → sign in with the India **auditor** email and password from `login.md`.
- [ ] **Expect:** if two-factor isn't set up yet, the Security page asks for it. Set it up with
      your phone (name it **"HIMS India auditor"**) and save the backup codes.
- [ ] **Expect:** the auditor's menu shows **Access reviews**, **Audit log** and **Audit integrity**
      only. **No** Staff, Accounts or settings.

### 17.2 Search
- [ ] **Do:** **Audit log** → leave everything empty → **Search**.
- [ ] **Expect:** the latest events: sign-ins, every change you made today, in plain words
      ("Facility added", "Bed status changed", "Access review completed", "Signed out of devices"…).
- [ ] **Do:** **Person** = `Asha` → **Search**.
- [ ] **Expect:** only events by or about Asha.
- [ ] **Do:** **Area** = **Hospital setup**, set **From** = today → **Search**.
- [ ] **Do:** **Reference number** = the reference Asha saw on her "no access" page (Part 9.2) → **Search**.
- [ ] **Expect:** exactly that event ("no access").
- [ ] **Do:** click an event where something changed (e.g. Test Branch One renamed).
- [ ] **Expect:** a details window with **What changed**: Field / **Before** / **After**, plus
      who, when, IP address and the reference number.
- [ ] **Do:** **Download CSV**.
- [ ] **Expect:** a CSV file of the matching events.
- [ ] **Do:** search again.
- [ ] **Expect:** your own searches and downloads now appear in the log too ("the auditor is
      audited").

### 17.3 Auditor in the admin console
- [ ] **Window C:** http://localhost:8000/admin/ → sign in as auditor (with code).
- [ ] **Expect:** only the **Audit** section is visible: **Audit events**, **Audit chain links** and
      **Audit integrity checks**. Open one event: you can read it, but there is no Save or Delete.

### 17.4 Auditor and access reviews
- [ ] **Window C (app):** **Access reviews** → open the completed review.
- [ ] **Expect:** the auditor can read and **Download (CSV)**, but sees **no** Keep, Remove,
      Complete or Start buttons.

### 17.5 Audit integrity: proof that nobody changed the audit log (needs PR #22)
Every audit record is "sealed" into a chain, like a wax seal. If anyone changes or removes a
record directly in the database, the seal breaks and HIMS reports it.

- [ ] **Window C (app):** menu → **Audit integrity**.
- [ ] **Expect:** "Latest check: **Never checked**" the first time, **Records sealed** = 0 and
      **Waiting to be sealed** = a number (all records made today). This is normal on your PC:
      there is no background job here, so sealing happens when a check runs.
- [ ] **Do:** press **Check now**. Wait a few seconds.
- [ ] **Expect:** green message "Passed: N record(s) checked, nothing was changed."; Latest check
      = **Passed**, "Started by a person (your auditor name)"; **Records sealed** is now N; a
      long **Chain fingerprint** (64 letters and numbers) is shown; **Signing key name** = `local`.
- [ ] **Do:** press **Check now** again.
- [ ] **Expect:** passed again, with a few more records (your first check is itself in the log).
      **Past checks** lists both, newest first.
- [ ] **Do:** click the date of a past check.
- [ ] **Expect:** the check's page: Passed, records checked, the chain fingerprint and a reference.
- [ ] **Do:** **Audit log** → **Area** = **Audit log use** → **Search**.
- [ ] **Expect:** "Audit log integrity checked" events, one for each check.
- [ ] **Window C (admin console):** **Audit** → **Audit integrity checks** → button
      **Run integrity check now** (top right).
- [ ] **Expect:** "Passed: … nothing was changed." and the check's details open. **Audit chain
      links** lists the links (numbers and fingerprints only, no Save or Delete).
- [ ] **Do (optional, terminal):** in a second Command Prompt in `backend`, with the virtual
      environment on: `python manage.py check_audit_log`
- [ ] **Expect:** `PASSED. Sealed … checked … chain head …`.
- [ ] **Do NOT** try to tamper with your real database to "see it fail". This is tested
      automatically on a throwaway database. A failed check shows a red warning, "possible
      security incident", and emails every auditor.

---

## Part 18: the admin console (Django admin) tour

**Window A**, admin tab (signed in as admin). Every change here is audited. Nothing can be deleted.

| Section → page | Check |
|---|---|
| **Organizations → Organizations** | Hospital details; edit the display name and save, then put it back. |
| **Facilities → Facilitys, Departments, Buildings, Floors, Wards, Rooms** | Same data as the app; departments have services and hours sections. |
| **Beds → Beds** | Beds with status; filter by status. |
| **Numbering → Numbering schemes, Number counters, Issued numbers** | Schemes match the app. Issued numbers is empty (patients come later). |
| **Features → Feature flags** | Your on/off changes with reasons. |
| **Staff → Staff members, Staff credentials, Staff documents, Credential expiry alerts, Designations, Specialties, Qualification types** | All your test data; codes of catalog entries cannot be changed. |
| **Identity → Users** | All accounts. Select Asha in the list: the **Action** drop-down has **Send invitation email (activate account)**, **Send password reset link (forgot password)**, **Sign out of all devices**, **Reset two-factor sign-in (lost phone)**. |
| **Identity → User sessions** | Who is signed in where. The secret session key is **never** shown. |
| **Identity → Invitations, Password resets, Mfa devices** | Read only. Links and secret keys are never shown. |
| **Access_Control → Roles, Role assignments, Permissions** | Roles and who has them. Revoke with the action **Revoke selected role assignments**. |
| **Access_Control → Access reviews, Access review items, Access review reminders** | See Part 16.7. |
| **Idempotency, Outbox** | Technical records (read only). Nothing to test; just check they open. |

Checks:
- [ ] **Do:** open **Identity → Users** → select Asha → action **Sign out of all devices** → **Go**.
- [ ] **Expect:** "Signed out 1 session(s)." Asha (Window B) is signed out after refresh.
- [ ] **Do:** **Access_Control → Role assignments** → **Add**: user `External Auditor Test`,
      role **Auditor**, Reason `Console test` → **Save**.
- [ ] **Expect:** saved. Then select it → **Revoke selected role assignments** → **Go** → revoked.
- [ ] **Do:** try to give **yourself** a role here.
- [ ] **Expect:** refused (nobody can give themselves access).
- [ ] **Window C (auditor app):** **Audit log** → **Area** **Admin console** → **Search**.
- [ ] **Expect:** your console changes are listed with "via admin-console".

---

## Part 19: leaving staff (termination)

**Window A** app + **Window B** (Asha signed in).

- [ ] **Window B:** sign in as Asha and leave her on a page.
- [ ] **Window A:** **Staff** → Asha → **Edit** → Employment status **Terminated**, Last working
      day = today → **Save**.
- [ ] **Expect:** Asha's sign-in account is switched off. Her postings end.
- [ ] **Window B:** refresh.
- [ ] **Expect:** Asha is signed out at once and cannot sign in any more.
- [ ] **Do:** do the same test with **Ravi** if you like: after termination, **Departments** →
      Cardiology no longer shows Ravi as head (cleared automatically).
- [ ] **Window C (auditor):** **Audit log** → **Person** `Asha` → **Search**.
- [ ] **Expect:** the termination and "Signed out of devices" are recorded.

---

## Part 20: safety checks (things that must be refused)

Each of these must be **refused** with a clear message. A refusal here is a **pass**.

| # | Do | Expect |
|---|---|---|
| 20.1 | **Accounts** → open your own account | "This is your own account. Another administrator has to change it." No switch-off button |
| 20.2 | **Departments** → **Edit** Cardiology → **Inactive** while Asha or Ravi still has an active posting, or the Cardiac Ward is active | Refused: close in order (end postings and wards first) |
| 20.3 | **Facilities** → **Edit** Test Branch One → **Inactive** while it has active departments | Refused for the same reason |
| 20.4 | **Locations** → set an **Occupied** bed status by hand | Not offered (only admissions will set it) |
| 20.5 | **Numbering** → **Continue from…** a number smaller than the current next number | Refused (numbers are never reused) |
| 20.6 | Open an old invitation or reset link a second time | "Link no longer valid" |
| 20.7 | Type the wrong two-factor code 3 times | Refused each time; nobody gets in |
| 20.8 | Admin console: wrong password 5 times in a row (use a wrong password on purpose) | "Too many failed sign-in attempts. Try again in 15 minutes." Wait 15 minutes, or use the app meanwhile |
| 20.9 | Window B: as a person **without** a role, type http://localhost:5175/staff in the address bar | "You don't have access to this", with a reference number |
| 20.10 | Access review: try to **Keep** your own row (no button) | Not possible; "Your own access: another reviewer decides" |
| 20.11 | Look for any **Delete** button in the app or admin console | None exists. Records are switched off, revoked or archived instead. Only exception: a department's opening-hours rows in the admin console (they are settings, and changes are audited) |
| 20.12 | Window A (admin): type http://localhost:5175/audit/integrity in the address bar | "You don't have access to this". Administrators cannot see or run the tamper check (only auditors can) |
| 20.13 | **Cover** → **Arrange cover** with yourself as the **Person covering** | Refused: "You cannot arrange cover that gives yourself access" |

---

## Part 21: repeat the key steps for the US hospital

The US hospital is a **completely separate** hospital with its own database.

1. Launcher (http://localhost:5173) → **US Hospitals**. The US app opens at **http://localhost:5174**.
2. **Window A**, new tab: http://localhost:5174.

- [ ] **Do:** try the **India** admin email and password here.
- [ ] **Expect:** refused. India accounts do not exist in the US hospital.
- [ ] **Do:** sign in with the **US** admin from `login.md` and set up two-factor (phone entry
      **"HIMS US admin"**).
- [ ] **Expect:** none of the India test data (Test Branch One, Asha, Ravi) appears here.
- [ ] **Hospital settings:** country **United States**, currency **USD**, time zone e.g.
      America/New_York.
- [ ] **Facilities:** create `UST1` `US Test Clinic`, Country **United States**, a US time zone.
- [ ] **Departments:** add `Cardiology` to it.
- [ ] **Job titles & catalogs:** the standard entries are the **US** ones (e.g. Attending
      Physician, Registered Nurse).
- [ ] **Staff:** add a doctor and add a licence: types include **State licence (US)**,
      **National Provider Identifier (US)** and **DEA registration (US)**.
- [ ] **Numbering:** the financial year note mentions the US fiscal year (often January, July or
      October), not April.
- [ ] **Admin console:** http://localhost:8001/admin/ with the US admin. Only US data is shown.
- [ ] **Emails:** in the launcher window, US lines start with `🇺🇸 [backend]` and links start with
      `http://localhost:5174/`.
- [ ] **Licence alerts for US** (in the CMD window):
      ```cmd
      set HIMS_ENV_FILE=.env.us
      python manage.py send_credential_expiry_alerts
      set HIMS_ENV_FILE=
      ```
      Always run the last line, so the next command uses India again.

Optionally repeat Parts 9, 15 and 17 for the US with the US auditor.

---

## Stop HIMS

1. Click in the **launcher window** and press `Ctrl+C`. Answer `Y` if asked.
2. **Expect:** "Stopping all hospital servers started by the launcher…".
3. Close the CMD windows and browser windows.

Your test data stays in the databases. That is fine for a local computer, because it is all
made up. Do not create test data like this on a real hospital server later.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| "Port 5173 is already in use" | An old launcher is still running. Find that CMD window and press `Ctrl+C`, or restart the computer. Then `npm run dev` again. |
| The app page is blank or "cannot connect" | Wait 20 seconds after clicking the hospital card. Make sure the launcher window is still open. Click the card again. |
| Admin console says "can't be reached" | Start that hospital from the launcher first (8000 = India, 8001 = US). |
| "Your role requires two-factor sign-in. Set it up in the HIMS app…" on the admin console | Sign in to the **app** first, set up two-factor on the Security page, then come back. |
| The 6-digit code is always wrong | The phone's time must be correct: Phone settings → Date & time → **automatic**. Wait for a fresh code. |
| Lost the phone or deleted the app entry | Use a backup code. Or, as another administrator, **Accounts** → that person → **Reset two-factor (lost phone)**. |
| Can't find the invitation or reset link | It is in the **launcher window**, not your real email. Scroll up. Make sure you copy the **whole** link. |
| "This record changed since you loaded it" | Someone (or another tab) changed it. Refresh the page and try again. This is correct behaviour. |
| Signed out suddenly | 30 minutes without activity, or someone signed you out on purpose in the test. Sign in again. |
| A thin bar appears at the top when you open a screen | Normal: each screen is downloaded the first time you open it (faster start). |
| "HIMS was updated" with a **Reload** button | HIMS was updated while the page was open. Press **Reload**; nothing you saved is lost. |
| "ModuleNotFoundError: opentelemetry" in the launcher window after a pull | The new libraries are not installed yet. Run the install block at the top of docs/workflows/database-migrations.md. |
| A page shows "Something went wrong" with a **Reference** number | Write the reference down. Report it (see below). The auditor can find the exact event with it. |
| You changed `login.md` passwords and forgot them | Ask Claude to help reset the admin password from the command line. |

---

## How to report a problem

For each problem, write down:

1. **Part and step number** (e.g. "Part 10.2, third box").
2. **Which hospital** (India or US) and **which window/person** (admin, Asha, auditor).
3. **What you did** and **what you expected** (copy the "Expect" line).
4. **What actually happened**: the exact message, plus a screenshot (Windows key + Shift + S).
5. The **Reference number**, if the screen shows one.
6. Paste the last 20 lines of the launcher window if there was an error.

Send these to Claude in one message: "Manual test found problems: …".

---

## Results sheet

Fill in **Pass**, **Fail** (with a note) or **Skipped**.

| Part | Area | India | US | Notes |
|---|---|---|---|---|
| 1 | First sign-in, two-factor, admin console sign-in | | | |
| 2 | Hospital settings | | | |
| 3 | Facilities | | | |
| 4 | Departments | | | |
| 5 | Locations and beds | | | |
| 6 | Numbering | | | |
| 7 | Job titles and catalogs | | | |
| 8 | Staff, postings, qualifications, licences, documents | | | |
| 9 | Invitation, activation, no-access page, giving access | | | |
| 10 | Department page: head, hours, services | | | |
| 11 | Roles and access | | | |
| 12 | Accounts (incl. cover arrangements) | | | |
| 13 | Licence expiry and alerts | | | |
| 14 | Features | | | |
| 15 | Security, My sign-ins, forgot password | | | |
| 16 | Access reviews | | | |
| 17 | Audit log and audit integrity (auditor) | | | |
| 18 | Admin console tour | | | |
| 19 | Leaving staff | | | |
| 20 | Safety checks | | | |

**Tested by:** ____________ **Date:** ____________ **Code version (git commit):** ____________
(find it with `git log --oneline -1` in the HIMS folder)
