# Driftwatch — administrator guide

A plain guide to the panel for the person who runs Driftwatch: what to set
where, what each option means, what is worth adjusting, and what is better left
alone. Examples are given in a form you can type in directly.

> This document is for the administrator/operator of a deployment. Technical
> documentation (for developers) is in [`README.md`](../README.md) and
> [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). Wersja polska:
> [ADMIN_GUIDE.pl.md](ADMIN_GUIDE.pl.md).

---

## 1. Roles — who can do what

- **Operator (superadmin)** — the owner of the instance. Sees all organizations,
  creates them, and manages instance settings, audit, operations, billing, and
  backups. The first registered or explicitly seeded account is also the
  administrator of its home organization.
- **Administrator** — manages one organization: its projects, sites, recipients,
  users, and settings. Cannot see other organizations.
- **User** — sees their organization's data; can edit only the projects and
  sites they have been granted edit access to. A project grant covers its sites;
  a site grant does not grant access to unrelated sites or project administration.

The rule: **the interface hides what a role cannot do, and the server blocks it
anyway** — "reaching" a hidden button gets you nowhere.

---

## 2. First steps

1. On a fresh installation, register the first account to become its operator
   and default-organization administrator. Ongoing registration closes by default.
   A non-loopback runtime needs explicit one-time signup or a seeded account;
   see [first-account setup](INSTALL.md#first-account-and-registration).
2. **Enable two-factor authentication** (Settings → Two-factor authentication).
   It is the most important protection for the operator account — see section 8.
3. If you serve multiple clients: in the **Organizations** panel create an
   organization and click **Manage** to "enter" it. Everything you then create
   (projects, sites, recipients, users) lands in that organization. The top
   banner shows which organization you are in; "Exit" returns to the operator
   view.

For personal monitoring, open **Organizations → Manage** for the default
organization. As its administrator, you can create projects and monitors without
a support grant. Access to another organization's data remains separate and
requires the support workflow on a public deployment. The first-owner claim is
transactional and durable; restarting or deleting accounts does not reopen it.

**Plans, limits and suspension (operator only).** Each organization card shows
its plan and usage: the number of sites and AI checks this month. A manually
managed organization can receive a plan template and explicit caps. Once it has
billing history, normal plan/cap edits are blocked: verified subscription state,
not an operator form, becomes the source of entitlements.

Limits are enforced transactionally by the server. The **Active** toggle
suspends an organization: users and new checks are blocked, while data, audit,
and billing history remain. **Permanent organization deletion is not exposed by
the panel or API.** Ending service requires controlled offboarding: export, a
grace period, provider cleanup, retention handling, and a backup tombstone.

The **Billing** screen shows the organization's real subscription state. New
purchases remain closed until the provider, self-service, approved legal gate
and correct test/live mode are configured. Self-service is for manually created
organizations; public registration must remain disabled. Enabling both public
registration and self-service billing is rejected by configuration validation.

---

## 3. Monitoring — projects, sites, recipients

- **Project** — groups sites and gives them shared AI rules and a notification
  mode. Click a project to see its sites and add another one ("Add site here").
- **Site** — a single address checked at a chosen interval. When adding:
  - **URL** — the full address, e.g. `https://example.com/pricing`.
  - **Area to watch** — click "Open visual picker" to point at a page fragment
    with the mouse (instead of typing a CSS selector by hand). The visual picker
    opens a real browser on the server — it works only when the server has a
    display (on plain Docker it will be unavailable; use the "Advanced" field
    instead).
  - **Record steps** — if the page needs a login or a banner dismissed, record
    those clicks; they are replayed before every check. Fill values are encrypted
    on the server. A URL change to a different origin requires clearing those
    steps or explicitly entering new fill values for the new origin.
  - **Interval** — how often to check, in minutes (e.g. 60).
- **Recipients** — the email addresses notifications go to. They are assigned
  to sites or projects. A recipient can have a **substitution** over a date
  range (holiday) — mail goes to the stand-in during that time. In the
  substitution dialog the **"Applies to"** field can narrow it to one project
  or one site; by default it covers all of that recipient's notifications. A
  more specific substitution (site) takes precedence over a more general one
  (project, then everything).

---

## 4. AI settings (the "AI analysis" section)

Monitoring itself does not require AI: the browser captures the selected region,
cleans explicitly excluded content and compares complete records with their
relationships. The first successful capture establishes a baseline and does not
create a change notification. A later detected difference becomes a stored event.
A price of one digit is meaningful; IDs, dates and prices are not guessed to be
noise. Read [monitoring semantics](MONITORING_SEMANTICS.md) for the exact limits.

At **Add site** or **Edit site**, select **All changes — without AI** to disable
paid analysis for that site. This explicitly sets **Every change** notifications,
without inheriting a significance filter. This path makes no AI call and consumes
no AI quota. It still needs recipients or a webhook for actual delivery. Keeping
AI enabled while removing the API key causes an analysis error, not the same mode.

With AI enabled, the model assesses the importance of an already detected change.
The verdict does not decide whether an event exists. Rules inherit in this order:
site → project → organization/instance settings → built-in default. The effective
rules panel shows which source applies.

| Option | What it is | Example / advice |
|---|---|---|
| **OpenAI API key (instance operator)** | The shared key for the model that judges changes. | `sk-...` (from platform.openai.com). Without it, analysis will not run. Stored encrypted; the panel shows only `********`. |
| **Model (instance operator)** | Which OpenAI model analyzes the diffs. | Choose a model supported by the configured provider and test your own reviewed examples; cost and agreement depend on the model and rules. |
| **Default notifications** | Whether to email about every change or only significant ones. | "Only significant changes" (recommended) or "Every change". Can be overridden per project/site. |
| **AI importance rules** | Your own words for what matters and what does not. | see the example below. Empty = the built-in rules are used (shown as grey text). |
| **Response format** (base prompt) | The instruction for how the model behaves and what language it writes in. | **Better left alone.** Empty = a sensible default (shown as placeholder). "Restore default" undoes changes. |

**Example importance rules** (you can paste this directly):

```
Significant: price changes, product availability, official announcements, new
or changed documents (including PDFs), changed dates, deadlines and opening
hours.

Not significant: typo fixes, visual changes, reordering, ad banners, navigation
and footer elements.
```

Below the AI settings there is a read-only **"What reaches the AI"** panel. It
shows what the system strips from a page before analysis (navigation, scripts,
footers…), which explicit technical attributes and ignored regions are removed, and
which fields the model returns. Visible IDs, dates and numbers remain meaningful. Worth a look before you change the rules — you
see exactly what they apply to.

---

## 5. Sending email (the "Email delivery" section)

The instance operator sets the shared provider, credentials and sender details,
and can send a test email. Organization administrators control mail content,
language, recipients and webhook within their own workspace.

| Option | What it is | Example |
|---|---|---|
| **Email provider** | How to send mail. | `auto` (picks by the credentials you provide), `smtp`, `brevo` or `log` (only writes to the log — for testing, nothing is sent). |
| **Email language** | The language of notification and password-reset emails for this organization. | `English` or `Polski`; default = English. |
| **From address** | The address mail is sent from. | `notifications@example.com` |
| **From name** | The displayed sender name. | `Driftwatch` (empty = your brand name) |
| **Subject (template)** | The email subject template. | leave the default if it fits |
| **Email intro** | Optional text at the top of each email. | e.g. "A change was detected on a monitored page." |

**SMTP variant** (your own server, Gmail, Office365):

| Option | Example |
|---|---|
| SMTP host | `smtp.gmail.com` |
| SMTP port | `587` |
| SMTP security | `starttls` (port 587) or `ssl` (port 465) |
| SMTP username | `notifications@example.com` |
| SMTP password | an app password (Gmail requires an "app password", not the regular one) — stored encrypted |

**Brevo variant** (HTTP API, simpler than SMTP):

- Set **Email provider** = `brevo` and paste the **Brevo API key**.

**Send a test email:** at the bottom of the section, type an address and click
**"Send test"** — Driftwatch sends one message through the currently saved
configuration and shows which channel it went through (or why it failed).
**Save the settings first** — the test uses saved values, not what you typed
before saving.

**Deliverability advice:** to keep mail out of spam, the sender address should
be in a domain with correct **SPF/DKIM/DMARC**. That is configured at your
domain/mail provider, not in Driftwatch.

**Technical alert recipients** — the addresses that receive operational
warnings (e.g. a page is blocked, a monitored selector disappeared). That is
your team, not the client.

**Webhook (Slack / Discord / your own)** — besides email, every significant
change can go to a webhook. In the "Webhook notifications" section paste the
address (a Slack/Discord incoming webhook or your own endpoint), pick the
format (`Generic JSON`, `Slack` or `Discord`) and click **"Send test webhook"**
(save the settings first). The address is treated as a secret (encrypted,
masked) and never lands in the logs. It must be public — internal/local
addresses are rejected.

---

## 6. Brand and appearance (branding)

You can put your own brand on Driftwatch — a name, logo, accent colour and
landing-page copy. Branding has **two layers**, exactly like the rest of the
settings:

- **Organization brand** (any administrator) — your organization's name, logo
  and accent colour; its members see them in the panel. An empty field =
  inherit from the instance settings.
- **Instance brand** (operator only) — the same fields as defaults for the
  whole instance, plus the content of the **public landing page** everyone sees
  before signing in.

You set this in **Settings → Brand**.

| Field | Layer | What it does |
|---|---|---|
| **Brand name** | org + instance | Replaces "Driftwatch" in the header, footer and browser tab title. |
| **Accent colour** | org + instance | A colour (hex, e.g. `#7c3aed`) recolouring buttons, highlights and the logo. A dark colour is automatically lightened so dark button text stays readable. |
| **Logo image** | org + instance | Upload a PNG or JPEG up to 2 MB. Empty = the built-in mark. The image is served from the application's own origin. |
| **Tagline** | instance | A short line above the hero heading and in the landing footer. |
| **Hero title / subtitle** | instance | The main text of the landing page's welcome section. |
| **Hero background image** | instance | Upload a PNG or JPEG up to 8 MB; it is darkened so the text stays readable. |

The landing fields (tagline, hero, background) are visible **only to the
operator** — there is one landing page per instance. Everything is optional:
empty fields give the polished default look. The colour must be valid hex;
images are checked by their actual content, size, and dimensions. Remote image
URLs and SVG are not rendered; bitmaps are kept in controlled same-origin
storage.

> **About the colour:** the accent is a single hex from which the whole palette
> is derived. If you prefer a ready-made colour set over your own hex, use the
> theme switcher in Settings — a custom branding accent takes precedence over
> the theme.

---

## 7. Instance settings — better left alone

These options (the "Capture and costs" section) are
visible only to the operator and affect the whole instance. **The defaults are
good — change them only deliberately.**

| Option | Advice |
|---|---|
| **Timeout / settle time** | Leave them, unless a specific page loads slowly. |
| **Min. interval / jitter** | Load guards for the shared engine. **Better left alone** — values too low can overload the browser. |
| **Snapshot retention** | How many snapshots to keep per site. The default is enough; raise it only if you need deeper history. |
| **OpenAI prices (per 1M tokens)** | Used only for **cost estimates** in the panel. Update them if OpenAI changes its pricing; they do not affect behaviour. |

In organization settings (when you "enter" an organization as the operator, or
as an administrator) these instance-wide fields are hidden — you edit only what
belongs to the organization. Every overridable field has a **"Restore
default"** which clears the organization's value and restores inheritance from
the instance settings.

The application URL, `DRIFTWATCH_BASE_URL`, belongs to deployment configuration,
not the panel form. It controls email links and the Origin guard; set it through
the [deployment instructions](DEPLOY.md).

---

## 8. Security

- **Two-factor authentication (2FA)** — Settings → enable, scan the QR code
  with an authenticator app (Google Authenticator etc.), enter the code, and
  **save the recovery codes** (shown once; each works one time when you don't
  have your phone). On a public deployment, operators and organization
  administrators must enroll before accessing protected application panels;
  the server enforces this requirement.
- **Re-authentication (step-up)** — backup/restore, invitations and sensitive
  account changes, opening checkout/portal, and granting support access require
  the password again (and a 2FA code when required). This is a deliberate guard
  on high-risk actions.
- **Passwords and secrets** — passwords are hashed (Argon2); keys (OpenAI,
  SMTP, 2FA, webhook) are encrypted in the database and masked in the panel
  (`********`). Changing a password signs out the other sessions.
- **User invitations** — an administrator creates an account with no password
  field. Delivery is queued durably; the user receives a single-use link valid
  for 24 hours from the delivery attempt and chooses the password. The `log`
  provider cannot deliver account links and surfaces `email_not_configured` in
  Operations. An administrator can resend the invitation, revoke all sessions,
  or reset TOTP, but never learns the customer's credential. These actions are
  audited.
- **Password reset** — the sign-in screen has "Forgot your password?". The user
  enters their email and receives a single-use link (valid 30 minutes). Using
  the link sets a new password and signs out all sessions. For this to work the
  instance must have email delivery configured (section 5). The form does not
  reveal whether an address has an account. Tokens are also bound to a random
  session generation; restoring the database changes it for every user and
  invalidates all old cookies and links.
- **Support access** — customer data remains locked when the operator enters
  another organization. Read and write access require MFA-backed step-up, a reason, and
  a short-lived grant. The grant can be revoked immediately and the server
  checks its database state and audits every request.

---

## 9. Operations, audit, and billing (operator)

- **Operations** — shows real database, scheduler, capture worker, queue,
  delivery, storage, and maintenance state. It becomes **degraded** for dead
  jobs, failed deliveries, or insufficient safety-copy space. An unresolved dead
  job can be redriven as one audited, idempotent successor. It is in-product
  diagnostics, not a replacement for external alerts and SLOs.
- **Audit** — append-only privileged events with actor, target, organization
  scope, and change details. Instance scope contains only control-plane events;
  customer events require entering that organization and, on a public deploy,
  a live support grant. A raw process log is not exposed as the product audit
  trail.
- **Billing** — inside an organization, shows subscription status, effective
  access, and hosted checkout/portal. Checkout and portal require step-up. Do not
  enable live mode before completing the production checklist and a review by
  the person operating the deployment and configuring the provider.
- **Download backup** — a consistent snapshot of the SQLite database (requires
  step-up; it contains password hashes and encrypted secrets, so store it
  safely). Best downloaded at a quiet moment and kept off the server.
- **Restore backup** — upload a previously downloaded copy (requires step-up).
  **It replaces all current data.** Before overwriting, Driftwatch saves the
  current database as a timestamped safety copy (`…-pre-restore-….db`) next to
  the database file. Sign in again after restoring. The file is validated (it
  must be a proper SQLite database with Driftwatch data), streamed with a limit,
  and migrated before installation. Restore rotates session generations, so all
  old sessions and links are invalidated.
- **Postgres** — SQLite backup/restore controls are hidden. Use the database
  provider's backups/PITR and the disaster-recovery runbook.
- **AI usage** — token counts and estimated costs, broken down by model, month,
  site and project. A missing price is **Unknown**, not zero. If any call lacks
  a price, the total remains unknown and the priced subtotal is shown separately.
  Zero means a known zero cost. Estimates are not a provider invoice.
- **Analysis provenance** — each completed run in the site detail preserves the
  model, rules source/version, exact system prompt, input SHA-256, truncation flag
  and usage record. A newly completed analysis appends a run; changing settings
  alone does not create one or rewrite historical inputs. Legacy records show missing fields as
  **Unknown** rather than borrowing today's settings.
- **Human review** — mark a completed verdict as significant/not significant.
  **Agreement on reviewed events** uses only detected events with both an AI
  verdict and a human label. It cannot measure changes the detector missed,
  overall recall, or correctness on unreviewed events.
- **Updates** — startup applies Alembic migrations unless disabled. Take and
  verify a backup before upgrading; automatic migration is not a guarantee
  against data loss. For production Postgres, use a separate pre-deploy migration
  job. Some downgrades intentionally refuse a lossy reversal, so prepare a
  forward fix or restore a compatible backup with its matching code and keys.

---

## 10. Quick cheat sheet: what to adjust, what not to

**Worth adjusting:**
- The OpenAI key and (possibly) the model.
- Importance rules — for your use case.
- Email details (provider, sender, SMTP/Brevo) and the email language.
- The brand: name, logo and accent colour for your company; as the operator
  also the landing page content (tagline, hero, background).
- Ignored selectors for specific "noisy" pages.
- The check interval per site.

**Better left alone (without a clear reason):**
- The response format (base prompt) — it is tuned; if needed, "Restore default".
- Capture min. interval / jitter — load guards.
- `DRIFTWATCH_BASE_URL`; it is deployment-owned and not editable in the panel.

**How to change things:** type a value into the field and click **Save
settings**. An empty non-secret field means "use the default" (shown as a grey
placeholder). A blank secret input keeps the current credential; use its
explicit **Remove stored credential** action to disable it, then authorize and
save the pending removal.


## 11. History, failures and recovery

Site history and Notifications load in pages. Use **Load older** for earlier
records; chart/statistics captions describe the loaded range, not an unqualified
all-time total. An old notification link opens its exact event even if it is not
in the first page. XLSX export uses the selected organization and requested
site/project scope. It is not limited to the pages loaded in the browser.

Open monitoring panels refresh every 15 seconds while visible, on window focus,
and through **Refresh**. The timestamp shows the last successful refresh; a
refresh failure marks the view as stale. This is not a guarantee about capture
scheduling or provider delivery time.

| State | Meaning and action |
| --- | --- |
| Pending / processing | Analysis has not finished. Refresh or wait for the next visible poll. |
| Without AI | Deliberate all-change monitoring. Inspect the diff; there is no importance verdict. |
| No delivery configured | No effective recipient and no webhook, so scheduled AI spend is skipped. Add a destination, then retry the event if needed. |
| AI error | Capture/diff survived but analysis failed. Inspect the error and configuration. Automatic retries back off 5, 15, 60 and 240 minutes, then require action. |
| AI quota reached | No model call is made. The retry is scheduled in 15 minutes; it can succeed after allowance resets or changes. |
| Delivery failure / partial delivery | Inspect recipient-level delivery rows. Retry resumes failed destinations; completed destinations are retained. |

**Re-analyze** calls AI with the current configuration and adds a completed run;
**Retry** resumes processing/delivery and may spend quota if analysis is missing.
A draft **Test rules** call also consumes AI quota and estimated cost, but does
not persist a verdict into the event. Its result belongs to the exact tested
draft; editing rules hides it.

Unsaved form edits require confirmation before leaving. Switching organizations
resets tenant forms and pending secret payloads; late responses from the previous
session/context are discarded. If a context-change error appears, review the
current banner and retry the action in that context. Read-only members see actions
according to their grants; the API independently checks every operation.

Bulk site creation retains successful rows and leaves only failed rows for retry.
Review the failing URL and error before submitting again. The visual picker has
separate retry/cancel controls; it needs a server display, so use the CSS field
when the deployment cannot open an interactive browser.

For common questions, see [FAQ](FAQ.md). For provider setup, installation and
backups, follow [README](../README.md) and [deployment instructions](DEPLOY.md).
