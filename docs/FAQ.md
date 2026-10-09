# Frequently asked questions

For installation, use [README](../README.md). The panel is documented in
[English](ADMIN_GUIDE.en.md) and [Polish](ADMIN_GUIDE.pl.md). The detection contract
and its limits are in [Monitoring semantics](MONITORING_SEMANTICS.md).

## Who becomes the administrator after downloading Driftwatch?

The first successful registration on a fresh instance becomes its
administrator/operator and administrator of the default organization.
This applies to that installation's database; it has no connection to the
author's instance. Later registration is closed by default. Invite more users
after configuring email. The first owner can manage their own workspace without
a support grant; operator support access to another organization still requires
the separate audited grant.

Concurrent registration cannot create two initial operators. The durable setup
claim survives restarts and account deletion. An upgrade keeps existing users
and roles. A non-loopback runtime must explicitly enable initial setup or seed
an operator before it is exposed. See [installation](INSTALL.md#first-account-and-registration).

## Do I need public signup, billing or a hosted service for a portfolio?

No. Publish the source repository with its tests, design decisions, screenshots
and documentation. Run your own copy locally; monitoring works with AI disabled.
Billing and ongoing public registration are optional and closed by default.
Publishing the source does not expose your local instance.

## Can I use Driftwatch commercially?

The public [PolyForm Noncommercial 1.0.0 license](../LICENSE) does not grant
commercial use of Driftwatch. A commercial product, paid hosted service or
commercial business deployment requires separate written permission from the
copyright holder. Noncommercial purposes and qualifying organizations are
defined in the license. Third-party components retain their independent
[licenses](../THIRD_PARTY_NOTICES.md).

## Can I run it without an OpenAI API key?

Yes. In Add/Edit site, select **All changes — without AI**. This explicitly uses
**Every change** notifications, makes no AI calls and consumes no AI quota.
Recipients or a webhook are still required to deliver notifications. The offline
[demo](DEMO.md) provides a reproducible example without paid services.

Removing the API key while keeping AI enabled is different: capture and diff can
succeed, but analysis records an error. It does not silently label the change
unimportant or disable AI.

## Does AI detect the changes?

The browser capture, cleaner and record comparison detect the change. AI then
assesses the importance of an existing event. With AI disabled, the same detector
works and every detected event is eligible for delivery.

## Why did my first check produce no alert?

The first successful capture creates the baseline. A later successful capture is
compared with it. Failed captures, missing selectors and HTTP error pages do not
replace a healthy baseline. Use the captured region and first real diff to check
that the selector watches the intended content.

## Will a short price or identifier be ignored?

No automatic minimum text length or visible-ID guess is used. A single digit,
date or identifier can be meaningful. Explicit technical attributes and selected
ignored regions are removed. A visible clock should be excluded deliberately
with an ignore selector.

## What if the same values remain but their associations change?

`Basic: 10, Pro: 20` becoming `Basic: 20, Pro: 10` is a change. Complete rows,
cards, definition terms and owning labels retain their relationships. Whole
independent records may move without a change; order within a generic container
is conservatively significant because arbitrary HTML does not declare semantics.
Ordered-list reordering is a change. Narrow selectors help reduce ambiguous noise.

## Does watching linked documents verify every PDF byte?

Optional document watching compares exposed ETag, Last-Modified and Content-Length
fingerprints on document-looking links. Missing or unchanged validators do not
prove identical bytes. Probe errors do not replace the page baseline.

## Why is analysis skipped with no destination configured?

Scheduled AI is skipped when there are no effective recipients and no webhook:
the verdict could not be delivered. The detected event remains available. Add a
destination and retry if needed. Explicit Re-analyze or Test rules can still call
the model without recipients and consume quota.

## What do pending, error, quota and insignificant mean?

Pending/processing means there is no completed verdict yet. **AI error** means
analysis failed and must not be read as “not significant.” **AI quota reached**
means allowance prevented a model call. **Without AI** is an intentional mode.
Only a successfully completed AI verdict can say significant or not significant.

AI failures retry after 5, 15, 60 and 240 minutes, then require action. A
quota-blocked event is scheduled again after 15 minutes, and can proceed after
allowance resets or changes. The application shows its scheduled retry state.

## What is the difference between Retry, Re-analyze and Test rules?

**Retry** resumes processing/delivery; missing analysis can cause a paid call.
**Re-analyze** assesses the stored event using current configuration and appends
a completed analysis run. **Test rules** runs a draft against an event, consumes
AI quota/cost, and returns a preview without changing its saved verdict. Editing
the draft hides the result so it cannot be mistaken for a test of the new text.

## Why is a cost Unknown instead of $0.00?

Unknown means no price is available for at least one call. Tokens and model usage
are still recorded. The total remains unknown; the known priced subtotal and
unknown-call count are displayed separately. A known zero price is shown as
$0.00. These values are estimates, not invoices. Configured model-specific price
overrides can price future calls; historical usage retains its recorded cost.

Usage covers recorded successful responses, previews and responses discarded
after ownership was lost. Transport errors, refusals or invalid structured
responses can incur provider charges without a stored usage row. Failed work
still consumes its reserved quota. Use the provider's billing records for total
spend; the dashboard is an estimate of recorded work.
Estimates use standard uncached input/output rates and do not apply cache or
batch discounts. The unused legacy cached-price field is no longer offered in
settings; old stored values do not affect estimates.

## Can I explain an old AI verdict after settings change?

Each new completed run stores model, rules source/version, exact system prompt,
input SHA-256, whether the input was truncated and the usage record ID. A new
analysis appends another run. Old provenance is not reconstructed from today's
settings. Legacy rows with missing provenance show Unknown. A hash identifies an
input; it is not a copy of that input or proof that the model was correct.

## Does the agreement percentage measure detection accuracy?

It measures agreement between AI and human importance labels on **reviewed,
detected events only**. Unreviewed events and changes never detected are excluded.
It cannot establish detection recall. The false-positive/negative counters here
describe importance-label disagreements within that reviewed set. Human labels
help review rules; they do not automatically train the model.

## Why can I view a site but not edit, pause or retry it?

Members can read their organization and edit only granted sites/projects. A
project edit grant covers its sites; a site grant does not grant unrelated edits.
Creating/deleting project structures is an administrator action. Interface
controls follow grants and the API independently authorizes every request.

## Why did switching organization clear my form?

Drafts and pending secret actions belong to the previous session/organization.
Explicit switches warn about unsaved changes. New context forms start clean and
late responses are discarded. Check the organization banner before repeating an
action. Ordinary administrators use their own organization automatically;
operator acting-organization context is a separate mechanism.

## Does entering an organization give the operator access to customer data?

An operator who is also the administrator of their own organization can manage
that organization through their existing membership. Entering another
organization does not grant access. On a public deployment, support read/write
access there also requires MFA-backed
re-authentication, a reason and an active limited-duration grant. Operators and
organization administrators must enroll 2FA before protected panels. Save the
single-use recovery codes when they are shown.

## Why can I not select an area visually in Docker?

The picker opens an interactive browser on the server and needs its display.
Use the manual CSS selector field on a deployment without a desktop. The picker
offers Retry after status/result failures and Cancel to stop a pending session.
Fill values are encrypted; switching a recorded login to a different URL origin
requires clearing its steps or entering fresh values for that origin.

## Why did only some recipients receive the message?

Inspect recipient-level rows in Notifications or event details. A partial
delivery retains successful destinations; retry resumes failed ones. Provider
acceptance is not proof that a message reached an inbox. Check provider delivery
logs and sender-domain configuration when investigating downstream delivery.

## Is the log email provider enough for invitations and password reset?

No. It is useful for monitoring delivery tests but sends no real email. Account
invitation/reset links require a real configured provider; account jobs surface
`email_not_configured` when delivery is unavailable. The reset form deliberately
does not disclose whether the entered address has an account.

## Where did older events go? Does XLSX export include them?

Site history and Notifications are paged. Select **Load older** to extend the
loaded range. Chart/statistics captions state that range. Old alert links fetch
their exact event independently of the list page. XLSX export applies the
selected organization and site/project filters, rather than just exporting the
currently loaded browser rows. Retention can remove old snapshots; pagination
cannot recover already removed data.

## Is the open dashboard live?

Visible monitoring queries poll every 15 seconds, refresh on focus and offer a
manual refresh. The last-success timestamp and stale-error state describe the
view's freshness. Scheduler, queue and provider delays are separate; a polling
interval does not guarantee capture or delivery completion within 15 seconds.

## Why does a bulk retry no longer include successful URLs?

Successfully created rows are removed from the retry input. Fix and retry the
failed rows only. Different selectors on the same URL can be legitimate sites,
so the application does not enforce global URL uniqueness. After an ambiguous
network timeout, inspect the site list before resubmitting: client recovery is
not a guarantee of server-side import idempotency.

## Why does source installation reject my existing environment?

The installer requires the checkout's own, unlinked `.venv` using Python
3.12.15 or a newer 3.12 patch. It preserves unsupported or shared environments;
rename an older environment and run the installer again to create a fresh one.
A supported upgrade removes only obsolete lxml after installing the current
dependency lock. See [installation and updates](INSTALL.md).

## What must stay out of a public Git repository?

Keep runtime `.env`, database files, snapshots, logs, backups, API/provider keys,
cookies, invite/reset links and encryption keys out of Git. Use the placeholder
`.env.example`, synthetic demo data and the [security policy](../SECURITY.md).
Secret scanning helps review the tree and history; exposed credentials must be
revoked/rotated rather than only deleted from the latest file.
