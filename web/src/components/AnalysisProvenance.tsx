import { Collapsible } from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import type { AnalysisRun } from "@/lib/types";

export function AnalysisProvenance({ run }: { run: AnalysisRun }) {
  const t = useT();
  const unknown = t("common.unknown");
  const fields = [
    { label: t("common.model"), value: run.model ?? unknown },
    { label: t("common.rulesSource"), value: run.rules_source ?? unknown },
    { label: t("common.rulesVersion"), value: run.rules_version ?? unknown, hash: true },
    { label: t("common.inputHash"), value: run.input_sha256 ?? unknown, hash: true },
    {
      label: t("common.inputTruncated"),
      value: run.input_truncated == null ? unknown : t(run.input_truncated ? "common.yes" : "common.no"),
    },
    { label: t("common.usageRecord"), value: run.usage_id ?? unknown },
  ];

  return (
    <Collapsible label={t("common.analysisProvenance")}>
      <dl className="grid gap-3 text-xs sm:grid-cols-2">
        {fields.map(({ label, value, hash }) => (
          <div key={label} className={hash ? "sm:col-span-2" : undefined}>
            <dt className="text-mist-500">{label}</dt>
            <dd className={hash ? "break-all font-mono text-mist-200" : "break-words text-mist-200"}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
      {run.system_prompt != null ? (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer font-medium text-mist-300">{t("common.systemPrompt")}</summary>
          <pre className="mt-2 whitespace-pre-wrap break-words rounded-md bg-ink-850 p-3 text-mist-400">
            {run.system_prompt}
          </pre>
        </details>
      ) : (
        <p className="mt-3 text-xs text-mist-500">{t("common.legacyProvenance")}</p>
      )}
    </Collapsible>
  );
}
