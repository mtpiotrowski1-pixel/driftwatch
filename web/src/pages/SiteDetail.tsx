import { AnalysisProvenance } from "@/components/AnalysisProvenance";
import { useDialogState } from "@/lib/useDialogState";
import {
  AlertTriangle,
  Camera,
  ExternalLink,
  History,
  Pause,
  Pencil,
  Play,
  RefreshCw,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  Trash2,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useNavigate } from "@/lib/navigation";

import { useUnsavedChanges } from "@/lib/useUnsavedChanges";
import { UnsavedChangesDialog } from "@/components/UnsavedChangesDialog";
import { ExportChangesButton } from "@/components/ExportChangesButton";
import { DataFreshness } from "@/components/DataFreshness";
import { ChangeBadge } from "@/components/ChangeBadge";
import { EffectiveRulesPanel } from "@/components/EffectiveRulesPanel";
import { compactSteps, InteractionStepsEditor } from "@/components/InteractionStepsEditor";
import { PickerActionPanel } from "@/components/PickerActionPanel";
import { RulesTester } from "@/components/RulesTester";
import { VisualPickerDialog } from "@/components/VisualPickerDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Collapsible } from "@/components/ui/collapsible";
import { Dialog, type DialogVisibilityProps } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, ErrorState, PageLoader, Spinner } from "@/components/ui/feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { useT, useTp, type Translate } from "@/i18n";
import { ApiError } from "@/lib/api";
import { canEditSite } from "@/lib/capabilities";
import { errorMessage } from "@/lib/errors";
import { usePickerCapabilities } from "@/lib/picker";
import {
  useChange,
  useChangeHistory,
  useCurrentUser,
  useCheckSite,
  useDeleteSite,
  useNotificationsForChange,
  useProjects,
  useReanalyzeChange,
  useRecipients,
  useRetryChange,
  useSetVerdict,
  useSite,
  useSiteEffectiveRules,
  useSnapshotSite,
  useUpdateSite,
} from "@/lib/queries";
import type { Change, CheckStatus, InteractionStep, NotificationMode, Site } from "@/lib/types";
import { cn, formatInterval, hostOf, relativeTime, splitLines } from "@/lib/utils";
import { STATUS_TONE } from "./Notifications";

type ModeChoice = "inherit" | NotificationMode;

const MODE_LABEL_KEY: Record<NotificationMode, string> = {
  only_significant: "sitedetail.mode.only_significant",
  always: "sitedetail.mode.always",
};

const CHECK_RESULT_KEY: Record<CheckStatus, string> = {
  baseline: "sitedetail.checkResult.baseline",
  unchanged: "sitedetail.checkResult.unchanged",
  changed: "sitedetail.checkResult.changed",
};

function needsAttention(change: Change): boolean {
  return change.retry_status === "requires_action" || !!change.ai_error || !!change.notification_error;
}

/** The change to show: an explicit click wins, then a valid `?change=` deep
 * link (from a notification email), then the newest change. */
export function resolveActiveChangeId(
  selectedId: number | null,
  changeParam: string | null,
  changes: { id: number }[],
): number | null {
  if (selectedId !== null && changes.some((change) => change.id === selectedId)) {
    return selectedId;
  }
  if (changeParam !== null) {
    const fromParam = Number(changeParam);
    if (Number.isSafeInteger(fromParam) && fromParam > 0) return fromParam;
  }
  return changes[0]?.id ?? null;
}

export function SiteDetail() {
  const { siteId } = useParams();
  return <SiteWorkspace key={siteId} />;
}

