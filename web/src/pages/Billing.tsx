import {
  AlertTriangle,
  Building2,
  CalendarClock,
  Check,
  CreditCard,
  ExternalLink,
  Gauge,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Link } from "@/lib/navigation";

import { StepUpDialog } from "@/components/StepUpDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, ErrorState, PageLoader, Spinner } from "@/components/ui/feedback";
import { useI18n, useT } from "@/i18n";
import { ApiError, organizationRequestContext } from "@/lib/api";
import {
  clearCheckoutKey,
  clearOrganizationCheckoutKeys,
  createBillingIdempotencyKey,
  getOrCreateCheckoutKey,
  trustedHostedBillingUrl,
  type CheckoutKeyScope,
} from "@/lib/billing";
import { useInOrgContext, useOrg } from "@/lib/orgContext";
import {
  useBillingCatalog,
  useBillingStatus,
  useCreateBillingCheckout,
  useCreateBillingPortal,
  useCurrentUser,
  useReconcileBilling,
} from "@/lib/queries";
import type {
  BillingCatalogPrice,
  BillingReconciliation,
  BillingSubscriptionStatus,
  HostedBillingSession,
} from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

type StepUpAction = "checkout" | "portal" | "reconcile";
type BadgeTone = "neutral" | "amber" | "emerald" | "rose";

const CHECKOUT_INACTIVE_STATUSES = new Set(["canceled", "incomplete_expired"]);
const KNOWN_STATUSES = new Set([
  "active",
  "trialing",
  "past_due",
  "unpaid",
  "paused",
  "incomplete",
  "incomplete_expired",
  "canceled",
]);

