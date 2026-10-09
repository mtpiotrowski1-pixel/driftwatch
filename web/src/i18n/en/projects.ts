const messages: Record<string, string> = {
  "projects.title": "Projects",
  "projects.subtitle": "Group sites so they share prompts, notification policy, and recipients.",
  "projects.newProject": "New project",
  "projects.loading": "Loading projects",

  "projects.empty.title": "No projects yet",
  "projects.empty.description": "Create a project to apply shared rules across a set of sites.",

  "projects.siteCount.one": "{count} site",
  "projects.siteCount.other": "{count} sites",
  "projects.recipientCount.one": "{count} recipient",
  "projects.recipientCount.other": "{count} recipients",

  "projects.mode.only_significant": "Only significant",
  "projects.mode.always": "Every change",
  "projects.mode.inherited": "Inherited",

  "projects.exportExcel": "Export to Excel",
  "projects.deleteAria": "Delete {name}",
  "projects.openAria": "Open {name}",
  "projects.editAria": "Edit {name}",

  "projects.create.title": "New project",
  "projects.create.namePlaceholder": "Competitors",
  "projects.create.submit": "Create project",
  "projects.created": "Project created",

  "projects.edit.title": "Edit project",
  "projects.field.name": "Name",
  "projects.field.notifications": "Notifications",
  "projects.notifications.inherit": "Inherit from global",
  "projects.notifications.only_significant": "Only significant changes",
  "projects.notifications.always": "Every change",
  "projects.field.rules": "AI importance rules",
  "projects.field.rulesHint": "Optional. Applies to every site in this project unless overridden.",
  "projects.field.rulesPlaceholder": "Flag pricing and availability changes.",
  "projects.field.recipients": "Recipients",
  "projects.noRecipients": "No recipients yet.",
  "projects.edit.submit": "Save project",
  "projects.updated": "Project updated",

  "projects.delete.title": "Delete this project?",
  "projects.delete.description":
    "Sites in this project are kept but will no longer inherit its rules.",
  "projects.delete.submit": "Delete project",
  "projects.deleted": "Project deleted",

  "projects.detail.back": "All projects",
  "projects.detail.addSite": "Add site here",
  "projects.detail.sites": "Sites",
  "projects.detail.notFound.title": "Project not found",
  "projects.detail.notFound.description": "It may have been deleted or belongs to another organization.",
  "projects.detail.empty.title": "No sites in this project yet",
  "projects.detail.empty.description": "Add the first site to start watching it here.",
};
export default messages;
