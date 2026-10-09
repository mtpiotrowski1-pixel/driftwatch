import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  Clock3,
  Database,
  HardDrive,
  ListChecks,
  Mail,
  RefreshCw,
  Send,
  ShieldOff,
  Webhook,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { type ReactNode } from "react";
import { useNavigate } from "@/lib/navigation";

import { DeadCheckIncidents } from "@/components/operations/DeadCheckIncidents";
import {
  useOperationsOverview,
  type OperationsCheckQueue,
  type OperationsOverview,
  type OperationsQueueOrganization,
} from "@/components/operations/data";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, ErrorState, PageLoader, Spinner } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { useI18n, useT, type Translate } from "@/i18n";
import { ApiError, RequestContextChangedError } from "@/lib/api";
import { OrganizationTransitionCancelledError, useOrg } from "@/lib/orgContext";
import { useCurrentUser, useOrganizations } from "@/lib/queries";
import { activeLocale, cn, formatDateTime } from "@/lib/utils";

type Tone = "neutral" | "emerald" | "amber" | "rose";

interface MetricItem {
  label: string;
  value: ReactNode;
  detail?: string;
}

export function Operations() {
  const t = useT();
  const { lang } = useI18n();
  const { data: user, isLoading: userLoading } = useCurrentUser();
  const { actingOrg, enterOrg } = useOrg();
  const navigate = useNavigate();
  const { notify } = useToast();
  const canRead = user?.is_superadmin === true && actingOrg === null;
  const overview = useOperationsOverview(canRead);
  const organizations = useOrganizations(canRead);

  if (userLoading) return <PageLoader label={t("operations.loading")} />;
  if (!user?.is_superadmin) {
    return (
      <EmptyState
        icon={<ShieldOff className="h-5 w-5" />}
        title={t("operations.superadmin.title")}
        description={t("operations.superadmin.description")}
      />
    );
  }
  if (actingOrg) {
    return (
      <div className="space-y-6">
        <header className="min-w-0">
          <h1 className="text-2xl font-semibold text-mist-100">
            {t("operations.tenant.title")}
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-mist-400">
            {t("operations.tenant.subtitle", { name: actingOrg.name })}
          </p>
        </header>
        <DeadCheckIncidents
          scope={{ kind: "tenant", organizationId: actingOrg.id }}
        />
      </div>
    );
  }
  if (overview.isLoading) return <PageLoader label={t("operations.loading")} />;
  if (!overview.data && overview.isError) {
    return <ErrorState onRetry={() => void overview.refetch()} />;
  }
  if (!overview.data) return <PageLoader label={t("operations.loading")} />;

  const data = overview.data;
  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-mist-100">{t("operations.title")}</h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-mist-400">
            {t("operations.subtitle")}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          className="w-full rounded-md sm:w-auto"
          disabled={overview.isFetching}
          onClick={() => void overview.refetch()}
        >
          {overview.isFetching ? <Spinner /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
          {t("operations.refresh")}
        </Button>
      </header>

      {overview.isError ? (
        <ErrorNote>{t("operations.refreshError")}</ErrorNote>
      ) : null}

      <DeadCheckIncidents
        scope={{ kind: "instance" }}
        organizationName={(organizationId) =>
          organizations.data?.find((organization) => organization.id === organizationId)?.name
          ?? t("operations.incidents.organizationFallback", { id: organizationId })
        }
        onOpenOrganization={(organizationId, organizationName) => {
          void enterOrg({ id: organizationId, name: organizationName })
            .then(() => navigate("/dashboard"))
            .catch((error: unknown) => {
              if (error instanceof OrganizationTransitionCancelledError) return;
              notify(
                error instanceof RequestContextChangedError
                  ? t("common.contextChanged")
                  : error instanceof ApiError
                    ? error.message
                    : t("common.requestFailed"),
                "error",
              );
            });
        }}
      />

      <OverallStatus data={data} />

      <div className="grid gap-4 xl:grid-cols-12">
        <DatabasePanel data={data} />
        <SchedulerPanel data={data} />
        <CapturePanel data={data} />
        <CheckQueuePanel data={data} locale={lang} />
        <DeliveryQueuePanel data={data} locale={lang} />
        <AccountEmailQueuePanel data={data} locale={lang} />
        <BillingWebhooksPanel data={data} locale={lang} />
        <StoragePanel data={data} />
        <MaintenancePanel data={data} locale={lang} />
      </div>
    </div>
  );
}

