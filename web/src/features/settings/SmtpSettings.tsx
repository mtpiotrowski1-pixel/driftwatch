import { Field, Input, Select } from "@/components/ui/field";
import { useT } from "@/i18n";
import type { Settings } from "@/lib/types";
import { SecretSettingControl } from "./controls";
import { MASKED } from "./model";
import type { TextSettingsFields, SecretSettingsFields } from "./useSettingsDraft";

interface SmtpSettingsProps {
  draft: TextSettingsFields & SecretSettingsFields;
  stored: Settings;
}

export function SmtpSettings({ draft, stored }: SmtpSettingsProps) {
  const t = useT();
  const {
    textValue, setTextField, secrets, setSecretField, removeSecretField, undoSecretRemoval,
  } = draft;
  return (
    <>

      <Field label={t("settings.email.smtpHost")} htmlFor="smtp_host">
        <Input
          id="smtp_host"
          value={textValue("smtp_host")}
          onChange={(event) => setTextField("smtp_host", event.target.value)}
          placeholder="smtp.example.com"
        />
      </Field>
      <Field label={t("settings.email.smtpPort")} htmlFor="smtp_port">
        <Input
          id="smtp_port"
          type="number"
          value={textValue("smtp_port")}
          onChange={(event) => setTextField("smtp_port", event.target.value)}
          placeholder="587"
        />
      </Field>
      <Field label={t("settings.email.smtpSecurity")} htmlFor="smtp_security">
        <Select
          id="smtp_security"
          value={textValue("smtp_security")}
          onChange={(event) => setTextField("smtp_security", event.target.value)}
        >
          <option value="starttls">{t("settings.email.securityStarttls")}</option>
          <option value="ssl">{t("settings.email.securitySsl")}</option>
          <option value="none">{t("settings.email.securityNone")}</option>
        </Select>
      </Field>
      <div />
      <Field label={t("settings.email.smtpUsername")} htmlFor="smtp_username">
        <Input
          id="smtp_username"
          value={textValue("smtp_username")}
          onChange={(event) => setTextField("smtp_username", event.target.value)}
          autoComplete="off"
        />
      </Field>
      <Field label={t("settings.email.smtpPassword")} htmlFor="smtp_password">
        <SecretSettingControl
          id="smtp_password"
          value={secrets.smtp_password ?? ""}
          onChange={(value) => setSecretField("smtp_password", value)}
          placeholder={stored.smtp_password === MASKED ? MASKED : ""}
          configured={stored.smtp_password === MASKED}
          removalPending={
            Object.prototype.hasOwnProperty.call(secrets, "smtp_password") &&
            secrets.smtp_password === ""
          }
          onRemove={() => removeSecretField("smtp_password")}
          onUndo={() => undoSecretRemoval("smtp_password")}
        />
      </Field>
      <Field
        label={t("settings.email.brevoApiKey")}
        hint={t("settings.email.brevoApiKeyHint")}
        htmlFor="brevo_api_key"
      >
        <SecretSettingControl
          id="brevo_api_key"
          value={secrets.brevo_api_key ?? ""}
          onChange={(value) => setSecretField("brevo_api_key", value)}
          placeholder={stored.brevo_api_key === MASKED ? MASKED : ""}
          configured={stored.brevo_api_key === MASKED}
          removalPending={
            Object.prototype.hasOwnProperty.call(secrets, "brevo_api_key") &&
            secrets.brevo_api_key === ""
          }
          onRemove={() => removeSecretField("brevo_api_key")}
          onUndo={() => undoSecretRemoval("brevo_api_key")}
        />
      </Field>

    </>
  );
}
