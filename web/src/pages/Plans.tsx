import { errorMessage } from "@/lib/errors";
import { useDialogState } from "@/lib/useDialogState";
import {
  Archive,
  BadgeDollarSign,
  Globe2,
  LockKeyhole,
  Pencil,
  Plus,
  ShieldOff,
  Tags,
  Trash2,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import { StepUpDialog } from "@/components/StepUpDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, type DialogVisibilityProps } from "@/components/ui/dialog";
import {
  CardGridSkeleton,
  EmptyState,
  ErrorNote,
  ErrorState,
  PageLoader,
  Spinner,
} from "@/components/ui/feedback";
import { Field, Input, Select } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { ApiError, instanceRequestContext } from "@/lib/api";
import { amountToCents, centsToAmount, formatMoney } from "@/lib/money";
import {
  useBillingPrices,
  useCreateBillingPrice,
  useCreatePlan,
  useCurrentUser,
  useDeletePlan,
  usePlans,
  usePricing,
  useSuggestPrice,
  useUpdatePlan,
  useUpdatePricing,
} from "@/lib/queries";
import type {
  BillingInterval,
  BillingPrice,
  BillingPriceInput,
  Plan,
  PlanInput,
  PricingContext,
} from "@/lib/types";
import { formatDateTime, parseLimit } from "@/lib/utils";

const PRICING_CURRENCIES = ["USD", "EUR", "GBP", "PLN"] as const;

export function Plans() {
  const t = useT();
  const { data: user, isLoading: meLoading } = useCurrentUser();
  const isOperator = user?.is_superadmin ?? false;
  const plans = usePlans(isOperator);
  const pricing = usePricing(isOperator);
  const billingPrices = useBillingPrices(isOperator);
  const { notify } = useToast();

  const creatingDialog = useDialogState(false);
  const { value: creating, setValue: setCreating } = creatingDialog;
  const editingDialog = useDialogState<Plan | null>(null);
  const { value: editing, setValue: setEditing } = editingDialog;
  const deletingDialog = useDialogState<Plan | null>(null);
  const { value: deleting, setValue: setDeleting } = deletingDialog;
  const publicationDialog = useDialogState<Plan | null>(null);
  const { value: changingPublication, setValue: setChangingPublication } = publicationDialog;

  if (meLoading) return <PageLoader label={t("plans.loading")} />;
  if (!isOperator) {
    return (
      <EmptyState
        icon={<ShieldOff className="h-5 w-5" />}
        title={t("organizations.superadminRequired.title")}
        description={t("organizations.superadminRequired.description")}
      />
    );
  }
  if (plans.isLoading || pricing.isLoading) return <CardGridSkeleton />;
  if (plans.isError) return <ErrorState onRetry={() => plans.refetch()} />;

  const list = plans.data ?? [];
  const currency = pricing.data?.currency ?? "USD";

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-100">
            {t("plans.title")}
          </h1>
          <p className="mt-1 text-sm text-mist-400">{t("plans.subtitle")}</p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" />
          {t("plans.newPlan")}
        </Button>
      </header>

      <section
        aria-labelledby="self-serve-hold-title"
        className="flex gap-3 rounded-lg border border-line-strong border-l-2 border-l-brand-700 bg-ink-900 px-4 py-3.5 shadow-card"
      >
        <LockKeyhole className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" aria-hidden="true" />
        <div>
          <h2 id="self-serve-hold-title" className="text-sm font-semibold text-mist-100">
            {t("plans.hold.title")}
          </h2>
          <p className="mt-1 text-xs leading-5 text-mist-400">{t("plans.hold.description")}</p>
        </div>
      </section>

      {list.length === 0 ? (
        <EmptyState
          icon={<Tags className="h-5 w-5" />}
          title={t("plans.empty.title")}
          description={t("plans.empty.description")}
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" />
              {t("plans.newPlan")}
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((plan) => {
            const planPrices = billingPrices.data?.filter(
              (price) => price.plan_id === plan.id,
            );
            return (
              <PlanCard
                key={plan.id}
                plan={plan}
                hasActivePrice={Boolean(planPrices?.some((price) => price.is_active))}
                hasPriceHistory={Boolean(planPrices?.length)}
                priceHistoryKnown={!billingPrices.isLoading && !billingPrices.isError}
                onEdit={() => setEditing(plan)}
                onDelete={() => setDeleting(plan)}
                onChangePublication={() => setChangingPublication(plan)}
              />
            );
          })}
        </div>
      )}

      <BillingPriceMappings
        plans={list}
        prices={billingPrices.data ?? []}
        isLoading={billingPrices.isLoading}
        isError={billingPrices.isError}
        onRetry={() => void billingPrices.refetch()}
      />

      {pricing.data ? <PricingCard pricing={pricing.data} /> : null}

      {creating ? (
        <PlanDialog
          key={creatingDialog.key}
          open={creatingDialog.open}
          onClosed={creatingDialog.onClosed}
          defaultCurrency={currency}
          onClose={creatingDialog.close}
          onSaved={() => {
            setCreating(false);
            notify(t("plans.created"));
          }}
        />
      ) : null}

      {editing ? (
        <PlanDialog
          key={editingDialog.key}
          open={editingDialog.open}
          onClosed={editingDialog.onClosed}
          plan={editing}
          defaultCurrency={currency}
          onClose={editingDialog.close}
          onSaved={() => {
            setEditing(null);
            notify(t("plans.updated"));
          }}
        />
      ) : null}

      {deleting ? (
        <DeletePlanDialog
          key={deletingDialog.key}
          open={deletingDialog.open}
          onClosed={deletingDialog.onClosed}
          plan={deleting}
          onClose={deletingDialog.close}
          onDeleted={() => {
            setDeleting(null);
            notify(t("plans.deleted"));
          }}
        />
      ) : null}

      {changingPublication ? (
        <PublicationDialog
          key={publicationDialog.key}
          open={publicationDialog.open}
          onClosed={publicationDialog.onClosed}
          plan={changingPublication}
          onClose={publicationDialog.close}
          onSaved={() => {
            notify(
              t(
                changingPublication.is_self_serve
                  ? "plans.archive.success"
                  : "plans.publish.success",
              ),
            );
            setChangingPublication(null);
          }}
        />
      ) : null}
    </div>
  );
}