function OverallStatus({ data }: { data: OperationsOverview }) {
  const t = useT();
  const healthy = data.status === "ok";
  const Icon = healthy ? CheckCircle2 : AlertTriangle;
  return (
    <section
      aria-labelledby="operations-overall-title"
      className={cn(
        "flex flex-col gap-4 rounded-lg border px-5 py-4 sm:flex-row sm:items-center",
        healthy
          ? "border-emerald-400/40 bg-[color-mix(in_srgb,var(--color-emerald-400)_7%,white)]"
          : "border-amber-400/40 bg-[color-mix(in_srgb,var(--color-amber-400)_8%,white)]",
      )}
    >
      <div
        className={cn(
          "grid h-10 w-10 shrink-0 place-items-center rounded-lg border",
          healthy
            ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-400"
            : "border-amber-400/30 bg-amber-400/10 text-amber-400",
        )}
        aria-hidden="true"
      >
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="operations-overall-title" className="text-base font-semibold text-mist-100">
            {healthy ? t("operations.overall.ok") : t("operations.overall.degraded")}
          </h2>
          <StatusBadge tone={healthy ? "emerald" : "amber"}>
            {t(`operations.status.${data.status}`)}
          </StatusBadge>
        </div>
        <p className="mt-1 text-sm text-mist-400">
          {healthy ? t("operations.overall.okDescription") : t("operations.overall.degradedDescription")}
        </p>
      </div>
      <dl className="grid shrink-0 grid-cols-2 gap-x-6 gap-y-2 text-xs sm:text-right">
        <div>
          <dt className="text-mist-500">{t("operations.generatedAt")}</dt>
          <dd className="mt-0.5 whitespace-nowrap text-mist-200">{formatDateTime(data.generated_at)}</dd>
        </div>
        <div>
          <dt className="text-mist-500">{t("operations.version")}</dt>
          <dd className="mt-0.5 font-mono text-mist-200">{data.version}</dd>
        </div>
      </dl>
    </section>
  );
}

function DatabasePanel({ data }: { data: OperationsOverview }) {
  const t = useT();
  const reachable = data.database.reachable;
  return (
    <OperationsPanel
      id="operations-database"
      title={t("operations.database.title")}
      icon={Database}
      className="xl:col-span-4"
      status={
        <StatusBadge tone={reachable ? "emerald" : "rose"}>
          {t(reachable ? "operations.database.reachable" : "operations.database.unreachable")}
        </StatusBadge>
      }
      metrics={[
        { label: t("operations.database.backend"), value: t(`operations.database.${data.database.backend}`) },
        { label: t("operations.database.connection"), value: t(reachable ? "operations.value.available" : "operations.value.unavailable") },
      ]}
    />
  );
}

function SchedulerPanel({ data }: { data: OperationsOverview }) {
  const t = useT();
  const scheduler = data.scheduler;
  const tone: Tone = !scheduler.expected
    ? "neutral"
    : scheduler.running && !scheduler.stale
      ? "emerald"
      : "rose";
  const status = !scheduler.expected
    ? t("operations.scheduler.disabled")
    : scheduler.stale
      ? t("operations.scheduler.stale")
      : scheduler.running
        ? t("operations.scheduler.running")
        : t("operations.scheduler.stopped");
  return (
    <OperationsPanel
      id="operations-scheduler"
      title={t("operations.scheduler.title")}
      icon={Clock3}
      className="xl:col-span-8"
      status={<StatusBadge tone={tone}>{status}</StatusBadge>}
      metrics={[
        { label: t("operations.scheduler.enabled"), value: booleanLabel(scheduler.expected, t) },
        { label: t("operations.scheduler.process"), value: booleanLabel(scheduler.running, t) },
        { label: t("operations.scheduler.freshness"), value: scheduler.stale ? t("operations.scheduler.stale") : t("operations.scheduler.current") },
        { label: t("operations.scheduler.lastTick"), value: nullableDate(scheduler.last_tick_at, t) },
      ]}
    />
  );
}

