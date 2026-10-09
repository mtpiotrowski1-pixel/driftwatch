import { useId } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, type TooltipProps } from "recharts";

import { useT } from "@/i18n";
import type { Change } from "@/lib/types";
import { activeLocale, parseApiTimestamp } from "@/lib/utils";

const DAYS = 14;

interface DayBucket {
  label: string;
  count: number;
}

// Local calendar day (YYYY-MM-DD). Bucketing and labelling must agree on the
// timezone, or a change near midnight lands in the wrong column.
function localDayKey(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function buildSeries(changes: Change[]): DayBucket[] {
  const counts = new Map<string, number>();
  for (const change of changes) {
    const key = localDayKey(parseApiTimestamp(change.created_at));
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  const locale = activeLocale();
  const today = new Date();
  const days: DayBucket[] = [];
  for (let offset = DAYS - 1; offset >= 0; offset -= 1) {
    const day = new Date(today);
    day.setDate(today.getDate() - offset);
    days.push({
      label: day.toLocaleDateString(locale, { day: "numeric", month: "short" }),
      count: counts.get(localDayKey(day)) ?? 0,
    });
  }
  return days;
}

function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  const t = useT();
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-ink-850 px-3 py-2 text-xs shadow-xl">
      <p className="text-mist-400">{label}</p>
      <p className="font-medium text-mist-100">
        {t("dashboard.activityTooltip", { count: payload[0].value ?? 0 })}
      </p>
    </div>
  );
}

export function ActivityChart({ changes }: { changes: Change[] }) {
  const t = useT();
  const captionId = useId();
  const series = buildSeries(changes);
  const total = series.reduce((sum, day) => sum + day.count, 0);
  return (
    <figure className="min-w-0" aria-labelledby={captionId}>
      <figcaption id={captionId} className="sr-only">
        {t("dashboard.activitySummary", { count: total, days: DAYS })}
      </figcaption>
      <div className="h-[120px] min-w-0" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <defs>
              <linearGradient id="activity-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--color-brand-400)" stopOpacity={0.5} />
                <stop offset="100%" stopColor="var(--color-brand-400)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--color-mist-500)", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--color-line)" }} />
            <Area
              type="monotone"
              dataKey="count"
              stroke="var(--color-brand-400)"
              strokeWidth={2}
              fill="url(#activity-fill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <thead>
          <tr>
            <th>{t("dashboard.activityDay")}</th>
            <th>{t("dashboard.activityCount")}</th>
          </tr>
        </thead>
        <tbody>
          {series.map((day) => (
            <tr key={day.label}>
              <td>{day.label}</td>
              <td>{day.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
