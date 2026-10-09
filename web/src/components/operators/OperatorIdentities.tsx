import { errorMessage } from "@/lib/errors";
import { useDialogState } from "@/lib/useDialogState";
import {
  LogOut,
  Mail,
  Pencil,
  Power,
  PowerOff,
  ShieldCheck,
  ShieldPlus,
  ShieldX,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import { StepUpDialog } from "@/components/StepUpDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, type DialogVisibilityProps } from "@/components/ui/dialog";
import { EmptyState, ErrorNote, ErrorState, PageLoader, Spinner } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { ApiError, instanceRequestContext } from "@/lib/api";
import {
  useCreateOperator,
  useInviteOperator,
  useOperators,
  useResetOperatorTotp,
  useRevokeOperatorSessions,
  useUpdateOperator,
} from "@/lib/queries";
import type { OperatorIdentity } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

type OperatorAction = "deactivate" | "reactivate" | "invite" | "revoke" | "reset-totp";

export function OperatorIdentities({ currentUserId }: { currentUserId: number }) {
  const t = useT();
  const operators = useOperators();
  const [createOpen, setCreateOpen] = useState(false);
  const editingDialog = useDialogState<OperatorIdentity | null>(null);
  const { value: editing, setValue: setEditing } = editingDialog;
  const [action, setAction] = useState<{
    kind: OperatorAction;
    operator: OperatorIdentity;
  } | null>(null);

  if (operators.isLoading) return <PageLoader label={t("access.operators.loading")} />;
  if (operators.isError) return <ErrorState onRetry={() => void operators.refetch()} />;

  const rows = operators.data ?? [];
  const addButton = (
    <Button onClick={() => setCreateOpen(true)}>
      <ShieldPlus className="h-4 w-4" />
      {t("access.operators.add")}
    </Button>
  );

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-mist-100">
            {t("access.operators.title")}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-mist-400">
            {t("access.operators.subtitle")}
          </p>
        </div>
        {addButton}
      </header>

      {rows.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck className="h-5 w-5" />}
          title={t("access.operators.empty.title")}
          description={t("access.operators.empty.description")}
          action={addButton}
        />
      ) : (
        <Card>
          <ul className="divide-y divide-line">
            {rows.map((operator) => (
              <OperatorRow
                key={operator.id}
                operator={operator}
                isSelf={operator.id === currentUserId}
                onEdit={() => setEditing(operator)}
                onAction={(kind) => setAction({ kind, operator })}
              />
            ))}
          </ul>
        </Card>
      )}

      <CreateOperatorDialog open={createOpen} onOpenChange={setCreateOpen} />
      {editing ? (
        <EditOperatorDialog key={editingDialog.key} open={editingDialog.open} onClosed={editingDialog.onClosed} operator={editing} onClose={editingDialog.close} />
      ) : null}
      {action ? (
        <OperatorActionDialog
          kind={action.kind}
          operator={action.operator}
          isSelf={action.operator.id === currentUserId}
          onClose={() => setAction(null)}
        />
      ) : null}
    </div>
  );
}