function PlanCard({
  plan,
  hasActivePrice,
  hasPriceHistory,
  priceHistoryKnown,
  onEdit,
  onDelete,
  onChangePublication,
}: {
  plan: Plan;
  hasActivePrice: boolean;
  hasPriceHistory: boolean;
  priceHistoryKnown: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onChangePublication: () => void;
}) {
  const t = useT();
  const limit = (value: number | null) =>
    value === null ? t("plans.card.unlimited") : String(value);
  const isCustom = plan.price_override_cents !== null;
  let publicationUnavailable: string | null = null;
  if (!plan.is_self_serve) {
    if (!priceHistoryKnown) publicationUnavailable = t("plans.publish.priceUnknown");
    else if (!plan.is_active) publicationUnavailable = t("plans.publish.inactive");
    else if (!hasActivePrice) publicationUnavailable = t("plans.publish.unavailable");
  }

  return (
    <Card className="flex flex-col">
      <CardBody className="flex-1 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-semibold text-mist-100">{plan.name}</p>
            <Badge tone="brand" className="mt-1">
              {plan.key}
            </Badge>
          </div>
          {plan.is_active ? null : (
            <Badge tone="neutral">{t("plans.card.inactive")}</Badge>
          )}
        </div>

        <Badge tone={plan.is_self_serve ? "emerald" : "neutral"}>
          {t(
            plan.is_self_serve
              ? "plans.card.selfServePublished"
              : "plans.card.selfServeArchived",
          )}
        </Badge>
        {publicationUnavailable ? (
          <p className="text-xs leading-relaxed text-amber-400">{publicationUnavailable}</p>
        ) : null}

        <dl className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <dt className="text-mist-500">{t("plans.card.sites")}</dt>
            <dd className="text-mist-200">{limit(plan.max_sites)}</dd>
          </div>
          <div>
            <dt className="text-mist-500">{t("plans.card.members")}</dt>
            <dd className="text-mist-200">{limit(plan.max_members)}</dd>
          </div>
          <div>
            <dt className="text-mist-500">{t("plans.card.aiChecks")}</dt>
            <dd className="text-mist-200">{limit(plan.monthly_ai_check_limit)}</dd>
          </div>
        </dl>

        <div>
          <p className="text-xs font-medium text-mist-500">
            {t("plans.card.referenceEstimate")}
          </p>
          <p className="text-lg font-semibold text-mist-100">
            {formatMoney(plan.effective_price_cents, plan.currency)}
          </p>
          <p className="text-xs text-mist-500">
            {isCustom
              ? t("plans.card.algorithm", {
                  amount: formatMoney(plan.suggested_price_cents, plan.currency),
                })
              : t("plans.card.auto")}
          </p>
        </div>
      </CardBody>
      <div className="flex flex-wrap items-center justify-between gap-1 border-t border-line px-3 py-2">
        <Button
          variant="ghost"
          size="sm"
          aria-label={t(plan.is_self_serve ? "plans.archive.title" : "plans.publish.title", {
            name: plan.name,
          })}
          title={publicationUnavailable ?? undefined}
          disabled={Boolean(publicationUnavailable)}
          onClick={onChangePublication}
        >
          {plan.is_self_serve ? (
            <Archive className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Globe2 className="h-4 w-4" aria-hidden="true" />
          )}
          {t(plan.is_self_serve ? "plans.archive.action" : "plans.publish.action")}
        </Button>
        <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("plans.editAria", { name: plan.name })}
          onClick={onEdit}
        >
          <Pencil className="h-4 w-4" />
        </Button>
        {priceHistoryKnown && !hasPriceHistory ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("plans.deleteAria", { name: plan.name })}
            onClick={onDelete}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        ) : null}
        </div>
      </div>
    </Card>
  );
}

