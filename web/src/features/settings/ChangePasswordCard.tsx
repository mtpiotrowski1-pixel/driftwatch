import { useState, type FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { SettingsSection } from "@/components/ui/settings-section";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { errorMessage } from "@/lib/errors";
import { useChangePassword } from "@/lib/queries";
import { passwordsMismatch } from "@/lib/utils";

export function ChangePasswordCard() {
  const t = useT();
  const changePassword = useChangePassword();
  const { notify } = useToast();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = passwordsMismatch(next, confirm);

  const error = changePassword.error ? errorMessage(changePassword.error, t) : null;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) return;
    changePassword.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent("");
          setNext("");
          setConfirm("");
          notify(t("settings.password.changed"));
        },
      },
    );
  }

  return (
    <SettingsSection title={t("settings.password.title")} icon={<KeyRound className="h-4 w-4" />} bodyClassName="space-y-5">
      <form onSubmit={handleSubmit} className="grid gap-5 lg:grid-cols-3">
        <Field label={t("settings.password.current")} htmlFor="current_password">
          <Input
            id="current_password"
            type="password"
            required
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
            autoComplete="current-password"
          />
        </Field>
        <Field label={t("settings.password.new")} hint={t("settings.password.newHint")} htmlFor="new_password">
          <Input
            id="new_password"
            type="password"
            required
            minLength={8}
            value={next}
            onChange={(event) => setNext(event.target.value)}
            autoComplete="new-password"
          />
        </Field>
        <Field label={t("settings.password.confirm")} htmlFor="confirm_password">
          <Input
            id="confirm_password"
            type="password"
            required
            minLength={8}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            autoComplete="new-password"
          />
        </Field>
        {mismatch ? (
          <div className="lg:col-span-3">
            <ErrorNote>{t("settings.password.mismatch")}</ErrorNote>
          </div>
        ) : null}
        {error ? (
          <div className="lg:col-span-3">
            <ErrorNote>{error}</ErrorNote>
          </div>
        ) : null}
        <div className="lg:col-span-3">
          <Button type="submit" disabled={changePassword.isPending}>
            <KeyRound className="h-4 w-4" />
            {t("settings.password.submit")}
          </Button>
        </div>
      </form>
    </SettingsSection>
  );
}
