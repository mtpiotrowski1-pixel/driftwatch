import { errorMessage } from "@/lib/errors";
import { useDialogState } from "@/lib/useDialogState";
import {
  LogOut,
  Mail,
  Pencil,
  ShieldOff,
  ShieldX,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import { OperatorIdentities } from "@/components/operators/OperatorIdentities";
import { StepUpDialog } from "@/components/StepUpDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, type DialogVisibilityProps } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, ErrorState, PageLoader, Spinner } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import {
  ApiError,
  instanceRequestContext,
  organizationRequestContext,
  type ApiRequestContext,
} from "@/lib/api";
import { useInOrgContext, useOrg } from "@/lib/orgContext";
import {
  useCreateUser,
  useCurrentUser,
  useDeleteUser,
  useInviteUser,
  useOrganizations,
  useProjects,
  useResetUserTotp,
  useRevokeUserSessions,
  useSetPermissions,
  useSites,
  useUpdateUser,
  useUsers,
} from "@/lib/queries";
import type { UserDetail } from "@/lib/types";

export function UsersPage() {
  const t = useT();
  const { data: currentUser, isLoading: meLoading } = useCurrentUser();
  const isSuperadmin = currentUser?.is_superadmin ?? false;
  const hasOrgContext = useInOrgContext();
  const { actingOrg } = useOrg();
  const organizationId = isSuperadmin
    ? actingOrg?.id ?? null
    : currentUser?.organization_id ?? null;
  const organizationContext = organizationId === null
    ? null
    : organizationRequestContext(organizationId);
  const inOrg = Boolean(currentUser && hasOrgContext && organizationContext);
  const users = useUsers(inOrg, organizationContext ?? instanceRequestContext);
  // The operator labels each user with its org; org-admins see only their own.
  const organizations = useOrganizations(isSuperadmin && inOrg);
  const { notify } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const editingDialog = useDialogState<UserDetail | null>(null);
  const { value: editing, setValue: setEditing } = editingDialog;
  const [deleting, setDeleting] = useState<UserDetail | null>(null);

  if (meLoading || (inOrg && users.isLoading)) {
    return <PageLoader label={t("access.loading")} />;
  }

  if (!(currentUser?.is_admin || currentUser?.is_superadmin)) {
    return (
      <EmptyState
        icon={<ShieldOff className="h-5 w-5" />}
        title={t("access.adminRequired.title")}
        description={t("access.adminRequired.description")}
      />
    );
  }

  if (isSuperadmin && !inOrg) {
    return <OperatorIdentities currentUserId={currentUser.id} />;
  }

  if (users.isError) return <ErrorState onRetry={() => users.refetch()} />;

  const userList = users.data ?? [];
  const orgNames = new Map((organizations.data ?? []).map((org) => [org.id, org.name]));
  const addButton = inOrg ? (
    <Button onClick={() => setCreateOpen(true)}>
      <UserPlus className="h-4 w-4" />
      {t("access.addUser")}
    </Button>
  ) : undefined;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-100">
            {t("access.title")}
          </h1>
          <p className="mt-1 text-sm text-mist-400">{t("access.subtitle")}</p>
        </div>
        {addButton}
      </header>

      {userList.length === 0 ? (
        <EmptyState
          icon={<Users className="h-5 w-5" />}
          title={t("access.empty.title")}
          description={t("access.empty.description")}
          action={addButton}
        />
      ) : (
        <Card>
          <ul className="divide-y divide-line">
            {userList.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                isSelf={user.id === currentUser.id}
                orgName={
                  isSuperadmin && user.organization_id != null
                    ? orgNames.get(user.organization_id)
                    : undefined
                }
                onEdit={() => setEditing(user)}
                onDelete={() => setDeleting(user)}
              />
            ))}
          </ul>
        </Card>
      )}

      <CreateUserDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        requestContext={organizationContext ?? instanceRequestContext}
        onCreated={() => {
          setCreateOpen(false);
          notify(t("access.userAdded"));
        }}
      />

      {editing ? (
        <EditUserDialog
          key={editingDialog.key}
          open={editingDialog.open}
          onClosed={editingDialog.onClosed}
          user={editing}
          isSelf={editing.id === currentUser.id}
          requestContext={organizationContext ?? instanceRequestContext}
          onClose={editingDialog.close}
          onSaved={() => {
            setEditing(null);
            notify(t("access.userUpdated"));
          }}
        />
      ) : null}

      {deleting ? (
        <DeleteUserDialog
          user={deleting}
          requestContext={organizationContext ?? instanceRequestContext}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null);
            notify(t("access.userRemoved"));
          }}
        />
      ) : null}
    </div>
  );
}

