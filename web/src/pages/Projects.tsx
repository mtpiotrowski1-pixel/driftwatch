import { errorMessage } from "@/lib/errors";
import { useDialogState } from "@/lib/useDialogState";
import { FolderPlus, FolderTree, Pencil, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "@/lib/navigation";

import { EffectiveRulesPanel } from "@/components/EffectiveRulesPanel";
import { RulesTester } from "@/components/RulesTester";
import { ExportChangesButton } from "@/components/ExportChangesButton";
import { EmptyStateArtwork } from "@/components/brand/EmptyStateArtwork";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardBody } from "@/components/ui/card";
import { ClickableCard } from "@/components/ui/clickable-card";
import { Dialog, type DialogVisibilityProps } from "@/components/ui/dialog";
import { CardGridSkeleton, EmptyState, ErrorNote, ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { useT, useTp } from "@/i18n";
import { canEditProject } from "@/lib/capabilities";
import { useInOrgContext } from "@/lib/orgContext";
import {
  useChanges,
  useCurrentUser,
  useCreateProject,
  useDeleteProject,
  useProjectEffectiveRules,
  useProjects,
  useRecipients,
  useSites,
  useUpdateProject,
} from "@/lib/queries";
import type { NotificationMode, Project } from "@/lib/types";

type ModeChoice = "inherit" | NotificationMode;

export function Projects() {
  const t = useT();
  const tp = useTp();
  const projects = useProjects();
  const createProject = useCreateProject();
  const inOrg = useInOrgContext();
  const { data: user } = useCurrentUser();
  const canCreate = inOrg && !!(user?.is_admin || user?.is_superadmin);
  const navigate = useNavigate();

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const editingDialog = useDialogState<Project | null>(null);
  const { value: editing, setValue: setEditing } = editingDialog;
  const deletingDialog = useDialogState<Project | null>(null);
  const { value: deleting, setValue: setDeleting } = deletingDialog;

  const { notify } = useToast();

  const createError = createProject.error ? errorMessage(createProject.error, t) : null;

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    createProject.mutate(
      { name: name.trim() },
      {
        onSuccess: () => {
          setName("");
          setCreateOpen(false);
          notify(t("projects.created"));
        },
      },
    );
  }

  if (projects.isLoading) return <CardGridSkeleton />;
  if (projects.isError) return <ErrorState onRetry={() => projects.refetch()} />;

  const projectList = projects.data ?? [];

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-100">
            {t("projects.title")}
          </h1>
          <p className="mt-1 text-sm text-mist-400">{t("projects.subtitle")}</p>
        </div>
        {canCreate ? (
          <Button onClick={() => setCreateOpen(true)}>
            <FolderPlus className="h-4 w-4" />
            {t("projects.newProject")}
          </Button>
        ) : null}
      </header>

      {projectList.length === 0 ? (
        <EmptyState
          icon={<FolderTree className="h-5 w-5" />}
          visual={<EmptyStateArtwork variant="workspace" />}
          title={t("projects.empty.title")}
          description={t("projects.empty.description")}
          action={
            canCreate ? (
              <Button onClick={() => setCreateOpen(true)}>
                <FolderPlus className="h-4 w-4" />
                {t("projects.newProject")}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projectList.map((project) => (
            <ClickableCard
              key={project.id}
              label={t("projects.openAria", { name: project.name })}
              onOpen={() => navigate(`/projects/${project.id}`)}
            >
              <CardBody className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-mist-100">{project.name}</p>
                    <p className="mt-0.5 text-xs text-mist-500">
                      {tp("projects.siteCount", project.site_count)}
                    </p>
                  </div>
                  <Badge tone={project.notification_mode ? "brand" : "neutral"}>
                    {project.notification_mode
                      ? t(`projects.mode.${project.notification_mode}`)
                      : t("projects.mode.inherited")}
                  </Badge>
                </div>

                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-mist-500">
                    {tp("projects.recipientCount", project.recipient_ids.length)}
                  </span>
                  <div className="pointer-events-auto relative z-10 flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("projects.editAria", { name: project.name })}
                      disabled={!canEditProject(user, project.id)}
                      onClick={() => setEditing(project)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <ExportChangesButton projectId={project.id} iconOnly />
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t("projects.deleteAria", { name: project.name })}
                      disabled={!canCreate}
                      onClick={() => setDeleting(project)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardBody>
            </ClickableCard>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen} title={t("projects.create.title")}>
        <form onSubmit={handleCreate} className="space-y-4">
          <Field label={t("projects.field.name")} htmlFor="project-name">
            <Input
              id="project-name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("projects.create.namePlaceholder")}
            />
          </Field>
          {createError ? <ErrorNote>{createError}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={createProject.isPending}>
              {t("projects.create.submit")}
            </Button>
          </div>
        </form>
      </Dialog>

      {editing ? (
        <EditProjectDialog
          key={editingDialog.key}
          open={editingDialog.open}
          onClosed={editingDialog.onClosed}
          project={editing}
          onClose={editingDialog.close}
          onSaved={() => {
            setEditing(null);
            notify(t("projects.updated"));
          }}
        />
      ) : null}

      {deleting ? (
        <DeleteProjectDialog
          key={deletingDialog.key}
          open={deletingDialog.open}
          onClosed={deletingDialog.onClosed}
          project={deleting}
          onClose={deletingDialog.close}
          onDeleted={() => {
            setDeleting(null);
            notify(t("projects.deleted"));
          }}
        />
      ) : null}
    </div>
  );
}

export function EditProjectDialog({
  open,
  onClosed,
  project,
  onClose,
  onSaved,
}: {
  project: Project;
  onClose: () => void;
  onSaved: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const recipients = useRecipients();
  const update = useUpdateProject(project.id);
  const sites = useSites();
  const changes = useChanges();
  const effectiveRules = useProjectEffectiveRules(project.id);

  const [name, setName] = useState(project.name);
  const [mode, setMode] = useState<ModeChoice>(project.notification_mode ?? "inherit");
  const [recipientIds, setRecipientIds] = useState<number[]>(project.recipient_ids);
  const [prompt, setPrompt] = useState(project.prompt ?? "");

  const error = update.error ? errorMessage(update.error, t) : null;

  // The newest change on any of this project's sites — the sample the draft
  // rules are dry-run against. The changes list arrives newest-first.
  const projectSiteIds = new Set(
    (sites.data ?? [])
      .filter((candidate) => candidate.project_id === project.id)
      .map((candidate) => candidate.id),
  );
  const sampleChangeId =
    (changes.data ?? []).find((change) => projectSiteIds.has(change.site_id))?.id ?? null;

  function toggleRecipient(id: number) {
    setRecipientIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      {
        name: name.trim(),
        notification_mode: mode === "inherit" ? null : mode,
        recipient_ids: recipientIds,
        prompt: prompt.trim() || null,
      },
      { onSuccess: onSaved },
    );
  }

  return (
    <Dialog open={open} onClosed={onClosed} onOpenChange={(open) => !open && onClose()} title={t("projects.edit.title")}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label={t("projects.field.name")} htmlFor="edit-project-name">
          <Input
            id="edit-project-name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label={t("projects.field.notifications")} htmlFor="edit-project-mode">
          <Select
            id="edit-project-mode"
            value={mode}
            onChange={(event) => setMode(event.target.value as ModeChoice)}
          >
            <option value="inherit">{t("projects.notifications.inherit")}</option>
            <option value="only_significant">
              {t("projects.notifications.only_significant")}
            </option>
            <option value="always">{t("projects.notifications.always")}</option>
          </Select>
        </Field>
        <Field
          label={t("projects.field.rules")}
          hint={t("projects.field.rulesHint")}
          htmlFor="edit-project-prompt"
        >
          <Textarea
            id="edit-project-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder={t("projects.field.rulesPlaceholder")}
          />
        </Field>
        <EffectiveRulesPanel rules={effectiveRules.data} />
        <RulesTester changeId={sampleChangeId} rules={prompt} />
        <Field label={t("projects.field.recipients")}>
          {recipients.isLoading ? <Spinner /> : recipients.isError ? <ErrorState onRetry={() => void recipients.refetch()} /> : (recipients.data ?? []).length === 0 ? (
            <p className="text-sm text-mist-500">{t("projects.noRecipients")}</p>
          ) : (
            <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
              {(recipients.data ?? []).map((recipient) => (
                <label
                  key={recipient.id}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border border-line bg-ink-900/50 px-3.5 py-2.5 transition-colors hover:border-brand-500/40"
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-brand-500"
                    checked={recipientIds.includes(recipient.id)}
                    onChange={() => toggleRecipient(recipient.id)}
                  />
                  <span className="min-w-0 truncate text-sm text-mist-100">
                    {recipient.name ?? recipient.email}
                  </span>
                </label>
              ))}
            </div>
          )}
        </Field>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={update.isPending || recipients.isLoading || recipients.isError}>
            {update.isPending ? <Spinner /> : null}
            {t("projects.edit.submit")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function DeleteProjectDialog({
  open,
  onClosed,
  project,
  onClose,
  onDeleted,
}: {
  project: Project;
  onClose: () => void;
  onDeleted: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const deleteProject = useDeleteProject();
  const error = deleteProject.error ? errorMessage(deleteProject.error, t) : null;

  return (
    <Dialog
      open={open} onClosed={onClosed}
      onOpenChange={(open) => !open && onClose()}
      title={t("projects.delete.title")}
      description={t("projects.delete.description")}
    >
      <div className="space-y-4">
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="danger"
            disabled={deleteProject.isPending}
            onClick={() => deleteProject.mutate(project.id, { onSuccess: onDeleted })}
          >
            {deleteProject.isPending ? <Spinner /> : <Trash2 className="h-3.5 w-3.5" />}
            {t("projects.delete.submit")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
