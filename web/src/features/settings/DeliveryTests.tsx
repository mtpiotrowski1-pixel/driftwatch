import { useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNote, Spinner } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { useT } from "@/i18n";
import type { ApiRequestContext } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { useTestEmail, useTestWebhook } from "@/lib/queries";
import { cn } from "@/lib/utils";

export function TestEmailRow({ requestContext }: { requestContext: ApiRequestContext }) {
  const t = useT();
  const testEmail = useTestEmail(requestContext);
  const [to, setTo] = useState("");
  const result = testEmail.data;
  const error = testEmail.error ? errorMessage(testEmail.error, t) : null;

  return (
    <Field label={t("settings.email.test")} hint={t("settings.email.testHint")} htmlFor="test-email-to">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          id="test-email-to"
          type="email"
          value={to}
          onChange={(event) => setTo(event.target.value)}
          placeholder="you@company.com"
          className="max-w-xs"
        />
        <Button
          type="button"
          variant="secondary"
          disabled={!to.trim() || testEmail.isPending}
          onClick={() => testEmail.mutate(to.trim())}
        >
          {testEmail.isPending ? <Spinner /> : <Send className="h-4 w-4" />}
          {t("settings.email.testSend")}
        </Button>
      </div>
      {result ? (
        <p className={cn("mt-2 text-sm", result.delivered ? "text-emerald-400" : "text-rose-400")}>
          {result.delivered
            ? t("settings.email.testOk", { channel: result.channel })
            : t("settings.email.testFail", { detail: result.detail ?? "" })}
        </p>
      ) : null}
      {error ? (
        <div className="mt-2">
          <ErrorNote>{error}</ErrorNote>
        </div>
      ) : null}
    </Field>
  );
}

export function TestWebhookRow({ requestContext }: { requestContext: ApiRequestContext }) {
  const t = useT();
  const test = useTestWebhook(requestContext);
  const result = test.data;
  const error = test.error ? errorMessage(test.error, t) : null;

  return (
    <div>
      <Button
        type="button"
        variant="secondary"
        disabled={test.isPending}
        onClick={() => test.mutate()}
      >
        {test.isPending ? <Spinner /> : <Send className="h-4 w-4" />}
        {t("settings.webhook.test")}
      </Button>
      {result ? (
        <p className={cn("mt-2 text-sm", result.delivered ? "text-emerald-400" : "text-rose-400")}>
          {result.delivered
            ? t("settings.webhook.testOk")
            : t("settings.webhook.testFail", { detail: result.detail ?? "" })}
        </p>
      ) : null}
      {error ? (
        <div className="mt-2">
          <ErrorNote>{error}</ErrorNote>
        </div>
      ) : null}
    </div>
  );
}
