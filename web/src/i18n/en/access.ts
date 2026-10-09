const messages: Record<string, string> = {
  "access.title": "Access",
  "access.subtitle": "Manage who can sign in and which projects and sites they can see.",
  "access.loading": "Loading access",
  "access.addUser": "Add user",

  "access.adminRequired.title": "Administrator access required",
  "access.adminRequired.description":
    "Only administrators can manage who has access to this workspace.",

  "access.instance.subtitle": "Instance-level identity boundary",
  "access.instance.title": "Operator identities are deployment-managed",
  "access.instance.description":
    "Operator accounts are provisioned through the controlled deployment procedure, not from a tenant access page. Enter an organization to manage its users.",
  "access.instance.action": "Open organizations",

  "access.operators.title": "Operator identities",
  "access.operators.subtitle":
    "Manage the small set of accounts that can operate the whole instance. Tenant users remain isolated inside their organizations.",
  "access.operators.loading": "Loading operator identities",
  "access.operators.add": "Add operator",
  "access.operators.empty.title": "No operator identities",
  "access.operators.empty.description":
    "Create a recovery operator before this instance is used in production.",
  "access.operators.self": "You",
  "access.operators.state.active": "Active",
  "access.operators.state.inactive": "Inactive",
  "access.operators.mfa.active": "2FA active",
  "access.operators.mfa.pending": "2FA not enrolled",
  "access.operators.firstLoginPending": "First sign-in pending",
  "access.operators.lastLogin": "Last sign-in: {date}",
  "access.operators.invite": "Send setup link",
  "access.operators.deactivate": "Deactivate",
  "access.operators.reactivate": "Reactivate",
  "access.operators.create.title": "Add operator",
  "access.operators.create.description":
    "This account can operate every organization. A single-use password setup link will be queued.",
  "access.operators.create.submit": "Create operator",
  "access.operators.edit.title": "Edit operator",
  "access.operators.edit.submit": "Save operator",
  "access.operators.confirm.createTitle": "Confirm operator creation",
  "access.operators.confirm.createDescription":
    "Creating an instance operator grants the highest application privilege.",
  "access.operators.confirm.editTitle": "Confirm operator changes",
  "access.operators.confirm.editDescription":
    "Changing {email} affects an instance-level identity.",
  "access.operators.confirm.inviteTitle": "Queue a new setup link?",
  "access.operators.confirm.inviteDescription":
    "A new single-use password setup link will be queued for {email}.",
  "access.operators.confirm.deactivateTitle": "Deactivate this operator?",
  "access.operators.confirm.deactivateDescription":
    "{email} will lose access immediately and all existing sessions will be revoked.",
  "access.operators.confirm.reactivateTitle": "Reactivate this operator?",
  "access.operators.confirm.reactivateDescription":
    "{email} will regain instance access and must satisfy the current 2FA policy.",
  "access.operators.toast.created": "Operator created; setup link queued",
  "access.operators.toast.updated": "Operator updated",
  "access.operators.toast.inviteQueued": "Setup link queued",
  "access.operators.toast.deactivated": "Operator deactivated",
  "access.operators.toast.reactivated": "Operator reactivated",
  "access.operators.error": "Could not update the operator",

  "access.empty.title": "No users yet",
  "access.empty.description": "Add a teammate so they can sign in to Driftwatch.",

  "access.role.superadmin": "Operator",
  "access.role.admin": "Admin",
  "access.role.member": "Member",
  "access.state.active": "Active",
  "access.state.inactive": "Inactive",

  "access.editAria": "Edit {email}",
  "access.userUpdated": "User updated",
  "access.editError": "Could not save the changes",
  "access.edit.title": "Edit user",
  "access.edit.submit": "Save changes",
  "access.field.activeUser": "Active",
  "access.field.activeUserHint": "Inactive users cannot sign in.",
  "access.deleteAria": "Delete {email}",

  "access.userAdded": "Invitation queued",
  "access.userRemoved": "User removed",

  "access.create.title": "Add user",
  "access.create.description":
    "We will email a secure link so they can set their own password. The link is valid for 24 hours.",
  "access.field.email": "Email",
  "access.field.emailPlaceholder": "teammate@company.com",
  "access.field.name": "Name",
  "access.field.nameHint": "Optional",
  "access.field.namePlaceholder": "Jordan Lee",
  "access.field.administrator": "Administrator",
  "access.field.administratorHint": "Admins have full access and can manage other users.",
  "access.create.submit": "Send invitation",

  "access.field.projects": "Projects",
  "access.field.sites": "Sites",
  "access.noProjects": "No projects yet.",
  "access.noSites": "No sites yet.",

  "access.delete.title": "Remove this user?",
  "access.delete.description": "{email} will lose access immediately.",
  "access.delete.submit": "Remove user",
  "access.stepup.createTitle": "Confirm account invitation",
  "access.stepup.createDescription":
    "Creating an account grants access to workspace data. Confirm with your current password.",
  "access.stepup.editTitle": "Confirm sensitive account changes",
    "access.stepup.editDescription":
      "Changing identity, role, status, or grants requires recent authentication.",
    "access.security.title": "Account security",
    "access.security.description": "Respond to a lost device or a potentially exposed session.",
    "access.security.sendInvitation": "Send password link",
    "access.security.sendInvitationTitle": "Send a new password link?",
    "access.security.sendInvitationDescription":
      "We will email {email} a single-use link that is valid for 24 hours.",
    "access.security.invitationSent": "Password link queued",
    "access.security.revokeSessions": "Revoke sessions",
    "access.security.revokeSessionsTitle": "Revoke all sessions?",
    "access.security.revokeSessionsDescription":
      "{email} will be signed out on every device and must authenticate again.",
    "access.security.sessionsRevokedDone": "All sessions revoked",
    "access.security.resetTotp": "Reset two-factor",
    "access.security.resetTotpTitle": "Reset two-factor authentication?",
    "access.security.resetTotpDescription":
      "{email} will lose the current authenticator and recovery codes, and will be signed out everywhere.",
    "access.security.totpResetDone": "Two-factor authentication reset",
  };
export default messages;
