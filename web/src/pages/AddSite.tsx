import { errorMessage } from "@/lib/errors";
import { Building2, Users } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useNavigate } from "@/lib/navigation";

import { UnsavedChangesDialog } from "@/components/UnsavedChangesDialog";
import { EffectiveRulesPanel } from "@/components/EffectiveRulesPanel";
import { compactSteps, InteractionStepsEditor } from "@/components/InteractionStepsEditor";
import { PickerActionPanel } from "@/components/PickerActionPanel";
import { VisualPickerDialog } from "@/components/VisualPickerDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible } from "@/components/ui/collapsible";
import { EmptyState, ErrorNote, ErrorState, Spinner } from "@/components/ui/feedback";
import { Field, Input, Label, Select, Textarea } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useT, useTp } from "@/i18n";
import { currentRequestContext, organizationRequestContext } from "@/lib/api";
import { canCreateSite, canEditProject } from "@/lib/capabilities";
import { useUnsavedChanges } from "@/lib/useUnsavedChanges";
import { useInOrgContext } from "@/lib/orgContext";
import { usePickerCapabilities } from "@/lib/picker";
import {
  useCreateSite,
  useCurrentUser,
  useInheritedEffectiveRules,
  useProjectEffectiveRules,
  useProjects,
  useRecipients,
} from "@/lib/queries";
import type { InteractionStep, NotificationMode, Site } from "@/lib/types";
import { normalizeUrl, splitLines } from "@/lib/utils";

type ModeChoice = "inherit" | NotificationMode;