function BillingPriceMappings({
  plans,
  prices,
  isLoading,
  isError,
  onRetry,
}: {
  plans: Plan[];
  prices: BillingPrice[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}) {
  const t = useT();
  const { notify } = useToast();
  const creatingDialog = useDialogState(false);
  const { value: creating, setValue: setCreating } = creatingDialog;

  return (
    <section aria-labelledby="provider-prices-title" className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 id="provider-prices-title" className="text-lg font-semibold text-mist-100">
            {t("plans.billing.title")}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-mist-400">
            {t("plans.billing.subtitle")}
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          disabled={plans.length === 0 || isLoading || isError}
          onClick={() => setCreating(true)}
        >
          <BadgeDollarSign className="h-4 w-4" aria-hidden="true" />
          {t("plans.billing.new")}
        </Button>
      </div>

      {isLoading ? (
        <div
          role="status"
          className="flex min-h-28 items-center justify-center gap-2 rounded-lg border border-line bg-ink-900 text-sm text-mist-400"
        >
          <Spinner />
          {t("plans.billing.loading")}
        </div>
      ) : isError ? (
        <div className="flex flex-col gap-3 rounded-lg border border-rose-400/25 bg-rose-400/[0.06] px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <ErrorNote>{t("plans.billing.loadError")}</ErrorNote>
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {t("common.retry")}
          </Button>
        </div>
      ) : prices.length === 0 ? (
        <div className="flex items-start gap-3 rounded-lg border border-line bg-ink-900 px-4 py-4">
          <BadgeDollarSign className="mt-0.5 h-5 w-5 shrink-0 text-mist-500" aria-hidden="true" />
          <div>
            <h3 className="text-sm font-semibold text-mist-100">
              {t("plans.billing.empty.title")}
            </h3>
            <p className="mt-1 text-sm text-mist-400">
              {t("plans.billing.empty.description")}
            </p>
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-ink-900">
          <table className="w-full min-w-[52rem] text-left text-sm">
            <thead className="border-b border-line bg-ink-850 text-xs font-semibold text-mist-500">
              <tr>
                <th scope="col" className="px-4 py-3">{t("plans.billing.column.plan")}</th>
                <th scope="col" className="px-4 py-3">{t("plans.billing.column.providerId")}</th>
                <th scope="col" className="px-4 py-3">{t("plans.billing.column.amount")}</th>
                <th scope="col" className="px-4 py-3">{t("plans.billing.column.interval")}</th>
                <th scope="col" className="px-4 py-3">{t("plans.billing.column.state")}</th>
                <th scope="col" className="px-4 py-3">{t("plans.billing.column.created")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {prices.map((price) => {
                const plan = plans.find((candidate) => candidate.id === price.plan_id);
                return (
                  <tr key={price.id} className="text-mist-300">
                    <td className="px-4 py-3">
                      <span className="font-medium text-mist-100">
                        {plan?.name ?? t("plans.billing.unknownPlan", { id: price.plan_id })}
                      </span>
                      <span className="mt-0.5 block text-xs text-mist-500">
                        {t("plans.billing.version", { version: price.version })}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <code className="rounded bg-ink-800 px-1.5 py-1 text-xs text-mist-200">
                        {price.provider_price_id}
                      </code>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-mist-100">
                      {formatMoney(price.unit_amount_minor, price.currency)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      {formatProviderInterval(price, t)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={price.is_active ? "emerald" : "neutral"}>
                        {t(price.is_active ? "plans.billing.active" : "plans.billing.retired")}
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-mist-400">
                      {formatDateTime(price.created_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {creating ? (
        <BillingPriceDialog
          key={creatingDialog.key}
          open={creatingDialog.open}
          onClosed={creatingDialog.onClosed}
          plans={plans}
          onClose={creatingDialog.close}
          onSaved={() => {
            setCreating(false);
            notify(t("plans.billing.created"));
          }}
        />
      ) : null}
    </section>
  );
}

function BillingPriceDialog({
  open,
  onClosed,
  plans,
  onClose,
  onSaved,
}: {
  plans: Plan[];
  onClose: () => void;
  onSaved: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const create = useCreateBillingPrice();
  const [planId, setPlanId] = useState(plans[0]?.id.toString() ?? "");
  const [providerPriceId, setProviderPriceId] = useState("");
  const [amount, setAmount] = useState("");
  const [interval, setInterval] = useState<BillingInterval>("month");
  const [intervalCount, setIntervalCount] = useState("1");
  const [pendingBody, setPendingBody] = useState<BillingPriceInput | null>(null);
  const selectedPlan = plans.find((plan) => String(plan.id) === planId) ?? null;
  const error = priceMappingError(create.error, t);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!selectedPlan) return;
    create.reset();
    setPendingBody({
      plan_id: selectedPlan.id,
      provider: "stripe",
      provider_price_id: providerPriceId.trim(),
      unit_amount_minor: amountToCents(amount),
      currency: selectedPlan.currency.toUpperCase(),
      recurring_interval: interval,
      interval_count: Number.parseInt(intervalCount, 10),
    });
  }

  function savePendingPrice() {
    if (!pendingBody) return;
    create.mutate(pendingBody, { onSuccess: onSaved });
  }

  return (
    <>
      <Dialog
        open={open} onClosed={onClosed}
        onOpenChange={(open) => !open && onClose()}
        title={t("plans.billing.dialog.title")}
        description={t("plans.billing.dialog.description")}
        className="w-[min(94vw,42rem)]"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("plans.billing.field.plan")} htmlFor="billing-price-plan">
              <Select
                id="billing-price-plan"
                required
                value={planId}
                onChange={(event) => setPlanId(event.target.value)}
              >
                {plans.map((plan) => (
                  <option key={plan.id} value={plan.id}>
                    {plan.name} ({plan.key})
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("plans.billing.field.provider")} htmlFor="billing-price-provider">
              <Input id="billing-price-provider" value="Stripe" disabled />
            </Field>
          </div>

          <Field
            label={t("plans.billing.field.providerPriceId")}
            hint={t("plans.billing.field.providerPriceIdHint")}
            htmlFor="billing-provider-price-id"
          >
            <Input
              id="billing-provider-price-id"
              required
              maxLength={255}
              pattern="[A-Za-z0-9_]+"
              autoComplete="off"
              spellCheck={false}
              value={providerPriceId}
              onChange={(event) => setProviderPriceId(event.target.value)}
              placeholder="price_123"
            />
          </Field>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label={t("plans.billing.field.amount")}
              hint={t("plans.billing.field.amountHint")}
              htmlFor="billing-price-amount"
            >
              <Input
                id="billing-price-amount"
                type="number"
                required
                min={0}
                step="0.01"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </Field>
            <Field label={t("plans.billing.field.currency")} htmlFor="billing-price-currency">
              <Input
                id="billing-price-currency"
                value={selectedPlan?.currency.toUpperCase() ?? ""}
                disabled
              />
            </Field>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("plans.billing.field.interval")} htmlFor="billing-price-interval">
              <Select
                id="billing-price-interval"
                value={interval}
                onChange={(event) => setInterval(event.target.value as BillingInterval)}
              >
                {(["day", "week", "month", "year"] as const).map((value) => (
                  <option key={value} value={value}>
                    {t(`plans.billing.interval.${value}`)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label={t("plans.billing.field.intervalCount")}
              htmlFor="billing-price-interval-count"
            >
              <Input
                id="billing-price-interval-count"
                type="number"
                required
                min={1}
                max={36}
                step={1}
                value={intervalCount}
                onChange={(event) => setIntervalCount(event.target.value)}
              />
            </Field>
          </div>

          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!selectedPlan || create.isPending}>
              {create.isPending ? <Spinner /> : null}
              {t("plans.billing.register")}
            </Button>
          </div>
        </form>
      </Dialog>

      {open && pendingBody ? (
        <StepUpDialog
          title={t("plans.billing.confirmTitle")}
          description={t("plans.billing.confirmDescription")}
          submitLabel={t("plans.billing.register")}
          requestContext={instanceRequestContext}
          onVerified={savePendingPrice}
          onClose={() => setPendingBody(null)}
        />
      ) : null}
    </>
  );
}

function PublicationDialog({
  open,
  onClosed,
  plan,
  onClose,
  onSaved,
}: {
  plan: Plan;
  onClose: () => void;
  onSaved: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const update = useUpdatePlan(plan.id);
  const [confirming, setConfirming] = useState(false);
  const publishing = !plan.is_self_serve;
  const error = publicationError(update.error, t);

  return (
    <>
      <Dialog
        open={open} onClosed={onClosed}
        onOpenChange={(open) => !open && onClose()}
        title={t(publishing ? "plans.publish.title" : "plans.archive.title", {
          name: plan.name,
        })}
        description={t(
          publishing ? "plans.publish.description" : "plans.archive.description",
        )}
      >
        <div className="space-y-4">
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button
              type="button"
              variant={publishing ? "primary" : "danger"}
              disabled={update.isPending}
              onClick={() => setConfirming(true)}
            >
              {update.isPending ? <Spinner /> : null}
              {t(publishing ? "plans.publish.action" : "plans.archive.action")}
            </Button>
          </div>
        </div>
      </Dialog>

      {open && confirming ? (
        <StepUpDialog
          title={t(
            publishing ? "plans.publish.confirmTitle" : "plans.archive.confirmTitle",
          )}
          description={t(
            publishing
              ? "plans.publish.confirmDescription"
              : "plans.archive.confirmDescription",
            { name: plan.name },
          )}
          submitLabel={t(publishing ? "plans.publish.action" : "plans.archive.action")}
          requestContext={instanceRequestContext}
          submitVariant={publishing ? "primary" : "danger"}
          onVerified={() =>
            update.mutate({ is_self_serve: publishing }, { onSuccess: onSaved })
          }
          onClose={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}

function formatProviderInterval(price: BillingPrice, t: ReturnType<typeof useT>): string {
  const interval = t(`plans.billing.interval.${price.recurring_interval}`);
  return price.interval_count === 1 ? interval : `${price.interval_count} × ${interval}`;
}

function priceMappingError(error: unknown, t: ReturnType<typeof useT>): string | null {
  if (!error) return null;
  if (!(error instanceof ApiError)) return t("plans.billing.error.action");
  if (error.status === 404) return t("plans.billing.error.stalePlan");
  if (error.status === 409) return t("plans.billing.error.conflict");
  if (error.status === 502 || error.status === 503) return t("plans.billing.error.provider");
  return t("plans.billing.error.action");
}

function publicationError(error: unknown, t: ReturnType<typeof useT>): string | null {
  if (!error) return null;
  if (error instanceof ApiError && error.status === 409) {
    return t("plans.publish.error.notReady");
  }
  return t("plans.publish.error.action");
}

function PricingCard({ pricing }: { pricing: PricingContext }) {
  const t = useT();
  const { notify } = useToast();
  const update = useUpdatePricing();

  const [baseFee, setBaseFee] = useState(String(pricing.base_fee));
  const [perSiteFee, setPerSiteFee] = useState(String(pricing.per_site_fee));
  const [aiMargin, setAiMargin] = useState(String(pricing.ai_margin));
  const [currency, setCurrency] = useState(pricing.currency);
  const [pendingUpdate, setPendingUpdate] = useState<Partial<PricingContext> | null>(null);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setPendingUpdate({
      base_fee: Number(baseFee),
      per_site_fee: Number(perSiteFee),
      ai_margin: Number(aiMargin),
      currency: currency.toUpperCase(),
    });
  }

  function savePendingUpdate() {
    if (!pendingUpdate) return;
    update.mutate(pendingUpdate, { onSuccess: () => notify(t("plans.pricing.saved")) });
  }

  const error = update.error ? errorMessage(update.error, t) : null;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>{t("plans.pricing.title")}</CardTitle>
          <p className="mt-1 text-sm text-mist-400">{t("plans.pricing.subtitle")}</p>
        </CardHeader>
        <CardBody>
          <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label={t("plans.pricing.baseFee")} htmlFor="pricing-base-fee">
              <Input
                id="pricing-base-fee"
                type="number"
                min={0}
                step="0.01"
                value={baseFee}
                onChange={(event) => setBaseFee(event.target.value)}
              />
            </Field>
            <Field label={t("plans.pricing.perSiteFee")} htmlFor="pricing-per-site-fee">
              <Input
                id="pricing-per-site-fee"
                type="number"
                min={0}
                step="0.01"
                value={perSiteFee}
                onChange={(event) => setPerSiteFee(event.target.value)}
              />
            </Field>
            <Field
              label={t("plans.pricing.aiMargin")}
              hint={t("plans.pricing.aiMarginHint")}
              htmlFor="pricing-ai-margin"
            >
              <Input
                id="pricing-ai-margin"
                type="number"
                min={0}
                step="0.1"
                value={aiMargin}
                onChange={(event) => setAiMargin(event.target.value)}
              />
            </Field>
            <Field label={t("plans.pricing.currency")} htmlFor="pricing-currency">
              <Select
                id="pricing-currency"
                value={currency}
                onChange={(event) => setCurrency(event.target.value)}
              >
                {PRICING_CURRENCIES.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <p className="text-xs text-mist-500">
            {t("plans.pricing.derived", {
              model: pricing.model,
              cost: `${pricing.cost_per_check.toFixed(4)} ${pricing.currency}`,
              prompt: pricing.avg_prompt_tokens,
              completion: pricing.avg_completion_tokens,
            })}
          </p>

          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <div className="flex justify-end">
            <Button type="submit" variant="secondary" disabled={update.isPending}>
              {update.isPending ? <Spinner /> : null}
              {t("plans.pricing.save")}
            </Button>
          </div>
          </form>
        </CardBody>
      </Card>
      {pendingUpdate ? (
        <StepUpDialog
          title={t("plans.pricing.confirmTitle")}
          description={t("plans.pricing.confirmDescription")}
          submitLabel={t("plans.pricing.save")}
          requestContext={instanceRequestContext}
          onVerified={savePendingUpdate}
          onClose={() => setPendingUpdate(null)}
        />
      ) : null}
    </>
  );
}

function PlanDialog({
  open,
  onClosed,
  plan,
  defaultCurrency,
  onClose,
  onSaved,
}: {
  plan?: Plan | null;
  defaultCurrency: string;
  onClose: () => void;
  onSaved: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const create = useCreatePlan();
  const update = useUpdatePlan(plan?.id ?? 0);
  const mutation = plan ? update : create;

  const [name, setName] = useState(plan?.name ?? "");
  const [key, setKey] = useState(plan?.key ?? "");
  const [maxSites, setMaxSites] = useState(plan?.max_sites?.toString() ?? "");
  const [maxMembers, setMaxMembers] = useState(plan?.max_members?.toString() ?? "");
  const [aiLimit, setAiLimit] = useState(plan?.monthly_ai_check_limit?.toString() ?? "");
  const [price, setPrice] = useState(
    plan?.price_override_cents != null ? centsToAmount(plan.price_override_cents) : "",
  );
  const [currency, setCurrency] = useState(plan?.currency ?? defaultCurrency);
  const [active, setActive] = useState(plan?.is_active ?? true);
  const [pendingBody, setPendingBody] = useState<PlanInput | null>(null);

  const suggestion = useSuggestPrice(parseLimit(maxSites), parseLimit(aiLimit), true);
  const suggestedAmount = suggestion.data
    ? formatMoney(suggestion.data.suggested_price_cents, suggestion.data.currency)
    : null;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const body: PlanInput = {
      key: key.trim(),
      name: name.trim(),
      max_sites: parseLimit(maxSites),
      max_members: parseLimit(maxMembers),
      monthly_ai_check_limit: parseLimit(aiLimit),
      // Blank means "follow the internal cost model"; a value pins a planning override.
      price_override_cents: price.trim() === "" ? null : amountToCents(price),
      currency: currency.toUpperCase(),
      is_active: active,
      // Publication has its own explicit release control. An ordinary edit must
      // preserve the current state; new templates always start unpublished.
      is_self_serve: plan?.is_self_serve ?? false,
      sort_order: plan?.sort_order ?? 0,
    };
    setPendingBody(body);
  }

  function savePendingPlan() {
    if (!pendingBody) return;
    if (plan) update.mutate(pendingBody, { onSuccess: onSaved });
    else create.mutate(pendingBody, { onSuccess: onSaved });
  }

  const error = mutation.error ? errorMessage(mutation.error, t) : null;

  return (
    <>
      <Dialog
        open={open} onClosed={onClosed}
        onOpenChange={(open) => !open && onClose()}
        title={plan ? t("plans.edit.title") : t("plans.create.title")}
      >
        <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("plans.field.name")} htmlFor="plan-name">
            <Input
              id="plan-name"
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <Field label={t("plans.field.key")} hint={t("plans.field.keyHint")} htmlFor="plan-key">
            <Input
              id="plan-key"
              required
              value={key}
              onChange={(event) => setKey(event.target.value)}
              placeholder="starter"
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label={t("plans.field.maxSites")}
            hint={t("plans.field.limitHint")}
            htmlFor="plan-max-sites"
          >
            <Input
              id="plan-max-sites"
              type="number"
              min={0}
              value={maxSites}
              onChange={(event) => setMaxSites(event.target.value)}
              placeholder="∞"
            />
          </Field>
          <Field
            label={t("plans.field.maxMembers")}
            hint={t("plans.field.limitHint")}
            htmlFor="plan-max-members"
          >
            <Input
              id="plan-max-members"
              type="number"
              min={0}
              value={maxMembers}
              onChange={(event) => setMaxMembers(event.target.value)}
              placeholder="∞"
            />
          </Field>
          <Field
            label={t("plans.field.aiLimit")}
            hint={t("plans.field.limitHint")}
            htmlFor="plan-ai-limit"
          >
            <Input
              id="plan-ai-limit"
              type="number"
              min={0}
              value={aiLimit}
              onChange={(event) => setAiLimit(event.target.value)}
              placeholder="∞"
            />
          </Field>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t("plans.field.price")}
            hint={
              suggestedAmount
                ? t("plans.field.priceHint", { amount: suggestedAmount })
                : t("plans.field.priceHintPlain")
            }
            htmlFor="plan-price"
          >
            <Input
              id="plan-price"
              type="number"
              min={0}
              step="0.01"
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              placeholder={suggestedAmount ?? ""}
            />
          </Field>
          <Field label={t("plans.pricing.currency")} htmlFor="plan-currency">
            <Select
              id="plan-currency"
              value={currency}
              onChange={(event) => setCurrency(event.target.value)}
            >
              {PRICING_CURRENCIES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {suggestedAmount ? (
          <button
            type="button"
            onClick={() => suggestion.data && setPrice(centsToAmount(suggestion.data.suggested_price_cents))}
            className="text-sm font-medium text-brand-700 underline underline-offset-2 hover:text-mist-100"
          >
            {t("plans.field.useSuggestion", { amount: suggestedAmount })}
          </button>
        ) : null}

        <div className="flex items-center justify-between rounded-lg border border-line bg-ink-900/50 px-3.5 py-3">
          <div>
            <p className="text-sm font-medium text-mist-300">{t("plans.field.active")}</p>
            <p className="text-xs text-mist-500">{t("plans.field.activeHint")}</p>
          </div>
          <Switch
            aria-label={t("plans.field.active")}
            checked={active}
            onCheckedChange={setActive}
          />
        </div>

        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? <Spinner /> : null}
            {t("plans.save")}
          </Button>
        </div>
        </form>
      </Dialog>
      {open && pendingBody ? (
        <StepUpDialog
          title={t("plans.change.confirmTitle")}
          description={t("plans.change.confirmDescription")}
          submitLabel={t("plans.save")}
          requestContext={instanceRequestContext}
          onVerified={savePendingPlan}
          onClose={() => setPendingBody(null)}
        />
      ) : null}
    </>
  );
}

function DeletePlanDialog({
  open,
  onClosed,
  plan,
  onClose,
  onDeleted,
}: {
  plan: Plan;
  onClose: () => void;
  onDeleted: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const remove = useDeletePlan();
  const [confirming, setConfirming] = useState(false);
  const error = remove.error ? errorMessage(remove.error, t) : null;

  return (
    <>
      <Dialog
        open={open} onClosed={onClosed}
        onOpenChange={(open) => !open && onClose()}
        title={t("plans.delete.title")}
        description={t("plans.delete.description", { name: plan.name })}
      >
        <div className="space-y-4">
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => setConfirming(true)}
            >
              {remove.isPending ? <Spinner /> : null}
              {t("plans.delete.submit")}
            </Button>
          </div>
        </div>
      </Dialog>
      {open && confirming ? (
        <StepUpDialog
          title={t("plans.delete.confirmTitle")}
          description={t("plans.delete.confirmDescription", { name: plan.name })}
          submitLabel={t("plans.delete.submit")}
          submitVariant="danger"
          requestContext={instanceRequestContext}
          onVerified={() => remove.mutate(plan.id, { onSuccess: onDeleted })}
          onClose={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}
