import { errorMessage } from "@/lib/errors";
import { useState, type FormEvent } from "react";
import { Link } from "@/lib/navigation";

import { Wordmark } from "@/components/brand/Logo";
import { BrandBackground } from "@/components/brand/BrandBackground";
import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { useT } from "@/i18n";
import { useRequestPasswordReset } from "@/lib/queries";

export function ForgotPassword() {
  const t = useT();
  const request = useRequestPasswordReset();
  const [email, setEmail] = useState("");
  const error = request.error ? errorMessage(request.error, t) : null;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    request.mutate(email);
  }

  return (
    <div className="relative isolate flex min-h-screen flex-col items-center justify-center overflow-hidden bg-ink-950 px-5 py-12">
      <BrandBackground variant="ambient" eager />
      <Wordmark className="dw-auth-brand relative mb-8 text-xl" />
      <div className="dw-auth-card relative w-full max-w-md animate-fade-rise">
        {request.isSuccess ? (
          <div className="space-y-4 text-center">
            <h1 className="text-lg font-semibold text-mist-100">{t("login.reset.sentTitle")}</h1>
            <p className="text-sm text-mist-400">{t("login.reset.sentBody")}</p>
            <Link
              to="/login"
              className="inline-block text-sm font-medium text-brand-700 underline underline-offset-2 hover:text-mist-100"
            >
              {t("login.reset.backToSignIn")}
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <h1 className="text-lg font-semibold text-mist-100">
                {t("login.reset.requestTitle")}
              </h1>
              <p className="mt-1 text-sm text-mist-400">{t("login.reset.requestBody")}</p>
            </div>
            <Field label={t("login.emailLabel")} htmlFor="email">
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder={t("login.emailPlaceholder")}
                autoComplete="email"
              />
            </Field>
            {error ? <ErrorNote>{error}</ErrorNote> : null}
            <Button type="submit" size="lg" className="w-full" disabled={request.isPending}>
              {t("login.reset.sendLink")}
            </Button>
            <Link
              to="/login"
              className="block text-center text-xs text-mist-500 hover:text-mist-300"
            >
              {t("login.reset.backToSignIn")}
            </Link>
          </form>
        )}
      </div>
    </div>
  );
}