function CapturePanel({ data }: { data: OperationsOverview }) {
  const t = useT();
  const capture = data.capture;
  const tone: Tone = capture.status === "ready" ? "emerald" : capture.status === "unavailable" ? "rose" : "neutral";
  const metrics: MetricItem[] = [
    { label: t("operations.capture.mode"), value: t(`operations.capture.mode.${capture.mode}`) },
    { label: t("operations.capture.active"), value: nullableNumber(capture.active, t) },
    { label: t("operations.capture.queued"), value: nullableNumber(capture.queued, t) },
    { label: t("operations.capture.activeCapacity"), value: nullableNumber(capture.active_capacity, t) },
    { label: t("operations.capture.queueCapacity"), value: nullableNumber(capture.queue_capacity, t) },
  ];
  return (
    <OperationsPanel
      id="operations-capture"
      title={t("operations.capture.title")}
      icon={Camera}
      className="xl:col-span-12"
      status={<StatusBadge tone={tone}>{t(`operations.capture.status.${capture.status}`)}</StatusBadge>}
      metrics={metrics}
      footer={capture.message ? (
        <p className="border-t border-line px-5 py-3 text-sm leading-relaxed text-mist-400">
          <span className="font-medium text-mist-300">{t("operations.capture.message")}:</span>{" "}
          <span className="break-words">{capture.message}</span>
        </p>
      ) : undefined}
    />
  );
}

function CheckQueuePanel({ data, locale }: { data: OperationsOverview; locale: string }) {
  const t = useT();
  const queue = data.check_queue;
  const metrics: MetricItem[] = [
    { label: t("operations.queue.pending"), value: formatNumber(queue.pending, locale) },
    { label: t("operations.queue.running"), value: formatNumber(queue.running, locale) },
    ...(queue.retrying !== undefined
      ? [{ label: t("operations.queue.retrying"), value: formatNumber(queue.retrying, locale) }]
      : []),
    { label: t("operations.queue.dead"), value: formatNumber(queue.dead, locale) },
    ...(queue.leased !== undefined
      ? [{ label: t("operations.queue.leased"), value: formatNumber(queue.leased, locale) }]
      : []),
    { label: t("operations.queue.oldest"), value: ageLabel(queue.oldest_pending_seconds, t, locale, "operations.queue.nonePending") },
    { label: t("operations.queue.capacity"), value: formatNumber(queue.capacity, locale) },
  ];
  const tone: Tone = queue.at_capacity ? "rose" : queue.dead > 0 ? "amber" : "emerald";
  return (
    <OperationsPanel
      id="operations-check-queue"
      title={t("operations.queue.title")}
      icon={ListChecks}
      className="xl:col-span-6"
      status={
        <StatusBadge tone={tone}>
          {queue.at_capacity ? t("operations.queue.atCapacity") : t("operations.queue.accepting")}
        </StatusBadge>
      }
      metrics={metrics}
      footer={queue.per_organization?.length ? (
        <OrganizationQueueTable rows={queue.per_organization} queue={queue} locale={locale} />
      ) : undefined}
    />
  );
}

