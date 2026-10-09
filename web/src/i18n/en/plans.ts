const messages: Record<string, string> = {
  "plans.title": "Entitlement templates",
  "plans.subtitle":
    "Define internal resource caps that an operator can assign to organizations.",
  "plans.loading": "Loading entitlement templates",
  "plans.newPlan": "New template",

  "plans.hold.title": "Self-service release controls",
  "plans.hold.description":
    "Publish only after an active provider price is verified. Archiving removes a plan from new purchases; it does not cancel subscriptions or change Stripe.",

  "plans.empty.title": "No entitlement templates yet",
  "plans.empty.description": "Create an internal template with explicit resource caps.",

  "plans.card.sites": "Sites",
  "plans.card.members": "Members",
  "plans.card.aiChecks": "AI checks / mo",
  "plans.card.unlimited": "Unlimited",
  "plans.card.auto": "Reference estimate from the cost model",
  "plans.card.algorithm": "Cost model: {amount}",
  "plans.card.referenceEstimate": "Internal monthly estimate",
  "plans.card.operatorAssigned": "Operator assigned",
  "plans.card.selfServePublished": "Publication enabled",
  "plans.card.selfServeArchived": "Publication disabled",
  "plans.card.inactive": "Inactive",
  "plans.editAria": "Edit {name}",
  "plans.deleteAria": "Delete {name}",
  "plans.publish.action": "Publish",
  "plans.archive.action": "Archive",
  "plans.publish.unavailable": "Register an active provider price before publishing this plan.",
  "plans.publish.inactive": "Activate this entitlement template before publishing it.",
  "plans.publish.priceUnknown": "Reload provider price mappings before publishing this plan.",
  "plans.publish.title": "Publish {name} for new purchases?",
  "plans.publish.description":
    "The plan will enter the self-service catalog only when the global billing and legal launch gates are ready. This does not create or modify a Stripe price.",
  "plans.publish.confirmTitle": "Confirm plan publication",
  "plans.publish.confirmDescription":
    "Re-authenticate before making {name} eligible for new self-service purchases.",
  "plans.publish.success": "Plan publication enabled",
  "plans.publish.error.notReady":
    "This deployment's billing, webhook or legal launch gates are not ready. The plan was not published.",
  "plans.publish.error.action": "The publication state could not be changed. Refresh and try again.",
  "plans.archive.title": "Archive {name} from new purchases?",
  "plans.archive.description":
    "The plan will leave the self-service catalog. Existing subscriptions and the corresponding Stripe price remain unchanged.",
  "plans.archive.confirmTitle": "Confirm plan archival",
  "plans.archive.confirmDescription":
    "Re-authenticate before removing {name} from new self-service purchases.",
  "plans.archive.success": "Plan publication disabled",

  // Versioned provider price mappings
  "plans.billing.title": "Provider price mappings",
  "plans.billing.subtitle":
    "Link externally created Stripe prices to immutable entitlement terms. A new mapping retires the previous local version for that plan.",
  "plans.billing.new": "Register price version",
  "plans.billing.loading": "Loading provider price mappings",
  "plans.billing.loadError": "Provider price mappings could not be loaded.",
  "plans.billing.empty.title": "No provider prices registered",
  "plans.billing.empty.description":
    "Create the recurring price in Stripe first, then register its exact terms here.",
  "plans.billing.column.plan": "Plan",
  "plans.billing.column.providerId": "Stripe price ID",
  "plans.billing.column.amount": "Amount",
  "plans.billing.column.interval": "Billing interval",
  "plans.billing.column.state": "Local state",
  "plans.billing.column.created": "Registered",
  "plans.billing.version": "Version {version}",
  "plans.billing.active": "Active mapping",
  "plans.billing.retired": "Retired",
  "plans.billing.unknownPlan": "Deleted plan #{id}",
  "plans.billing.dialog.title": "Register a Stripe price",
  "plans.billing.dialog.description":
    "This verifies and stores an existing Stripe price. It does not create, update, activate or archive anything in Stripe.",
  "plans.billing.field.plan": "Entitlement plan",
  "plans.billing.field.provider": "Provider",
  "plans.billing.field.providerPriceId": "Stripe price ID",
  "plans.billing.field.providerPriceIdHint": "Use the exact recurring Price ID, for example price_123.",
  "plans.billing.field.amount": "Exact recurring amount",
  "plans.billing.field.amountHint": "Must match the amount already configured in Stripe.",
  "plans.billing.field.currency": "Currency",
  "plans.billing.field.interval": "Recurring interval",
  "plans.billing.field.intervalCount": "Interval count",
  "plans.billing.interval.day": "Day",
  "plans.billing.interval.week": "Week",
  "plans.billing.interval.month": "Month",
  "plans.billing.interval.year": "Year",
  "plans.billing.register": "Verify and register",
  "plans.billing.confirmTitle": "Confirm provider price mapping",
  "plans.billing.confirmDescription":
    "Re-authenticate before verifying the Stripe price and activating a new local mapping version. Any current local version will be retired.",
  "plans.billing.created": "Provider price version registered",
  "plans.billing.error.conflict":
    "The price was not registered. Confirm that the Stripe price and product are active, the ID is unique, and the amount, currency and recurrence match exactly.",
  "plans.billing.error.provider":
    "Stripe could not be verified right now. No local price version was created.",
  "plans.billing.error.stalePlan":
    "The selected entitlement plan no longer exists. Close this dialog, refresh and choose another plan.",
  "plans.billing.error.action": "The provider price version could not be registered.",

  // Internal cost model
  "plans.pricing.title": "Internal cost model",
  "plans.pricing.subtitle":
    "Planning only. These values do not charge a customer or activate an entitlement.",
  "plans.pricing.baseFee": "Reference base amount",
  "plans.pricing.perSiteFee": "Reference amount per site",
  "plans.pricing.aiMargin": "AI cost multiplier",
  "plans.pricing.aiMarginHint": "Multiplier applied to raw OpenAI cost for internal planning.",
  "plans.pricing.currency": "Currency",
  "plans.pricing.save": "Save cost model",
  "plans.pricing.saved": "Cost model saved",
  "plans.pricing.confirmTitle": "Confirm cost model change",
  "plans.pricing.confirmDescription":
    "Re-authenticate before changing the platform-wide reference values used for internal pricing estimates.",
  "plans.pricing.derived":
    "On {model}, one AI check costs about {cost} — from a real average of {prompt} + {completion} tokens.",

  // Create / edit dialog
  "plans.create.title": "New entitlement template",
  "plans.edit.title": "Edit entitlement template",
  "plans.field.name": "Name",
  "plans.field.key": "Key",
  "plans.field.keyHint": "Short lowercase identifier, e.g. starter.",
  "plans.field.maxSites": "Site limit",
  "plans.field.maxMembers": "Member limit",
  "plans.field.aiLimit": "AI checks / month",
  "plans.field.limitHint": "Leave blank for unlimited.",
  "plans.field.price": "Reference monthly estimate",
  "plans.field.priceHint": "Planning only. Leave blank to use the cost-model estimate of {amount}.",
  "plans.field.priceHintPlain": "Planning only. Leave blank to use the cost-model estimate.",
  "plans.field.active": "Active",
  "plans.field.activeHint": "Inactive templates cannot be assigned to new organizations.",
  "plans.field.useSuggestion": "Use estimate {amount}",
  "plans.save": "Save template",
  "plans.change.confirmTitle": "Confirm entitlement template change",
  "plans.change.confirmDescription":
    "Re-authenticate before changing templates that control customer resource limits.",
  "plans.created": "Entitlement template created",
  "plans.updated": "Entitlement template updated",
  "plans.deleted": "Entitlement template deleted",

  "plans.delete.title": "Delete this entitlement template?",
  "plans.delete.description":
    "{name} will be removed. Templates with billing history must be archived instead; assigned organizations keep their current caps.",
  "plans.delete.submit": "Delete template",
  "plans.delete.confirmTitle": "Confirm template deletion",
  "plans.delete.confirmDescription":
    "Re-authenticate before deleting {name}. Published templates cannot be deleted and must be archived instead.",

  // Public access-availability page
  "plans.public.eyebrow": "Access availability",
  "plans.public.setupEyebrow": "Your own installation",
  "plans.public.setupTitle": "You manage your monitoring workspace",
  "plans.public.setupSubtitle": "Run Driftwatch on your own computer or server. Create the administrator account to configure monitoring and invite your team.",
  "plans.public.setupStatusTitle": "The first account administers this installation",
  "plans.public.setupNote": "You provide the hosting and choose any optional notification or AI services. Their costs depend on your own providers and settings.",
  "plans.public.title": "Paid plans are not available for self-service",
  "plans.public.subtitle":
    "Driftwatch does not currently accept payment or activate paid access from public registration.",
  "plans.public.cta": "Create limited workspace",
  "plans.public.closedTitle": "Workspace access is currently invite-only",
  "plans.public.closedSubtitle":
    "Public account creation is closed. Sign in with an existing account or contact the operator responsible for your workspace.",
  "plans.public.closedStatusTitle": "Operator-managed onboarding",
  "plans.public.closedStatusBody":
    "New workspaces and administrators are provisioned deliberately instead of being created from an anonymous form.",
  "plans.public.closedManualNote":
    "Public registration remains closed until the verification, legal and billing launch gates are ready.",
  "plans.public.statusTitle": "Bounded free access, not a paid plan",
  "plans.public.statusBody":
    "Every public registration receives the same limited workspace. A plan name or URL parameter cannot increase its resources.",
  "plans.public.manualNote":
    "Additional access is unavailable through self-service and requires operator review.",
  "plans.public.defaultSites": "Monitored site limit",
  "plans.public.defaultMembers": "Team member limit",
  "plans.public.defaultAi": "Monthly AI-check limit",
  "plans.public.backHome": "Back to home",
};
export default messages;
