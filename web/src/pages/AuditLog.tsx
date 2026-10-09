import { ScrollText, ShieldOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, PageLoader } from "@/components/ui/feedback";
import { useT } from "@/i18n";
import { useAuditEvents, useCurrentUser } from "@/lib/queries";
import type { AuditEvent } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

type AuditTone = "neutral" | "amber" | "emerald" | "rose";

function actionTone(action: string): AuditTone {
  if (action.endsWith(".deleted") || action === "backup.restored") return "rose";
  if (action.endsWith(".created") || action === "account.totp_enabled") return "emerald";
  if (
    action.endsWith(".updated") ||
    action.startsWith("account.") ||
    action.includes("password")
  ) {
    return "amber";
  }
  return "neutral";
}

function valueLabel(value: unknown): string {
  if (value == null) return "-";
  if (Array.isArray(value)) return value.join(", ") || "-";
  if (typeof value === "object") {
    const change = value as { from?: unknown; to?: unknown };
    if ("from" in change || "to" in change) {
      return `${valueLabel(change.from)} -> ${valueLabel(change.to)}`;
    }
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}: ${valueLabel(item)}`)
      .join("; ");
  }
  return String(value);
}

function EventDetails({ details }: { details: Record<string, unknown> }) {
  const t = useT();
  const rows = Object.entries(details).flatMap(([key, value]) => {
    if (key === "changes" && value && typeof value === "object" && !Array.isArray(value)) {
      return Object.entries(value as Record<string, unknown>);
    }
    return [[key, value] as [string, unknown]];
  });
  if (rows.length === 0) return null;
  return (
    <dl className="mt-3 flex flex-wrap gap-2">
      {rows.map(([key, value]) => (
        <div key={key} className="rounded-md border border-line bg-ink-900 px-2.5 py-1 text-xs">
          <dt className="inline text-mist-500">
            {t(`audit.detail.${key}`) === `audit.detail.${key}`
              ? key.replaceAll("_", " ")
              : t(`audit.detail.${key}`)}
            :{" "}
          </dt>
          <dd className="inline break-words text-mist-300">
            {value === "scheduled" ? t("audit.value.scheduled") : valueLabel(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function AuditRow({ event }: { event: AuditEvent }) {
  const t = useT();
  const actionKey = `audit.action.${event.action}`;
  const translated = t(actionKey);
  const actionLabel = translated === actionKey ? event.action.replaceAll(".", " ") : translated;
  const targetTypeKey = `audit.target.${event.target_type}`;
  const translatedTargetType = t(targetTypeKey);
  const targetType =
    translatedTargetType === targetTypeKey ? event.target_type : translatedTargetType;
  const target =
    event.target_label ??
    (event.target_id ? `${targetType} #${event.target_id}` : targetType);

  return (
    <li className="grid gap-3 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={actionTone(event.action)}>{actionLabel}</Badge>
          <p className="truncate text-sm font-medium text-mist-100">{target}</p>
        </div>
        <p className="mt-1.5 text-xs text-mist-500">
          {event.actor_email}
          {event.source_ip ? ` · ${event.source_ip}` : ""}
        </p>
        <EventDetails details={event.details} />
      </div>
      <time
        dateTime={event.occurred_at}
        className="text-xs text-mist-500 lg:justify-self-end"
      >
        {formatDateTime(event.occurred_at)}
      </time>
    </li>
  );
}

export function AuditLog() {
  const t = useT();
  const { data: user, isLoading: userLoading } = useCurrentUser();
  const isAdmin = Boolean(user?.is_admin || user?.is_superadmin);
  const events = useAuditEvents(isAdmin);

  if (userLoading) return <PageLoader label={t("audit.loading")} />;
  if (!isAdmin) {
    return (
      <EmptyState
        icon={<ShieldOff className="h-5 w-5" />}
        title={t("audit.adminRequired.title")}
        description={t("audit.adminRequired.description")}
      />
    );
  }
  if (events.isLoading) return <PageLoader label={t("audit.loading")} />;
  if (events.isError) return <ErrorState onRetry={() => events.refetch()} />;

  const rows = events.data?.pages.flat() ?? [];
  return (
    <div className="space-y-7">
      <header>
        <h1 className="text-2xl font-semibold text-mist-100">{t("audit.title")}</h1>
        <p className="mt-1 text-sm text-mist-400">{t("audit.subtitle")}</p>
      </header>
      {rows.length === 0 ? (
        <EmptyState
          icon={<ScrollText className="h-5 w-5" />}
          title={t("audit.empty.title")}
          description={t("audit.empty.description")}
        />
      ) : (
        <Card>
          <ol className="divide-y divide-line">
            {rows.map((event) => (
              <AuditRow key={event.id} event={event} />
            ))}
          </ol>
        </Card>
      )}
      {events.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            variant="secondary"
            disabled={events.isFetchingNextPage}
            onClick={() => void events.fetchNextPage()}
          >
            {events.isFetchingNextPage ? t("audit.loadingOlder") : t("audit.loadOlder")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
