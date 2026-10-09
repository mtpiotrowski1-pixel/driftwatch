import { Button } from "@/components/ui/button";
import { DataFreshness } from "@/components/DataFreshness";
import { Bell } from "lucide-react";
import { useState } from "react";
import { Link } from "@/lib/navigation";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, PageLoader } from "@/components/ui/feedback";
import { useT } from "@/i18n";
import { useNotifications } from "@/lib/queries";
import type { Notification } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

const FILTERS: { labelKey: string; status?: string }[] = [
  { labelKey: "notifications.filter.all" },
  { labelKey: "notifications.filter.sent", status: "sent" },
  { labelKey: "notifications.filter.failed", status: "failed" },
  { labelKey: "notifications.filter.skipped", status: "skipped" },
];

const SKIPPED_NO_RECIPIENTS = "no recipients resolved for this site or its project";

export const STATUS_TONE: Record<Notification["status"], "emerald" | "rose" | "neutral"> = {
  sent: "emerald",
  failed: "rose",
  skipped: "neutral",
};

export function Notifications() {
  const t = useT();
  const [status, setStatus] = useState<string | undefined>(undefined);
  const notifications = useNotifications(status);

  const rows = notifications.data?.pages.flat() ?? [];

  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-mist-100">{t("notifications.title")}</h1>
          <p className="mt-1 text-sm text-mist-400">{t("notifications.subtitle")}</p>
        </div>
        <div
          className="flex w-full gap-1 overflow-x-auto rounded-lg border border-line bg-ink-900 p-1 sm:w-auto"
          role="group"
          aria-label={t("notifications.filterLabel")}
        >
          {FILTERS.map((filter) => (
            <button
              key={filter.labelKey}
              type="button"
              onClick={() => setStatus(filter.status)}
              aria-pressed={status === filter.status}
              className={cn(
                "min-h-10 shrink-0 rounded-md px-3.5 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
                status === filter.status
                  ? "bg-brand-500 text-[#151915]"
                  : "text-mist-400 hover:bg-ink-850 hover:text-mist-100",
              )}
            >
              {t(filter.labelKey)}
            </button>
          ))}
        </div>
      </header>

      <DataFreshness updatedAt={notifications.dataUpdatedAt} fetching={notifications.isFetching} stale={notifications.isRefetchError} onRefresh={() => void notifications.refetch()} />

      {notifications.isLoading ? (
        <PageLoader label={t("notifications.loading")} />
      ) : notifications.isError ? (
        <ErrorState onRetry={() => notifications.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<Bell className="h-5 w-5" />}
          title={t("notifications.empty.title")}
          description={t("notifications.empty.description")}
        />
      ) : (
        <Card
          aria-busy={notifications.isFetching}
          className={cn(notifications.isFetching && "opacity-60 transition-opacity")}
        >
          <ul className="divide-y divide-line">
            {rows.map((notification) => (
              <li
                key={notification.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-2 px-5 py-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:gap-x-4"
              >
                <Badge tone={STATUS_TONE[notification.status]} className="w-fit shrink-0 self-start">
                  {t(`notifications.status.${notification.status}`)}
                </Badge>
                <div className="col-span-2 min-w-0 sm:col-span-1">
                  <p className="truncate text-sm font-medium text-mist-100">
                    {notification.headline ?? t("notifications.headlineFallback")}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-mist-500">
                    {notification.recipient_email} {"\u00b7"}{" "}
                    {notification.site_id ? (
                      <Link
                        to={`/sites/${notification.site_id}?change=${notification.change_id}`}
                        className="font-medium text-mist-300 underline decoration-line-strong underline-offset-2 hover:text-mist-100"
                      >
                        {notification.site_name ?? t("notifications.siteFallback")}
                      </Link>
                    ) : (
                      (notification.site_name ?? t("notifications.siteFallback"))
                    )}{" "}
                    {"\u00b7"} {notification.channel}
                  </p>
                  {notification.error ? (
                    <p
                      className={cn(
                        "mt-2 rounded-md border px-2.5 py-1.5 text-xs",
                        notification.status === "skipped"
                          ? "border-line bg-ink-850 text-mist-400"
                          : "border-rose-400/30 bg-rose-400/10 text-rose-400",
                      )}
                    >
                      {notification.status === "skipped" &&
                      notification.error === SKIPPED_NO_RECIPIENTS
                        ? t("notifications.reason.noRecipients")
                        : notification.error}
                    </p>
                  ) : null}
                </div>
                <time
                  dateTime={notification.sent_at}
                  className="col-start-2 row-start-1 shrink-0 self-center text-xs text-mist-500 sm:col-start-3"
                >
                  {relativeTime(notification.sent_at)}
                </time>
              </li>
            ))}
          </ul>
          {notifications.hasNextPage ? <Button variant="ghost" className="w-full" disabled={notifications.isFetchingNextPage} onClick={() => void notifications.fetchNextPage()}>{t("common.loadMore")}</Button> : null}
        </Card>
      )}
    </div>
  );
}
