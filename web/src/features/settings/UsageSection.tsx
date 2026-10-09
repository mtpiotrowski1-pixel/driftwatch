import { BarChart3 } from "lucide-react";
import { ReviewAgreement } from "@/components/ReviewAgreement";
import { SettingsSection } from "@/components/ui/settings-section";
import { useT } from "@/i18n";
import type { UsageBucket, UsageSummary } from "@/lib/types";
import { formatCost } from "@/lib/utils";

export function UsageSection({ usage }: { usage?: UsageSummary }) {
  const t = useT();
  return (
    <SettingsSection
      title={t("settings.usage.title")}
      icon={<BarChart3 className="h-4 w-4" />}
      bodyClassName="space-y-5"
    >
      {usage ? (
        <>
          {usage.unknown_cost_calls > 0 ? (
            <p className="text-sm text-mist-400">
              {t("common.unknownCost", {
                count: usage.unknown_cost_calls,
                known: formatCost(usage.known_cost_usd),
              })}
            </p>
          ) : null}
          <div className="grid grid-cols-3 gap-4">
            <UsageStat label={t("settings.usage.totalCost")} value={formatCost(usage.total_cost_usd)} />
            <UsageStat label={t("settings.usage.tokens")} value={usage.total_tokens.toLocaleString()} />
            <UsageStat label={t("settings.usage.calls")} value={usage.calls.toLocaleString()} />
          </div>
          {usage.by_model.length > 0 ? (
            <ul className="mt-5 divide-y divide-line border-t border-line">
              {usage.by_model.map((row) => (
                <li
                  key={row.model}
                  className="flex items-center justify-between gap-4 py-3 text-sm"
                >
                  <span className="truncate font-mono text-mist-300">{row.model}</span>
                  <span className="flex shrink-0 items-center gap-4 text-mist-400">
                    <span>{row.calls.toLocaleString()} {t("settings.usage.callsSuffix")}</span>
                    <span>{row.total_tokens.toLocaleString()} {t("settings.usage.tokensSuffix")}</span>
                    <span className="text-mist-100">{formatCost(row.cost_usd)}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
          <UsageBreakdown title={t("settings.usage.byMonth")} rows={usage.by_month} />
          <UsageBreakdown title={t("settings.usage.bySite")} rows={usage.by_site} />
          <UsageBreakdown title={t("settings.usage.byProject")} rows={usage.by_project} />
          <ReviewAgreement />
        </>
      ) : (
        <p className="text-sm text-mist-500">{t("settings.usage.unavailable")}</p>
      )}
    </SettingsSection>
  );
}

function UsageStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-sm text-mist-400">{label}</p>
      <p className="text-xl font-semibold text-mist-100">{value}</p>
    </div>
  );
}

function UsageBreakdown({ title, rows }: { title: string; rows: UsageBucket[] }) {
  const t = useT();
  if (rows.length === 0) return null;
  return (
    <div className="mt-6">
      <p className="text-sm font-medium text-mist-300">{title}</p>
      <ul className="mt-2 divide-y divide-line border-t border-line">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center justify-between gap-4 py-3 text-sm">
            <span className="truncate text-mist-300">{row.label}</span>
            <span className="flex shrink-0 items-center gap-4 text-mist-400">
              <span>{row.calls.toLocaleString()} {t("settings.usage.callsSuffix")}</span>
              <span>{row.total_tokens.toLocaleString()} {t("settings.usage.tokensSuffix")}</span>
              <span className="text-mist-100">{formatCost(row.cost_usd)}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