function OperatorRow({
  operator,
  isSelf,
  onEdit,
  onAction,
}: {
  operator: OperatorIdentity;
  isSelf: boolean;
  onEdit: () => void;
  onAction: (kind: OperatorAction) => void;
}) {
  const t = useT();
  return (
    <li className="flex flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-300/35 text-sm font-semibold text-brand-700">
          {(operator.name ?? operator.email).slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-mist-100">
              {operator.name ?? operator.email}
            </p>
            {isSelf ? <Badge tone="brand">{t("access.operators.self")}</Badge> : null}
          </div>
          <p className="truncate text-xs text-mist-500">{operator.email}</p>
          <p className="mt-1 text-xs text-mist-500">
            {operator.last_login_at
              ? t("access.operators.lastLogin", { date: formatDateTime(operator.last_login_at) })
              : t("access.operators.firstLoginPending")}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 lg:justify-end">
        <Badge tone={operator.totp_enabled ? "emerald" : "amber"}>
          {operator.totp_enabled
            ? t("access.operators.mfa.active")
            : t("access.operators.mfa.pending")}
        </Badge>
        <Badge tone={operator.is_active ? "emerald" : "neutral"}>
          {operator.is_active
            ? t("access.operators.state.active")
            : t("access.operators.state.inactive")}
        </Badge>
        <Button variant="secondary" size="sm" onClick={() => onAction("invite")} disabled={!operator.is_active}>
          <Mail className="h-3.5 w-3.5" />
          {t("access.operators.invite")}
        </Button>
        <Button variant="secondary" size="sm" onClick={onEdit}>
          <Pencil className="h-3.5 w-3.5" />
          {t("common.edit")}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("access.security.revokeSessions")}
          title={t("access.security.revokeSessions")}
          onClick={() => onAction("revoke")}
        >
          <LogOut className="h-4 w-4" />
        </Button>
        {operator.totp_enabled ? (
          <Button
            variant="danger"
            size="icon"
            aria-label={t("access.security.resetTotp")}
            title={t("access.security.resetTotp")}
            onClick={() => onAction("reset-totp")}
          >
            <ShieldX className="h-4 w-4" />
          </Button>
        ) : null}
        {!isSelf ? (
          <Button
            variant={operator.is_active ? "danger" : "ghost"}
            size="sm"
            onClick={() => onAction(operator.is_active ? "deactivate" : "reactivate")}
          >
            {operator.is_active ? (
              <PowerOff className="h-3.5 w-3.5" />
            ) : (
              <Power className="h-3.5 w-3.5" />
            )}
            {t(
              operator.is_active
                ? "access.operators.deactivate"
                : "access.operators.reactivate",
            )}
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function CreateOperatorDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  const { notify } = useToast();
  const create = useCreateOperator();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [confirming, setConfirming] = useState(false);
  const error = create.error ? errorMessage(create.error, t) : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    setConfirming(true);
  }

  function createOperator() {
    create.mutate(
      { email: email.trim(), name: name.trim() || undefined },
      {
        onSuccess: () => {
          setEmail("");
          setName("");
          onOpenChange(false);
          notify(t("access.operators.toast.created"));
        },
      },
    );
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={onOpenChange}
        title={t("access.operators.create.title")}
        description={t("access.operators.create.description")}
      >
        <form onSubmit={submit} className="space-y-4">
          <Field label={t("access.field.email")} htmlFor="operator-email">
            <Input
              id="operator-email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="operator@company.com"
            />
          </Field>
          <Field label={t("access.field.name")} hint={t("access.field.nameHint")} htmlFor="operator-name">
            <Input
              id="operator-name"
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <Spinner /> : <ShieldPlus className="h-4 w-4" />}
              {t("access.operators.create.submit")}
            </Button>
          </div>
        </form>
      </Dialog>
      {confirming ? (
        <StepUpDialog
          title={t("access.operators.confirm.createTitle")}
          description={t("access.operators.confirm.createDescription")}
          submitLabel={t("access.operators.create.submit")}
          requestContext={instanceRequestContext}
          onVerified={createOperator}
          onClose={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}

function EditOperatorDialog({
  open,
  onClosed,
  operator,
  onClose,
}: {
  operator: OperatorIdentity;
  onClose: () => void;
} & DialogVisibilityProps) {
  const t = useT();
  const { notify } = useToast();
  const update = useUpdateOperator(operator.id);
  const [email, setEmail] = useState(operator.email);
  const [name, setName] = useState(operator.name ?? "");
  const [confirming, setConfirming] = useState(false);
  const error = update.error ? errorMessage(update.error, t) : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    setConfirming(true);
  }

  function save() {
    update.mutate(
      { email: email.trim(), name: name.trim() || null },
      {
        onSuccess: () => {
          onClose();
          notify(t("access.operators.toast.updated"));
        },
      },
    );
  }

  return (
    <>
      <Dialog
        open={open} onClosed={onClosed}
        onOpenChange={(next) => !next && onClose()}
        title={t("access.operators.edit.title")}
        description={operator.email}
      >
        <form onSubmit={submit} className="space-y-4">
          <Field label={t("access.field.email")} htmlFor="edit-operator-email">
            <Input
              id="edit-operator-email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label={t("access.field.name")} htmlFor="edit-operator-name">
            <Input
              id="edit-operator-name"
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? <Spinner /> : null}
              {t("access.operators.edit.submit")}
            </Button>
          </div>
        </form>
      </Dialog>
      {open && confirming ? (
        <StepUpDialog
          title={t("access.operators.confirm.editTitle")}
          description={t("access.operators.confirm.editDescription", { email: operator.email })}
          submitLabel={t("access.operators.edit.submit")}
          requestContext={instanceRequestContext}
          onVerified={save}
          onClose={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}

function OperatorActionDialog({
  kind,
  operator,
  isSelf,
  onClose,
}: {
  kind: OperatorAction;
  operator: OperatorIdentity;
  isSelf: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const { notify } = useToast();
  const update = useUpdateOperator(operator.id);
  const invite = useInviteOperator(operator.id);
  const revokeSessions = useRevokeOperatorSessions(operator.id, isSelf);
  const resetTotp = useResetOperatorTotp(operator.id, isSelf);

  function run() {
    if (kind === "invite") {
      invite.mutate(undefined, {
        onSuccess: () => notify(t("access.operators.toast.inviteQueued")),
        onError: (error) => notify(apiMessage(error, t("access.operators.error")), "error"),
      });
      return;
    }
    if (kind === "revoke") {
      revokeSessions.mutate(undefined, {
        onSuccess: () => notify(t("access.security.sessionsRevokedDone")),
        onError: (error) => notify(apiMessage(error, t("access.operators.error")), "error"),
      });
      return;
    }
    if (kind === "reset-totp") {
      resetTotp.mutate(undefined, {
        onSuccess: () => notify(t("access.security.totpResetDone")),
        onError: (error) => notify(apiMessage(error, t("access.operators.error")), "error"),
      });
      return;
    }
    update.mutate(
      { is_active: kind === "reactivate" },
      {
        onSuccess: () =>
          notify(
            t(
              kind === "reactivate"
                ? "access.operators.toast.reactivated"
                : "access.operators.toast.deactivated",
            ),
          ),
        onError: (error) => notify(apiMessage(error, t("access.operators.error")), "error"),
      },
    );
  }

  const copy = operatorActionCopy(kind);
  const destructive = kind === "deactivate" || kind === "revoke" || kind === "reset-totp";
  return (
    <StepUpDialog
      title={t(copy.title)}
      description={t(copy.description, { email: operator.email })}
      submitLabel={t(copy.submit)}
      submitVariant={destructive ? "danger" : "primary"}
      requestContext={instanceRequestContext}
      onVerified={run}
      onClose={onClose}
    />
  );
}

function operatorActionCopy(kind: OperatorAction): {
  title: string;
  description: string;
  submit: string;
} {
  if (kind === "revoke") {
    return {
      title: "access.security.revokeSessionsTitle",
      description: "access.security.revokeSessionsDescription",
      submit: "access.security.revokeSessions",
    };
  }
  if (kind === "reset-totp") {
    return {
      title: "access.security.resetTotpTitle",
      description: "access.security.resetTotpDescription",
      submit: "access.security.resetTotp",
    };
  }
  return {
    title: `access.operators.confirm.${kind}Title`,
    description: `access.operators.confirm.${kind}Description`,
    submit: `access.operators.${kind}`,
  };
}

function apiMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}
