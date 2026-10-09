import { Gauge } from "lucide-react";
import { Field, Input } from "@/components/ui/field";
import { SettingsSection } from "@/components/ui/settings-section";
import { useT } from "@/i18n";
import type { NumberSettingsFields } from "./useSettingsDraft";

export function CaptureSection({ draft }: { draft: NumberSettingsFields }) {
  const t = useT();
  const { numberValue, setNumberField } = draft;
  return (
    <SettingsSection title={t("settings.capture.title")} icon={<Gauge className="h-4 w-4" />} bodyClassName="grid gap-5 lg:grid-cols-2">
      {/* Capture timing and retention tune the shared engine, so only the
                      operator sets them; organizations cannot override them. */}

      <Field label={t("settings.capture.timeout")} htmlFor="capture_timeout_seconds">
        <Input
          id="capture_timeout_seconds"
          type="number"
          min={1}
          value={numberValue("capture_timeout_seconds")}
          onChange={(event) => setNumberField("capture_timeout_seconds", event.target.value)}
          placeholder="30"
        />
      </Field>
      <Field label={t("settings.capture.settle")} htmlFor="capture_settle_ms">
        <Input
          id="capture_settle_ms"
          type="number"
          min={0}
          value={numberValue("capture_settle_ms")}
          onChange={(event) => setNumberField("capture_settle_ms", event.target.value)}
          placeholder="500"
        />
      </Field>
      <Field
        label={t("settings.capture.minInterval")}
        hint={t("settings.capture.minIntervalHint")}
        htmlFor="capture_min_interval_seconds"
      >
        <Input
          id="capture_min_interval_seconds"
          type="number"
          min={0}
          value={numberValue("capture_min_interval_seconds")}
          onChange={(event) =>
            setNumberField("capture_min_interval_seconds", event.target.value)
          }
          placeholder="5"
        />
      </Field>
      <Field label={t("settings.capture.jitter")} hint={t("settings.capture.jitterHint")} htmlFor="capture_jitter_ms">
        <Input
          id="capture_jitter_ms"
          type="number"
          min={0}
          value={numberValue("capture_jitter_ms")}
          onChange={(event) => setNumberField("capture_jitter_ms", event.target.value)}
          placeholder="0"
        />
      </Field>
      <Field
        label={t("settings.capture.retention")}
        hint={t("settings.capture.retentionHint")}
        htmlFor="snapshot_retention"
      >
        <Input
          id="snapshot_retention"
          type="number"
          min={1}
          value={numberValue("snapshot_retention")}
          onChange={(event) => setNumberField("snapshot_retention", event.target.value)}
          placeholder="20"
        />
      </Field>

      <Field label={t("settings.capture.inputPrice")} htmlFor="openai_price_input_per_1m">
        <Input
          id="openai_price_input_per_1m"
          type="number"
          min={0}
          step={0.01}
          value={numberValue("openai_price_input_per_1m")}
          onChange={(event) => setNumberField("openai_price_input_per_1m", event.target.value)}
          placeholder="0.15"
        />
      </Field>
      <Field label={t("settings.capture.outputPrice")} htmlFor="openai_price_output_per_1m">
        <Input
          id="openai_price_output_per_1m"
          type="number"
          min={0}
          step={0.01}
          value={numberValue("openai_price_output_per_1m")}
          onChange={(event) => setNumberField("openai_price_output_per_1m", event.target.value)}
          placeholder="0.60"
        />
      </Field>
      <p className="text-xs text-mist-500 lg:col-span-2">{t("settings.capture.priceScope")}</p>
    </SettingsSection>
  );
}