function RoleBadge({ user }: { user: UserDetail }) {
  const t = useT();
  if (user.is_superadmin) return <Badge tone="brand">{t("access.role.superadmin")}</Badge>;
  if (user.is_admin) return <Badge tone="amber">{t("access.role.admin")}</Badge>;
  return <Badge tone="neutral">{t("access.role.member")}</Badge>;
}

function UserRow({
  user,
  isSelf,
  orgName,
  onEdit,
  onDelete,
}: {
  user: UserDetail;
  isSelf: boolean;
  orgName?: string;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const t = useT();

  return (
    <li className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <button
        type="button"
        onClick={onEdit}
        className="flex min-w-0 items-center gap-3 text-left"
        aria-label={t("access.editAria", { email: user.email })}
      >
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-300/35 text-sm font-semibold text-brand-700">
          {(user.name ?? user.email).slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-mist-100">{user.name ?? user.email}</p>
          <p className="truncate text-xs text-mist-500">{user.email}</p>
        </div>
      </button>
      <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:gap-3">
        {orgName ? (
          <Badge tone="neutral" className="hidden md:inline-flex">
            {orgName}
          </Badge>
        ) : null}
        <RoleBadge user={user} />
        <Badge tone={user.is_active ? "emerald" : "neutral"}>
          {user.is_active ? t("access.state.active") : t("access.state.inactive")}
        </Badge>
        <Button variant="secondary" size="sm" onClick={onEdit}>
          <Pencil className="h-3.5 w-3.5" />
          {t("common.edit")}
        </Button>
        {isSelf ? null : (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("access.deleteAria", { email: user.email })}
            onClick={onDelete}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </li>
  );
}

function CreateUserDialog({
  open,
  onOpenChange,
  requestContext,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  requestContext: ApiRequestContext;
  onCreated: () => void;
}) {
  const t = useT();
  const createUser = useCreateUser(requestContext);

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const error = createUser.error ? errorMessage(createUser.error, t) : null;

  function create() {
    createUser.mutate(
      { email: email.trim(), name: name.trim() || undefined, is_admin: isAdmin },
      {
        onSuccess: () => {
          setEmail("");
          setName("");
          setIsAdmin(false);
          onCreated();
        },
      },
    );
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setConfirming(true);
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
        title={t("access.create.title")}
        description={t("access.create.description")}
      >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label={t("access.field.email")} htmlFor="user-email">
          <Input
            id="user-email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={t("access.field.emailPlaceholder")}
          />
        </Field>
        <Field label={t("access.field.name")} hint={t("access.field.nameHint")} htmlFor="user-name">
          <Input
            id="user-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("access.field.namePlaceholder")}
          />
        </Field>
        <ToggleRow
          label={t("access.field.administrator")}
          hint={t("access.field.administratorHint")}
          checked={isAdmin}
          onChange={setIsAdmin}
        />
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={createUser.isPending}>
            {createUser.isPending ? <Spinner /> : null}
            {t("access.create.submit")}
          </Button>
        </div>
      </form>
      </Dialog>
      {confirming ? (
        <StepUpDialog
          title={t("access.stepup.createTitle")}
          description={t("access.stepup.createDescription")}
          submitLabel={t("access.create.submit")}
          requestContext={requestContext}
          onVerified={create}
          onClose={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}

function EditUserDialog({
  open,
  onClosed,
  user,
  isSelf,
  requestContext,
  onClose,
  onSaved,
}: {
  user: UserDetail;
  isSelf: boolean;
  requestContext: ApiRequestContext;
  onClose: () => void;
  onSaved: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const { notify } = useToast();
  const projects = useProjects();
  const sites = useSites();
  const updateUser = useUpdateUser(user.id, requestContext);
  const inviteUser = useInviteUser(user.id, requestContext);
  const setPermissions = useSetPermissions(user.id, requestContext);
  const revokeSessions = useRevokeUserSessions(user.id, requestContext);
  const resetTotp = useResetUserTotp(user.id, requestContext);

  const [email, setEmail] = useState(user.email);
  const [name, setName] = useState(user.name ?? "");
  const [isAdmin, setIsAdmin] = useState(user.is_admin);
  const [isActive, setIsActive] = useState(user.is_active);
  const [projectIds, setProjectIds] = useState<number[]>(user.project_ids);
  const [siteIds, setSiteIds] = useState<number[]>(user.site_ids);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [securityAction, setSecurityAction] = useState<
    "invite" | "revoke" | "reset-totp" | null
  >(null);

  // The operator role is granted at the database level; a user cannot change
  // their own role or status. Grants apply only to plain members.
  const canManageRole = !isSelf && !user.is_superadmin;
  const showPermissions = canManageRole && !isAdmin;
  const pending =
    updateUser.isPending ||
    inviteUser.isPending ||
    setPermissions.isPending ||
    revokeSessions.isPending ||
    resetTotp.isPending;

  function toggle(set: typeof setProjectIds, id: number) {
    set((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }

  const permissionsChanged =
    projectIds.length !== user.project_ids.length ||
    siteIds.length !== user.site_ids.length ||
    projectIds.some((id) => !user.project_ids.includes(id)) ||
    siteIds.some((id) => !user.site_ids.includes(id));

  async function save() {
    setError(null);
    try {
      await updateUser.mutateAsync({
        email: email.trim(),
        name: name.trim() || null,
        ...(canManageRole ? { is_admin: isAdmin } : {}),
        ...(isSelf ? {} : { is_active: isActive }),
      });
      if (showPermissions && permissionsChanged) {
        await setPermissions.mutateAsync({ project_ids: projectIds, site_ids: siteIds });
      }
      onSaved();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("access.editError"));
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const sensitiveChange =
      email.trim().toLowerCase() !== user.email.toLowerCase() ||
      (canManageRole && isAdmin !== user.is_admin) ||
      (!isSelf && isActive !== user.is_active) ||
      (showPermissions && permissionsChanged);
    if (sensitiveChange) {
      setConfirming(true);
      return;
    }
    void save();
  }

  function runSecurityAction() {
    const action = securityAction;
    const mutation =
      action === "invite" ? inviteUser : action === "reset-totp" ? resetTotp : revokeSessions;
    mutation.mutate(undefined, {
      onSuccess: () => {
        notify(
          t(
            action === "invite"
              ? "access.security.invitationSent"
              : action === "reset-totp"
              ? "access.security.totpResetDone"
              : "access.security.sessionsRevokedDone",
          ),
        );
        setSecurityAction(null);
      },
      onError: (caught) => {
        setError(caught instanceof ApiError ? caught.message : t("access.editError"));
      },
    });
  }

  return (
    <>
      <Dialog
        open={open} onClosed={onClosed}
        onOpenChange={(open) => !open && onClose()}
        title={t("access.edit.title")}
        description={user.email}
      >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label={t("access.field.email")} htmlFor="edit-user-email">
          <Input
            id="edit-user-email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>
        <Field label={t("access.field.name")} htmlFor="edit-user-name">
          <Input
            id="edit-user-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("access.field.namePlaceholder")}
          />
        </Field>
        {!isSelf ? (
          <div className="space-y-3 border-t border-line pt-4">
            <div>
              <p className="text-sm font-semibold text-mist-200">
                {t("access.security.title")}
              </p>
              <p className="mt-1 text-xs text-mist-500">
                {t("access.security.description")}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setSecurityAction("invite")}
              >
                <Mail className="h-4 w-4" />
                {t("access.security.sendInvitation")}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setSecurityAction("revoke")}
              >
                <LogOut className="h-4 w-4" />
                {t("access.security.revokeSessions")}
              </Button>
              {user.totp_enabled ? (
                <Button
                  type="button"
                  variant="danger"
                  onClick={() => setSecurityAction("reset-totp")}
                >
                  <ShieldX className="h-4 w-4" />
                  {t("access.security.resetTotp")}
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}

        {canManageRole ? (
          <ToggleRow
            label={t("access.field.administrator")}
            hint={t("access.field.administratorHint")}
            checked={isAdmin}
            onChange={setIsAdmin}
          />
        ) : null}
        {isSelf ? null : (
          <ToggleRow
            label={t("access.field.activeUser")}
            hint={t("access.field.activeUserHint")}
            checked={isActive}
            onChange={setIsActive}
          />
        )}

        {showPermissions ? (
          <>
            <GrantList
              label={t("access.field.projects")}
              empty={t("access.noProjects")}
              items={(projects.data ?? []).map((project) => ({
                id: project.id,
                label: project.name,
              }))}
              selected={projectIds}
              onToggle={(id) => toggle(setProjectIds, id)}
            />
            <GrantList
              label={t("access.field.sites")}
              empty={t("access.noSites")}
              items={(sites.data ?? []).map((site) => ({
                id: site.id,
                label: site.name ?? site.url,
              }))}
              selected={siteIds}
              onToggle={(id) => toggle(setSiteIds, id)}
            />
          </>
        ) : null}

        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? <Spinner /> : null}
            {t("access.edit.submit")}
          </Button>
        </div>
      </form>
      </Dialog>
      {open && confirming ? (
        <StepUpDialog
          title={t("access.stepup.editTitle")}
          description={t("access.stepup.editDescription")}
          submitLabel={t("access.edit.submit")}
          requestContext={requestContext}
          onVerified={() => void save()}
          onClose={() => setConfirming(false)}
        />
      ) : null}
      {open && securityAction ? (
        <StepUpDialog
          title={t(
            securityAction === "invite"
              ? "access.security.sendInvitationTitle"
              : securityAction === "reset-totp"
              ? "access.security.resetTotpTitle"
              : "access.security.revokeSessionsTitle",
          )}
          description={t(
            securityAction === "invite"
              ? "access.security.sendInvitationDescription"
              : securityAction === "reset-totp"
              ? "access.security.resetTotpDescription"
              : "access.security.revokeSessionsDescription",
            { email: user.email },
          )}
          submitLabel={t(
            securityAction === "invite"
              ? "access.security.sendInvitation"
              : securityAction === "reset-totp"
              ? "access.security.resetTotp"
              : "access.security.revokeSessions",
          )}
          submitVariant={securityAction === "invite" ? "primary" : "danger"}
          requestContext={requestContext}
          onVerified={runSecurityAction}
          onClose={() => setSecurityAction(null)}
        />
      ) : null}
    </>
  );
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-line bg-ink-900/50 px-3.5 py-3">
      <div>
        <p className="text-sm font-medium text-mist-300">{label}</p>
        <p className="text-xs text-mist-500">{hint}</p>
      </div>
      <Switch aria-label={label} checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

function GrantList({
  label,
  empty,
  items,
  selected,
  onToggle,
}: {
  label: string;
  empty: string;
  items: { id: number; label: string }[];
  selected: number[];
  onToggle: (id: number) => void;
}) {
  return (
    <Field label={label}>
      {items.length === 0 ? (
        <p className="text-sm text-mist-500">{empty}</p>
      ) : (
        <div className="max-h-44 space-y-2 overflow-y-auto pr-1">
          {items.map((item) => (
            <label
              key={item.id}
              className="flex cursor-pointer items-center gap-3 rounded-lg border border-line bg-ink-900/50 px-3.5 py-2.5 transition-colors hover:border-brand-500/40"
            >
              <input
                type="checkbox"
                className="h-4 w-4 accent-brand-500"
                checked={selected.includes(item.id)}
                onChange={() => onToggle(item.id)}
              />
              <span className="min-w-0 truncate text-sm text-mist-100">{item.label}</span>
            </label>
          ))}
        </div>
      )}
    </Field>
  );
}

function DeleteUserDialog({
  user,
  requestContext,
  onClose,
  onDeleted,
}: {
  user: UserDetail;
  requestContext: ApiRequestContext;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const t = useT();
  const deleteUser = useDeleteUser(requestContext);
  const { notify } = useToast();

  function handleDelete() {
    deleteUser.mutate(user.id, {
      onSuccess: onDeleted,
      onError: (error) => {
        if (error instanceof ApiError) notify(error.message, "error");
      },
    });
  }

  return (
    <StepUpDialog
      title={t("access.delete.title")}
      description={t("access.delete.description", { email: user.email })}
      submitLabel={t("access.delete.submit")}
      submitVariant="danger"
      requestContext={requestContext}
      onVerified={handleDelete}
      onClose={onClose}
    />
  );
}
