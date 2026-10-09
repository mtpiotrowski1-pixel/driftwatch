import { errorMessage } from "@/lib/errors";
import { useDialogState } from "@/lib/useDialogState";
import { Building2, LogIn, Pencil, Plus, ShieldOff } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "@/lib/navigation";

import { StepUpDialog } from "@/components/StepUpDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardBody } from "@/components/ui/card";
import { ClickableCard } from "@/components/ui/clickable-card";
import { Dialog, type DialogVisibilityProps } from "@/components/ui/dialog";
import {
  CardGridSkeleton,
  EmptyState,
  ErrorNote,
  ErrorState,
  PageLoader,
  Spinner,
} from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useT, useTp } from "@/i18n";
import {
  ApiError,
  RequestContextChangedError,
  instanceRequestContext,
} from "@/lib/api";
import {
  useCreateOrganization,
  useCurrentUser,
  useOrganizations,
  usePlans,
  useUpdateOrganization,
} from "@/lib/queries";
import { OrganizationTransitionCancelledError, useOrg } from "@/lib/orgContext";
import type { Organization } from "@/lib/types";
import { parseLimit } from "@/lib/utils";

export function Organizations() {
  const t = useT();
  const tp = useTp();
  const { data: currentUser, isLoading: meLoading } = useCurrentUser();
  const organizations = useOrganizations(currentUser?.is_superadmin ?? false);
  const createOrganization = useCreateOrganization();
  const { enterOrg } = useOrg();
  const navigate = useNavigate();
  const { notify } = useToast();

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [pendingCreateName, setPendingCreateName] = useState<string | null>(null);
  const editingDialog = useDialogState<Organization | null>(null);
  const { value: editing, setValue: setEditing } = editingDialog;

  function handleManage(organization: Organization) {
    void enterOrg({ id: organization.id, name: organization.name })
      .then(() => navigate("/dashboard"))
      .catch((error: unknown) => {
        if (error instanceof OrganizationTransitionCancelledError) return;
        notify(
          error instanceof RequestContextChangedError
            ? t("common.contextChanged")
            : error instanceof ApiError
              ? error.message
              : t("common.requestFailed"),
          "error",
        );
      });
  }

  const createError =
    createOrganization.error ? errorMessage(createOrganization.error, t) : null;

  if (meLoading) return <PageLoader label={t("organizations.loading")} />;

  if (!currentUser?.is_superadmin) {
    return (
      <EmptyState
        icon={<ShieldOff className="h-5 w-5" />}
        title={t("organizations.superadminRequired.title")}
        description={t("organizations.superadminRequired.description")}
      />
    );
  }

  if (organizations.isLoading) return <CardGridSkeleton />;
  if (organizations.isError) return <ErrorState onRetry={() => organizations.refetch()} />;

  const orgList = organizations.data ?? [];

  function handleCreate(event: FormEvent) {
    event.preventDefault();
    setPendingCreateName(name.trim());
  }

  function createPendingOrganization() {
    if (!pendingCreateName) return;
    createOrganization.mutate(
      { name: pendingCreateName },
      {
        onSuccess: () => {
          setName("");
          setCreateOpen(false);
          notify(t("organizations.created"));
        },
      },
    );
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-100">
            {t("organizations.title")}
          </h1>
          <p className="mt-1 text-sm text-mist-400">{t("organizations.subtitle")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          {t("organizations.newOrganization")}
        </Button>
      </header>

      {orgList.length === 0 ? (
        <EmptyState
          icon={<Building2 className="h-5 w-5" />}
          title={t("organizations.empty.title")}
          description={t("organizations.empty.description")}
          action={
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              {t("organizations.newOrganization")}
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {orgList.map((org) => {
            const isOwn = org.id === currentUser.organization_id;
            return (
              <ClickableCard
                key={org.id}
                label={t("organizations.openAria", { name: org.name })}
                onOpen={() => handleManage(org)}
              >
                <CardBody className="space-y-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-mist-100">{org.name}</p>
                      <p className="mt-0.5 text-xs text-mist-500">
                        {tp("organizations.memberCount", org.member_count)} ·{" "}
                        {tp("organizations.siteCount", org.site_count)}
                      </p>
                    </div>
                    <Badge tone={org.is_active ? "emerald" : "rose"}>
                      {org.is_active
                        ? t("organizations.state.active")
                        : t("organizations.state.suspended")}
                    </Badge>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <Badge tone="brand">{org.plan}</Badge>
                    {org.billing_managed ? (
                      <Badge tone={org.billing_suspended ? "rose" : "neutral"}>
                        {t(
                          org.billing_suspended
                            ? "organizations.billing.suspended"
                            : "organizations.billing.managed",
                        )}
                      </Badge>
                    ) : null}
                    <span className="text-mist-500">
                      {t("organizations.usage.sites", {
                        used: org.site_count,
                        limit: org.max_sites ?? "∞",
                      })}
                    </span>
                    <span className="text-mist-500">
                      {t("organizations.usage.members", {
                        used: org.member_count,
                        limit: org.max_members ?? "∞",
                      })}
                    </span>
                    <span className="text-mist-500">
                      {t("organizations.usage.ai", {
                        used: org.ai_checks_this_month,
                        limit: org.monthly_ai_check_limit ?? "∞",
                      })}
                    </span>
                  </div>

                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700">
                      <LogIn className="h-3.5 w-3.5" />
                      {isOwn ? t("organizations.yours") : t("organizations.enter")}
                    </span>
                    <div className="pointer-events-auto relative z-10 flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t("organizations.editAria", { name: org.name })}
                        onClick={() => setEditing(org)}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardBody>
              </ClickableCard>
            );
          })}
        </div>
      )}

      <Dialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title={t("organizations.create.title")}
        description={t("organizations.create.description")}
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <Field label={t("organizations.field.name")} htmlFor="organization-name">
            <Input
              id="organization-name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("organizations.create.namePlaceholder")}
            />
          </Field>
          {createError ? <ErrorNote>{createError}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={createOrganization.isPending}>
              {createOrganization.isPending ? <Spinner /> : null}
              {t("organizations.create.submit")}
            </Button>
          </div>
        </form>
      </Dialog>

      {pendingCreateName ? (
        <StepUpDialog
          title={t("organizations.create.confirmTitle")}
          description={t("organizations.create.confirmDescription")}
          submitLabel={t("organizations.create.submit")}
          requestContext={instanceRequestContext}
          onVerified={createPendingOrganization}
          onClose={() => setPendingCreateName(null)}
        />
      ) : null}

      {editing ? (
        <EditOrganizationDialog
          key={editingDialog.key}
          open={editingDialog.open}
          onClosed={editingDialog.onClosed}
          organization={editing}
          onClose={editingDialog.close}
          onSaved={() => {
            setEditing(null);
            notify(t("organizations.updated"));
          }}
        />
      ) : null}
    </div>
  );
}

function EditOrganizationDialog({
  open,
  onClosed,
  organization,
  onClose,
  onSaved,
}: {
  organization: Organization;
  onClose: () => void;
  onSaved: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const update = useUpdateOrganization(organization.id);
  const plans = usePlans();

  const [name, setName] = useState(organization.name);
  const [active, setActive] = useState(organization.is_active);
  const [plan, setPlan] = useState(organization.plan);
  const [planId, setPlanId] = useState(organization.plan_id?.toString() ?? "");
  const [maxSites, setMaxSites] = useState(organization.max_sites?.toString() ?? "");
  const [maxMembers, setMaxMembers] = useState(organization.max_members?.toString() ?? "");
  const [aiLimit, setAiLimit] = useState(organization.monthly_ai_check_limit?.toString() ?? "");
  const [pendingPatch, setPendingPatch] = useState<{
    name?: string;
    is_active?: boolean;
    plan?: string;
    plan_id?: number | null;
    max_sites?: number | null;
    max_members?: number | null;
    monthly_ai_check_limit?: number | null;
  } | null>(null);

  const error = update.error ? errorMessage(update.error, t) : null;

  function handlePlanChange(value: string) {
    setPlanId(value);
    const chosen = (plans.data ?? []).find((candidate) => candidate.id === Number(value));
    if (chosen) {
      setPlan(chosen.key);
      setMaxSites(chosen.max_sites?.toString() ?? "");
      setMaxMembers(chosen.max_members?.toString() ?? "");
      setAiLimit(chosen.monthly_ai_check_limit?.toString() ?? "");
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const patch: NonNullable<typeof pendingPatch> = {};
    const nextName = name.trim();
    const nextPlan = plan.trim() || "free";
    const nextPlanId = planId === "" ? null : Number(planId);
    const nextMaxSites = parseLimit(maxSites);
    const nextMaxMembers = parseLimit(maxMembers);
    const nextAiLimit = parseLimit(aiLimit);
    if (nextName !== organization.name) patch.name = nextName;
    if (active !== organization.is_active) patch.is_active = active;
    if (!organization.billing_managed) {
      if (nextPlan !== organization.plan) patch.plan = nextPlan;
      if (nextPlanId !== organization.plan_id) patch.plan_id = nextPlanId;
      if (nextMaxSites !== organization.max_sites) patch.max_sites = nextMaxSites;
      if (nextMaxMembers !== organization.max_members) patch.max_members = nextMaxMembers;
      if (nextAiLimit !== organization.monthly_ai_check_limit) {
        patch.monthly_ai_check_limit = nextAiLimit;
      }
    }
    if (Object.keys(patch).length === 0) {
      onSaved();
      return;
    }
    const entitlementChange = Object.keys(patch).some((key) => key !== "name");
    if (entitlementChange) {
      setPendingPatch(patch);
      return;
    }
    update.mutate(patch, { onSuccess: onSaved });
  }

  return (
    <>
      <Dialog open={open} onClosed={onClosed} onOpenChange={(open) => !open && onClose()} title={t("organizations.edit.title")}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label={t("organizations.field.name")} htmlFor="edit-organization-name">
          <Input
            id="edit-organization-name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field
          label={t("organizations.field.planSelect")}
          hint={t(
            organization.billing_managed
              ? "organizations.billing.managedHint"
              : "organizations.field.planSelectHint",
          )}
          htmlFor="edit-organization-plan-select"
        >
          <Select
            id="edit-organization-plan-select"
            value={planId}
            disabled={organization.billing_managed}
            onChange={(event) => handlePlanChange(event.target.value)}
          >
            <option value="">{t("organizations.field.noPlan")}</option>
            {(plans.data ?? []).map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label={t("organizations.field.plan")}
          hint={t("organizations.field.planHint")}
          htmlFor="edit-organization-plan"
        >
          <Input
            id="edit-organization-plan"
            value={plan}
            disabled={organization.billing_managed}
            onChange={(event) => setPlan(event.target.value)}
            placeholder="business"
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label={t("organizations.field.maxSites")}
            hint={t("organizations.field.limitHint")}
            htmlFor="edit-organization-max-sites"
          >
            <Input
              id="edit-organization-max-sites"
              type="number"
              min={0}
              value={maxSites}
              disabled={organization.billing_managed}
              onChange={(event) => setMaxSites(event.target.value)}
              placeholder="∞"
            />
          </Field>
          <Field
            label={t("organizations.field.maxMembers")}
            hint={t("organizations.field.limitHint")}
            htmlFor="edit-organization-max-members"
          >
            <Input
              id="edit-organization-max-members"
              type="number"
              min={0}
              value={maxMembers}
              disabled={organization.billing_managed}
              onChange={(event) => setMaxMembers(event.target.value)}
              placeholder="∞"
            />
          </Field>
          <Field
            label={t("organizations.field.aiLimit")}
            hint={t("organizations.field.limitHint")}
            htmlFor="edit-organization-ai-limit"
          >
            <Input
              id="edit-organization-ai-limit"
              type="number"
              min={0}
              value={aiLimit}
              disabled={organization.billing_managed}
              onChange={(event) => setAiLimit(event.target.value)}
              placeholder="∞"
            />
          </Field>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-line bg-ink-900/50 px-3.5 py-3">
          <div>
            <p className="text-sm font-medium text-mist-300">{t("organizations.field.active")}</p>
            <p className="text-xs text-mist-500">
              {t(
                organization.billing_suspended
                  ? "organizations.billing.suspendedHint"
                  : "organizations.field.activeHint",
              )}
            </p>
          </div>
          <Switch
            aria-label={t("organizations.field.active")}
            checked={active}
            disabled={organization.billing_suspended}
            onCheckedChange={setActive}
          />
        </div>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? <Spinner /> : null}
            {t("organizations.edit.submit")}
          </Button>
        </div>
      </form>
      </Dialog>
      {open && pendingPatch ? (
        <StepUpDialog
          title={t("organizations.edit.confirmTitle")}
          description={t("organizations.edit.confirmDescription")}
          submitLabel={t("organizations.edit.submit")}
          requestContext={instanceRequestContext}
          onVerified={() => update.mutate(pendingPatch, { onSuccess: onSaved })}
          onClose={() => setPendingPatch(null)}
        />
      ) : null}
    </>
  );
}
