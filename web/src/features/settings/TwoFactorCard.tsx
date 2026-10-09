import { useState, type FormEvent } from "react";
import { ShieldCheck } from "lucide-react";
import { StepUpDialog } from "@/components/StepUpDialog";
import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { SettingsSection } from "@/components/ui/settings-section";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api";
import { useCurrentUser, useTotpDisable, useTotpEnable, useTotpSetup } from "@/lib/queries";
import type { TotpSetup } from "@/lib/types";
import { cn } from "@/lib/utils";

export type TwoFactorEnable = ReturnType<typeof useTotpEnable>;

export function TwoFactorCard({ enable }: { enable: TwoFactorEnable }) {
  const t = useT();
  const { data: user } = useCurrentUser();
  const setup = useTotpSetup();
  const disable = useTotpDisable();
  const { notify } = useToast();

  const [enrollment, setEnrollment] = useState<TotpSetup | null>(null);
  const [code, setCode] = useState("");
  const [enrollmentAuthOpen, setEnrollmentAuthOpen] = useState(false);
  const [disableAuthOpen, setDisableAuthOpen] = useState(false);

  const enabled = user?.totp_enabled ?? false;
  const error =
    (setup.error ?? enable.error ?? disable.error) instanceof ApiError
      ? ((setup.error ?? enable.error ?? disable.error) as ApiError).message
      : null;

  function startEnrollment() {
    setup.mutate(undefined, { onSuccess: (data) => setEnrollment(data) });
  }

  function confirmEnrollment(event: FormEvent) {
    event.preventDefault();
    enable.mutate(code.trim(), {
      onSuccess: () => {
        setEnrollment(null);
        setCode("");
        notify(t("twofa.manage.enabled"));
      },
    });
  }

  function confirmDisable() {
    disable.mutate(undefined, {
      onSuccess: () => {
        notify(t("twofa.manage.disabled"));
      },
    });
  }

  return (
    <SettingsSection title={t("twofa.manage.title")} icon={<ShieldCheck className="h-4 w-4" />} bodyClassName="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <ShieldCheck
          className={cn("h-4 w-4", enabled ? "text-emerald-400" : "text-mist-500")}
        />
        <span className={enabled ? "text-emerald-400" : "text-mist-400"}>
          {enabled ? t("twofa.manage.statusOn") : t("twofa.manage.statusOff")}
        </span>
      </div>
      <p className="text-sm text-mist-500">{t("twofa.manage.description")}</p>

      {!enabled && !enrollment && !enable.data ? (
        <Button onClick={() => setEnrollmentAuthOpen(true)} disabled={setup.isPending}>
          <ShieldCheck className="h-4 w-4" />
          {t("twofa.manage.enable")}
        </Button>
      ) : null}

      {enrollmentAuthOpen ? (
        <StepUpDialog
          title={t("twofa.manage.enable")}
          description={t("twofa.manage.description")}
          submitLabel={t("twofa.manage.enable")}
          onVerified={startEnrollment}
          onClose={() => setEnrollmentAuthOpen(false)}
        />
      ) : null}

      {enrollment ? (
        <form onSubmit={confirmEnrollment} className="space-y-3">
          <p className="text-sm text-mist-400">{t("twofa.manage.scan")}</p>
          <img
            src={enrollment.qr_svg_data_uri}
            alt={t("twofa.manage.qrAlt")}
            className="h-44 w-44 rounded-lg bg-white p-2"
          />
          <p className="text-xs text-mist-500">{t("twofa.manage.manualEntry")}</p>
          <code className="block break-all rounded-lg border border-line bg-ink-900/60 px-3 py-2 font-mono text-xs text-mist-200">
            {enrollment.secret}
          </code>
          <Field label={t("twofa.manage.codeLabel")} htmlFor="totp_code">
            <Input
              id="totp_code"
              required
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="123456"
            />
          </Field>
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <div className="flex gap-2">
            <Button type="submit" disabled={enable.isPending}>
              {t("twofa.manage.confirm")}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEnrollment(null)}>
              {t("common.cancel")}
            </Button>
          </div>
        </form>
      ) : null}

      {enabled ? (
        <div className="space-y-3">
          <p className="text-sm text-mist-500">{t("twofa.manage.disableHint")}</p>
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <Button
            type="button"
            variant="danger"
            disabled={disable.isPending}
            onClick={() => setDisableAuthOpen(true)}
          >
            {t("twofa.manage.disable")}
          </Button>
        </div>
      ) : null}

      {disableAuthOpen ? (
        <StepUpDialog
          title={t("twofa.manage.disable")}
          description={t("twofa.manage.disableHint")}
          submitLabel={t("twofa.manage.disable")}
          submitVariant="danger"
          onVerified={confirmDisable}
          onClose={() => setDisableAuthOpen(false)}
        />
      ) : null}

      {error && !enrollment && !enabled ? <ErrorNote>{error}</ErrorNote> : null}
    </SettingsSection>
  );
}
