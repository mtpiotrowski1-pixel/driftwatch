import { errorMessage } from "@/lib/errors";
import { useDialogState } from "@/lib/useDialogState";
import { CalendarClock, Mail, Pencil, Trash2, UserPlus, Users } from "lucide-react";
import { useState, type FormEvent } from "react";

import { EmptyStateArtwork } from "@/components/brand/EmptyStateArtwork";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, type DialogVisibilityProps } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, ErrorState, PageLoader, Spinner } from "@/components/ui/feedback";
import { Field, Input, Label, Select } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useT, useTp } from "@/i18n";
import { useInOrgContext } from "@/lib/orgContext";
import { canManageRecipient } from "@/lib/capabilities";
import {
  useAddSubstitution,
  useCreateRecipient,
  useCurrentUser,
  useDeleteRecipient,
  useDeleteSubstitution,
  useProjects,
  useRecipients,
  useSites,
  useSubstitutions,
  useUpdateRecipient,
} from "@/lib/queries";
import type { Recipient, Substitution } from "@/lib/types";

export function Recipients() {
  const recipients = useRecipients();
  const sites = useSites();
  const projects = useProjects();
  const { data: user } = useCurrentUser();
  const createRecipient = useCreateRecipient();
  const deleteRecipient = useDeleteRecipient();
  const inOrg = useInOrgContext();
  const { notify } = useToast();
  const t = useT();
  const tp = useTp();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const editingDialog = useDialogState<Recipient | null>(null);
  const { value: editing, setValue: setEditing } = editingDialog;
  const coveringDialog = useDialogState<Recipient | null>(null);
  const { value: covering, setValue: setCovering } = coveringDialog;
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const deletingDialog = useDialogState<Recipient | null>(null);
  const { value: deleting, setValue: setDeleting } = deletingDialog;

  const createError = createRecipient.error ? errorMessage(createRecipient.error, t) : null;

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    createRecipient.mutate(
      { email: email.trim(), name: name.trim() || undefined },
      {
        onSuccess: () => {
          setEmail("");
          setName("");
          setDialogOpen(false);
          notify(t("recipients.toast.added"));
        },
      },
    );
  }

  function handleDelete(id: number) {
    setPendingDeleteId(id);
    deleteRecipient.mutate(id, {
      onSuccess: () => { notify(t("recipients.toast.removed")); setDeleting(null); },
      onError: (error) => notify(errorMessage(error, t), "error"),
      onSettled: () => setPendingDeleteId(null),
    });
  }

  if (recipients.isLoading) return <PageLoader label={t("recipients.loading")} />;
  if (recipients.isError) return <ErrorState onRetry={() => recipients.refetch()} />;

  const recipientList = recipients.data ?? [];
  const siteList = sites.data ?? [];
  const projectList = projects.data ?? [];
  const canCreate = inOrg && !!user && (user.is_admin || user.is_superadmin || !!user.project_ids?.length || !!user.site_ids?.length);
  const effectiveSites = (recipientId: number) => siteList.filter((site) =>
    site.recipient_ids.includes(recipientId) || projectList.some((project) => project.id === site.project_id && project.recipient_ids.includes(recipientId)));
  const siteCount = (recipientId: number) =>
    effectiveSites(recipientId).length;
  const canManage = (recipientId: number) =>
    canManageRecipient(user, recipientId, siteList, projectList);

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-100">
            {t("recipients.title")}
          </h1>
          <p className="mt-1 text-sm text-mist-400">{t("recipients.subtitle")}</p>
        </div>
        {canCreate ? (
          <Button onClick={() => setDialogOpen(true)}>
            <UserPlus className="h-4 w-4" />
            {t("recipients.add")}
          </Button>
        ) : null}
      </header>

      {recipientList.length === 0 ? (
        <EmptyState
          icon={<Users className="h-5 w-5" />}
          visual={<EmptyStateArtwork variant="delivery" />}
          title={t("recipients.empty.title")}
          description={t("recipients.empty.description")}
          action={
            canCreate ? (
              <Button onClick={() => setDialogOpen(true)}>
                <UserPlus className="h-4 w-4" />
                {t("recipients.add")}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Card>
          <ul className="divide-y divide-line">
            {recipientList.map((recipient) => {
              const count = siteCount(recipient.id);
              return (
                <li
                  key={recipient.id}
                  className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-brand-300/35 text-brand-700">
                      <Mail className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-mist-100">
                        {recipient.name ?? recipient.email}
                      </p>
                      {recipient.name ? (
                        <p className="truncate text-xs text-mist-500">{recipient.email}</p>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:gap-3">
                    <Badge tone="neutral">{sites.isLoading || projects.isLoading || sites.isError || projects.isError ? "—" : tp("recipients.siteCount", count)}</Badge>
                    <Badge tone={recipient.active ? "emerald" : "neutral"}>
                      {recipient.active ? t("recipients.active") : t("recipients.inactive")}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("recipients.aria.manageCover", { email: recipient.email })}
                      onClick={() => setCovering(recipient)}
                      disabled={!canManage(recipient.id)}
                    >
                      <CalendarClock className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("recipients.aria.edit", { email: recipient.email })}
                      onClick={() => setEditing(recipient)}
                      disabled={!canManage(recipient.id)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("recipients.aria.remove", { email: recipient.email })}
                      onClick={() => setDeleting(recipient)}
                      disabled={!canManage(recipient.id) || deleteRecipient.isPending}
                    >
                      {deleteRecipient.isPending && pendingDeleteId === recipient.id ? (
                        <Spinner />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {deleting ? <DeleteRecipientDialog key={deletingDialog.key} open={deletingDialog.open} onClosed={deletingDialog.onClosed} recipient={deleting} onClose={deletingDialog.close} onDelete={() => handleDelete(deleting.id)} pending={deleteRecipient.isPending} /> : null}

      <Dialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={t("recipients.add")}
        description={t("recipients.dialog.description")}
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <Field label={t("recipients.field.email")} htmlFor="recipient-email">
            <Input
              id="recipient-email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t("recipients.placeholder.email")}
            />
          </Field>
          <Field
            label={t("recipients.field.name")}
            hint={t("recipients.field.optional")}
            htmlFor="recipient-name"
          >
            <Input
              id="recipient-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("recipients.placeholder.name")}
            />
          </Field>
          {createError ? <ErrorNote>{createError}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setDialogOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={createRecipient.isPending}>
              {t("recipients.add")}
            </Button>
          </div>
        </form>
      </Dialog>

      {editing ? (
        <EditRecipientDialog
          key={editingDialog.key}
          open={editingDialog.open}
          onClosed={editingDialog.onClosed}
          recipient={editing}
          onClose={editingDialog.close}
          onSaved={() => {
            setEditing(null);
            notify(t("recipients.toast.updated"));
          }}
        />
      ) : null}

      {covering ? (
        <SubstitutionsDialog key={coveringDialog.key} open={coveringDialog.open} onClosed={coveringDialog.onClosed} recipient={covering} onClose={coveringDialog.close} />
      ) : null}
    </div>
  );
}

function DeleteRecipientDialog({ open, onClosed, recipient, onClose, onDelete, pending }: { recipient: Recipient; onClose: () => void; onDelete: () => void; pending: boolean } & DialogVisibilityProps) {
  const t = useT();
  const sites = useSites();
  const projects = useProjects();
  const substitutions = useSubstitutions(recipient.id);
  const affectedProjects = (projects.data ?? []).filter((project) => project.recipient_ids.includes(recipient.id));
  const affectedSites = (sites.data ?? []).filter((site) => site.recipient_ids.includes(recipient.id) || affectedProjects.some((project) => project.id === site.project_id));
  const loading = sites.isLoading || projects.isLoading || substitutions.isLoading;
  const failed = sites.isError || projects.isError || substitutions.isError;
  return <Dialog open={open} onClosed={onClosed} onOpenChange={(open) => { if (!open && !pending) onClose(); }} title={t("recipients.delete.title")} description={recipient.email}>
    <div className="space-y-4">
      {loading ? <Spinner /> : failed ? <ErrorState onRetry={() => { void sites.refetch(); void projects.refetch(); void substitutions.refetch(); }} /> : <p className="text-sm text-mist-300">{t("recipients.delete.impact", { sites: affectedSites.length, projects: affectedProjects.length, substitutions: substitutions.data?.length ?? 0 })}</p>}
      <div className="flex justify-end gap-2"><Button variant="secondary" disabled={pending} onClick={onClose}>{t("common.cancel")}</Button><Button variant="danger" disabled={pending || loading || failed} onClick={onDelete}>{pending ? <Spinner /> : null}{t("common.delete")}</Button></div>
    </div>
  </Dialog>;
}

function EditRecipientDialog({
  open,
  onClosed,
  recipient,
  onClose,
  onSaved,
}: {
  recipient: Recipient;
  onClose: () => void;
  onSaved: () => void;
} & DialogVisibilityProps) {
  const update = useUpdateRecipient(recipient.id);
  const t = useT();
  const [name, setName] = useState(recipient.name ?? "");
  const [active, setActive] = useState(recipient.active);

  const error = update.error ? errorMessage(update.error, t) : null;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    update.mutate({ name: name.trim() || null, active }, { onSuccess: onSaved });
  }

  return (
    <Dialog
      open={open} onClosed={onClosed}
      onOpenChange={(open) => !open && onClose()}
      title={t("recipients.edit.title")}
      description={recipient.email}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field
          label={t("recipients.field.name")}
          hint={t("recipients.field.optional")}
          htmlFor="edit-recipient-name"
        >
          <Input
            id="edit-recipient-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <div className="flex items-center justify-between rounded-lg border border-line bg-ink-900/50 px-3.5 py-3">
          <div>
            <Label htmlFor="edit-recipient-active">{t("recipients.edit.activeLabel")}</Label>
            <p className="text-xs text-mist-500">{t("recipients.edit.activeHint")}</p>
          </div>
          <Switch id="edit-recipient-active" checked={active} onCheckedChange={setActive} />
        </div>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? <Spinner /> : null}
            {t("recipients.edit.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function SubstitutionsDialog({
  open,
  onClosed,
  recipient,
  onClose,
}: {
  recipient: Recipient;
  onClose: () => void;
} & DialogVisibilityProps) {
  const substitutions = useSubstitutions(recipient.id);
  const addSubstitution = useAddSubstitution(recipient.id);
  const deleteSubstitution = useDeleteSubstitution(recipient.id);
  const projects = useProjects();
  const sites = useSites();
  const { notify } = useToast();
  const t = useT();

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  // "all", or "project:<id>" / "site:<id>" — parsed into ids on submit.
  const [scope, setScope] = useState("all");
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);

  const addError = addSubstitution.error ? errorMessage(addSubstitution.error, t) : null;
  const items = substitutions.data ?? [];
  const projectName = (id: number) =>
    (projects.data ?? []).find((project) => project.id === id)?.name ?? `#${id}`;
  const siteLabel = (id: number) => {
    const site = (sites.data ?? []).find((candidate) => candidate.id === id);
    return site?.name || site?.url || `#${id}`;
  };

  function scopeLabel(substitution: Substitution): string {
    if (substitution.site_id !== null) {
      return t("recipients.cover.scope.site", { name: siteLabel(substitution.site_id) });
    }
    if (substitution.project_id !== null) {
      return t("recipients.cover.scope.project", { name: projectName(substitution.project_id) });
    }
    return t("recipients.cover.scope.all");
  }

  function handleAdd(event: FormEvent) {
    event.preventDefault();
    const [kind, rawId] = scope.split(":");
    const scopedId = rawId ? Number(rawId) : undefined;
    addSubstitution.mutate(
      {
        substitute_email: email.trim(),
        substitute_name: name.trim() || undefined,
        start_date: startDate,
        end_date: endDate,
        project_id: kind === "project" ? scopedId : undefined,
        site_id: kind === "site" ? scopedId : undefined,
      },
      {
        onSuccess: () => {
          setEmail("");
          setName("");
          setStartDate("");
          setEndDate("");
          setScope("all");
          notify(t("recipients.cover.toast.added"));
        },
      },
    );
  }

  function handleDelete(id: number) {
    setPendingDeleteId(id);
    deleteSubstitution.mutate(id, {
      onError: (error) => notify(errorMessage(error, t), "error"),
      onSettled: () => setPendingDeleteId(null),
    });
  }

  return (
    <Dialog
      open={open} onClosed={onClosed}
      onOpenChange={(open) => !open && onClose()}
      title={t("recipients.cover.title")}
      description={t("recipients.cover.description", { email: recipient.email })}
    >
      <div className="space-y-5">
        {substitutions.isLoading ? (
          <div className="flex justify-center py-6">
            <Spinner className="text-brand-700" />
          </div>
        ) : substitutions.isError ? (
          <ErrorState onRetry={() => void substitutions.refetch()} />
        ) : items.length === 0 ? (
          <p className="text-sm text-mist-500">{t("recipients.cover.none")}</p>
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line">
            {items.map((substitution) => (
              <li
                key={substitution.id}
                className="flex items-center justify-between gap-3 px-3.5 py-2.5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-mist-100">
                    {substitution.substitute_name
                      ? `${substitution.substitute_name} (${substitution.substitute_email})`
                      : substitution.substitute_email}
                  </p>
                  <p className="text-xs text-mist-500">
                    {substitution.start_date} → {substitution.end_date}
                  </p>
                  <p className="text-xs text-mist-600">{scopeLabel(substitution)}</p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t("recipients.cover.aria.remove", {
                    email: substitution.substitute_email,
                  })}
                  onClick={() => handleDelete(substitution.id)}
                  disabled={deleteSubstitution.isPending && pendingDeleteId === substitution.id}
                >
                  {deleteSubstitution.isPending && pendingDeleteId === substitution.id ? (
                    <Spinner />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </Button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={handleAdd} className="grid gap-4 sm:grid-cols-2">
          <Field label={t("recipients.cover.substituteEmail")} htmlFor="substitute-email">
            <Input
              id="substitute-email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t("recipients.cover.placeholder.email")}
            />
          </Field>
          <Field
            label={t("recipients.field.name")}
            hint={t("recipients.field.optional")}
            htmlFor="substitute-name"
          >
            <Input
              id="substitute-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label={t("recipients.cover.startDate")} htmlFor="substitute-start">
            <Input
              id="substitute-start"
              type="date"
              required
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </Field>
          <Field label={t("recipients.cover.endDate")} htmlFor="substitute-end">
            <Input
              id="substitute-end"
              type="date"
              required
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </Field>
          <div className="sm:col-span-2">
            {projects.isLoading || sites.isLoading ? <Spinner /> : projects.isError || sites.isError ? <ErrorState onRetry={() => { void projects.refetch(); void sites.refetch(); }} /> : null}
            <Field
              label={t("recipients.cover.appliesTo")}
              hint={t("recipients.cover.appliesToHint")}
              htmlFor="substitute-scope"
            >
              <Select
                id="substitute-scope"
                disabled={projects.isLoading || projects.isError || sites.isLoading || sites.isError}
                value={scope}
                onChange={(event) => setScope(event.target.value)}
              >
                <option value="all">{t("recipients.cover.scope.all")}</option>
                {(projects.data ?? []).map((project) => (
                  <option key={`project-${project.id}`} value={`project:${project.id}`}>
                    {t("recipients.cover.scope.project", { name: project.name })}
                  </option>
                ))}
                {(sites.data ?? []).map((site) => (
                  <option key={`site-${site.id}`} value={`site:${site.id}`}>
                    {t("recipients.cover.scope.site", { name: site.name || site.url })}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          {addError ? (
            <div className="sm:col-span-2">
              <ErrorNote>{addError}</ErrorNote>
            </div>
          ) : null}
          <div className="flex justify-end sm:col-span-2">
            <Button type="submit" disabled={addSubstitution.isPending || projects.isLoading || projects.isError || sites.isLoading || sites.isError}>
              {addSubstitution.isPending ? <Spinner /> : null}
              {t("recipients.cover.add")}
            </Button>
          </div>
        </form>
      </div>
    </Dialog>
  );
}
