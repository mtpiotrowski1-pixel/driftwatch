import { Sparkles } from "lucide-react";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { SettingsSection } from "@/components/ui/settings-section";
import { useT } from "@/i18n";
import type { FactoryDefaults, Settings } from "@/lib/types";
import { RestoreDefault, SecretSettingControl } from "./controls";
import { MASKED } from "./model";
import type { SettingsDraft, TextSettingsFields, SecretSettingsFields } from "./useSettingsDraft";
type AiDraft = TextSettingsFields & SecretSettingsFields & Pick<
  SettingsDraft,
  "modeValue" | "setDefaultMode" | "rulesValue" | "setImportanceRules"
>;

interface AiSectionProps {
  draft: AiDraft;
  stored: Settings;
  factoryDefaults?: FactoryDefaults;
  isPlatformScope: boolean;
}

export function AiSection({ draft, stored, factoryDefaults, isPlatformScope }: AiSectionProps) {
  const t = useT();
  const {
    textValue, setTextField, secrets, setSecretField, removeSecretField,
    undoSecretRemoval, modeValue, setDefaultMode, rulesValue, setImportanceRules,
  } = draft;
  return (
    <SettingsSection
      title={t("settings.ai.title")}
      icon={<Sparkles className="h-4 w-4" />}
      bodyClassName="grid gap-5 lg:grid-cols-2"
    >
      {isPlatformScope ? (
        <>
          <Field label={t("settings.ai.apiKey")} htmlFor="openai_api_key">
            <SecretSettingControl
              id="openai_api_key"
              value={secrets.openai_api_key ?? ""}
              onChange={(value) => setSecretField("openai_api_key", value)}
              placeholder={stored.openai_api_key === MASKED ? MASKED : "sk-..."}
              configured={stored.openai_api_key === MASKED}
              removalPending={
                Object.prototype.hasOwnProperty.call(secrets, "openai_api_key") &&
                secrets.openai_api_key === ""
              }
              onRemove={() => removeSecretField("openai_api_key")}
              onUndo={() => undoSecretRemoval("openai_api_key")}
            />
          </Field>
          <Field label={t("settings.ai.model")} htmlFor="openai_model">
            <Input
              id="openai_model"
              value={textValue("openai_model")}
              onChange={(event) => setTextField("openai_model", event.target.value)}
              placeholder="gpt-4o-mini"
            />
          </Field>
        </>
      ) : null}
      <Field label={t("settings.ai.defaultNotifications")} htmlFor="default_notification_mode">
        <Select
          id="default_notification_mode"
          value={modeValue}
          onChange={(event) => {
            setDefaultMode(event.target.value);
          }}
        >
          <option value="only_significant">{t("settings.ai.modeOnlySignificant")}</option>
          <option value="always">{t("settings.ai.modeAlways")}</option>
        </Select>
      </Field>
      <div className="lg:col-span-2">
        <Field
          label={t("settings.ai.importanceRules")}
          hint={t("settings.ai.importanceRulesHint")}
          htmlFor="importance_rules"
        >
          <Textarea
            id="importance_rules"
            value={rulesValue}
            onChange={(event) => {
              setImportanceRules(event.target.value);
            }}
            placeholder={factoryDefaults?.importance_rules ?? ""}
          />
          <RestoreDefault
            onClick={() => {
              setImportanceRules("");
            }}
          />
        </Field>
      </div>
      <div className="lg:col-span-2">
        <Field
          label={t("settings.ai.responseFormat")}
          hint={t("settings.ai.responseFormatHint")}
          htmlFor="base_prompt"
        >
          <Textarea
            id="base_prompt"
            value={textValue("base_prompt")}
            onChange={(event) => setTextField("base_prompt", event.target.value)}
            placeholder={factoryDefaults?.base_prompt ?? ""}
          />
          <RestoreDefault onClick={() => setTextField("base_prompt", "")} />
        </Field>
      </div>
    </SettingsSection>
  );
}
