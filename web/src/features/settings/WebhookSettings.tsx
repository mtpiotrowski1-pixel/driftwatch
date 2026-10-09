import { Field, Select } from "@/components/ui/field";
import { useT } from "@/i18n";
import type { ApiRequestContext } from "@/lib/api";
import type { Settings } from "@/lib/types";
import { SecretSettingControl } from "./controls";
import { TestWebhookRow } from "./DeliveryTests";
import { MASKED } from "./model";
import type { TextSettingsFields, SecretSettingsFields } from "./useSettingsDraft";

interface WebhookSettingsProps {
  draft: TextSettingsFields & SecretSettingsFields;
  stored: Settings;
  settingsContext: ApiRequestContext;
}

export function WebhookSettings({ draft, stored, settingsContext }: WebhookSettingsProps) {
  const t = useT();
  const {
    textValue, setTextField, secrets, setSecretField, removeSecretField, undoSecretRemoval,
  } = draft;
  return (
    <div className="border-line lg:col-span-2 space-y-5 border-t pt-5">
      <p className="text-sm font-medium text-mist-300">
        {t("settings.webhook.title")}
      </p>
      <div className="grid gap-5 lg:grid-cols-2">
        <Field
          label={t("settings.webhook.url")}
          hint={t("settings.webhook.urlHint")}
          htmlFor="notification_webhook_url"
        >
          <SecretSettingControl
            id="notification_webhook_url"
            value={secrets.notification_webhook_url ?? ""}
            onChange={(value) => setSecretField("notification_webhook_url", value)}
            placeholder={
              stored.notification_webhook_url === MASKED
                ? MASKED
                : "https://hooks.slack.com/services/…"
            }
            configured={stored.notification_webhook_url === MASKED}
            removalPending={
              Object.prototype.hasOwnProperty.call(
                secrets,
                "notification_webhook_url",
              ) && secrets.notification_webhook_url === ""
            }
            onRemove={() => removeSecretField("notification_webhook_url")}
            onUndo={() => undoSecretRemoval("notification_webhook_url")}
          />
        </Field>
        <Field label={t("settings.webhook.format")} htmlFor="notification_webhook_format">
          <Select
            id="notification_webhook_format"
            value={textValue("notification_webhook_format") || "generic"}
            onChange={(event) =>
              setTextField("notification_webhook_format", event.target.value)
            }
          >
            <option value="generic">{t("settings.webhook.formatGeneric")}</option>
            <option value="slack">{t("settings.webhook.formatSlack")}</option>
            <option value="discord">{t("settings.webhook.formatDiscord")}</option>
          </Select>
        </Field>
      </div>
      <TestWebhookRow requestContext={settingsContext} />
    </div>

  );
}
