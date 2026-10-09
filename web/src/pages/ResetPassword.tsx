import { errorMessage } from "@/lib/errors";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "@/lib/navigation";

import { Wordmark } from "@/components/brand/Logo";
import { BrandBackground } from "@/components/brand/BrandBackground";
import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { useResetPassword } from "@/lib/queries";
import { passwordsMismatch } from "@/lib/utils";

export function ResetPassword() {
  const t = useT();
  const navigate = useNavigate();
  const { notify } = useToast();
  // The token arrives in the URL fragment (never the query string), so it is read
  // from the hash — which the browser keeps out of requests, logs, and Referer.
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
  const reset = useResetPassword();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = passwordsMismatch(password, confirm);
  const error = reset.error ? errorMessage(reset.error, t) : null;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) return;
    reset.mutate(
      { token, new_password: password },
      {
        onSuccess: () => {
          notify(t("login.reset.done"));
          navigate("/login", { replace: true });
        },
      },
    );
  }

  return (
    <div className="relative isolate flex min-h-screen flex-col items-center justify-center overflow-hidden bg-ink-950 px-5 py-12">
      <BrandBackground variant="ambient" eager />
      <Wordmark className="dw-auth-brand relative mb-8 text-xl" />
      <div className="dw-auth-card relative w-full max-w-md animate-fade-rise">
        {token ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            <h1 className="text-lg font-semibold text-mist-100">{t("login.reset.setTitle")}</h1>
            <Field
              label={t("login.reset.newPassword")}
              hint={t("login.reset.newPasswordHint")}
              htmlFor="new-password"
            >
              <Input
                id="new-password"
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
              />
            </Field>
            <Field label={t("login.reset.confirm")} htmlFor="confirm-password">
              <Input
                id="confirm-password"
                type="password"
                required
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                autoComplete="new-password"
              />
            </Field>
            {mismatch ? <ErrorNote>{t("login.reset.mismatch")}</ErrorNote> : null}
            {error ? <ErrorNote>{error}</ErrorNote> : null}
            <Button type="submit" size="lg" className="w-full" disabled={reset.isPending}>
              {t("login.reset.submit")}
            </Button>
          </form>
        ) : (
          <div className="space-y-4 text-center">
            <h1 className="text-lg font-semibold text-mist-100">{t("login.reset.invalidTitle")}</h1>
            <p className="text-sm text-mist-400">{t("login.reset.invalidBody")}</p>
            <Link
              to="/forgot-password"
              className="inline-block text-sm font-medium text-brand-700 underline underline-offset-2 hover:text-mist-100"
            >
              {t("login.reset.requestNew")}
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
