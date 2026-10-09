import { Check, ShieldAlert } from "lucide-react";
import { StepUpDialog } from "@/components/StepUpDialog";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorState, PageLoader } from "@/components/ui/feedback";
import { useT } from "@/i18n";
import { instanceRequestContext, organizationRequestContext } from "@/lib/api";
import { useCurrentUser, useFactoryDefaults, useRecipients, useSettings, useUsage } from "@/lib/queries";
import { ChangePasswordCard } from "./ChangePasswordCard";
import { ConfigurationForm } from "./ConfigurationForm";
import { OperationsCard } from "./OperationsCard";
import { PreferencesCard } from "./PreferencesCard";
import { TwoFactorCard, type TwoFactorEnable } from "./TwoFactorCard";
import { UsageSection } from "./UsageSection";
import { useSettingsDraft } from "./useSettingsDraft";

/** Resolve access and organization context once, then compose settings domains. */
export function SettingsWorkspace({ enable }: { enable: TwoFactorEnable }) {
  const t = useT();
  const { data: user, isLoading: userLoading } = useCurrentUser();
  const organizationId = user?.is_superadmin ? user.acting_organization_id : user?.organization_id;
  const requestContext = organizationId == null
    ? instanceRequestContext
    : organizationRequestContext(organizationId);
  const settings = useSettings(requestContext, user != null);
  const usage = useUsage();
  const recipients = useRecipients();
  const isAdmin = Boolean(user?.is_admin || user?.is_superadmin);
  const factory = useFactoryDefaults(isAdmin);
  const stored = settings.data ?? {};
  const draft = useSettingsDraft(stored, requestContext);
  const isPlatformScope = user?.is_superadmin === true && user.acting_organization_id == null;

  if (userLoading || settings.isLoading) return <PageLoader label={t("settings.loading")} />;
  if (isAdmin && settings.isError) return <ErrorState onRetry={() => settings.refetch()} />;

  return (
    <div className="space-y-8">
      <Dialog
        open={draft.blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open) draft.blocker.reset?.();
        }}
        title={t("common.unsaved.title")}
        description={t("common.unsaved.body")}
      >
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => draft.blocker.reset?.()}>
            {t("common.unsaved.stay")}
          </Button>
          <Button variant="danger" onClick={() => draft.blocker.proceed?.()}>
            {t("common.unsaved.leave")}
          </Button>
        </div>
      </Dialog>
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-100">{t("settings.title")}</h1>
          <p className="mt-1 text-sm text-mist-400">{t("settings.subtitle")}</p>
        </div>
        {draft.saved ? (
          <span className="inline-flex items-center gap-1.5 text-sm text-emerald-400">
            <Check className="h-4 w-4" />
            {t("settings.saved")}
          </span>
        ) : null}
      </header>
      {isAdmin ? (
        <ConfigurationForm
          draft={draft}
          stored={stored}
          requestContext={requestContext}
          isPlatformScope={isPlatformScope}
          factoryDefaults={factory.data}
          recipients={recipients.data ?? []}
        />
      ) : (
        <div className="flex items-center gap-3 rounded-lg border border-line-strong bg-ink-900 px-4 py-3 text-sm text-mist-400 shadow-card">
          <ShieldAlert className="h-4 w-4 shrink-0 text-mist-500" />
          {t("settings.adminOnly")}
        </div>
      )}
      <h2 className="dw-text-surface dw-section-heading font-mono text-xs font-semibold uppercase text-mist-400">
        {t("settings.group.account")}
      </h2>
      <PreferencesCard />
      <ChangePasswordCard />
      <TwoFactorCard enable={enable} />
      {isAdmin ? (
        <h2 className="dw-text-surface dw-section-heading font-mono text-xs font-semibold uppercase text-mist-400">
          {t("settings.group.data")}
        </h2>
      ) : null}
      {isPlatformScope ? <OperationsCard /> : null}
      {isAdmin ? <UsageSection usage={usage.data} /> : null}
      {draft.pendingSecretSave ? (
        <StepUpDialog
          title={t("settings.security.confirmTitle")}
          description={t("settings.security.confirmDescription")}
          submitLabel={t("settings.security.confirmSubmit")}
          requestContext={requestContext}
          onVerified={draft.confirmSensitiveSave}
          onClose={draft.cancelSensitiveSave}
        />
      ) : null}
    </div>
  );
}
