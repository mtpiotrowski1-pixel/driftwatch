import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { relativeTime } from "@/lib/utils";

interface DataFreshnessProps {
  updatedAt: number;
  fetching: boolean;
  stale: boolean;
  onRefresh: () => void;
}

export function DataFreshness({ updatedAt, fetching, stale, onRefresh }: DataFreshnessProps) {
  const t = useT();
  const time = updatedAt ? relativeTime(new Date(updatedAt).toISOString()) : "—";
  return (
    <div className="dw-text-surface flex w-fit max-w-full flex-wrap items-center gap-3 text-xs text-mist-500" role="status">
      <span>{stale ? t("common.staleData") : t("common.updatedAt", { time })}</span>
      <Button variant="ghost" size="sm" disabled={fetching} onClick={onRefresh}>
        <RefreshCw className="h-3.5 w-3.5" />
        {t("common.refresh")}
      </Button>
    </div>
  );
}