function OrganizationQueueTable({
  rows,
  queue,
  locale,
}: {
  rows: OperationsQueueOrganization[];
  queue: OperationsCheckQueue;
  locale: string;
}) {
  const t = useT();
  const showRetrying = queue.retrying !== undefined && rows.some((row) => row.retrying !== undefined);
  const showLeased = queue.leased !== undefined && rows.some((row) => row.leased !== undefined);
  return (
    <div className="border-t border-line px-5 py-4">
      <h3 className="text-sm font-semibold text-mist-200">{t("operations.queue.byOrganization")}</h3>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[32rem] text-left text-xs">
          <thead className="text-mist-500">
            <tr className="border-b border-line">
              <th className="pb-2 pr-4 font-medium">{t("operations.queue.organization")}</th>
              <th className="px-3 pb-2 text-right font-medium">{t("operations.queue.pending")}</th>
              <th className="px-3 pb-2 text-right font-medium">{t("operations.queue.running")}</th>
              {showRetrying ? <th className="px-3 pb-2 text-right font-medium">{t("operations.queue.retrying")}</th> : null}
              <th className="px-3 pb-2 text-right font-medium">{t("operations.queue.dead")}</th>
              {showLeased ? <th className="pl-3 pb-2 text-right font-medium">{t("operations.queue.leased")}</th> : null}
            </tr>
          </thead>
          <tbody className="divide-y divide-line/70 text-mist-300">
            {rows.map((row) => (
              <tr key={row.organization_id}>
                <td className="py-2.5 pr-4 font-medium text-mist-200">
                  {row.organization_name || `#${row.organization_id}`}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(row.pending, locale)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(row.running, locale)}</td>
                {showRetrying ? <td className="px-3 py-2.5 text-right tabular-nums">{row.retrying === undefined ? t("operations.value.notReported") : formatNumber(row.retrying, locale)}</td> : null}
                <td className="px-3 py-2.5 text-right tabular-nums">{formatNumber(row.dead, locale)}</td>
                {showLeased ? <td className="pl-3 py-2.5 text-right tabular-nums">{row.leased === undefined ? t("operations.value.notReported") : formatNumber(row.leased, locale)}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DeliveryQueuePanel({ data, locale }: { data: OperationsOverview; locale: string }) {
  const t = useT();
  const queue = data.delivery_queue;
  const tone: Tone = queue.exhausted > 0 ? "rose" : queue.failed > 0 ? "amber" : "emerald";
  return (
    <OperationsPanel
      id="operations-delivery-queue"
      title={t("operations.delivery.title")}
      icon={Send}
      className="xl:col-span-6"
      status={<StatusBadge tone={tone}>{t(queue.exhausted > 0 ? "operations.delivery.attention" : "operations.delivery.processing")}</StatusBadge>}
      metrics={[
        { label: t("operations.delivery.pending"), value: formatNumber(queue.pending, locale) },
        { label: t("operations.delivery.failed"), value: formatNumber(queue.failed, locale) },
        { label: t("operations.delivery.sent"), value: formatNumber(queue.sent, locale) },
        { label: t("operations.delivery.exhausted"), value: formatNumber(queue.exhausted, locale) },
        { label: t("operations.delivery.leased"), value: formatNumber(queue.leased, locale) },
        { label: t("operations.delivery.oldest"), value: ageLabel(queue.oldest_unsent_seconds, t, locale, "operations.delivery.noneUnsent") },
      ]}
    />
  );
}

function BillingWebhooksPanel({ data, locale }: { data: OperationsOverview; locale: string }) {
  const t = useT();
  const webhooks = data.billing_webhooks;
  const needsAttention = webhooks.failed > 0 || webhooks.stale_processing > 0;
  const tone: Tone = webhooks.failed > 0 ? "rose" : webhooks.stale_processing > 0 ? "amber" : "emerald";
  return (
    <OperationsPanel
      id="operations-billing-webhooks"
      title={t("operations.billingWebhooks.title")}
      icon={Webhook}
      className="xl:col-span-6"
      status={
        <StatusBadge tone={tone}>
          {t(needsAttention ? "operations.billingWebhooks.attention" : "operations.billingWebhooks.healthy")}
        </StatusBadge>
      }
      metrics={[
        { label: t("operations.billingWebhooks.total"), value: formatNumber(webhooks.total, locale) },
        { label: t("operations.billingWebhooks.received"), value: formatNumber(webhooks.received, locale) },
        { label: t("operations.billingWebhooks.processing"), value: formatNumber(webhooks.processing, locale) },
        { label: t("operations.billingWebhooks.stale"), value: formatNumber(webhooks.stale_processing, locale) },
        { label: t("operations.billingWebhooks.completed"), value: formatNumber(webhooks.completed, locale) },
        { label: t("operations.billingWebhooks.failed"), value: formatNumber(webhooks.failed, locale) },
        { label: t("operations.billingWebhooks.staleAfter"), value: durationLabel(webhooks.stale_after_seconds, locale) },
        { label: t("operations.billingWebhooks.lastProcessed"), value: nullableDate(webhooks.last_processed_at, t) },
        { label: t("operations.billingWebhooks.lastFailed"), value: nullableDate(webhooks.last_failed_at, t) },
      ]}
    />
  );
}

function AccountEmailQueuePanel({
  data,
  locale,
}: {
  data: OperationsOverview;
  locale: string;
}) {
  const t = useT();
  const queue = data.account_email_queue;
  const hasRecentFailures = queue.failed_recent > 0;
  const tone: Tone = hasRecentFailures ? "rose" : queue.stale_pending ? "amber" : "emerald";
  const status = hasRecentFailures
    ? t("operations.accountEmail.recentFailures")
    : queue.stale_pending
      ? t("operations.accountEmail.stale")
      : t("operations.accountEmail.processing");
  return (
    <OperationsPanel
      id="operations-account-email"
      title={t("operations.accountEmail.title")}
      icon={Mail}
      className="xl:col-span-6"
      status={<StatusBadge tone={tone}>{status}</StatusBadge>}
      metrics={[
        { label: t("operations.accountEmail.pending"), value: formatNumber(queue.pending, locale) },
        { label: t("operations.accountEmail.leased"), value: formatNumber(queue.leased, locale) },
        { label: t("operations.accountEmail.sent"), value: formatNumber(queue.sent, locale) },
        { label: t("operations.accountEmail.cancelled"), value: formatNumber(queue.cancelled, locale) },
        { label: t("operations.accountEmail.failedRecent"), value: formatNumber(queue.failed_recent, locale) },
        { label: t("operations.accountEmail.failedTotal"), value: formatNumber(queue.failed_total, locale) },
        {
          label: t("operations.accountEmail.oldest"),
          value: ageLabel(
            queue.oldest_pending_seconds,
            t,
            locale,
            "operations.accountEmail.nonePending",
          ),
        },
        {
          label: t("operations.accountEmail.staleAfter"),
          value: durationLabel(queue.pending_stale_after_seconds, locale),
        },
        {
          label: t("operations.accountEmail.failureWindow"),
          value: durationLabel(queue.recent_failure_window_seconds, locale),
        },
      ]}
    />
  );
}

function StoragePanel({ data }: { data: OperationsOverview }) {
  const t = useT();
  const storage = data.storage;
  return (
    <OperationsPanel
      id="operations-storage"
      title={t("operations.storage.title")}
      icon={HardDrive}
      className="xl:col-span-7"
      metrics={[
        { label: t("operations.storage.database"), value: nullableBytes(storage.db_bytes, t) },
        { label: t("operations.storage.wal"), value: nullableBytes(storage.wal_bytes, t) },
        { label: t("operations.storage.diskFree"), value: nullableBytes(storage.disk_free_bytes, t) },
        {
          label: t("operations.storage.lastBackup"),
          value:
            data.database.backend === "postgresql" && !storage.last_backup_at
              ? t("operations.storage.externalBackup")
              : nullableDate(storage.last_backup_at, t),
        },
      ]}
      footer={storage.last_backup_file ? (
        <dl className="border-t border-line px-5 py-3 text-xs">
          <dt className="text-mist-500">{t("operations.storage.backupFile")}</dt>
          <dd className="mt-1 break-all font-mono text-mist-300">{storage.last_backup_file}</dd>
        </dl>
      ) : undefined}
    />
  );
}

function MaintenancePanel({ data, locale }: { data: OperationsOverview; locale: string }) {
  const t = useT();
  const maintenance = data.maintenance;
  const metrics: MetricItem[] = [
    { label: t("operations.maintenance.mode"), value: booleanLabel(maintenance.enabled, t) },
    { label: t("operations.maintenance.activeRequests"), value: formatNumber(maintenance.active_requests, locale) },
    ...(maintenance.retry_after_seconds !== undefined
      ? [{ label: t("operations.maintenance.retryAfter"), value: maintenance.retry_after_seconds === null ? t("operations.value.none") : durationLabel(maintenance.retry_after_seconds, locale) }]
      : []),
    ...(maintenance.updated_at !== undefined
      ? [{ label: t("operations.maintenance.updated"), value: nullableDate(maintenance.updated_at, t) }]
      : []),
  ];
  return (
    <OperationsPanel
      id="operations-maintenance"
      title={t("operations.maintenance.title")}
      icon={Wrench}
      className="xl:col-span-5"
      status={
        <StatusBadge tone={maintenance.enabled ? "amber" : "neutral"}>
          {t(maintenance.enabled ? "operations.maintenance.enabled" : "operations.maintenance.disabled")}
        </StatusBadge>
      }
      metrics={metrics}
    />
  );
}

function OperationsPanel({
  id,
  title,
  icon: Icon,
  status,
  metrics,
  footer,
  className,
}: {
  id: string;
  title: string;
  icon: LucideIcon;
  status?: ReactNode;
  metrics: MetricItem[];
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <section aria-labelledby={id} className={cn("overflow-hidden rounded-lg border border-line-strong bg-ink-900 shadow-card", className)}>
      <header className="flex min-h-16 items-center gap-3 px-5 py-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line bg-ink-850 text-mist-300" aria-hidden="true">
          <Icon className="h-4 w-4" />
        </span>
        <h2 id={id} className="min-w-0 flex-1 text-sm font-semibold text-mist-100">{title}</h2>
        {status}
      </header>
      <dl className="grid grid-cols-2 gap-x-5 gap-y-5 border-t border-line px-5 py-4 sm:grid-cols-[repeat(auto-fit,minmax(8rem,1fr))]">
        {metrics.map((metric) => (
          <div key={metric.label} className="min-w-0">
            <dt className="text-xs leading-relaxed text-mist-500">{metric.label}</dt>
            <dd className="mt-1 break-words text-sm font-semibold tabular-nums text-mist-200">{metric.value}</dd>
            {metric.detail ? <p className="mt-0.5 text-xs text-mist-500">{metric.detail}</p> : null}
          </div>
        ))}
      </dl>
      {footer}
    </section>
  );
}

function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <Badge tone={tone}>{children}</Badge>;
}

function booleanLabel(value: boolean, t: Translate): string {
  return t(value ? "operations.value.yes" : "operations.value.no");
}

function nullableNumber(value: number | null, t: Translate): string {
  return value === null ? t("operations.value.notReported") : formatNumber(value, activeLocale());
}

function nullableDate(value: string | null, t: Translate): string {
  return value ? formatDateTime(value) : t("operations.value.never");
}

function nullableBytes(value: number | null, t: Translate): string {
  return value === null ? t("operations.value.notReported") : formatBytes(value, activeLocale());
}

function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value);
}

function formatBytes(value: number, locale: string): string {
  const safe = Math.max(0, value);
  if (safe === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(safe) / Math.log(1024)), units.length - 1);
  const amount = safe / 1024 ** index;
  const formatted = new Intl.NumberFormat(locale, {
    maximumFractionDigits: index === 0 ? 0 : amount < 10 ? 1 : 0,
  }).format(amount);
  return `${formatted} ${units[index]}`;
}

function ageLabel(
  seconds: number | null,
  t: Translate,
  locale: string,
  emptyKey: string,
): string {
  return seconds === null ? t(emptyKey) : durationLabel(seconds, locale);
}

function durationLabel(seconds: number, locale: string): string {
  const safe = Math.max(0, seconds);
  if (safe < 60) return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(safe)} s`;
  if (safe < 3_600) return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(safe / 60)} min`;
  if (safe < 86_400) return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(safe / 3_600)} h`;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(safe / 86_400)} d`;
}

export const operationsFormatters = { formatBytes, durationLabel };
