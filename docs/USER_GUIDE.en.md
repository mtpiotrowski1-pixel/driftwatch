# Driftwatch — user guide

This guide walks through the app using the names of its controls. No programming
knowledge is required. The [interface gallery](screenshots/README.md) shows current
views with synthetic data.

On a fresh installation, register the first account to become its
administrator/operator. Further registration is closed by default; an
administrator invites additional users (section 10). A running instance can
also be initialized with a seeded owner. See [installation](INSTALL.md).

> Polish version: [USER_GUIDE.pl.md](USER_GUIDE.pl.md). The language switch and
> sign-out live at the bottom of the menu, in the bottom-left corner (see section 2).

What it does: Driftwatch watches the web pages you choose and emails you when
something that matters changes (a price, a policy, an offer) — so you never have
to check them by hand.

---

## Glossary — a few terms to start

- **Site** — a single web address that Driftwatch watches.
- **Project** — a group of sites that share rules and recipients (think of it
  like a folder).
- **Recipient** — an email address that receives alerts.
- **Change** — a difference detected on a page between two checks.
- **Significant change** — a change the AI judged important according to your rules
  (e.g. a price change, not a typo in a banner).
- **Starting point** (a.k.a. baseline) — the saved state of a page that later checks compare against.
- **Organization** — an isolated personal or team workspace: its own projects,
  sites and recipients, invisible to other organizations.

## Roles — why your menu differs from someone else's

Some menu items appear depending on your permissions:

- **Operator** (superadmin) — the owner of the whole instance;
  additionally sees **Organizations** (section 9).
- **Administrator** — manages their organization; sees **Access** (users,
  section 10) and the full **Settings** (section 8).
- **Member** — sees the organization's data but can only edit what they were granted
  access to. They can still change their own password and language.

---

## 1. Signing in

1. **Email** — type your email address.
2. **Password** — type the password you set from your invitation, or your initial
   administrator password on a fresh installation. Administrators do not receive
   or choose an invited user's password.
3. **Sign in** — click to enter.
4. **Forgot your password?** — we'll email you a link to set a new one (the link is
  valid for 30 minutes — see section 1a).

If two-factor authentication is on (a code from an app on your phone), after the
password the app will also ask for a six-digit code (or one of your recovery codes).
How to enable it — see section 8.

Administrators on an exposed deployment must enroll TOTP before accessing the
product. The first owner can manage their home organization through their
administrator membership, without a support grant. Operator access to another
organization requires a time-limited audited support grant. See the
[administrator guide](ADMIN_GUIDE.en.md).

### 1a. Resetting your password

After clicking **Forgot your password?**, enter your email and click **Send reset
link**. If the account exists, you'll get a message with a link. The link opens a
**Choose a new password** screen, where you type the new password twice (at least 8
characters) and confirm with **Set new password**. Then sign in with the new one.

---

## 2. Finding your way around (the menu)

After signing in, the **menu** on the left is what you use the whole time.

1. **Dashboard** — the home overview.
2. **Add site** — add a new web address to watch.
3. **Projects** — groups of sites with shared rules.
4. **Recipients** — the email addresses that receive alerts.
5. **Notifications** — the history of sent messages.
6. **Settings** — configuration and your account.

Depending on your role, the menu may also show: **Access** — for an administrator
(section 10) — and **Organizations** — for the operator (section 9).

**At the very bottom of the menu (bottom-left corner)** you'll find your profile
(name and email), the **language switch** (English / Polski), and **Sign out**.
That's the quickest place to change the language and to leave your account safely.

The **Dashboard** shows the key numbers (how many sites, how many changes, the AI
analysis cost), an activity chart, the most recent changes, and a tile for each of
your sites with a **Check now** button that checks a page immediately.

---

## 3. Adding a site to watch

This is the most important task. Click **Add site** in the menu.

1. **URL** — paste the full address you want to watch (e.g. `https://example.com/pricing`).
2. **Name** — your own readable name (e.g. "Competitor pricing"). Optional.
3. **Create site** — saves it and starts watching.

Also on this screen:
- **Pick the area to watch** — instead of the whole page you can point at a specific
  part with the mouse ("Open visual picker"). It works when the server has a
  display; if not, the whole page is watched and you can type a selector by hand in
  the "Advanced" section.
- **Record steps** — if the page needs a login or a banner dismissed, record those
  clicks once; they are replayed before every check.
- **Check interval** — how often (in minutes) to check (e.g. 60).
- **Notifications** — when to alert: *inherit from project or global*, *only
  significant changes*, or *every change*.
- **Recipients** — who should be notified about this site.
- **Analysis** — choose AI disabled to monitor without an OpenAI key. This mode
  requires Every change notifications; it records the diff without an AI verdict.

The visual picker depends on the deployment and is disabled in reference Compose.
You can still enter a CSS selector and configured interaction steps manually.

You can also turn on **Bulk add** (top) to paste many addresses at once, one per line.

---

## 4. Projects

Projects group sites and give them shared rules. Click **Projects** in the menu.

