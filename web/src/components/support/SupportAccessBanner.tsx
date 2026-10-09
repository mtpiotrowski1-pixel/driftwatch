import {
  Building2,
  Clock3,
  LockKeyhole,
  RotateCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useReducer, useState, type FormEvent, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
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
import {
  useGrantSupportAccess,
  useRevokeSupportAccess,
  useSupportAccess,
  clearSupportTenantCache,
  type SupportAccessState,
} from "@/lib/supportAccess";
import { cn, formatDateTime } from "@/lib/utils";

interface SupportAccessBannerProps {
  organizationId: number;
  organizationName: string;
  onExit: () => Promise<void>;
}

export function SupportAccessBanner({
  organizationId,
  organizationName,
  onExit,
}: SupportAccessBannerProps) {
  const t = useT();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const access = useSupportAccess(organizationId);
  const revoke = useRevokeSupportAccess(organizationId);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [, refreshExpiry] = useReducer((value: number) => value + 1, 0);
  const expiresAt = access.data?.expires_at;
  const refetchAccess = access.refetch;

  useEffect(() => {
    setDialogOpen(false);
  }, [organizationId]);

  useEffect(() => {
    if (!expiresAt) return;
    const remaining = Date.parse(expiresAt) - Date.now();
    if (!Number.isFinite(remaining)) return;
    const timer = window.setTimeout(
      () => {
        clearSupportTenantCache(queryClient);
        refreshExpiry();
        void refetchAccess();
      },
      Math.max(remaining + 100, 0),
    );
    return () => window.clearTimeout(timer);
  }, [expiresAt, queryClient, refetchAccess]);

  async function handleRevoke() {
    try {
      await revoke.mutateAsync();
      notify(t("support.revoke.success"));
    } catch {
      // The mutation exposes its safe ApiError below; retain write-state until
      // the server confirms the cookie was actually removed.
    }
  }

  async function handleExitWithRevoke() {
    try {
      await revoke.mutateAsync();
      await onExit();
    } catch {
      // Do not leave an apparently inactive workspace while its access grant is
      // still live. The inline mutation error explains why exit was stopped.
    }
  }

  const accessEnabled = access.data ? hasUnexpiredSupportAccess(access.data) : false;
  const revokeError = revoke.error instanceof ApiError
    ? revoke.error.message
    : revoke.isError
      ? t("common.requestFailed")
      : null;

  if (access.isLoading) {
    return (
      <BannerFrame icon={<Spinner />} tone="neutral">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-mist-100">{t("support.checking.title")}</p>
          <p className="mt-0.5 text-xs text-mist-400">
            {t("support.checking.description", { name: organizationName })}
          </p>
          {revokeError ? (
            <p role="alert" className="mt-1.5 text-xs text-rose-400">
              {revokeError}
            </p>
          ) : null}
        </div>
        <ExitButton
          onClick={() => void handleExitWithRevoke()}
          disabled={revoke.isPending}
        />
      </BannerFrame>
    );
  }

  if (
    access.isError ||
    !access.data ||
    access.data.organization_id !== organizationId
  ) {
    return (
      <BannerFrame icon={<ShieldAlert className="h-4 w-4" />} tone="danger">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-rose-400">{t("support.error.title")}</p>
          <p className="mt-0.5 text-xs text-mist-400">{t("support.error.description")}</p>
          {revokeError ? (
            <p role="alert" className="mt-1.5 text-xs text-rose-400">
              {revokeError}
            </p>
          ) : null}
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end">
          <Button
            variant="secondary"
            size="sm"
            className="flex-1 rounded-md sm:flex-none"
            onClick={() => void access.refetch()}
          >
            <RotateCw className="h-3.5 w-3.5" />
            {t("common.retry")}
          </Button>
          <ExitButton
            onClick={() => void handleExitWithRevoke()}
            disabled={revoke.isPending}
          />
        </div>
      </BannerFrame>
    );
  }

  if (!access.data.required) {
    return (
      <BannerFrame icon={<Building2 className="h-4 w-4" />} tone="local">
        <p className="min-w-0 flex-1 text-sm text-mist-200">
          {t("organizations.managing", { name: organizationName })}
        </p>
        <ExitButton onClick={() => void onExit()} />
      </BannerFrame>
    );
  }

  return (
    <>
      <BannerFrame
        icon={
          accessEnabled ? (
            <ShieldCheck className="h-4 w-4" />
          ) : (
            <LockKeyhole className="h-4 w-4" />
          )
        }
        tone={accessEnabled ? "write" : "readonly"}
      >
        <div className="min-w-0 flex-1">
          <p
            className={cn(
              "text-sm font-semibold",
              accessEnabled ? "text-amber-300" : "text-mist-100",
            )}
          >
            {accessEnabled ? t("support.write.title") : t("support.readonly.title")}
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-mist-400">
            {accessEnabled && access.data.expires_at ? (
              <>
                {t("support.write.description", { name: organizationName })} {" "}
                <Clock3 className="mb-0.5 ml-1 inline h-3 w-3" /> {" "}
                <time dateTime={access.data.expires_at}>
                  {t("support.write.expires", {
                    time: formatDateTime(access.data.expires_at),
                  })}
                </time>
              </>
            ) : (
              t("support.readonly.description", { name: organizationName })
            )}
          </p>
          {revokeError ? (
            <p role="alert" className="mt-1.5 text-xs text-rose-400">
              {revokeError}
            </p>
          ) : null}
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end">
          {accessEnabled ? (
            <Button
              variant="secondary"
              size="sm"
              className="flex-1 rounded-md sm:flex-none"
              disabled={revoke.isPending}
              onClick={() => void handleRevoke()}
            >
              {revoke.isPending ? <Spinner /> : <LockKeyhole className="h-3.5 w-3.5" />}
              {t("support.revoke.action")}
            </Button>
          ) : (
            <Button
              size="sm"
              className="flex-1 rounded-md sm:flex-none"
              onClick={() => setDialogOpen(true)}
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              {t("support.grant.action")}
            </Button>
          )}
          <ExitButton
            onClick={accessEnabled ? () => void handleExitWithRevoke() : () => void onExit()}
            disabled={accessEnabled && revoke.isPending}
          />
        </div>
      </BannerFrame>

      {dialogOpen ? (
        <SupportAccessDialog
          organizationId={organizationId}
          organizationName={organizationName}
          onClose={() => setDialogOpen(false)}
        />
      ) : null}
    </>
  );
}

function SupportAccessDialog({
  organizationId,
  organizationName,
  onClose,
}: {
  organizationId: number;
  organizationName: string;
  onClose: () => void;
}) {
  const t = useT();
  const { notify } = useToast();
  const { data: user } = useCurrentUser();
  const context = organizationRequestContext(organizationId);
  const stepUp = useStepUp(context);
  const grant = useGrantSupportAccess(organizationId);
  const [reason, setReason] = useState("");
  const [ticket, setTicket] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [attemptError, setAttemptError] = useState<string | null>(null);
  const pending = stepUp.isPending || grant.isPending;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const normalizedReason = reason.trim();
    const normalizedTicket = ticket.trim();
    const credentials = {
      password,
      totp_code: user?.totp_enabled ? code.trim() : undefined,
    };
    setPassword("");
    setCode("");
    if (normalizedReason.length < 10) {
      setValidationError(t("support.reason.invalid"));
      return;
    }
    setValidationError(null);
    setAttemptError(null);
    stepUp.reset();
    grant.reset();
    try {
      assertRequestContextCurrent(context);
      await stepUp.mutateAsync(credentials);
      assertRequestContextCurrent(context);
      await grant.mutateAsync({
        reason: normalizedReason,
        ticket: normalizedTicket || undefined,
      });
      notify(t("support.grant.success"));
      onClose();
    } catch (error) {
      setAttemptError(
        error instanceof RequestContextChangedError
          ? t("common.contextChanged")
          : error instanceof ApiError
            ? error.message
            : t("common.requestFailed"),
      );
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !pending && onClose()}
      title={t("support.dialog.title")}
      description={t("support.dialog.description", { name: organizationName })}
    >
      <form onSubmit={(event) => void handleSubmit(event)} className="space-y-5">
        <Field
          label={t("support.reason.label")}
          hint={t("support.reason.hint")}
          htmlFor="support-reason"
        >
          <Textarea
            id="support-reason"
            required
            autoFocus
            minLength={10}
            maxLength={500}
            value={reason}
            aria-invalid={validationError ? true : undefined}
            onChange={(event) => {
              setReason(event.target.value);
              if (validationError) setValidationError(null);
            }}
            placeholder={t("support.reason.placeholder")}
          />
        </Field>
        <Field
          label={t("support.ticket.label")}
          hint={t("support.ticket.hint")}
          htmlFor="support-ticket"
        >
          <Input
            id="support-ticket"
            maxLength={100}
            value={ticket}
            onChange={(event) => setTicket(event.target.value)}
            placeholder={t("support.ticket.placeholder")}
          />
        </Field>

        <div className="space-y-4 border-t border-line pt-5">
          <p className="text-sm text-mist-400">{t("support.reauth")}</p>
          <Field label={t("twofa.stepup.password")} htmlFor="support-password">
            <Input
              id="support-password"
              type="password"
              required
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </Field>
          {user?.totp_enabled ? (
            <Field
              label={t("twofa.stepup.code")}
              hint={t("twofa.stepup.codeHint")}
              htmlFor="support-code"
            >
              <Input
                id="support-code"
                required
                maxLength={20}
                value={code}
                onChange={(event) => setCode(event.target.value)}
                autoComplete="one-time-code"
                placeholder="123456"
              />
            </Field>
          ) : null}
        </div>

        {validationError || attemptError ? (
          <ErrorNote>{validationError ?? attemptError}</ErrorNote>
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
            {pending ? <Spinner /> : <ShieldCheck className="h-4 w-4" />}
            {t("support.grant.confirm")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function hasUnexpiredSupportAccess(state: SupportAccessState): boolean {
  if (!state.access_enabled || !state.expires_at) return false;
  const expiresAt = Date.parse(state.expires_at);
  return Number.isFinite(expiresAt) && expiresAt > Date.now();
}

function ExitButton({ onClick, disabled = false }: { onClick: () => void; disabled?: boolean }) {
  const t = useT();
  return (
    <Button
      variant="ghost"
      size="sm"
      className="flex-1 rounded-md underline sm:flex-none"
      onClick={onClick}
      disabled={disabled}
    >
      {t("organizations.exit")}
    </Button>
  );
}

function BannerFrame({
  icon,
  tone,
  children,
}: {
  icon: ReactNode;
  tone: "neutral" | "danger" | "local" | "readonly" | "write";
  children: ReactNode;
}) {
  return (
    <section
      aria-live="polite"
      className={cn(
        "mb-6 flex flex-col gap-3 rounded-lg border bg-ink-900 px-4 py-3 sm:flex-row sm:items-center",
        tone === "neutral" && "border-line bg-ink-900 text-mist-400",
        tone === "danger" && "border-rose-400/30",
        tone === "local" && "border-brand-600/30",
        tone === "readonly" && "border-line-strong bg-ink-900",
        tone === "write" && "border-amber-400/35",
      )}
    >
      <span
        className={cn(
          "grid h-8 w-8 shrink-0 place-items-center rounded-full border",
          tone === "write"
            ? "border-amber-400/30 bg-amber-400/10 text-amber-300"
            : tone === "danger"
              ? "border-rose-400/30 bg-rose-400/10 text-rose-400"
              : "border-line bg-ink-850 text-mist-300",
        )}
      >
        {icon}
      </span>
      {children}
    </section>
  );
}
