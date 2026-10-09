const messages: Record<string, string> = {
  "settings.security.confirmTitle": "Authorize protected changes",
  "settings.security.confirmDescription":
    "Re-authenticate before changing delivery routes, credentials, or a private integration endpoint.",
  "settings.security.confirmSubmit": "Save protected settings",
  "settings.security.removeStored": "Remove stored credential",
  "settings.security.removePending": "This credential will be removed when you save.",
  "settings.security.undoRemove": "Undo",
  // Page header
  "settings.title": "Settings",
  "settings.subtitle": "Your preferences and account — plus workspace configuration for admins.",
  "settings.loading": "Loading settings",
  "settings.saved": "Saved",

  // Section group labels
  "settings.group.account": "Your account",
  "settings.group.data": "Usage & operations",

  // Admin gate
  "settings.adminOnly":
    "Only administrators can change workspace configuration. You can still update your password below.",

  // AI analysis card
  "settings.ai.title": "AI analysis",
  "settings.ai.apiKey": "OpenAI API key",
  "settings.ai.model": "Model",
  "settings.ai.defaultNotifications": "Default notifications",
  "settings.ai.modeOnlySignificant": "Only significant changes",
  "settings.ai.modeAlways": "Every change",
  "settings.ai.importanceRules": "Global importance rules",
  "settings.ai.importanceRulesHint": "Plain-language guidance for rating change significance.",
  "settings.ai.importanceRulesPlaceholder":
    "Treat pricing, availability, and policy changes as significant.",
  "settings.ai.responseFormat": "AI response format (advanced)",
  "settings.ai.responseFormatHint":
    "Leave blank to use the built-in template. Only change to restructure the AI's JSON contract.",

  // Email delivery card
  "settings.email.title": "Email delivery",
  "settings.email.provider": "Email provider",
  "settings.email.providerAuto": "Auto-detect",
  "settings.email.providerBrevo": "Brevo",
  "settings.email.providerSmtp": "SMTP",
  "settings.email.providerLog": "Log only",
  "settings.email.language": "Email language",
  "settings.email.languageHint":
    "Language of notification and password-reset emails sent to this organization's recipients",
  "settings.email.languageDefault": "Default (English)",
  "settings.email.fromEmail": "From email",
  "settings.email.fromName": "From name",
  "settings.email.subjectTemplate": "Email subject template",
  "settings.email.subjectTemplateHint": "{site}, {headline}, {severity} placeholders",
  "settings.email.subjectTemplatePlaceholder": "{site} changed — {headline}",
  "settings.email.intro": "Email intro",
  "settings.email.introHint": "Optional intro line prepended to each notification",
  "settings.email.smtpHost": "SMTP host",
  "settings.email.smtpPort": "SMTP port",
  "settings.email.smtpSecurity": "SMTP security",
  "settings.email.securityStarttls": "STARTTLS",
  "settings.email.securitySsl": "SSL",
  "settings.email.securityNone": "None",
  "settings.email.smtpUsername": "SMTP username",
  "settings.email.smtpPassword": "SMTP password",
  "settings.email.brevoApiKey": "Brevo API key",
  "settings.email.brevoApiKeyHint": "Used when SMTP is not configured.",
  "settings.email.downThreshold": "Down-alert failure threshold",
  "settings.email.downThresholdHint":
    "Consecutive failed checks before a stronger 'site appears down' alert is sent (default 5).",
  "settings.email.technicalRecipients": "Technical alert recipients",
  "settings.email.technicalRecipientsHint":
    "Who is notified when a capture or delivery breaks.",
  "settings.email.noRecipients": "No recipients yet.",
  "settings.email.test": "Send a test email",
  "settings.email.testHint": "Sends one message using the saved settings above. Save first.",
  "settings.email.testSend": "Send test",
  "settings.email.testOk": "Sent via {channel}.",
  "settings.email.testFail": "Could not send: {detail}",

  // Webhook notifications
  "settings.webhook.title": "Webhook notifications",
  "settings.webhook.url": "Webhook URL",
  "settings.webhook.urlHint":
    "Posted to on every notify-worthy change. A Slack or Discord incoming-webhook URL, or your own endpoint. Stored encrypted.",
  "settings.webhook.format": "Payload format",
  "settings.webhook.formatGeneric": "Generic JSON",
  "settings.webhook.formatSlack": "Slack",
  "settings.webhook.formatDiscord": "Discord",
  "settings.webhook.test": "Send test webhook",
  "settings.webhook.testOk": "Webhook delivered.",
  "settings.webhook.testFail": "Could not deliver: {detail}",

  // Capture & cost card
  "settings.capture.title": "Capture & cost",
  "settings.capture.timeout": "Capture timeout (seconds)",
  "settings.capture.settle": "Settle delay (ms)",
  "settings.capture.minInterval": "Minimum interval (seconds)",
  "settings.capture.minIntervalHint": "Polite delay between page checks",
  "settings.capture.jitter": "Jitter (ms)",
  "settings.capture.jitterHint": "Random extra delay",
  "settings.capture.retention": "Snapshot retention",
  "settings.capture.retentionHint": "How many snapshots to keep per site.",
  "settings.capture.inputPrice": "Input price (per 1M tokens)",
  "settings.capture.outputPrice": "Output price (per 1M tokens)",
  "settings.capture.priceScope": "Estimates cover recorded responses at standard uncached prices. Provider discounts and unrecorded failed responses are excluded.",

  // Capture filters card
  "settings.filters.title": "Capture filters",
  "settings.filters.watchDocuments": "Watch linked documents",
  "settings.filters.watchDocumentsHint":
    "Also check linked files (PDF, Word, Excel) for replacement under the same URL — up to 20 documents per site, verified with lightweight HEAD requests.",
  "settings.filters.ignoreSelectors": "Ignore selectors",
  "settings.filters.ignoreSelectorsHint":
    "One per line. We skip these areas when looking for changes.",

  "settings.restoreDefault": "Restore default",

  "settings.filtering.title": "What reaches the AI",
  "settings.filtering.intro":
    "Before anything is compared or sent to the model, each page is reduced to its meaningful content — only the resulting diff, never the whole page, is analysed.",
  "settings.filtering.strippedTags": "Always removed",
  "settings.filtering.strippedTagsHint":
    "These elements never carry watched content and are dropped from every page.",
  "settings.filtering.volatile": "Collapsed to a placeholder",
  "settings.filtering.volatileHint":
    "Values matching these patterns change on every load, so they are neutralised before diffing.",
  "settings.filtering.response": "Model response",
  "settings.filtering.responseHint":
    "The model must always return exactly these fields; the prompt above shapes their content.",

  // Save button
  "settings.save": "Save settings",

  // Change password card
  "settings.password.title": "Change password",
  "settings.password.current": "Current password",
  "settings.password.new": "New password",
  "settings.password.newHint": "At least 8 characters",
  "settings.password.confirm": "Confirm new password",
  "settings.password.mismatch": "Passwords do not match.",
  "settings.password.submit": "Update password",
  "settings.password.changed": "Password changed",

  // Operations card
  "settings.ops.title": "Operations",
  "settings.ops.openAudit": "Open audit log",
  "settings.ops.detectingCapabilities": "Detecting deployment capabilities…",
  "settings.ops.capabilitiesUnavailable":
    "Deployment capabilities could not be loaded.",
  "settings.ops.providerManagedBackup":
    "This deployment uses a managed database. Backup and restore are performed in the infrastructure layer under the disaster-recovery runbook.",
  "settings.scope.instance":
    "You're editing the instance defaults. Every organization inherits these unless it sets its own.",
  "settings.scope.org":
    "You're editing this organization's settings. Clear a field to fall back to the instance default.",
  "settings.ops.downloadBackup": "Download backup",
  "settings.ops.backupConfirm":
    "The backup contains password hashes and secrets. Confirm your identity to download it.",
  "settings.ops.restore": "Restore backup",
  "settings.ops.restoreConfirm":
    "Restoring replaces all current data with the uploaded backup. Confirm your identity to continue.",
  "settings.ops.restorePick":
    "Choose a Driftwatch backup file. The current database is saved to a timestamped safety copy first.",
  "settings.ops.restoreSubmit": "Replace database",
  "settings.ops.restoreDone": "Database restored. Please sign in again.",

  // AI usage card
  "settings.usage.title": "AI usage",
  "settings.usage.totalCost": "Total cost",
  "settings.usage.tokens": "Tokens",
  "settings.usage.calls": "Calls",
  "settings.usage.byMonth": "By month",
  "settings.usage.bySite": "By site",
  "settings.usage.byProject": "By project",
  "settings.usage.callsSuffix": "calls",
  "settings.usage.tokensSuffix": "tokens",
  "settings.usage.unavailable": "Usage data is unavailable.",

  // Branding card
  "settings.branding.title": "Branding",
  "settings.branding.name": "Brand name",
  "settings.branding.nameHint": "Shown in the header, footer, and browser tab. Defaults to Driftwatch.",
  "settings.branding.accent": "Accent colour",
  "settings.branding.accentHint":
    "Recolours buttons, highlights, and the logo. Leave blank for the default.",
  "settings.branding.logo": "Logo image",
  "settings.branding.logoHint":
    "Upload a PNG or JPEG up to 2 MB. Leave empty to use the built-in mark.",
  "settings.branding.landingHeading": "Public landing page",
  "settings.branding.landingNote":
    "Operator only — these shape the public landing every visitor sees before signing in.",
  "settings.branding.tagline": "Tagline",
  "settings.branding.heroTitle": "Hero headline",
  "settings.branding.heroSubtitle": "Hero subtitle",
  "settings.branding.heroBackground": "Hero background image",
  "settings.branding.heroBackgroundHint":
    "Upload a PNG or JPEG up to 8 MB. The image is dimmed so text stays readable.",
  "settings.branding.upload": "Upload image",
  "settings.branding.replace": "Replace image",
  "settings.branding.remove": "Remove image",
  "settings.branding.assetSaved": "Brand image updated",
  "settings.branding.assetRemoved": "Brand image removed",

  // Toasts
  "settings.toast.saved": "Settings saved",
};
export default messages;