1. **New project** — creates a new project.
2. **Project card** — click it to open the project, see its sites, and add more
  ("Add site here"). Each card also has **edit** and **delete** icons and **Export
  to Excel** (download the project's changes as a spreadsheet).

In a project you set shared **AI rules** (what counts as important) and the
**notification mode** (every change / only significant), which every site inside
inherits. Deleting a project keeps its sites — they simply stop inheriting its rules.

---

## 5. A site and its change view

Clicking a site (from the dashboard or a project) opens its detail page. This is
where you see exactly what changed.

1. **Check now** — checks the page right away, without waiting for the schedule. The
  same toolbar also has: **Test check** (check the page but send no alerts),
  **Set starting point** (save the page as it is now), **Pause**, **Edit**, **Export to Excel**
  (download the changes), and **Delete**.
2. **Change view** — colours show exactly what changed: **red** = removed/old,
  **green** = new. Above it is a short AI summary (e.g. "Price dropped from 199 to
  149") and a verdict on whether the change is **significant**.

On the left is the list of every detected change for this site — click any one to
see its diff.

**When something fails:** if a check or an email delivery fails, the change gets a
red **Needs attention** badge. Open it and use **Retry** (resend the email) or
**Re-analyze** (re-run the AI analysis without sending an email).

AI disabled, waiting, failed and quota-blocked states are shown separately from
an insignificant verdict. The analysis history records each actual run with its
model and rules/input provenance; re-analysis preserves earlier runs. A preview
uses provider tokens but does not overwrite the saved verdict. Unknown pricing
is shown as unknown. A capture failure retains the last successful baseline.

---

## 6. Recipients

Recipients are the email addresses your alerts go to. Click **Recipients**.

1. **Add recipient** — add a new email address.
2. **Calendar icon (holiday cover)** — when someone is away, set a **cover** for
  chosen dates: during that time their alerts go to a stand-in. You can limit a
  cover to a single project or a single site, or leave it on all notifications.

Next to each recipient are also **edit** (rename, enable/disable — an inactive
recipient is skipped during delivery) and **delete** icons.

---

## 7. Notifications

This is the **history** of every notification: who it went to, when, and whether it
was delivered. You can filter by status: **All**, **Sent**, **Failed**, and
**Skipped**. This is where you confirm that alerts are actually going out.

---

## 8. Settings (for an administrator)

Organization administrators configure importance rules, mail content/language,
recipients, webhook and branding. Shared model credentials, model selection,
mail provider/sender and the email test belong to the instance operator's
settings. Members can change their own password, language and theme.

1. **OpenAI API key (operator)** — the key for the model that rates changes. Without it the
  analysis won't run. It is stored encrypted (the field only shows `********`).
2. **Model (operator)** — which configured model rates differences. Review current provider
   pricing and the usage screen; a model without known pricing is not estimated
   as another model or reported as free.
3. **Email provider (operator)** — how to send mail (Auto-detect / SMTP / Brevo / Log only). Below it
  you enter the sender and mail-server details.
4. **Webhook URL** — optional: besides email, every significant change can also go
  to Slack, Discord, or your own endpoint.
5. **Save settings** — stores your changes. **Remember to click it after every
  change.**

A few more useful things on this page:

- **Send test email (operator)** — in instance settings, sends one test message to an address you
  pick so you can confirm mail works. Save your settings first. The webhook has the
  same kind of button, **Send test webhook**.
- **Operations (instance operator only)** — download or restore a SQLite backup
  from instance settings after re-authentication. Restore replaces the whole
  database, saves a safety copy and invalidates sessions. Organization
  administrators do not have these controls. Raw logs are read by the operator
  on the host; they are not available for download through the product.
- **Preferences** — change the **language** and the **color theme** of the app.
- **Branding** — set the **brand name**, **logo**, and **accent color** for your
  organization; your team sees them across the app, and a blank field inherits the
  instance default. If you are the operator, the same card also sets the **public
  landing page** — its tagline, hero text, and background image that visitors see
  before signing in.
- **Change password**, **two-factor authentication (2FA)** (see section 8a),
  **AI usage** (costs — by month, site, and project), and the **"What reaches the
  AI"** panel (what the system strips from a page before analysis).

A blank field usually means "use the default value".

### 8a. Turning on two-factor authentication (2FA)

In the **Two-factor authentication** section, click **Enable two-factor
authentication**, scan the QR code with an authenticator app (or enter the key by
hand), type the generated code, and confirm with **Confirm and enable**. Save the
**recovery codes** shown — each works once if your phone is unavailable; they won't
be shown again.

---

## 9. Organizations and plans (operator only)

If you are the operator, the menu shows **Organizations**. The default
organization is your initial workspace. Additional organizations keep separate
teams or monitoring workspaces isolated.

1. **New organization** — sets up another workspace.
2. **Plan and usage** — the card shows the plan label (e.g. `business`) and the
  usage counters: **Sites X/Y** and **AI/mo X/Y** (AI checks this month against the
  limit).
3. **Edit** (pencil) — here you set the **plan**, the **site limit**, the **monthly
  AI-check limit**, and **suspension** (stops access and new checks while keeping
  the data). The **Manage** button (on the card)
  enters the organization to manage its projects and sites; you come back via the
  "Managing…" banner at the top.

Only the **operator** can change these limits or lift a suspension. Billing
remains optional and disabled by default.

---

## 10. Access and users (administrator)

Here an administrator invites users by email, sets their role (administrator /
member), enables/disables accounts and grants permissions to projects or sites.
The invited person chooses their own password through the single-use link.
Administrators can revoke sessions or reset 2FA after re-authentication; password
recovery uses **Forgot your password?** and the configured mail provider. A member
can view their organization's data and edit only granted resources.

---

## FAQ

- **I'm not getting emails.** In **Settings**, check the email section and click
  "Send test". Make sure the recipient is assigned to the site or project and is
  active.
- **Too many notifications.** On the project or site, set "only significant
  changes" mode and add to the AI rules what is unimportant (banners, typos).
- **I changed a setting and nothing happened.** Check that you clicked **Save
  settings**.
- **A change has a red "Needs attention" badge.** Open it and click **Retry**
  (resend) or **Re-analyze** (re-run the AI analysis).
- **How do I change the language or sign out?** At the bottom of the menu, in the
  bottom-left corner (language is also in Settings → Preferences).
- **I forgot my password.** On the sign-in screen, click "Forgot your password?".
