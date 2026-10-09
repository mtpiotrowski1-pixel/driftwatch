import { Badge } from "@/components/ui/badge";
import { useT } from "@/i18n";
import type { Change } from "@/lib/types";

type BadgeChange = Pick<Change, "significant" | "ai_error" | "notification_error" | "analysis_status">;

export function changeStatus(change: BadgeChange): {
  tone: "amber" | "neutral" | "brand" | "rose";
  labelKey: string;
} {
  if (change.notification_error) {
    return { tone: "rose", labelKey: "sitedetail.badge.needsAttention" };
  }
  if (change.analysis_status === "disabled") return { tone: "neutral", labelKey: "sitedetail.badge.withoutAi" };
  if (change.analysis_status === "quota_blocked") return { tone: "amber", labelKey: "sitedetail.badge.quotaPaused" };
  if (change.ai_error) return { tone: "rose", labelKey: "sitedetail.badge.needsAttention" };
  if (change.analysis_status === "processing") return { tone: "brand", labelKey: "sitedetail.badge.processing" };
  if (change.analysis_status === "pending") return { tone: "neutral", labelKey: "sitedetail.badge.pending" };
  if (change.significant === null) {
    return { tone: "neutral", labelKey: "sitedetail.badge.notAnalyzed" };
  }
  if (change.significant) return { tone: "amber", labelKey: "sitedetail.badge.significant" };
  return { tone: "neutral", labelKey: "sitedetail.badge.notSignificant" };
}

export function ChangeBadge({ change }: { change: BadgeChange }) {
  const t = useT();
  const { tone, labelKey } = changeStatus(change);
  return <Badge tone={tone}>{t(labelKey)}</Badge>;
}
