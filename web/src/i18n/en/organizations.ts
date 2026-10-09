const messages: Record<string, string> = {
  "organizations.title": "Organizations",
  "organizations.subtitle":
    "Each organization is an isolated workspace with its own projects, sites, and recipients.",
  "organizations.loading": "Loading organizations",
  "organizations.newOrganization": "New organization",

  "organizations.superadminRequired.title": "Operator access required",
  "organizations.superadminRequired.description":
    "Only the instance operator can create and manage organizations.",

  "organizations.empty.title": "No organizations yet",
  "organizations.empty.description":
    "Create an organization to hold a client's projects, sites, and recipients.",

  "organizations.memberCount.one": "{count} member",
  "organizations.memberCount.other": "{count} members",
  "organizations.siteCount.one": "{count} site",
  "organizations.siteCount.other": "{count} sites",

  "organizations.state.active": "Active",
  "organizations.state.inactive": "Inactive",
  "organizations.state.suspended": "Suspended",
  "organizations.usage.sites": "Sites {used}/{limit}",
  "organizations.usage.members": "Members {used}/{limit}",
  "organizations.usage.ai": "AI/mo {used}/{limit}",
  "organizations.billing.managed": "Billing managed",
  "organizations.billing.suspended": "Suspended by billing",
  "organizations.billing.managedHint":
    "The payment provider owns this plan and its limits. Change the subscription through billing controls.",
  "organizations.billing.suspendedHint":
    "Access can only be restored by a current subscription event from the payment provider.",
  "organizations.yours": "Your organization",

  "organizations.enter": "Manage",
  "organizations.managing": "Managing {name} — projects, sites and people you add belong to it",
  "organizations.exit": "Exit organization",

  "organizations.created": "Organization created",
  "organizations.updated": "Organization updated",

  "organizations.field.name": "Name",
  "organizations.field.active": "Active",
  "organizations.field.activeHint":
    "Suspension locks members out while preserving customer data, audit records, and billing history.",
  "organizations.field.plan": "Plan",
  "organizations.field.planHint": "A label for the billing plan, e.g. free, starter, business.",
  "organizations.field.maxSites": "Site limit",
  "organizations.field.maxMembers": "Member limit",
  "organizations.field.aiLimit": "AI checks / month",
  "organizations.field.limitHint": "Leave blank for no limit.",
  "organizations.field.planSelect": "Plan (from catalog)",
  "organizations.field.planSelectHint": "Assigning a plan fills the caps below; you can still override them.",
  "organizations.field.noPlan": "No plan (set caps manually)",

  "organizations.create.title": "New organization",
  "organizations.create.description":
    "Projects, sites, and recipients you add will belong to this organization.",
  "organizations.create.namePlaceholder": "Acme Corp",
  "organizations.create.submit": "Create organization",
  "organizations.create.confirmTitle": "Confirm organization creation",
  "organizations.create.confirmDescription":
    "Re-authenticate before provisioning a new isolated customer workspace.",

  "organizations.edit.title": "Edit organization",
  "organizations.edit.submit": "Save changes",
  "organizations.edit.confirmTitle": "Confirm entitlement change",
  "organizations.edit.confirmDescription":
    "Suspension is reversible and preserves customer records. Other entitlement changes can affect service and cost immediately.",
  "organizations.openAria": "Open {name}",
  "organizations.editAria": "Rename {name}",
};
export default messages;