function SiteWorkspace() {
  const { siteId } = useParams();
  const id = Number(siteId);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { notify } = useToast();
  const t = useT();
  const tp = useTp();

  const site = useSite(id);
  const changes = useChangeHistory(id);
  const { data: user } = useCurrentUser();
  const projects = useProjects();
  const check = useCheckSite();
  const snapshot = useSnapshotSite();
  const update = useUpdateSite(id);
  const deleteSite = useDeleteSite();

  const [selectedChangeId, setSelectedChangeId] = useState<number | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const editingDialog = useDialogState(false);
  const { value: editOpen, setValue: setEditOpen } = editingDialog;

  if (site.isLoading || changes.isLoading) return <PageLoader label={t("sitedetail.loading")} />;
  const siteMissing = site.error instanceof ApiError && site.error.status === 404;
  if ((site.isError && !siteMissing) || (changes.isError && !changes.data))
    return (
      <ErrorState
        onRetry={() => {
          site.refetch();
          changes.refetch();
        }}
      />
    );
  if (!site.data) {
    return (
      <EmptyState
        icon={<History className="h-5 w-5" />}
        title={t("sitedetail.notFound.title")}
        description={t("sitedetail.notFound.description")}
        action={<Button onClick={() => navigate("/dashboard")}>{t("sitedetail.notFound.back")}</Button>}
      />
    );
  }

  const current = site.data;
  const editable = canEditSite(user, current);
  // Keep the API's stable id DESC cursor order, including equal timestamps.
  const changeList = changes.data?.pages.flat() ?? [];
  const activeChangeId = resolveActiveChangeId(
    selectedChangeId,
    searchParams.get("change"),
    changeList,
  );
  const attentionCount = changeList.filter(needsAttention).length;
  // Nobody would receive an email for this site: neither the site itself nor
  // its project has recipients. Shown only once the project list has loaded,
  // so a slow fetch never flashes a false warning.
  const project = projects.data?.find((candidate) => candidate.id === current.project_id) ?? null;
  const noRecipients =
    current.recipient_ids.length === 0 &&
    (current.project_id === null ? !!projects.data : project !== null) &&
    (project === null || project.recipient_ids.length === 0);

  function handleDelete() {
    deleteSite.mutate(id, { onSuccess: () => navigate("/dashboard") });
  }

  function runCheck(analyze: boolean) {
    check.mutate(
      { id, analyze },
      {
        onSuccess: (result) => {
          if (result.capture_error) {
            notify(result.capture_error, "error");
            return;
          }
          notify(t("sitedetail.toast.checkComplete", { result: t(CHECK_RESULT_KEY[result.status]) }));
        },
        onError: (error) => notify(messageOf(error, t), "error"),
      },
    );
  }

  function selectChange(changeId: number) {
    setSelectedChangeId(changeId);
    setSearchParams(
      (currentParams) => {
        const nextParams = new URLSearchParams(currentParams);
        nextParams.set("change", String(changeId));
        return nextParams;
      },
      { replace: true },
    );
  }

  const deleteError = deleteSite.error ? errorMessage(deleteSite.error, t) : null;

  return (
    <div className="space-y-8">
      <header className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="truncate text-2xl font-semibold tracking-tight text-mist-100">
                {current.name ?? hostOf(current.url)}
              </h1>
              <Badge tone={current.enabled ? "emerald" : "neutral"}>
                {current.enabled ? t("sitedetail.status.enabled") : t("sitedetail.status.paused")}
              </Badge>
              {current.last_alert_code ? (
                <Badge tone="rose" title={current.last_alert_detail ?? undefined}>
                  {t("sitedetail.alert", { code: current.last_alert_code })}
                </Badge>
              ) : null}
            </div>
            <a
              href={current.url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1.5 text-sm text-mist-400 hover:text-brand-700"
            >
              <span className="truncate">{current.url}</span>
              <ExternalLink className="h-3.5 w-3.5 shrink-0" />
            </a>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {editable ? <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => runCheck(true)}
              disabled={check.isPending}
            >
              {check.isPending ? <Spinner /> : <Play className="h-3.5 w-3.5" />}
              {t("sitedetail.action.checkNow")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              title={t("sitedetail.action.dryCheck.title")}
              onClick={() => runCheck(false)}
              disabled={check.isPending}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              {t("sitedetail.action.dryCheck")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              title={t("sitedetail.action.snapshot.title")}
              onClick={() =>
                snapshot.mutate(id, {
                  onSuccess: (result) => {
                    if (result.capture_error) {
                      notify(result.capture_error, "error");
                      return;
                    }
                    notify(t("sitedetail.toast.snapshotCaptured"));
                  },
                  onError: (error) => notify(messageOf(error, t), "error"),
                })
              }
              disabled={snapshot.isPending}
            >
              {snapshot.isPending ? <Spinner /> : <Camera className="h-3.5 w-3.5" />}
              {t("sitedetail.action.snapshot")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => update.mutate({ enabled: !current.enabled }, { onError: (error) => notify(errorMessage(error, t), "error") })}
              disabled={update.isPending}
            >
              {current.enabled ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {current.enabled ? t("sitedetail.action.pause") : t("sitedetail.action.enable")}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setEditOpen(true)}>
              <Pencil className="h-3.5 w-3.5" />
              {t("common.edit")}
            </Button>
            </> : <span className="text-sm text-mist-500">{t("common.readOnly")}</span>}
            <ExportChangesButton siteId={id} />
            {editable ? <Button variant="danger" size="sm" onClick={() => setConfirmOpen(true)}>
              <Trash2 className="h-3.5 w-3.5" />
              {t("common.delete")}
            </Button> : null}
          </div>
        </div>

        <Card>
          <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Detail
              label={t("sitedetail.detail.interval")}
              value={formatInterval(current.check_interval_minutes)}
            />
            <Detail
              label={t("sitedetail.detail.lastChecked")}
              value={relativeTime(current.last_checked_at)}
            />
            <Detail
              label={t("sitedetail.detail.notifications")}
              value={
                current.notification_mode
                  ? t(MODE_LABEL_KEY[current.notification_mode])
                  : t("sitedetail.detail.inherited")
              }
            />
            <Detail label={t("sitedetail.detail.changes")} value={String(current.change_count)} />
          </CardBody>
        </Card>
      </header>

      <DataFreshness updatedAt={Math.min(site.dataUpdatedAt, changes.dataUpdatedAt)} fetching={site.isFetching || changes.isFetching} stale={site.isRefetchError || changes.isRefetchError} onRefresh={() => { void site.refetch(); void changes.refetch(); }} />

      {noRecipients ? (
        <div className="flex items-center gap-3 rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{t("sitedetail.noRecipients")}</span>
        </div>
      ) : null}

      {attentionCount > 0 ? (
        <div className="flex items-center gap-3 rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{tp("sitedetail.attention", attentionCount)}</span>
        </div>
      ) : null}

      {changeList.length > 0 ? (
        <div className="space-y-2">
          {changes.hasNextPage ? <p className="text-xs text-mist-500">{t("common.loadedHistory", { count: changeList.length })}</p> : null}
          <ChangeStats changes={changeList} needsAction={attentionCount} />
        </div>
      ) : null}

      {changeList.length === 0 ? (
        <EmptyState
          icon={<History className="h-5 w-5" />}
          title={
            current.last_checked_at
              ? t("sitedetail.empty.title")
              : t("sitedetail.empty.uncheckedTitle")
          }
          description={
            current.last_checked_at
              ? t("sitedetail.empty.description")
              : t("sitedetail.empty.uncheckedDescription")
          }
          action={
            current.last_checked_at || !editable ? undefined : (
              <Button onClick={() => runCheck(true)} disabled={check.isPending}>
                {check.isPending ? <Spinner /> : <Play className="h-4 w-4" />}
                {t("sitedetail.empty.uncheckedAction")}
              </Button>
            )
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
          <Card className="h-fit max-h-[28rem] overflow-y-auto lg:max-h-none">
            <ul className="divide-y divide-line">
              {changeList.map((change) => (
                <li key={change.id}>
                  <button
                    type="button"
                    onClick={() => selectChange(change.id)}
                    aria-pressed={change.id === activeChangeId}
                    className={cn(
                      "flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition-colors",
                      change.id === activeChangeId ? "bg-brand-500/10" : "hover:bg-ink-800/60",
                    )}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm text-mist-100">
                        {change.headline ?? t("sitedetail.change.contentChanged")}
                      </p>
                      <p className="mt-0.5 text-xs text-mist-500">{relativeTime(change.created_at)}</p>
                    </div>
                    <ChangeBadge change={change} />
                  </button>
                </li>
              ))}
            </ul>
            {changes.hasNextPage ? <Button variant="ghost" className="w-full" onClick={() => void changes.fetchNextPage()} disabled={changes.isFetchingNextPage}>{t("common.loadMore")}</Button> : null}
            {changes.isFetchNextPageError ? <ErrorNote>{t("common.requestFailed")} <button onClick={() => void changes.fetchNextPage()}>{t("common.retry")}</button></ErrorNote> : null}
          </Card>

          {activeChangeId ? <ChangeView changeId={activeChangeId} siteId={id} editable={editable} /> : null}
        </div>
      )}

      <Dialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("sitedetail.delete.title")}
        description={t("sitedetail.delete.description")}
      >
        <div className="space-y-4">
          {deleteError ? <ErrorNote>{deleteError}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" onClick={handleDelete} disabled={deleteSite.isPending}>
              {deleteSite.isPending ? <Spinner /> : <Trash2 className="h-3.5 w-3.5" />}
              {t("sitedetail.delete.confirm")}
            </Button>
          </div>
        </div>
      </Dialog>

      {editOpen ? (
        <EditSiteDialog
          key={editingDialog.key}
          open={editingDialog.open}
          onClosed={editingDialog.onClosed}
          site={current}
          latestChangeId={changeList[0]?.id ?? null}
          onClose={editingDialog.close}
          onSaved={() => {
            setEditOpen(false);
            notify(t("sitedetail.toast.siteUpdated"));
          }}
        />
      ) : null}
    </div>
  );
}

function ChangeView({ changeId, siteId, editable }: { changeId: number; siteId: number; editable: boolean }) {
  const change = useChange(changeId);
  const deliveries = useNotificationsForChange(changeId);
  const retry = useRetryChange();
  const reanalyze = useReanalyzeChange();
  const { notify } = useToast();
  const t = useT();

  if (change.isLoading) return <PageLoader label={t("sitedetail.change.loading")} />;
  if (change.isError || !change.data) {
    return <ErrorState onRetry={() => void change.refetch()} />;
  }

  if (change.data.site_id !== siteId) return <ErrorNote>{t("sitedetail.notFound.description")}</ErrorNote>;
  const detail = change.data;
  const hasError = detail.ai_error || detail.notification_error;
  const deliveryRows = deliveries.data ?? [];
  // The head of analysis_runs is the current verdict; anything after it is a
  // previous verdict preserved across re-analyses.
  const previousRuns = detail.analysis_runs.slice(1);

  return (
    <Card>
      <CardBody className="space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-mist-100">
              {detail.headline ?? t("sitedetail.change.contentChanged")}
            </h2>
            <p className="mt-1 text-xs text-mist-500">{relativeTime(detail.created_at)}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <ChangeBadge change={detail} />
            {editable && detail.significant !== null ? <VerdictToggle change={detail} /> : null}
          </div>
        </div>

        {detail.analysis_status ? <p className="text-xs text-mist-500">{t(`common.analysisStatus.${detail.analysis_status}`)}</p> : null}

        {detail.summary ? <p className="text-sm text-mist-300">{detail.summary}</p> : null}
        {detail.analysis_runs[0] ? <AnalysisProvenance run={detail.analysis_runs[0]} /> : null}

        {detail.ai_error ? (
          <ErrorNote>{t("sitedetail.change.analysisFailed", { error: detail.ai_error })}</ErrorNote>
        ) : null}
        {detail.notification_error ? (
          <ErrorNote>
            {t("sitedetail.change.deliveryFailed", { error: detail.notification_error })}
          </ErrorNote>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          {hasError ? (
            <Button
              variant="secondary"
              size="sm"
              disabled={!editable || retry.isPending}
              onClick={() =>
                retry.mutate(detail.id, {
                  onSuccess: () => notify(t("sitedetail.toast.retryQueued")),
                  onError: (error) => notify(messageOf(error, t), "error"),
                })
              }
            >
              {retry.isPending ? <Spinner /> : <RotateCcw className="h-3.5 w-3.5" />}
              {t("sitedetail.action.retry")}
            </Button>
          ) : null}
          <Button
            variant="secondary"
            size="sm"
            title={t("sitedetail.action.reanalyze.title")}
            disabled={!editable || reanalyze.isPending}
            onClick={() =>
              reanalyze.mutate(detail.id, {
                onSuccess: () => notify(t("sitedetail.toast.reanalysisQueued")),
                onError: (error) => notify(messageOf(error, t), "error"),
              })
            }
          >
            {reanalyze.isPending ? <Spinner /> : <RefreshCw className="h-3.5 w-3.5" />}
            {t("sitedetail.action.reanalyze")}
          </Button>
        </div>

        {detail.ai_retry_count > 0 || detail.notification_retry_count > 0 ? (
          <p className="text-xs text-mist-500">
            {[
              detail.ai_retry_count > 0
                ? t("sitedetail.retries.analysis", { count: detail.ai_retry_count })
                : null,
              detail.notification_retry_count > 0
                ? t("sitedetail.retries.delivery", { count: detail.notification_retry_count })
                : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        ) : null}

        {previousRuns.length > 0 ? (
          <Collapsible label={t("sitedetail.previous.title")}>
            <ul className="divide-y divide-line rounded-lg border border-line">
              {previousRuns.map((run) => (
                <li key={run.id} className="space-y-1 px-3.5 py-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={run.significant ? "amber" : "neutral"}>
                      {run.significant
                        ? t("sitedetail.previous.significant")
                        : t("sitedetail.previous.minor")}
                    </Badge>
                    <span className="min-w-0 text-sm text-mist-100">{run.headline}</span>
                    <span className="ml-auto shrink-0 text-xs text-mist-500">
                      {relativeTime(run.created_at)}
                    </span>
                  </div>
                  <p className="text-xs text-mist-400">{run.summary}</p>
                  <AnalysisProvenance run={run} />
                </li>
              ))}
            </ul>
          </Collapsible>
        ) : null}

        {deliveries.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-mist-500" role="status">
            <Spinner aria-hidden="true" />
            {t("sitedetail.deliveries.loading")}
          </div>
        ) : deliveries.isError ? (
          <div className="space-y-2">
            <ErrorNote>{t("sitedetail.deliveries.loadError")}</ErrorNote>
            <Button variant="secondary" size="sm" onClick={() => void deliveries.refetch()}>
              <RefreshCw className="h-3.5 w-3.5" />
              {t("common.retry")}
            </Button>
          </div>
        ) : deliveryRows.length > 0 ? (
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-mist-300">
              {t("sitedetail.deliveries.title")}
            </h3>
            <ul className="divide-y divide-line rounded-lg border border-line">
              {deliveryRows.map((delivery) => (
                <li key={delivery.id} className="flex items-start gap-3 px-3.5 py-2.5">
                  <Badge tone={STATUS_TONE[delivery.status]} className="mt-0.5 shrink-0">
                    {t(`notifications.status.${delivery.status}`)}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-mist-100">{delivery.recipient_email}</p>
                    {delivery.error ? (
                      <p
                        className={cn(
                          "mt-0.5 text-xs",
                          delivery.status === "failed" ? "text-rose-400" : "text-mist-500",
                        )}
                      >
                        {delivery.error}
                      </p>
                    ) : null}
                  </div>
                  <span className="shrink-0 text-xs text-mist-500">
                    {relativeTime(delivery.sent_at)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {detail.diff_html ? (
          <div dangerouslySetInnerHTML={{ __html: detail.diff_html }} />
        ) : (
          <p className="text-sm text-mist-400">{t("sitedetail.change.noDiff")}</p>
        )}
      </CardBody>
    </Card>
  );
}

/** Agree/disagree with the AI's significance verdict. Clicking the active
 * choice again clears the review. The human verdict never overwrites the AI's
 * own field — it contributes to agreement on reviewed, detected events. */
function VerdictToggle({ change }: { change: Change }) {
  const t = useT();
  const { notify } = useToast();
  const setVerdict = useSetVerdict();

  const agreed = change.user_verdict !== null && change.user_verdict === change.significant;
  const disagreed = change.user_verdict !== null && change.user_verdict !== change.significant;

  function submit(agree: boolean) {
    const active = agree ? agreed : disagreed;
    const verdict = active ? null : agree ? change.significant : !change.significant;
    setVerdict.mutate(
      { id: change.id, verdict },
      { onError: (error) => notify(messageOf(error, t), "error") },
    );
  }

  return (
    <div
      className="flex items-center gap-1"
      role="group"
      aria-label={t("sitedetail.verdict.label")}
    >
      <span className="text-xs text-mist-500">{t("sitedetail.verdict.label")}</span>
      <button
        type="button"
        title={t("sitedetail.verdict.agree")}
        aria-pressed={agreed}
        disabled={setVerdict.isPending}
        onClick={() => submit(true)}
        className={cn(
          "rounded-lg border p-1.5 transition-colors",
          agreed
            ? "border-emerald-400/50 bg-emerald-400/15 text-emerald-400"
            : "border-line text-mist-500 hover:text-mist-300",
        )}
      >
        <ThumbsUp className="h-3.5 w-3.5" />
        <span className="sr-only">{t("sitedetail.verdict.agree")}</span>
      </button>
      <button
        type="button"
        title={t("sitedetail.verdict.disagree")}
        aria-pressed={disagreed}
        disabled={setVerdict.isPending}
        onClick={() => submit(false)}
        className={cn(
          "rounded-lg border p-1.5 transition-colors",
          disagreed
            ? "border-rose-400/50 bg-rose-400/15 text-rose-400"
            : "border-line text-mist-500 hover:text-mist-300",
        )}
      >
        <ThumbsDown className="h-3.5 w-3.5" />
        <span className="sr-only">{t("sitedetail.verdict.disagree")}</span>
      </button>
    </div>
  );
}

function EditSiteDialog({
  open,
  onClosed,
  site,
  latestChangeId,
  onClose,
  onSaved,
}: {
  site: Site;
  latestChangeId: number | null;
  onClose: () => void;
  onSaved: () => void;
} & DialogVisibilityProps) {
  const recipients = useRecipients();
  const update = useUpdateSite(site.id);
  const effectiveRules = useSiteEffectiveRules(site.id);
  const capabilities = usePickerCapabilities();
  const t = useT();
  const tp = useTp();

  const [name, setName] = useState(site.name ?? "");
  const [cssSelector, setCssSelector] = useState(site.css_selector ?? "");
  const [intervalMinutes, setIntervalMinutes] = useState(site.check_interval_minutes);
  const [analysisMode, setAnalysisMode] = useState<"ai" | "disabled">(site.analysis_mode ?? "ai");
  const [mode, setMode] = useState<ModeChoice>(site.notification_mode ?? "inherit");
  const [prompt, setPrompt] = useState(site.prompt ?? "");
  const [ignoreSelectors, setIgnoreSelectors] = useState(site.ignore_selectors.join("\n"));
  const [recipientIds, setRecipientIds] = useState<number[]>(site.recipient_ids);
  const [steps, setSteps] = useState<InteractionStep[]>(site.interaction_steps);
  const [picker, setPicker] = useState<"select" | "record" | null>(null);

  const dirty = JSON.stringify([name, cssSelector, intervalMinutes, mode, prompt, ignoreSelectors, recipientIds, steps, analysisMode]) !== JSON.stringify([site.name ?? "", site.css_selector ?? "", site.check_interval_minutes, site.notification_mode ?? "inherit", site.prompt ?? "", site.ignore_selectors.join("\n"), site.recipient_ids, site.interaction_steps, site.analysis_mode ?? "ai"]);
  const blocker = useUnsavedChanges(open && dirty);
  const [discardOpen, setDiscardOpen] = useState(false);
  function requestClose() { if (dirty) setDiscardOpen(true); else onClose(); }

  const error = update.error ? errorMessage(update.error, t) : null;
  const pickerLoading = capabilities.isLoading;
  const pickerAvailable = capabilities.data?.available ?? false;
  const pickerUnavailable =
    !pickerLoading && !pickerAvailable
      ? (capabilities.data?.reason ?? t("sitedetail.edit.pickerUnavailable"))
      : null;
  const pickerDisabled = pickerLoading || !!pickerUnavailable;
  const compactedSteps = compactSteps(steps);

  function toggleRecipient(id: number) {
    setRecipientIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      {
        name: name.trim() || null,
        css_selector: cssSelector.trim() || null,
        check_interval_minutes: intervalMinutes,
        analysis_mode: analysisMode,
        notification_mode: analysisMode === "disabled" ? "always" : mode === "inherit" ? null : mode,
        prompt: prompt.trim() || null,
        ignore_selectors: splitLines(ignoreSelectors),
        recipient_ids: recipientIds,
        interaction_steps: compactSteps(steps),
      },
      { onSuccess: onSaved },
    );
  }

  return (
    <>
    <UnsavedChangesDialog blocker={blocker} />
    <Dialog open={open && discardOpen} onOpenChange={setDiscardOpen} title={t("common.unsaved.title")} description={t("common.unsaved.body")}>
      <div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => setDiscardOpen(false)}>{t("common.unsaved.stay")}</Button><Button variant="danger" onClick={onClose}>{t("common.unsaved.leave")}</Button></div>
    </Dialog>
    <Dialog
      open={open} onClosed={onClosed}
      onOpenChange={(open) => !open && requestClose()}
      title={t("sitedetail.edit.title")}
      className="w-[min(94vw,40rem)]"
    >
      <form onSubmit={handleSubmit} className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        <Field label={t("sitedetail.edit.name")} htmlFor="edit-name">
          <Input id="edit-name" value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <PickerActionPanel
          title={t("picker.pick.title")}
          explainer={t("picker.pick.explainer")}
          actionLabel={t("picker.pick.action")}
          onAction={() => setPicker("select")}
          disabled={pickerDisabled}
          unavailable={pickerUnavailable}
        >
          {cssSelector.trim() ? (
            <div className="flex items-center gap-2">
              <Badge tone="emerald" className="min-w-0 max-w-full">
                <span className="sr-only">{t("picker.pick.selectedLabel")}: </span>
                <span className="truncate" title={cssSelector}>
                  {t("picker.pick.selected", { selector: cssSelector })}
                </span>
              </Badge>
              <Button type="button" variant="ghost" size="sm" onClick={() => setCssSelector("")}>
                {t("picker.pick.clear")}
              </Button>
            </div>
          ) : (
            <p className="text-xs text-mist-500">{t("picker.pick.watchingWhole")}</p>
          )}
        </PickerActionPanel>
        <Collapsible
          label={t("picker.pick.advanced")}
          defaultOpen={!!cssSelector || !!pickerUnavailable}
        >
          <Field label={t("sitedetail.edit.selector")} htmlFor="edit-selector">
            <Input
              id="edit-selector"
              value={cssSelector}
              onChange={(event) => setCssSelector(event.target.value)}
              placeholder="main .prices"
            />
          </Field>
        </Collapsible>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("sitedetail.edit.interval")} htmlFor="edit-interval">
            <Input
              id="edit-interval"
              type="number"
              min={1}
              value={intervalMinutes}
              onChange={(event) => setIntervalMinutes(Number(event.target.value))}
            />
          </Field>
          <Field label={t("common.analysisMode")} hint={t("common.analysisModeHint")} htmlFor="edit-analysis-mode">
            <Select id="edit-analysis-mode" value={analysisMode} onChange={(event) => { const value = event.target.value as "ai" | "disabled"; setAnalysisMode(value); if (value === "disabled") setMode("always"); }}><option value="ai">{t("common.analysisAi")}</option><option value="disabled">{t("common.analysisDisabled")}</option></Select>
          </Field>
          <Field label={t("sitedetail.edit.notifications")} htmlFor="edit-mode">
            <Select
              id="edit-mode"
              disabled={analysisMode === "disabled"}
              value={mode}
              onChange={(event) => setMode(event.target.value as ModeChoice)}
            >
              <option value="inherit">{t("sitedetail.edit.mode.inherit")}</option>
              <option value="only_significant">{t("sitedetail.edit.mode.only_significant")}</option>
              <option value="always">{t("sitedetail.edit.mode.always")}</option>
            </Select>
          </Field>
        </div>
        <Field
          label={t("sitedetail.edit.prompt")}
          hint={t("sitedetail.edit.prompt.hint")}
          htmlFor="edit-prompt"
        >
          <Textarea
            id="edit-prompt"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
          />
        </Field>
        <EffectiveRulesPanel rules={effectiveRules.data} />
        <RulesTester changeId={latestChangeId} rules={prompt} />
        <PickerActionPanel
          title={t("picker.record.title")}
          explainer={t("picker.record.explainer")}
          actionLabel={t("picker.record.action")}
          onAction={() => setPicker("record")}
          disabled={pickerDisabled}
          unavailable={pickerUnavailable}
        >
          {compactedSteps.length > 0 ? (
            <div className="flex items-center gap-2">
              <Badge tone="emerald">{tp("picker.record.count", compactedSteps.length)}</Badge>
              <Button type="button" variant="ghost" size="sm" onClick={() => setSteps([])}>
                {t("picker.record.clear")}
              </Button>
            </div>
          ) : null}
        </PickerActionPanel>
        <Collapsible
          label={t("picker.record.advanced")}
          defaultOpen={steps.length > 0 || !!ignoreSelectors || !!pickerUnavailable}
        >
          <Field label={t("sitedetail.edit.steps")} hint={t("sitedetail.edit.steps.hint")}>
            <InteractionStepsEditor steps={steps} onChange={setSteps} />
          </Field>
          <Field
            label={t("sitedetail.edit.ignore")}
            hint={t("sitedetail.edit.ignore.hint")}
            htmlFor="edit-ignore"
          >
            <Textarea
              id="edit-ignore"
              value={ignoreSelectors}
              onChange={(event) => setIgnoreSelectors(event.target.value)}
              placeholder={".cookie-banner\n#ads"}
            />
          </Field>
        </Collapsible>
        <Field label={t("sitedetail.edit.recipients")}>
          {recipients.isLoading ? <Spinner /> : recipients.isError ? <ErrorState onRetry={() => void recipients.refetch()} /> : (recipients.data ?? []).length === 0 ? (
            <p className="text-sm text-mist-500">{t("sitedetail.edit.noRecipients")}</p>
          ) : (
            <div className="max-h-44 space-y-2 overflow-y-auto pr-1">
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
          <Button type="button" variant="ghost" onClick={requestClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={update.isPending || recipients.isLoading || recipients.isError}>
            {update.isPending ? <Spinner /> : null}
            {t("sitedetail.edit.save")}
          </Button>
        </div>
      </form>
      {open && picker ? (
        <VisualPickerDialog
          open
          mode={picker}
          url={site.url}
          siteId={site.id}
          onClose={() => setPicker(null)}
          onSelect={setCssSelector}
          onSteps={(recorded) => setSteps((current) => [...current, ...recorded])}
        />
      ) : null}
    </Dialog>
    </>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-mist-500">{label}</p>
      <p className="mt-0.5 text-sm text-mist-100">{value}</p>
    </div>
  );
}

function ChangeStats({ changes, needsAction }: { changes: Change[]; needsAction: number }) {
  const t = useT();
  const significant = changes.filter((change) => change.significant === true).length;
  const notified = changes.filter((change) => change.notified_at !== null).length;
  const stats = [
    { label: t("sitedetail.stats.total"), value: changes.length, alert: false },
    { label: t("sitedetail.stats.significant"), value: significant, alert: false },
    { label: t("sitedetail.stats.notified"), value: notified, alert: false },
    { label: t("sitedetail.stats.needsAction"), value: needsAction, alert: needsAction > 0 },
  ];
  return (
    <Card>
      <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label}>
            <p className="text-xs text-mist-500">{stat.label}</p>
            <p
              className={cn(
                "mt-0.5 text-2xl font-semibold tracking-tight",
                stat.alert ? "text-amber-400" : "text-mist-100",
              )}
            >
              {stat.value}
            </p>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

function messageOf(error: unknown, t: Translate): string {
  return errorMessage(error, t);
}