export function AddSite() {
  const t = useT();
  const tp = useTp();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inOrg = useInOrgContext();
  const { data: user } = useCurrentUser();
  const projects = useProjects();
  const recipients = useRecipients();
  const organizationId = user?.is_superadmin ? user.acting_organization_id : user?.organization_id;
  const createSite = useCreateSite(organizationId == null ? currentRequestContext : organizationRequestContext(organizationId));
  const capabilities = usePickerCapabilities();
  const { notify } = useToast();

  const [bulk, setBulk] = useState(false);
  const [url, setUrl] = useState("");
  const [bulkUrls, setBulkUrls] = useState("");
  const [name, setName] = useState("");
  // Pre-select the project when arriving from a project's "Add site here".
  const initialProjectId = useRef(searchParams.get("project") ?? "").current;
  const [projectId, setProjectId] = useState(initialProjectId);
  const [cssSelector, setCssSelector] = useState("");
  const [intervalMinutes, setIntervalMinutes] = useState(60);
  const [analysisMode, setAnalysisMode] = useState<"ai" | "disabled">("ai");
  const [notificationMode, setNotificationMode] = useState<ModeChoice>("inherit");
  const [enabled, setEnabled] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [ignoreSelectors, setIgnoreSelectors] = useState("");
  const [steps, setSteps] = useState<InteractionStep[]>([]);
  const [recipientIds, setRecipientIds] = useState<number[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [failures, setFailures] = useState<string[]>([]);
  const saved = useRef(false);
  const dirty = Boolean(
    url || bulkUrls || name || cssSelector || prompt || ignoreSelectors ||
    steps.length || recipientIds.length || bulk || projectId !== initialProjectId ||
    intervalMinutes !== 60 || analysisMode !== "ai" || notificationMode !== "inherit" || !enabled,
  );
  const blocker = useUnsavedChanges(dirty, () => saved.current);
  const [picker, setPicker] = useState<"select" | "record" | null>(null);

  // The rules a new site would inherit: the selected project's chain, or the
  // org/global chain while no project is chosen.
  const projectRules = useProjectEffectiveRules(projectId ? Number(projectId) : null);
  const inheritedRules = useInheritedEffectiveRules(!projectId);
  const effectiveRules = projectId ? projectRules.data : inheritedRules.data;

  const error = createSite.error ? errorMessage(createSite.error, t) : null;
  const pickerLoading = capabilities.isLoading;
  const pickerAvailable = capabilities.data?.available ?? false;
  // Why a picker can't run right now, split so the UI can react differently:
  // a host without a picker shows a degraded note, a missing URL is a soft hint.
  const pickerUnavailable =
    !pickerLoading && !pickerAvailable
      ? (capabilities.data?.reason ?? t("addsite.pickerUnavailable"))
      : null;
  const urlBlocked = !bulk && !url.trim() ? t("addsite.enterUrlFirst") : null;
  const pickerDisabled = pickerLoading || !!pickerUnavailable || !!urlBlocked;
  const compactedSteps = compactSteps(steps);
  const validProject = !!(user?.is_admin || user?.is_superadmin) || (projectId !== "" && canEditProject(user, Number(projectId)));

  function toggleRecipient(id: number) {
    setRecipientIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
  }

  function sharedFields(): Partial<Site> {
    return {
      project_id: projectId ? Number(projectId) : null,
      css_selector: cssSelector.trim() || undefined,
      check_interval_minutes: intervalMinutes,
      analysis_mode: analysisMode,
      notification_mode: analysisMode === "disabled" ? "always" : notificationMode === "inherit" ? null : notificationMode,
      enabled,
      prompt: prompt.trim() || undefined,
      ignore_selectors: splitLines(ignoreSelectors),
      interaction_steps: compactSteps(steps),
      recipient_ids: recipientIds,
    };
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (projects.isLoading || projects.isError || recipients.isLoading || recipients.isError || !validProject) return;
    if (bulk) {
      void handleBulkSubmit();
      return;
    }
    createSite.mutate(
      { ...sharedFields(), url: normalizeUrl(url), name: name.trim() || undefined },
      { onSuccess: (created) => { saved.current = true; navigate(`/sites/${created.id}`); } },
    );
  }

  async function handleBulkSubmit() {
    const urls = splitLines(bulkUrls).map(normalizeUrl);
    if (urls.length === 0) return;

    setSubmitting(true);
    setFailures([]);
    const base = sharedFields();
    const failed: string[] = [];
    const failedUrls: string[] = [];
    let created = 0;

    // Sequential so the backend isn't hit with a burst and failures map cleanly to each URL.
    for (const target of urls) {
      try {
        await createSite.mutateAsync({ ...base, url: target });
        created += 1;
      } catch (caught) {
        failed.push(`${target} — ${errorMessage(caught, t)}`);
        failedUrls.push(target);
      }
    }

    setSubmitting(false);
    setFailures(failed);
    // Keep only failed URLs for a safe retry. Successful rows already exist.
    setBulkUrls(failedUrls.join("\n"));

    if (created > 0) {
      notify(
        t("addsite.bulkResult", { created, total: urls.length }),
        failed.length ? "error" : "success",
      );
    } else {
      notify(t("addsite.bulkNoneCreated"), "error");
    }
    if (failed.length === 0) { saved.current = true; navigate("/dashboard"); }
  }

  // The operator must enter an organization before adding a site to it.
  if (!inOrg || !canCreateSite(user)) {
    return (
      <EmptyState
        icon={<Building2 className="h-5 w-5" />}
        title={t(inOrg ? "common.readOnly" : "addsite.enterOrgTitle")}
        description={t(inOrg ? "common.readOnly" : "addsite.enterOrgDescription")}
        action={
          <Button onClick={() => navigate(inOrg ? "/dashboard" : "/organizations")}>
            <Building2 className="h-4 w-4" />
            {t(inOrg ? "sitedetail.notFound.back" : "addsite.enterOrgAction")}
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-8">
      <UnsavedChangesDialog blocker={blocker} />
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-100">
            {t("addsite.title")}
          </h1>
          <p className="mt-1 text-sm text-mist-400">{t("addsite.subtitle")}</p>
        </div>
        <label className="flex items-center gap-3 rounded-lg border border-line bg-ink-900/50 px-3.5 py-2.5">
          <span className="text-sm text-mist-300">{t("addsite.bulkAdd")}</span>
          <Switch checked={bulk} onCheckedChange={setBulk} aria-label={t("addsite.bulkAdd")} />
        </label>
      </header>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>{t("addsite.sectionWhatToWatch")}</CardTitle>
            </CardHeader>
            <CardBody className="space-y-5">
              {bulk ? (
                <Field label={t("addsite.urlsLabel")} hint={t("addsite.urlsHint")} htmlFor="urls">
                  <Textarea
                    id="urls"
                    required
                    className="min-h-32"
                    value={bulkUrls}
                    onChange={(event) => setBulkUrls(event.target.value)}
                    placeholder={"https://example.com/pricing\nhttps://example.com/changelog"}
                  />
                </Field>
              ) : (
                <>
                  <Field label={t("addsite.urlLabel")} htmlFor="url">
                    <Input
                      id="url"
                      type="url"
                      required
                      value={url}
                      onChange={(event) => setUrl(event.target.value)}
                      onBlur={() => setUrl(normalizeUrl(url))}
                      placeholder="example.com/pricing"
                    />
                  </Field>
                  <Field
                    label={t("addsite.nameLabel")}
                    hint={t("addsite.nameHint")}
                    htmlFor="name"
                  >
                    <Input
                      id="name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      placeholder={t("addsite.namePlaceholder")}
                    />
                  </Field>
                </>
              )}
              {bulk ? null : (
                <PickerActionPanel
                  title={t("picker.pick.title")}
                  explainer={t("picker.pick.explainer")}
                  actionLabel={t("picker.pick.action")}
                  onAction={() => setPicker("select")}
                  disabled={pickerDisabled}
                  unavailable={pickerUnavailable}
                  blockedHint={urlBlocked}
                >
                  {cssSelector.trim() ? (
                    <div className="flex items-center gap-2">
                      <Badge tone="emerald" className="min-w-0 max-w-full">
                        <span className="sr-only">{t("picker.pick.selectedLabel")}: </span>
                        <span className="truncate" title={cssSelector}>
                          {t("picker.pick.selected", { selector: cssSelector })}
                        </span>
                      </Badge>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setCssSelector("")}
                      >
                        {t("picker.pick.clear")}
                      </Button>
                    </div>
                  ) : (
                    <p className="text-xs text-mist-500">{t("picker.pick.watchingWhole")}</p>
                  )}
                </PickerActionPanel>
              )}
              <Collapsible
                label={t("picker.pick.advanced")}
                defaultOpen={!!cssSelector || bulk || !!pickerUnavailable}
              >
                <Field
                  label={t("addsite.cssSelectorLabel")}
                  hint={t("addsite.cssSelectorHint")}
                  htmlFor="selector"
                >
                  <Input
                    id="selector"
                    value={cssSelector}
                    onChange={(event) => setCssSelector(event.target.value)}
                    placeholder="main .prices"
                  />
                </Field>
              </Collapsible>
              {projects.isLoading ? <Spinner /> : projects.isError ? <ErrorState onRetry={() => void projects.refetch()} /> : null}
              <Field label={t("addsite.projectLabel")} htmlFor="project">
                <Select
                  id="project"
                  value={projectId}
                  disabled={projects.isLoading || projects.isError}
                  onChange={(event) => setProjectId(event.target.value)}
                >
                  {user?.is_admin || user?.is_superadmin ? <option value="">{t("addsite.noProject")}</option> : <option value="" disabled>{t("addsite.projectLabel")}</option>}
                  {(projects.data ?? []).filter((project) => canEditProject(user, project.id)).map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t("addsite.sectionHowItRuns")}</CardTitle>
            </CardHeader>
            <CardBody className="space-y-5">
              <Field label={t("addsite.intervalLabel")} htmlFor="interval">
                <Input
                  id="interval"
                  type="number"
                  min={1}
                  required
                  value={intervalMinutes}
                  onChange={(event) => setIntervalMinutes(Number(event.target.value))}
                />
              </Field>
              <Field label={t("common.analysisMode")} hint={t("common.analysisModeHint")} htmlFor="analysis-mode">
                <Select id="analysis-mode" value={analysisMode} onChange={(event) => { const mode = event.target.value as "ai" | "disabled"; setAnalysisMode(mode); if (mode === "disabled") setNotificationMode("always"); }}>
                  <option value="ai">{t("common.analysisAi")}</option><option value="disabled">{t("common.analysisDisabled")}</option>
                </Select>
              </Field>
              <Field label={t("addsite.notificationsLabel")} htmlFor="mode">
                <Select
                  id="mode"
                  disabled={analysisMode === "disabled"}
                  value={notificationMode}
                  onChange={(event) => setNotificationMode(event.target.value as ModeChoice)}
                >
                  <option value="inherit">{t("addsite.modeInherit")}</option>
                  <option value="only_significant">{t("addsite.modeOnlySignificant")}</option>
                  <option value="always">{t("addsite.modeAlways")}</option>
                </Select>
              </Field>
              <div className="flex items-center justify-between rounded-lg border border-line bg-ink-900/50 px-3.5 py-3">
                <div>
                  <Label htmlFor="enabled">{t("addsite.enabledLabel")}</Label>
                  <p className="text-xs text-mist-500">{t("addsite.enabledHint")}</p>
                </div>
                <Switch id="enabled" checked={enabled} onCheckedChange={setEnabled} />
              </div>
              <Field
                label={t("addsite.promptLabel")}
                hint={t("addsite.promptHint")}
                htmlFor="prompt"
              >
                <Textarea
                  id="prompt"
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder={t("addsite.promptPlaceholder")}
                />
              </Field>
              <EffectiveRulesPanel rules={effectiveRules} />
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{t("addsite.sectionCapture")}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-5">
            {bulk ? null : (
              <PickerActionPanel
                title={t("picker.record.title")}
                explainer={t("picker.record.explainer")}
                actionLabel={t("picker.record.action")}
                onAction={() => setPicker("record")}
                disabled={pickerDisabled}
                unavailable={pickerUnavailable}
                blockedHint={urlBlocked}
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
            )}
            <Collapsible
              label={t("picker.record.advanced")}
              defaultOpen={steps.length > 0 || !!ignoreSelectors || bulk || !!pickerUnavailable}
            >
              <Field
                label={t("addsite.interactionStepsLabel")}
                hint={t("addsite.interactionStepsHint")}
              >
                <InteractionStepsEditor steps={steps} onChange={setSteps} />
              </Field>
              <Field
                label={t("addsite.ignoreSelectorsLabel")}
                hint={t("addsite.ignoreSelectorsHint")}
                htmlFor="ignore"
              >
                <Textarea
                  id="ignore"
                  value={ignoreSelectors}
                  onChange={(event) => setIgnoreSelectors(event.target.value)}
                  placeholder={".cookie-banner\n#ads\nfooter .timestamp"}
                />
              </Field>
            </Collapsible>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("addsite.sectionRecipients")}</CardTitle>
          </CardHeader>
          <CardBody>
            {recipients.isLoading ? <Spinner /> : recipients.isError ? <ErrorState onRetry={() => void recipients.refetch()} /> : (recipients.data ?? []).length === 0 ? (
              <EmptyState
                icon={<Users className="h-5 w-5" />}
                title={t("addsite.noRecipientsTitle")}
                description={t("addsite.noRecipientsDescription")}
              />
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {(recipients.data ?? []).map((recipient) => (
                  <label
                    key={recipient.id}
                    className="flex cursor-pointer items-center gap-3 rounded-lg border border-line bg-ink-900/50 px-3.5 py-3 transition-colors hover:border-brand-500/40"
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-brand-500"
                      checked={recipientIds.includes(recipient.id)}
                      onChange={() => toggleRecipient(recipient.id)}
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-mist-100">
                        {recipient.name ?? recipient.email}
                      </span>
                      {recipient.name ? (
                        <span className="block truncate text-xs text-mist-500">
                          {recipient.email}
                        </span>
                      ) : null}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        {error && !bulk ? <ErrorNote>{error}</ErrorNote> : null}
        {failures.length > 0 ? (
          <Card>
            <CardBody className="space-y-2">
              <p className="text-sm font-medium text-rose-400">
                {tp("addsite.failures", failures.length)}
              </p>
              <ul className="space-y-1 text-xs text-mist-400">
                {failures.map((failure) => (
                  <li key={failure} className="break-words">
                    {failure}
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>
        ) : null}

        <div className="flex items-center gap-3">
          <Button type="submit" size="lg" disabled={createSite.isPending || submitting || projects.isLoading || projects.isError || recipients.isLoading || recipients.isError || !validProject}>
            {bulk ? t("addsite.createSites") : t("addsite.createSite")}
          </Button>
          <Button type="button" variant="ghost" onClick={() => navigate("/dashboard")}>
            {t("common.cancel")}
          </Button>
        </div>
      </form>

      {picker ? (
        <VisualPickerDialog
          open
          mode={picker}
          url={url.trim()}
          onClose={() => setPicker(null)}
          onSelect={setCssSelector}
          onSteps={(recorded) => setSteps((current) => [...current, ...recorded])}
        />
      ) : null}
    </div>
  );
}
