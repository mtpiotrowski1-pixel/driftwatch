import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CircleCheck,
  DollarSign,
  Globe2,
  Play,
  Plus,
  Power,
} from "lucide-react";
import { type MouseEvent, type ReactNode, lazy, Suspense, useState } from "react";
import { Link } from "@/lib/navigation";

import { ExportChangesButton } from "@/components/ExportChangesButton";
import { DataFreshness } from "@/components/DataFreshness";
import { ChangeBadge } from "@/components/ChangeBadge";
import { OnboardingProgress } from "@/components/OnboardingProgress";
import { BrandBackground } from "@/components/brand/BrandBackground";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, PageLoader, Spinner } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api";
import { canCreateSite, canEditSite } from "@/lib/capabilities";
import { useInOrgContext, useOrg } from "@/lib/orgContext";
import {
  useActionRequired,
  useCurrentUser,
  useChangeHistory,
  useCheckSite,
  useSites,
  useUsage,
} from "@/lib/queries";
import type { Change, CheckStatus, Site } from "@/lib/types";
import { formatCost, formatInterval, hostOf, relativeTime } from "@/lib/utils";

const ActivityChart = lazy(() =>
  import("@/components/ActivityChart").then((module) => ({ default: module.ActivityChart })),
);

const STATUS_KEY: Record<CheckStatus, string> = {
  baseline: "dashboard.statusBaseline",
  unchanged: "dashboard.statusUnchanged",
  changed: "dashboard.statusChanged",
};

const ALERT_LABEL_KEY: Record<string, string> = {
  selector_missing: "dashboard.alert.selector_missing",
  blocked: "dashboard.alert.blocked",
  capture_failed: "dashboard.alert.capture_failed",
};

