import { ArrowLeft, FolderTree, Pencil, Plus } from "lucide-react";
import { useDialogState } from "@/lib/useDialogState";
import { useParams } from "react-router-dom";
import { useNavigate } from "@/lib/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, ErrorState, PageLoader } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { useT, useTp } from "@/i18n";
import { canEditProject } from "@/lib/capabilities";
import { useInOrgContext } from "@/lib/orgContext";
import { useCurrentUser, useProjects, useSites } from "@/lib/queries";

import { EditProjectDialog } from "./Projects";

export function ProjectDetail() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const t = useT();
  const tp = useTp();
  const navigate = useNavigate();
  const projects = useProjects();
  const sites = useSites();
  const inOrg = useInOrgContext();
  const { data: user } = useCurrentUser();
  const editable = canEditProject(user, id);
  const { notify } = useToast();
  const editingDialog = useDialogState(false);
  const { value: editing, setValue: setEditing } = editingDialog;

  if (projects.isLoading || sites.isLoading) return <PageLoader label={t("projects.loading")} />;
  if (projects.isError || sites.isError)
    return (
      <ErrorState
        onRetry={() => {
          projects.refetch();
          sites.refetch();
        }}
      />
    );

  const project = (projects.data ?? []).find((candidate) => candidate.id === id);
  if (!project) {
    return (
      <EmptyState
        icon={<FolderTree className="h-5 w-5" />}
        title={t("projects.detail.notFound.title")}
        description={t("projects.detail.notFound.description")}
        action={
          <Button variant="secondary" onClick={() => navigate("/projects")}>
            <ArrowLeft className="h-4 w-4" />
            {t("projects.detail.back")}
          </Button>
        }
      />
    );
  }

  const projectSites = (sites.data ?? []).filter((site) => site.project_id === id);

  return (
    <div className="space-y-8">
      <button
        type="button"
        onClick={() => navigate("/projects")}
        className="flex items-center gap-1.5 text-sm text-mist-400 transition-colors hover:text-mist-100"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("projects.detail.back")}
      </button>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-mist-100">
              {project.name}
            </h1>
            <Badge tone={project.notification_mode ? "brand" : "neutral"}>
              {project.notification_mode
                ? t(`projects.mode.${project.notification_mode}`)
                : t("projects.mode.inherited")}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-mist-400">
            {tp("projects.recipientCount", project.recipient_ids.length)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" disabled={!editable} onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" />
            {t("common.edit")}
          </Button>
          {inOrg && editable ? (
            <Button onClick={() => navigate(`/sites/new?project=${project.id}`)}>
              <Plus className="h-4 w-4" />
              {t("projects.detail.addSite")}
            </Button>
          ) : null}
        </div>
      </header>

      {projectSites.length === 0 ? (
        <EmptyState
          icon={<FolderTree className="h-5 w-5" />}
          title={t("projects.detail.empty.title")}
          description={t("projects.detail.empty.description")}
          action={
            inOrg && editable ? (
              <Button onClick={() => navigate(`/sites/new?project=${project.id}`)}>
                <Plus className="h-4 w-4" />
                {t("projects.detail.addSite")}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projectSites.map((site) => (
            <Card key={site.id} hover>
              <CardBody>
                <button
                  type="button"
                  onClick={() => navigate(`/sites/${site.id}`)}
                  className="block w-full space-y-2 text-left"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate font-semibold text-mist-100">
                      {site.name ?? site.url}
                    </p>
                    <Badge tone={site.enabled ? "emerald" : "neutral"}>
                      {site.enabled ? t("sitedetail.status.enabled") : t("sitedetail.status.paused")}
                    </Badge>
                  </div>
                  <p className="truncate text-xs text-mist-500">{site.url}</p>
                </button>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {editing ? (
        <EditProjectDialog
          key={editingDialog.key}
          open={editingDialog.open}
          onClosed={editingDialog.onClosed}
          project={project}
          onClose={editingDialog.close}
          onSaved={() => {
            setEditing(false);
            notify(t("projects.updated"));
          }}
        />
      ) : null}
    </div>
  );
}
