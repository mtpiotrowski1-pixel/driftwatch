import { Mail } from "lucide-react";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { SettingsSection } from "@/components/ui/settings-section";
import { useT } from "@/i18n";
import type { ApiRequestContext } from "@/lib/api";
import type { Recipient, Settings } from "@/lib/types";
import { TestEmailRow } from "./DeliveryTests";
import { SmtpSettings } from "./SmtpSettings";
import { TechnicalAlerts } from "./TechnicalAlerts";
import { WebhookSettings } from "./WebhookSettings";
import type {
  SettingsDraft, TextSettingsFields, SecretSettingsFields, NumberSettingsFields,
} from "./useSettingsDraft";

type DeliveryDraft = TextSettingsFields & SecretSettingsFields & NumberSettingsFields & Pick<
  SettingsDraft, "technicalValue" | "toggleTechnical"
>;

interface EmailSectionProps {
  draft: DeliveryDraft;
  stored: Settings;
  settingsContext: ApiRequestContext;
  isPlatformScope: boolean;
  recipients: Recipient[];
}

export function EmailSection({ draft, stored, settingsContext, isPlatformScope, recipients }: EmailSectionProps) {
  const t = useT();
  const { textValue, setTextField } = draft;
  return (
    <SettingsSection
      title={t("settings.email.title")}
      icon={<Mail className="h-4 w-4" />}
      bodyClassName="grid gap-5 lg:grid-cols-2"
    >
      {isPlatformScope ? (
        <Field label={t("settings.email.provider")} htmlFor="email_provider">
          <Select
            id="email_provider"
            value={textValue("email_provider")}
            onChange={(event) => setTextField("email_provider", event.target.value)}
          >
            <option value="auto">{t("settings.email.providerAuto")}</option>
            <option value="brevo">{t("settings.email.providerBrevo")}</option>
            <option value="smtp">{t("settings.email.providerSmtp")}</option>
            <option value="log">{t("settings.email.providerLog")}</option>
          </Select>
        </Field>
      ) : null}
      <Field
        label={t("settings.email.language")}
        hint={t("settings.email.languageHint")}
        htmlFor="email_language"
      >
        <Select
          id="email_language"
          value={textValue("email_language")}
          onChange={(event) => setTextField("email_language", event.target.value)}
        >
          <option value="">{t("settings.email.languageDefault")}</option>
          <option value="en">English</option>
          <option value="pl">Polski</option>
        </Select>
      </Field>
      {isPlatformScope ? (
        <Field label={t("settings.email.fromEmail")} htmlFor="notification_from_email">
          <Input
            id="notification_from_email"
            type="email"
            value={textValue("notification_from_email")}
            onChange={(event) => setTextField("notification_from_email", event.target.value)}
            placeholder="alerts@company.com"
          />
        </Field>
      ) : null}
      <Field label={t("settings.email.fromName")} htmlFor="notification_from_name">
        <Input
          id="notification_from_name"
          value={textValue("notification_from_name")}
          onChange={(event) => setTextField("notification_from_name", event.target.value)}
          placeholder="Driftwatch"
        />
      </Field>
      <div className="lg:col-span-2">
        <Field
          label={t("settings.email.subjectTemplate")}
          hint={t("settings.email.subjectTemplateHint")}
          htmlFor="email_subject_template"
        >
          <Input
            id="email_subject_template"
            value={textValue("email_subject_template")}
            onChange={(event) => setTextField("email_subject_template", event.target.value)}
            placeholder={t("settings.email.subjectTemplatePlaceholder")}
          />
        </Field>
      </div>
      <div className="lg:col-span-2">
        <Field
          label={t("settings.email.intro")}
          hint={t("settings.email.introHint")}
          htmlFor="email_body_intro"
        >
          <Textarea
            id="email_body_intro"
            value={textValue("email_body_intro")}
            onChange={(event) => setTextField("email_body_intro", event.target.value)}
          />
        </Field>
      </div>
      {isPlatformScope ? <SmtpSettings draft={draft} stored={stored} /> : null}
      <TechnicalAlerts draft={draft} recipients={recipients} />
      <div className="border-line lg:col-span-2 border-t pt-5">
        {isPlatformScope ? <TestEmailRow requestContext={settingsContext} /> : null}
      </div>
      <WebhookSettings draft={draft} stored={stored} settingsContext={settingsContext} />
    </SettingsSection>
  );
}
