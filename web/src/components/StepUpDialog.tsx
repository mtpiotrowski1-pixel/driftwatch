import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNote } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { useT } from "@/i18n";
import {
  ApiError,
  RequestContextChangedError,
  assertRequestContextCurrent,
  currentRequestContext,
  type ApiRequestContext,
} from "@/lib/api";
import { useCurrentUser, useStepUp } from "@/lib/queries";

/** Re-authenticate before a sensitive action. On success it runs ``onVerified``
 * (which performs the action) and closes — the server now holds a short-lived
 * step-up cookie the action endpoint requires. */
export function StepUpDialog({
  title,
  description,
  submitLabel,
  submitVariant = "primary",
  requestContext = currentRequestContext,
  onVerified,
  onClose,
}: {
  title: string;
  description?: string;
  submitLabel: string;
  submitVariant?: "primary" | "danger";
  requestContext?: ApiRequestContext;
  onVerified: () => void | Promise<void>;
  onClose: () => void;
}) {
  const t = useT();
  const { data: user } = useCurrentUser();
  const stepUp = useStepUp(requestContext);

  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [workflowError, setWorkflowError] = useState<string | null>(null);

  const error = workflowError
    ?? (stepUp.error instanceof ApiError
      ? stepUp.error.message
      : stepUp.isError
        ? t("common.requestFailed")
        : null);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const credentials = {
      password,
      totp_code: user?.totp_enabled ? code.trim() : undefined,
    };
    setPassword("");
    setCode("");
    setWorkflowError(null);
    stepUp.reset();
    try {
      assertRequestContextCurrent(requestContext);
    } catch {
      setWorkflowError(t("common.contextChanged"));
      return;
    }
    stepUp.mutate(
      credentials,
      {
        onSuccess: async () => {
          try {
            assertRequestContextCurrent(requestContext);
            await onVerified();
            onClose();
          } catch (caught) {
            setWorkflowError(
              caught instanceof RequestContextChangedError
                ? t("common.contextChanged")
                : caught instanceof ApiError
                  ? caught.message
                  : t("common.requestFailed"),
            );
          }
        },
      },
    );
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()} title={title} description={description}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-mist-400">{t("twofa.stepup.prompt")}</p>
        <Field label={t("twofa.stepup.password")} htmlFor="stepup-password">
          <Input
            id="stepup-password"
            type="password"
            required
            autoFocus
            disabled={stepUp.isPending}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </Field>
        {user?.totp_enabled ? (
          <Field
            label={t("twofa.stepup.code")}
            hint={t("twofa.stepup.codeHint")}
            htmlFor="stepup-code"
          >
            <Input
              id="stepup-code"
              autoComplete="one-time-code"
              required
              disabled={stepUp.isPending}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="123456"
            />
          </Field>
        ) : null}
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" variant={submitVariant} disabled={stepUp.isPending}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
