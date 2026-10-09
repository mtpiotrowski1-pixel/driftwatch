import { Field, Input } from "@/components/ui/field";
import { useT } from "@/i18n";
import type { Recipient } from "@/lib/types";
import type { SettingsDraft, NumberSettingsFields } from "./useSettingsDraft";
type AlertDraft = NumberSettingsFields & Pick<SettingsDraft, "technicalValue" | "toggleTechnical">;

export function TechnicalAlerts({ draft, recipients }: { draft: AlertDraft; recipients: Recipient[] }) {
  const t = useT();
  const { numberValue, setNumberField, technicalValue, toggleTechnical } = draft;
  return (
    <>
      <Field
        label={t("settings.email.downThreshold")}
        hint={t("settings.email.downThresholdHint")}
        htmlFor="site_down_failure_threshold"
      >
        <Input
          id="site_down_failure_threshold"
          type="number"
          min={1}
          value={numberValue("site_down_failure_threshold")}
          onChange={(event) =>
            setNumberField("site_down_failure_threshold", event.target.value)
          }
          placeholder="5"
        />
      </Field>
      <div />
      <div className="lg:col-span-2">
        <Field
          label={t("settings.email.technicalRecipients")}
          hint={t("settings.email.technicalRecipientsHint")}
        >
          {recipients.length === 0 ? (
            <p className="text-sm text-mist-500">{t("settings.email.noRecipients")}</p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {recipients.map((recipient) => (
                <label
                  key={recipient.id}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border border-line bg-ink-900/50 px-3.5 py-2.5 transition-colors hover:border-brand-500/40"
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-brand-500"
                    checked={technicalValue.includes(recipient.id)}
                    onChange={() => {
                      toggleTechnical(recipient.id);
                    }}
                  />
                  <span className="min-w-0 truncate text-sm text-mist-100">
                    {recipient.name ?? recipient.email}
                  </span>
                </label>
              ))}
            </div>
          )}
        </Field>
      </div>

    </>
  );
}
