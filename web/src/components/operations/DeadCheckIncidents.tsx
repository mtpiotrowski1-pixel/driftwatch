import {
  AlertOctagon,
  ArrowDown,
  Building2,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { useId, useMemo, useRef, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNote, Spinner } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import {
  ApiError,
  RequestContextChangedError,
  assertRequestContextCurrent,
  organizationRequestContext,
} from "@/lib/api";
import { useCurrentUser, useStepUp } from "@/lib/queries";
import { cn, formatDateTime } from "@/lib/utils";

import {
  useDeadCheckIncidents,
  useRedriveDeadCheck,
  type DeadCheckIncident,
  type DeadCheckScope,
} from "./data";

interface DeadCheckIncidentsProps {
  scope: DeadCheckScope;
  organizationName?: (organizationId: number) => string;
  onOpenOrganization?: (organizationId: number, organizationName: string) => void;
}

export function DeadCheckIncidents({
  scope,
  organizationName,
  onOpenOrganization,
}: DeadCheckIncidentsProps) {
  const t = useT();
  const incidents = useDeadCheckIncidents(scope, true);
  const [selected, setSelected] = useState<DeadCheckIncident | null>(null);
  const rows = useMemo(
    () => incidents.data?.pages.flatMap((page) => page.items) ?? [],
    [incidents.data],
  );
  const instance = scope.kind === "instance";
  const queryError =
    incidents.error instanceof ApiError
      ? incidents.error.message
      : incidents.isError
        ? t("operations.incidents.error")
        : null;

  return (
    <>
      <section
        aria-labelledby="operations-incidents-title"
        className="overflow-hidden rounded-lg border border-line-strong bg-ink-900 shadow-card"
      >
        <header className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 gap-3">
            <span
              className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-rose-400/25 bg-rose-400/10 text-rose-400"
              aria-hidden="true"
            >
              <AlertOctagon className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2
                  id="operations-incidents-title"
                  className="text-base font-semibold text-mist-100"
                >
                  {t("operations.incidents.title")}
                </h2>
                {!incidents.isLoading ? (
                  <Badge tone={rows.length > 0 ? "rose" : "emerald"}>
                    {rows.length > 0
                      ? t("operations.incidents.visibleCount", { count: rows.length })
                      : t("operations.incidents.clear")}
                  </Badge>
                ) : null}
              </div>
              <p className="mt-1 max-w-3xl text-sm leading-relaxed text-mist-400">
                {t(
                  instance
                    ? "operations.incidents.instanceDescription"
                    : "operations.incidents.tenantDescription",
                )}
              </p>
            </div>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="w-full rounded-md sm:w-auto"
            disabled={incidents.isFetching}
            onClick={() => void incidents.refetch()}
          >
            {incidents.isFetching && !incidents.isFetchingNextPage ? (
              <Spinner aria-hidden="true" />
            ) : (
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
            )}
            {t("operations.incidents.refresh")}
          </Button>
        </header>

        {queryError ? (
          <div className="space-y-3 border-t border-line px-5 py-4">
            <ErrorNote>{queryError}</ErrorNote>
            {rows.length === 0 ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => void incidents.refetch()}
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                {t("common.retry")}
              </Button>
            ) : null}
          </div>
        ) : null}

        {incidents.isLoading ? (
          <div
            role="status"
            aria-live="polite"
            className="flex min-h-36 items-center justify-center gap-2 border-t border-line text-sm text-mist-400"
          >
            <Spinner aria-hidden="true" />
            {t("operations.incidents.loading")}
          </div>
        ) : rows.length === 0 && !queryError ? (
          <div className="flex min-h-36 flex-col items-center justify-center gap-2 border-t border-line px-5 py-8 text-center">
            <CheckCircle2 className="h-6 w-6 text-emerald-400" aria-hidden="true" />
            <p className="text-sm font-semibold text-mist-200">
              {t("operations.incidents.emptyTitle")}
            </p>
            <p className="max-w-lg text-xs leading-relaxed text-mist-500">
              {t("operations.incidents.emptyDescription")}
            </p>
          </div>
        ) : rows.length > 0 ? (
          <ul className="divide-y divide-line border-t border-line">
            {rows.map((incident) => {
              const name = organizationName?.(incident.organization_id);
              return (
                <IncidentRow
                  key={incident.id}
                  incident={incident}
                  organizationName={name}
                  instance={instance}
                  onAction={() => {
                    if (instance && onOpenOrganization) {
                      onOpenOrganization(
                        incident.organization_id,
                        name ?? t("operations.incidents.organizationFallback", {
                          id: incident.organization_id,
                        }),
                      );
                      return;
                    }
                    setSelected(incident);
                  }}
                />
              );
            })}
          </ul>
        ) : null}

        {incidents.hasNextPage ? (
          <div className="flex justify-center border-t border-line px-5 py-4">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={incidents.isFetchingNextPage}
              onClick={() => void incidents.fetchNextPage()}
            >
              {incidents.isFetchingNextPage ? (
                <Spinner aria-hidden="true" />
              ) : (
                <ArrowDown className="h-4 w-4" aria-hidden="true" />
              )}
              {t("operations.incidents.loadMore")}
            </Button>
          </div>
        ) : null}
      </section>

      {selected && scope.kind === "tenant" ? (
        <RedriveDialog
          incident={selected}
          organizationId={scope.organizationId}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </>
  );
}

function IncidentRow({
  incident,
  organizationName,
  instance,
  onAction,
}: {
  incident: DeadCheckIncident;
  organizationName?: string;
  instance: boolean;
  onAction: () => void;
}) {
  const t = useT();
  return (
    <li className="grid gap-4 px-5 py-4 transition-colors hover:bg-ink-850/55 lg:grid-cols-[minmax(13rem,1.35fr)_minmax(7rem,.7fr)_minmax(8rem,.8fr)_auto] lg:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-semibold text-mist-100">
            {instance
              ? organizationName ??
                t("operations.incidents.organizationFallback", {
                  id: incident.organization_id,
                })
              : t("operations.incidents.job", { id: incident.id })}
          </p>
          <Badge tone="rose">{t("operations.incidents.status.dead")}</Badge>
          {incident.original_job_id ? (
            <Badge tone="amber">{t("operations.incidents.recoveryAttempt")}</Badge>
          ) : null}
        </div>
        <p className="mt-1 text-xs text-mist-500">
          {instance ? `${t("operations.incidents.job", { id: incident.id })} · ` : null}
          {t("operations.incidents.site", { id: incident.site_id })}
        </p>
      </div>

      <IncidentDatum
        label={t("operations.incidents.origin")}
        value={t(`operations.incidents.source.${incident.source}`)}
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-1 lg:gap-1">
        <IncidentDatum
          label={t("operations.incidents.attempts")}
          value={String(incident.attempt_count)}
          compact
        />
        <IncidentDatum
          label={t("operations.incidents.completed")}
          value={formatDateTime(incident.completed_at ?? incident.enqueued_at)}
          dateTime={incident.completed_at ?? incident.enqueued_at}
          compact
        />
      </div>

      <Button
        type="button"
        variant={instance ? "secondary" : "primary"}
        size="sm"
        className="w-full rounded-md lg:w-auto"
        onClick={onAction}
      >
        {instance ? (
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
        ) : (
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
        )}
        {t(
          instance
            ? "operations.incidents.openOrganization"
            : "operations.incidents.redriveAction",
        )}
      </Button>
    </li>
  );
}

function IncidentDatum({
  label,
  value,
  dateTime,
  compact = false,
}: {
  label: string;
  value: string;
  dateTime?: string;
  compact?: boolean;
}) {
  return (
    <dl className={cn("min-w-0", compact && "lg:flex lg:items-baseline lg:gap-2")}>
      <dt className="text-xs text-mist-500">{label}</dt>
      <dd className="mt-1 break-words text-xs font-medium text-mist-300 lg:mt-0">
        {dateTime ? <time dateTime={dateTime}>{value}</time> : value}
      </dd>
    </dl>
  );
}

function RedriveDialog({
  incident,
  organizationId,
  onClose,
}: {
  incident: DeadCheckIncident;
  organizationId: number;
  onClose: () => void;
}) {
  const t = useT();
  const { notify } = useToast();
  const { data: user } = useCurrentUser();
  const context = organizationRequestContext(organizationId);
  const stepUp = useStepUp(context);
  const redrive = useRedriveDeadCheck(organizationId);
  const errorId = useId();
  const request = useRef<{ fingerprint: string; key: string } | null>(null);
  const [reason, setReason] = useState("");
  const [ticket, setTicket] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [validationError, setValidationError] = useState<{
    field: "reason" | "ticket" | "password" | "totp";
    message: string;
  } | null>(null);
  const [attemptError, setAttemptError] = useState<string | null>(null);
  const pending = stepUp.isPending || redrive.isPending;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const normalizedReason = reason.trim();
    const normalizedTicket = ticket.trim();
    const normalizedCode = code.trim();
    const credentials = {
      password,
      totp_code: user?.totp_enabled ? normalizedCode : undefined,
    };

    // Credentials should never survive an attempted privileged action in UI state.
    setPassword("");
    setCode("");

    if (normalizedReason.length < 10) {
      setValidationError({
        field: "reason",
        message: t("operations.incidents.reasonInvalid"),
      });
      return;
    }
    if (!normalizedTicket) {
      setValidationError({
        field: "ticket",
        message: t("operations.incidents.ticketInvalid"),
      });
      return;
    }
    if (!credentials.password) {
      setValidationError({
        field: "password",
        message: t("operations.incidents.passwordInvalid"),
      });
      return;
    }
    if (user?.totp_enabled && !normalizedCode) {
      setValidationError({
        field: "totp",
        message: t("operations.incidents.totpInvalid"),
      });
      return;
    }

    setValidationError(null);
    setAttemptError(null);
    stepUp.reset();
    redrive.reset();
    const fingerprint = JSON.stringify([normalizedReason, normalizedTicket]);
    if (request.current?.fingerprint !== fingerprint) {
      request.current = { fingerprint, key: crypto.randomUUID() };
    }

    try {
      assertRequestContextCurrent(context);
      await stepUp.mutateAsync(credentials);
      assertRequestContextCurrent(context);
      const result = await redrive.mutateAsync({
        jobId: incident.id,
        idempotency_key: request.current.key,
        reason: normalizedReason,
        ticket: normalizedTicket,
      });
      notify(
        t(
          result.created
            ? "operations.incidents.redriveQueued"
            : "operations.incidents.redriveAlreadyQueued",
        ),
      );
      onClose();
    } catch (error) {
      setAttemptError(
        error instanceof RequestContextChangedError
          ? t("common.contextChanged")
          : error instanceof ApiError
            ? error.message
            : t("operations.incidents.redriveError"),
      );
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !pending && onClose()}
      title={t("operations.incidents.dialogTitle", { id: incident.id })}
      description={t("operations.incidents.dialogDescription", { site: incident.site_id })}
    >
      <form
        noValidate
        aria-busy={pending}
        className="space-y-5"
        onSubmit={(event) => void handleSubmit(event)}
      >
        <div className="flex items-start gap-3 border-y border-line py-3 text-xs text-mist-400">
          <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-mist-500" aria-hidden="true" />
          <p>{t("operations.incidents.dialogSafety")}</p>
        </div>

        <Field
          label={t("operations.incidents.reasonLabel")}
          hint={t("operations.incidents.reasonHint")}
          htmlFor="redrive-reason"
        >
          <Textarea
            id="redrive-reason"
            required
            autoFocus
            minLength={10}
            maxLength={500}
            disabled={pending}
            value={reason}
            aria-invalid={validationError?.field === "reason" ? true : undefined}
            aria-describedby={validationError?.field === "reason" ? errorId : undefined}
            placeholder={t("operations.incidents.reasonPlaceholder")}
            onChange={(event) => {
              setReason(event.target.value);
              setValidationError(null);
              setAttemptError(null);
            }}
          />
        </Field>
        <Field
          label={t("operations.incidents.ticketLabel")}
          hint={t("operations.incidents.ticketHint")}
          htmlFor="redrive-ticket"
        >
          <Input
            id="redrive-ticket"
            required
            maxLength={100}
            disabled={pending}
            value={ticket}
            aria-invalid={validationError?.field === "ticket" ? true : undefined}
            aria-describedby={validationError?.field === "ticket" ? errorId : undefined}
            placeholder={t("operations.incidents.ticketPlaceholder")}
            onChange={(event) => {
              setTicket(event.target.value);
              setValidationError(null);
              setAttemptError(null);
            }}
          />
        </Field>

        <div className="space-y-4 border-t border-line pt-5">
          <p className="text-sm text-mist-400">{t("support.reauth")}</p>
          <Field label={t("twofa.stepup.password")} htmlFor="redrive-password">
            <Input
              id="redrive-password"
              type="password"
              required
              maxLength={128}
              disabled={pending}
              value={password}
              aria-invalid={validationError?.field === "password" ? true : undefined}
              aria-describedby={validationError?.field === "password" ? errorId : undefined}
              autoComplete="current-password"
              onChange={(event) => {
                setPassword(event.target.value);
                setValidationError(null);
                setAttemptError(null);
              }}
            />
          </Field>
          {user?.totp_enabled ? (
            <Field
              label={t("twofa.stepup.code")}
              hint={t("twofa.stepup.codeHint")}
              htmlFor="redrive-code"
            >
              <Input
                id="redrive-code"
                required
                maxLength={20}
                disabled={pending}
                value={code}
                aria-invalid={validationError?.field === "totp" ? true : undefined}
                aria-describedby={validationError?.field === "totp" ? errorId : undefined}
                autoComplete="one-time-code"
                inputMode="numeric"
                placeholder="123456"
                onChange={(event) => {
                  setCode(event.target.value);
                  setValidationError(null);
                  setAttemptError(null);
                }}
              />
            </Field>
          ) : null}
        </div>

        {validationError || attemptError ? (
          <div id={errorId}>
            <ErrorNote>{validationError?.message ?? attemptError}</ErrorNote>
          </div>
        ) : null}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="ghost"
            className="w-full rounded-md sm:w-auto"
            disabled={pending}
            onClick={onClose}
          >
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            className="w-full rounded-md sm:w-auto"
            disabled={pending}
          >
            {pending ? (
              <Spinner aria-hidden="true" />
            ) : (
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
            )}
            {pending
              ? t("operations.incidents.redrivePending")
              : t("operations.incidents.redriveConfirm")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