export function Dashboard() {
  const t = useT();
  const { actingOrg } = useOrg();
  const inOrg = useInOrgContext();
  const { data: user } = useCurrentUser();
  const canCreate = inOrg && canCreateSite(user);
  const sites = useSites();
  const changes = useChangeHistory();
  const actionRequired = useActionRequired();
  const usage = useUsage();

  if (sites.isLoading || changes.isLoading || actionRequired.isLoading) {
    return <PageLoader label={t("dashboard.loading")} />;
  }
  if (sites.isError || (changes.isError && !changes.data) || actionRequired.isError) {
    return (
      <ErrorState
        onRetry={() => {
          void sites.refetch();
          void changes.refetch();
          void actionRequired.refetch();
        }}
      />
    );
  }

  const siteList = sites.data ?? [];
  const changeList = changes.data?.pages.flat() ?? [];
  const attentionList = actionRequired.data ?? [];
  const totalChanges = siteList.reduce((sum, site) => sum + site.change_count, 0);
  const recentChanges = changeList.slice(0, 6);
  const siteName = (siteId: number) => {
    const site = siteList.find((candidate) => candidate.id === siteId);
    return site?.name ?? hostOf(site?.url) ?? t("dashboard.unknownSite");
  };

  return (
    <div className="space-y-8">
      <header className="dw-dashboard-hero focus-on-dark relative isolate overflow-hidden rounded-2xl border border-white/20 p-6 text-white shadow-halo sm:p-8">
        <BrandBackground variant="dark" eager />
        <div className="relative flex min-h-28 flex-wrap items-center justify-between gap-6">
          <div className="dw-art-copy max-w-2xl">
            <p className="mb-3 text-xs font-bold uppercase text-brand-300">
              {t("dashboard.eyebrow")}
            </p>
            <h1 className="text-3xl font-semibold text-white sm:text-4xl">{t("dashboard.title")}</h1>
            <p className="mt-3 max-w-xl text-base leading-relaxed text-on-art-muted">{t("dashboard.subtitle")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {changeList.length > 0 ? <ExportChangesButton /> : null}
            {canCreate && siteList.length > 0 ? (
              <Button asChild>
                <Link to="/sites/new">
                  <Plus className="h-4 w-4" />
                  {t("dashboard.addSite")}
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </header>

      <DataFreshness updatedAt={Math.min(sites.dataUpdatedAt, changes.dataUpdatedAt)} fetching={sites.isFetching || changes.isFetching} stale={sites.isRefetchError || changes.isRefetchError} onRefresh={() => { void sites.refetch(); void changes.refetch(); void actionRequired.refetch(); void usage.refetch(); }} />

      {canCreate ? (
        <OnboardingProgress key={actingOrg?.id ?? "tenant"} sites={siteList} />
      ) : null}

      {siteList.length === 0 ? (
        canCreate ? null : <OperatorEmptyWorkspace />
      ) : (
        <>
          {attentionList.length > 0 ? (
            <ActionQueue changes={attentionList} siteName={siteName} />
          ) : (
            <div className="flex items-center gap-3 rounded-md border border-line border-l-2 border-l-emerald-400 bg-ink-900 px-4 py-3 text-sm text-mist-300">
              <CircleCheck className="h-5 w-5 shrink-0 text-emerald-400" />
              {t("dashboard.noAttention")}
            </div>
          )}

          <dl className="glass grid rounded-lg sm:grid-cols-2 lg:grid-cols-4 lg:divide-x lg:divide-line">
            <Metric
              icon={<Globe2 className="h-4 w-4" />}
              label={t("dashboard.statTotalSites")}
              value={String(siteList.length)}
            />
            <Metric
              icon={<Power className="h-4 w-4" />}
              label={t("dashboard.statEnabled")}
              value={String(siteList.filter((site) => site.enabled).length)}
            />
            <Metric
              icon={<Activity className="h-4 w-4" />}
              label={t("dashboard.statChanges")}
              value={String(totalChanges)}
            />
            <Metric
              icon={<DollarSign className="h-4 w-4" />}
              label={t("dashboard.statAiSpend")}
              value={usage.data ? formatCost(usage.data.total_cost_usd) : "—"}
            />
          </dl>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.65fr)]">
            <section className="min-w-0">
              <SectionHeader title={t("dashboard.recentChanges")} />
              {recentChanges.length === 0 ? (
                <EmptyState
                  icon={<Activity className="h-5 w-5" />}
                  title={t("dashboard.noChangesTitle")}
                  description={t("dashboard.noChangesDescription")}
                />
              ) : (
                <div className="glass overflow-hidden rounded-lg">
                  <ul className="divide-y divide-line">
                    {recentChanges.map((change) => (
                      <li key={change.id}>
                        <Link
                          to={`/sites/${change.site_id}?change=${change.id}`}
                          className="flex min-h-16 items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-ink-850 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus sm:px-5"
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-mist-100">
                              {change.headline ?? t("dashboard.contentChanged")}
                            </p>
                            <p className="mt-0.5 truncate text-xs text-mist-500">
                              {siteName(change.site_id)} · {relativeTime(change.created_at)}
                            </p>
                          </div>
                          <ChangeBadge change={change} />
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            <section className="min-w-0">
              <SectionHeader
                title={t("dashboard.activity")}
                meta={t("dashboard.lastDays", { days: 14 })}
              />
              <div className="glass min-h-52 rounded-lg p-4">
                {changes.hasNextPage ? <p className="mb-3 text-xs text-mist-500">{t("common.loadedHistory", { count: changeList.length })}</p> : null}
                {changeList.length > 0 ? (
                  <Suspense fallback={<div className="h-[150px]" />}>
                    <ActivityChart changes={changeList} />
                  </Suspense>
                ) : (
                  <div className="flex h-44 items-center justify-center text-sm text-mist-500">
                    {t("dashboard.noActivity")}
                  </div>
                )}
                {changes.hasNextPage ? <Button variant="ghost" size="sm" disabled={changes.isFetchingNextPage} onClick={() => void changes.fetchNextPage()}>{t("common.loadMore")}</Button> : null}
              </div>
            </section>
          </div>

          <section>
            <SectionHeader title={t("dashboard.sites")} meta={String(siteList.length)} />
            <div className="glass overflow-hidden rounded-lg">
              <div className="hidden grid-cols-[minmax(14rem,1.4fr)_8rem_minmax(18rem,1fr)_auto] gap-4 border-b border-line bg-ink-850 px-5 py-2.5 text-xs font-semibold text-mist-500 lg:grid">
                <span>{t("dashboard.monitorColumn")}</span>
                <span>{t("dashboard.statusColumn")}</span>
                <span>{t("dashboard.activityColumn")}</span>
                <span className="sr-only">{t("dashboard.actionsColumn")}</span>
              </div>
              <div className="divide-y divide-line">
                {siteList.map((site) => (
                  <SiteRow key={site.id} site={site} />
                ))}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function OperatorEmptyWorkspace() {
  const t = useT();
  return (
    <section className="panel rounded-xl px-6 py-10 text-center">
      <Globe2 className="mx-auto h-6 w-6 text-mist-500" />
      <h2 className="mt-3 text-lg font-semibold text-mist-100">
        {t("dashboard.operatorEmptyTitle")}
      </h2>
      <p className="mx-auto mt-1 max-w-lg text-sm text-mist-400">
        {t("dashboard.operatorEmptyDescription")}
      </p>
    </section>
  );
}

function ActionQueue({
  changes,
  siteName,
}: {
  changes: Change[];
  siteName: (siteId: number) => string;
}) {
  const t = useT();
  return (
    <section className="overflow-hidden rounded-lg border border-rose-400/30 bg-ink-900">
      <div className="flex items-start gap-3 border-b border-rose-400/20 bg-rose-400/10 px-4 py-3.5 sm:px-5">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-mist-100">
            {t("dashboard.attentionTitle", { count: changes.length })}
          </h2>
          <p className="mt-0.5 text-xs text-mist-500">{t("dashboard.attentionDescription")}</p>
        </div>
      </div>
      <ul className="divide-y divide-line">
        {changes.slice(0, 3).map((change) => (
          <li key={change.id}>
            <Link
              to={`/sites/${change.site_id}?change=${change.id}`}
              className="flex items-center justify-between gap-4 px-4 py-3 text-sm hover:bg-ink-850 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus sm:px-5"
            >
              <span className="min-w-0">
                <span className="block truncate font-semibold text-mist-100">
                  {change.headline ?? t("dashboard.contentChanged")}
                </span>
                <span className="mt-0.5 block truncate text-xs text-mist-500">
                  {siteName(change.site_id)} · {relativeTime(change.created_at)}
                </span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 text-rose-400" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="flex min-h-24 items-center gap-3 border-b border-line px-5 py-4 last:border-b-0 sm:nth-[odd]:border-r lg:border-b-0">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-ink-800 text-brand-700">
        {icon}
      </span>
      <div className="min-w-0">
        <dt className="truncate text-xs font-medium text-mist-500">{label}</dt>
        <dd className="mt-0.5 tabular-nums text-2xl font-semibold text-mist-100">{value}</dd>
      </div>
    </div>
  );
}

function SectionHeader({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="dw-text-surface dw-section-heading mb-3 flex items-center justify-between gap-4">
      <h2 className="text-lg font-semibold text-mist-100">{title}</h2>
      {meta ? <span className="text-xs text-mist-500">{meta}</span> : null}
    </div>
  );
}

function SiteRow({ site }: { site: Site }) {
  const t = useT();
  const { notify } = useToast();
  const check = useCheckSite();
  const { data: user } = useCurrentUser();
  const [lastStatus, setLastStatus] = useState<CheckStatus | null>(null);

  async function handleCheck(event: MouseEvent) {
    event.preventDefault();
    try {
      const result = await check.mutateAsync({ id: site.id });
      if (result.capture_error) {
        notify(result.capture_error, "error");
        setLastStatus(null);
        return;
      }
      setLastStatus(result.status);
    } catch (error) {
      notify(error instanceof ApiError ? error.message : t("common.errorTitle"), "error");
    }
  }

  return (
    <article className="grid gap-3 px-4 py-4 transition-colors hover:bg-ink-850 sm:px-5 lg:grid-cols-[minmax(14rem,1.4fr)_8rem_minmax(18rem,1fr)_auto] lg:items-center lg:gap-4">
      <div className="min-w-0">
        <Link
          to={`/sites/${site.id}`}
          className="inline-flex max-w-full items-center gap-2 font-semibold text-mist-100 hover:underline focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <span className="truncate">{site.name ?? hostOf(site.url) ?? site.url}</span>
          <ArrowRight className="h-3.5 w-3.5 shrink-0" />
        </Link>
        <p className="mt-0.5 truncate font-mono text-xs text-mist-500">{site.url}</p>
      </div>
      <div className="flex items-center gap-2 lg:block">
        <Badge tone={site.enabled ? "emerald" : "neutral"}>
          {site.enabled ? t("dashboard.statusEnabled") : t("dashboard.statusPaused")}
        </Badge>
        {site.last_alert_code ? (
          <Badge
            tone="rose"
            title={[t(ALERT_LABEL_KEY[site.last_alert_code] ?? "dashboard.alert.generic"), site.last_alert_detail]
              .filter(Boolean)
              .join(" — ")}
            className="lg:mt-1.5"
          >
            {t("dashboard.alertBadge")}
          </Badge>
        ) : null}
      </div>
      <dl className="grid grid-cols-3 gap-3 text-xs">
        <Stat label={t("dashboard.cardChanges")} value={String(site.change_count)} />
        <Stat label={t("dashboard.cardChecked")} value={relativeTime(site.last_checked_at)} />
        <Stat label={t("dashboard.cardInterval")} value={formatInterval(site.check_interval_minutes)} />
      </dl>
      <div className="flex flex-wrap items-center gap-3 lg:justify-end">
        {lastStatus ? (
          <span className="text-xs text-mist-500">{t(STATUS_KEY[lastStatus])}</span>
        ) : null}
        <Button variant="secondary" size="sm" onClick={handleCheck} disabled={!canEditSite(user, site) || check.isPending}>
          {check.isPending ? <Spinner /> : <Play className="h-3.5 w-3.5" />}
          {t("dashboard.checkNow")}
        </Button>
      </div>
    </article>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-mist-500">{label}</dt>
      <dd className="mt-0.5 truncate tabular-nums text-mist-300">{value}</dd>
    </div>
  );
}
