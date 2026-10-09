import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorState, PageLoader } from "@/components/ui/feedback";
import { SettingsWorkspace } from "@/features/settings/SettingsWorkspace";
import { TwoFactorCard, type TwoFactorEnable } from "@/features/settings/TwoFactorCard";
import { useT } from "@/i18n";
import { useCurrentUser, useTotpEnable } from "@/lib/queries";

export { buildSettingsPayload } from "@/features/settings/model";
export { ConfigurationInput } from "@/features/settings/controls";

export function SettingsPage() {
  const t = useT();
  const { data: user, isLoading, isError, refetch } = useCurrentUser();
  // The enrollment view is replaced after /auth/me confirms MFA. Keep the
  // one-time result above that boundary until the user saves their codes.
  const enable = useTotpEnable();

  return (
    <>
      {isLoading ? <PageLoader label={t("settings.loading")} /> : isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : user?.mfa_enrollment_required ? (
        <RequiredMfaEnrollment enable={enable} />
      ) : <SettingsWorkspace enable={enable} />}
      {enable.data ? (
        <Dialog
          open
          dismissible={false}
          onOpenChange={() => undefined}
          title={t("twofa.manage.recoveryTitle")}
          description={t("twofa.manage.recoveryHint")}
        >
          <ul className="mb-6 grid grid-cols-2 gap-2 rounded-lg border border-line bg-ink-850 p-4 font-mono text-sm text-mist-100">
            {enable.data.recovery_codes.map((recoveryCode) => (
              <li key={recoveryCode}>{recoveryCode}</li>
            ))}
          </ul>
          <Button onClick={enable.reset} className="w-full">
            {t("twofa.manage.recoveryDone")}
          </Button>
        </Dialog>
      ) : null}
    </>
  );
}

function RequiredMfaEnrollment({ enable }: { enable: TwoFactorEnable }) {
  const t = useT();
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-mist-100">
          {t("twofa.required.title")}
        </h1>
        <p className="mt-2 text-sm leading-6 text-mist-400">
          {t("twofa.required.description")}
        </p>
      </header>
      <TwoFactorCard enable={enable} />
    </div>
  );
}