export function Billing() {
  const t = useT();
  const { lang } = useI18n();
  const [searchParams] = useSearchParams();
  const { data: user, isLoading: userLoading } = useCurrentUser();
  const { actingOrg } = useOrg();
  const inOrganization = useInOrgContext();
  const organizationId = user?.is_superadmin
    ? actingOrg?.id ?? null
    : user?.organization_id ?? null;
  const canRead = Boolean(
    (user?.is_admin || user?.is_superadmin) && inOrganization && organizationId !== null,
  );
  const statusQuery = useBillingStatus(canRead, organizationId);
  const catalogQuery = useBillingCatalog(canRead, organizationId);
  const checkout = useCreateBillingCheckout(organizationId);
  const portal = useCreateBillingPortal(organizationId);
  const reconcile = useReconcileBilling();

  const [selectedPrice, setSelectedPrice] = useState<BillingCatalogPrice | null>(null);
  const [checkoutKey, setCheckoutKey] = useState<string | null>(null);
  const [portalKey, setPortalKey] = useState<string | null>(null);
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [stepUpAction, setStepUpAction] = useState<StepUpAction | null>(null);
  const [redirectError, setRedirectError] = useState(false);
  const checkoutResult = searchParams.get("checkout");
  const previousOrganizationId = useRef(organizationId);

  useEffect(() => {
    if (previousOrganizationId.current === organizationId) return;
    previousOrganizationId.current = organizationId;
    setSelectedPrice(null);
    setCheckoutKey(null);
    setPortalKey(null);
    setConsentAccepted(false);
    setConfirmationOpen(false);
    setStepUpAction(null);
    setRedirectError(false);
    checkout.reset();
    portal.reset();
    reconcile.reset();
  }, [checkout, organizationId, portal, reconcile]);

  useEffect(() => {
    if (checkoutResult === "success" && organizationId !== null) {
      clearOrganizationCheckoutKeys(organizationId);
    }
  }, [checkoutResult, organizationId]);

  if (userLoading) return <PageLoader label={t("billing.loading")} />;
  if (!user?.is_admin && !user?.is_superadmin) {
    return (
      <EmptyState
        icon={<ShieldOff className="h-5 w-5" />}
        title={t("billing.access.title")}
        description={t("billing.access.description")}
      />
    );
  }
  if (!inOrganization) {
    return (
      <EmptyState
        icon={<Building2 className="h-5 w-5" />}
        title={t("billing.organization.title")}
        description={t("billing.organization.description")}
        action={
          <Button asChild variant="secondary" size="sm">
            <Link to="/organizations">{t("billing.organization.action")}</Link>
          </Button>
        }
      />
    );
  }
  if (statusQuery.isLoading || catalogQuery.isLoading) {
    return <PageLoader label={t("billing.loading")} />;
  }
  if (
    (!statusQuery.data && statusQuery.isError) ||
    (!catalogQuery.data && catalogQuery.isError)
  ) {
    return (
      <ErrorState
        onRetry={() => {
          void statusQuery.refetch();
          void catalogQuery.refetch();
        }}
      />
    );
  }
  if (!statusQuery.data || !catalogQuery.data) {
    return <PageLoader label={t("billing.loading")} />;
  }

  const billingStatus = statusQuery.data;
  const catalog = catalogQuery.data;
  const checkoutReady = Boolean(
    billingStatus.self_serve_ready &&
      catalog.self_serve_ready &&
      catalog.terms_version &&
      catalog.privacy_version &&
      catalog.terms_url &&
      catalog.privacy_url &&
      catalog.terms_sha256 &&
      catalog.privacy_sha256,
  );
  const portalReady = billingStatus.provider_configured;
  const subscription = billingStatus.subscription;
  const canCheckout =
    subscription === null || CHECKOUT_INACTIVE_STATUSES.has(subscription.status);
  const actionPending = checkout.isPending || portal.isPending || reconcile.isPending;
  const actionError = redirectError
    ? t("billing.error.redirect")
    : billingActionError(checkout.error ?? portal.error, t);
  function beginCheckout(price: BillingCatalogPrice) {
    checkout.reset();
    portal.reset();
    setRedirectError(false);
    if (selectedPrice?.billing_price_id !== price.billing_price_id || checkoutKey === null) {
      const scope = checkoutKeyScope(price);
      setCheckoutKey(scope ? getOrCreateCheckoutKey(scope) : createBillingIdempotencyKey("checkout"));
    }
    setSelectedPrice(price);
    setConsentAccepted(false);
    setConfirmationOpen(true);
  }

  function beginPortal() {
    checkout.reset();
    portal.reset();
    setRedirectError(false);
    if (portalKey === null) setPortalKey(createBillingIdempotencyKey("portal"));
    setStepUpAction("portal");
  }

  function beginReconciliation() {
    reconcile.reset();
    setStepUpAction("reconcile");
  }

  function confirmCheckout() {
    if (!consentAccepted || !selectedPrice || !checkoutReady) return;
    setConfirmationOpen(false);
    setStepUpAction("checkout");
  }

  function createCheckout() {
    if (
      !checkoutReady ||
      !selectedPrice ||
      !checkoutKey ||
      !catalog.terms_version ||
      !catalog.privacy_version ||
      !catalog.terms_sha256 ||
      !catalog.privacy_sha256
    ) {
      return;
    }
    checkout.mutate(
      {
        billing_price_id: selectedPrice.billing_price_id,
        idempotency_key: checkoutKey,
        accepted_terms_version: catalog.terms_version,
        accepted_privacy_version: catalog.privacy_version,
        accepted_terms_sha256: catalog.terms_sha256,
        accepted_privacy_sha256: catalog.privacy_sha256,
      },
      {
        onSuccess: redirectToHostedSession,
        onError: (error) => {
          const scope = checkoutKeyScope(selectedPrice);
          if (error instanceof ApiError && error.status === 409 && scope) {
            clearCheckoutKey(scope);
            setCheckoutKey(null);
          }
        },
      },
    );
  }

  function checkoutKeyScope(price: BillingCatalogPrice): CheckoutKeyScope | null {
    if (
      organizationId === null ||
      !catalog.terms_sha256 ||
      !catalog.privacy_sha256
    ) {
      return null;
    }
    return {
      organizationId,
      billingPriceId: price.billing_price_id,
      termsSha256: catalog.terms_sha256,
      privacySha256: catalog.privacy_sha256,
    };
  }

  function createPortal() {
    if (!portalReady || !portalKey) return;
    portal.mutate(portalKey, { onSuccess: redirectToHostedSession });
  }

  function reconcileActiveOrganization() {
    if (!user?.is_superadmin || !actingOrg) return;
    reconcile.mutate(actingOrg.id);
  }

  function runStepUpAction() {
    if (stepUpAction === "checkout") createCheckout();
    else if (stepUpAction === "portal") createPortal();
    else if (stepUpAction === "reconcile") reconcileActiveOrganization();
  }

  function redirectToHostedSession(session: HostedBillingSession) {
    const trustedUrl = trustedHostedBillingUrl(session.url);
    if (!trustedUrl) {
      setRedirectError(true);
      return;
    }
    window.location.assign(trustedUrl);
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-mist-100">{t("billing.title")}</h1>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-mist-400">
            {t("billing.subtitle")}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          className="w-full rounded-md sm:w-auto"
          disabled={statusQuery.isFetching || catalogQuery.isFetching || actionPending}
          onClick={() => {
            void statusQuery.refetch();
            void catalogQuery.refetch();
          }}
        >
          {statusQuery.isFetching || catalogQuery.isFetching ? (
            <Spinner />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          {t("billing.refresh")}
        </Button>
      </header>

      {checkoutResult === "success" ? (
        <ResultNotice tone="success" title={t("billing.return.success.title")}>
          {t("billing.return.success.description")}
        </ResultNotice>
      ) : null}
      {checkoutResult === "cancelled" ? (
        <ResultNotice tone="neutral" title={t("billing.return.cancelled.title")}>
          {t("billing.return.cancelled.description")}
        </ResultNotice>
      ) : null}
      {statusQuery.isError || catalogQuery.isError ? (
        <ErrorNote>{t("billing.refreshError")}</ErrorNote>
      ) : null}
      {actionError ? <ErrorNote>{actionError}</ErrorNote> : null}

      {subscription ? (
        <SubscriptionPanel
          subscription={subscription}
          portalReady={portalReady}
          customerExists={billingStatus.customer_exists}
          actionPending={actionPending}
          onManage={beginPortal}
        />
      ) : (
        <NoSubscriptionPanel />
      )}

      {user.is_superadmin && actingOrg ? (
        <ReconciliationPanel
          providerConfigured={billingStatus.provider_configured}
          customerExists={billingStatus.customer_exists}
          isPending={reconcile.isPending}
          result={reconcile.data ?? null}
          error={billingActionError(reconcile.error, t)}
          onReconcile={beginReconciliation}
        />
      ) : null}

      {!checkoutReady ? (
        <ReadinessClosed />
      ) : canCheckout ? (
        catalog.prices.length > 0 ? (
          <section aria-labelledby="billing-plans-title" className="space-y-4">
            <div>
              <h2 id="billing-plans-title" className="text-lg font-semibold text-mist-100">
                {t("billing.plans.title")}
              </h2>
              <p className="mt-1 text-sm text-mist-400">{t("billing.plans.description")}</p>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {catalog.prices.map((price) => (
                <PriceCard
                  key={price.billing_price_id}
                  price={price}
                  locale={lang}
                  disabled={actionPending}
                  onSelect={() => beginCheckout(price)}
                />
              ))}
            </div>
          </section>
        ) : (
          <EmptyState
            icon={<CreditCard className="h-5 w-5" />}
            title={t("billing.plans.empty.title")}
            description={t("billing.plans.empty.description")}
          />
        )
      ) : null}

      {billingStatus.customer_exists && portalReady && !subscription ? (
        <div className="flex justify-end border-t border-line pt-4">
          <Button variant="secondary" disabled={actionPending} onClick={beginPortal}>
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {t("billing.portal.action")}
          </Button>
        </div>
      ) : null}

      {selectedPrice &&
      catalog.terms_version &&
      catalog.privacy_version &&
      catalog.terms_url &&
      catalog.privacy_url ? (
        <Dialog
          open={confirmationOpen}
          onOpenChange={setConfirmationOpen}
          title={t("billing.checkout.title")}
          description={t("billing.checkout.description", { plan: selectedPrice.plan_name })}
        >
          <div className="space-y-4">
            <div className="flex items-baseline justify-between gap-4 rounded-lg border border-line bg-ink-850 px-4 py-3">
              <span className="font-medium text-mist-100">{selectedPrice.plan_name}</span>
              <span className="shrink-0 font-semibold text-mist-100">
                {formatMoney(selectedPrice, lang)}
              </span>
            </div>
            <div className="flex items-start gap-3 rounded-lg border border-line bg-ink-900 px-4 py-3 text-sm leading-relaxed text-mist-300">
              <input
                id="billing-legal-consent"
                type="checkbox"
                className="mt-0.5 h-4 w-4 shrink-0 accent-brand-500"
                checked={consentAccepted}
                onChange={(event) => setConsentAccepted(event.target.checked)}
                aria-describedby="billing-legal-consent-text"
              />
              <p id="billing-legal-consent-text">
                <label htmlFor="billing-legal-consent" className="cursor-pointer">
                  {t("billing.checkout.consentPrefix")}
                </label>{" "}
                <a
                  href={catalog.terms_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-brand-300 underline decoration-brand-500/50 underline-offset-2 hover:text-brand-200"
                >
                  {t("billing.checkout.termsLink", { version: catalog.terms_version })}
                </a>{" "}
                {t("billing.checkout.consentAnd")} {" "}
                <a
                  href={catalog.privacy_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-brand-300 underline decoration-brand-500/50 underline-offset-2 hover:text-brand-200"
                >
                  {t("billing.checkout.privacyLink", { version: catalog.privacy_version })}
                </a>{" "}
                {t("billing.checkout.consentSuffix")}
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setConfirmationOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="button" disabled={!consentAccepted} onClick={confirmCheckout}>
                <LockKeyhole className="h-4 w-4" aria-hidden="true" />
                {t("billing.checkout.continue")}
              </Button>
            </div>
          </div>
        </Dialog>
      ) : null}

      {stepUpAction && organizationId !== null ? (
        <StepUpDialog
          title={t(stepUpMessageKey(stepUpAction, "title"))}
          description={t(stepUpMessageKey(stepUpAction, "description"))}
          submitLabel={t(stepUpMessageKey(stepUpAction, "submit"))}
          requestContext={organizationRequestContext(organizationId)}
          onVerified={runStepUpAction}
          onClose={() => setStepUpAction(null)}
        />
      ) : null}
    </div>
  );
}

function SubscriptionPanel({
  subscription,
  portalReady,
  customerExists,
  actionPending,
  onManage,
}: {
  subscription: BillingSubscriptionStatus;
  portalReady: boolean;
  customerExists: boolean;
  actionPending: boolean;
  onManage: () => void;
}) {
  const t = useT();
  const statusKey = KNOWN_STATUSES.has(subscription.status) ? subscription.status : "unknown";
  return (
    <section aria-labelledby="billing-current-title" className="overflow-hidden rounded-lg border border-line bg-ink-900">
      <div className="flex flex-col gap-4 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase text-mist-500">{t("billing.current.eyebrow")}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h2 id="billing-current-title" className="text-lg font-semibold text-mist-100">
              {subscription.plan_name ?? t("billing.current.unmapped")}
            </h2>
            <Badge tone={statusTone(subscription.status)}>{t(`billing.status.${statusKey}`)}</Badge>
          </div>
        </div>
        {portalReady && customerExists ? (
          <Button variant="secondary" disabled={actionPending} onClick={onManage}>
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {t("billing.portal.action")}
          </Button>
        ) : null}
      </div>
      <dl className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-3">
        <StatusMetric
          icon={ShieldCheck}
          label={t("billing.current.access")}
          value={t(
            subscription.entitlement_active
              ? "billing.current.accessActive"
              : "billing.current.accessInactive",
          )}
        />
        <StatusMetric
          icon={CalendarClock}
          label={t(
            subscription.cancel_at_period_end
              ? "billing.current.endsAt"
              : "billing.current.periodEnd",
          )}
          value={formatDateTime(subscription.current_period_end)}
        />
        <StatusMetric
          icon={Gauge}
          label={t("billing.current.validUntil")}
          value={formatDateTime(subscription.entitlement_valid_until)}
        />
      </dl>
      {subscription.cancel_at_period_end ? (
        <p className="border-t border-amber-400/25 bg-amber-400/[0.07] px-5 py-3 text-sm text-amber-400">
          {t("billing.current.cancels")}
        </p>
      ) : null}
      {!subscription.entitlement_active ? (
        <p className="border-t border-rose-400/25 bg-rose-400/[0.06] px-5 py-3 text-sm text-rose-400">
          {t("billing.current.inactiveWarning")}
        </p>
      ) : null}
    </section>
  );
}

function NoSubscriptionPanel() {
  const t = useT();
  return (
    <section className="flex items-start gap-4 rounded-lg border border-line bg-ink-900 px-5 py-4">
      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-line bg-ink-850 text-mist-400">
        <CreditCard className="h-5 w-5" aria-hidden="true" />
      </div>
      <div>
        <h2 className="font-semibold text-mist-100">{t("billing.none.title")}</h2>
        <p className="mt-1 text-sm text-mist-400">{t("billing.none.description")}</p>
      </div>
    </section>
  );
}

function ReconciliationPanel({
  providerConfigured,
  customerExists,
  isPending,
  result,
  error,
  onReconcile,
}: {
  providerConfigured: boolean;
  customerExists: boolean;
  isPending: boolean;
  result: BillingReconciliation | null;
  error: string | null;
  onReconcile: () => void;
}) {
  const t = useT();
  const unavailableReason = !providerConfigured
    ? t("billing.reconcile.providerUnavailable")
    : !customerExists
      ? t("billing.reconcile.unavailable")
      : null;

  return (
    <section
      aria-labelledby="billing-reconcile-title"
      className="flex flex-col gap-4 rounded-lg border border-line bg-ink-900 px-5 py-4 sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="max-w-3xl">
        <h2 id="billing-reconcile-title" className="text-sm font-semibold text-mist-100">
          {t("billing.reconcile.title")}
        </h2>
        <p className="mt-1 text-sm leading-relaxed text-mist-400">
          {t("billing.reconcile.description")}
        </p>
        {unavailableReason ? (
          <p className="mt-2 text-xs text-amber-400">{unavailableReason}</p>
        ) : null}
        {result ? (
          <p role="status" className="mt-2 text-xs font-medium text-emerald-400">
            {t("billing.reconcile.result", {
              seen: result.subscriptions_seen,
              updated: result.subscriptions_updated,
            })}
          </p>
        ) : null}
        {error ? (
          <div className="mt-3">
            <ErrorNote>{error}</ErrorNote>
          </div>
        ) : null}
      </div>
      <Button
        variant="secondary"
        size="sm"
        className="w-full sm:w-auto"
        disabled={Boolean(unavailableReason) || isPending}
        onClick={onReconcile}
      >
        {isPending ? (
          <Spinner />
        ) : (
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        )}
        {t("billing.reconcile.action")}
      </Button>
    </section>
  );
}

function ReadinessClosed() {
  const t = useT();
  return (
    <section className="flex items-start gap-4 rounded-lg border border-amber-400/30 bg-amber-400/[0.07] px-5 py-4">
      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-amber-400/30 bg-amber-400/10 text-amber-400">
        <AlertTriangle className="h-5 w-5" aria-hidden="true" />
      </div>
      <div>
        <h2 className="font-semibold text-mist-100">{t("billing.readiness.title")}</h2>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-mist-400">
          {t("billing.readiness.description")}
        </p>
      </div>
    </section>
  );
}

function stepUpMessageKey(
  action: StepUpAction,
  part: "title" | "description" | "submit",
): string {
  return action === "reconcile"
    ? `billing.reconcile.stepup.${part}`
    : `billing.stepup.${action}.${part}`;
}

function PriceCard({
  price,
  locale,
  disabled,
  onSelect,
}: {
  price: BillingCatalogPrice;
  locale: string;
  disabled: boolean;
  onSelect: () => void;
}) {
  const t = useT();
  return (
    <article className="flex min-h-64 flex-col rounded-lg border border-line bg-ink-900 p-5 shadow-card">
      <div>
        <h3 className="text-base font-semibold text-mist-100">{price.plan_name}</h3>
        <p className="mt-3 text-3xl font-semibold tabular-nums text-mist-100">
          {formatMoney(price, locale)}
        </p>
        <p className="mt-1 text-xs text-mist-500">{formatBillingInterval(price, t)}</p>
      </div>
      <ul className="mt-5 flex-1 space-y-2.5 text-sm text-mist-300">
        <PlanLimit
          text={t("billing.plan.sites", {
            value: price.max_sites ?? t("billing.plan.unlimited"),
          })}
        />
        <PlanLimit
          text={t("billing.plan.members", {
            value: price.max_members ?? t("billing.plan.unlimited"),
          })}
        />
        <PlanLimit
          text={t("billing.plan.aiChecks", {
            value: price.monthly_ai_check_limit ?? t("billing.plan.unlimited"),
          })}
        />
      </ul>
      <Button className="mt-5 w-full" disabled={disabled} onClick={onSelect}>
        <CreditCard className="h-4 w-4" aria-hidden="true" />
        {t("billing.plan.choose", { plan: price.plan_name })}
      </Button>
    </article>
  );
}

function PlanLimit({ text }: { text: string }) {
  return (
    <li className="flex items-start gap-2">
      <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" aria-hidden="true" />
      <span>{text}</span>
    </li>
  );
}

function StatusMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof ShieldCheck;
  label: string;
  value: string;
}) {
  return (
    <div className="bg-ink-850 px-5 py-4">
      <dt className="flex items-center gap-2 text-xs font-medium text-mist-500">
        <Icon className="h-4 w-4" aria-hidden="true" />
        {label}
      </dt>
      <dd className="mt-1.5 text-sm font-medium text-mist-200">{value}</dd>
    </div>
  );
}

function ResultNotice({
  tone,
  title,
  children,
}: {
  tone: "success" | "neutral";
  title: string;
  children: string;
}) {
  return (
    <section
      role="status"
      className={
        tone === "success"
          ? "rounded-lg border border-emerald-400/25 bg-emerald-400/[0.07] px-5 py-4"
          : "rounded-lg border border-line bg-ink-900 px-5 py-4"
      }
    >
      <h2 className="font-semibold text-mist-100">{title}</h2>
      <p className="mt-1 text-sm text-mist-400">{children}</p>
    </section>
  );
}

function formatMoney(price: BillingCatalogPrice, locale: string): string {
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: price.currency,
      maximumFractionDigits: 2,
    }).format(price.unit_amount_minor / 100);
  } catch {
    return `${(price.unit_amount_minor / 100).toFixed(2)} ${price.currency}`;
  }
}

function formatBillingInterval(price: BillingCatalogPrice, t: ReturnType<typeof useT>): string {
  const intervalKey = ["day", "week", "month", "year"].includes(price.recurring_interval)
    ? price.recurring_interval
    : "period";
  return price.interval_count === 1
    ? t("billing.price.perInterval", { interval: t(`billing.interval.${intervalKey}`) })
    : t("billing.price.everyIntervals", {
        count: price.interval_count,
        interval: t(`billing.interval.${intervalKey}.plural`),
      });
}

function statusTone(status: string): BadgeTone {
  if (status === "active" || status === "trialing") return "emerald";
  if (status === "past_due" || status === "incomplete") return "amber";
  if (status === "unpaid" || status === "paused") return "rose";
  return "neutral";
}

function billingActionError(error: unknown, t: ReturnType<typeof useT>): string | null {
  if (!error) return null;
  if (error instanceof ApiError && error.status === 409) return t("billing.error.conflict");
  if (error instanceof ApiError && (error.status === 502 || error.status === 503)) {
    return t("billing.error.unavailable");
  }
  return t("billing.error.action");
}
