import { Eye, Filter } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Field, Textarea } from "@/components/ui/field";
import { SettingsSection } from "@/components/ui/settings-section";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n";
import type { FactoryDefaults } from "@/lib/types";
import { RestoreDefault } from "./controls";
import type { SettingsDraft, TextSettingsFields } from "./useSettingsDraft";
type FilteringDraft = TextSettingsFields & Pick<SettingsDraft, "ignoreValue" | "setIgnoreSelectors">;

export function FilteringSection({ draft }: { draft: FilteringDraft }) {
  const t = useT();
  const { textValue, setTextField, ignoreValue, setIgnoreSelectors } = draft;
  return (
    <SettingsSection title={t("settings.filters.title")} icon={<Filter className="h-4 w-4" />} bodyClassName="space-y-5">
      <div className="flex items-center justify-between gap-4 rounded-lg border border-line bg-ink-900/50 px-3.5 py-3">
        <div>
          <p className="text-sm font-medium text-mist-200">
            {t("settings.filters.watchDocuments")}
          </p>
          <p className="text-xs text-mist-500">
            {t("settings.filters.watchDocumentsHint")}
          </p>
        </div>
        <Switch
          aria-label={t("settings.filters.watchDocuments")}
          checked={textValue("watch_linked_documents") === "true"}
          onCheckedChange={(value) =>
            setTextField("watch_linked_documents", value ? "true" : "false")
          }
        />
      </div>
      <Field
        label={t("settings.filters.ignoreSelectors")}
        hint={t("settings.filters.ignoreSelectorsHint")}
        htmlFor="ignore_selectors"
      >
        <Textarea
          id="ignore_selectors"
          value={ignoreValue}
          onChange={(event) => {
            setIgnoreSelectors(event.target.value);
          }}
          placeholder={".cookie-banner\n#ads\nfooter .timestamp"}
        />
        <RestoreDefault
          onClick={() => {
            setIgnoreSelectors("");
          }}
        />
      </Field>
    </SettingsSection>
  );
}

/** Read-only window into what the engine removes before the model sees a change,
 * and the fixed response it must return — so the operator can edit prompts and
 * ignore rules above with full knowledge of what they affect. */
export function FilteringReferenceCard({ defaults }: { defaults: FactoryDefaults }) {
  const t = useT();
  return (
    <SettingsSection title={t("settings.filtering.title")} icon={<Eye className="h-4 w-4" />} bodyClassName="space-y-6 text-sm text-mist-400">
      <p>{t("settings.filtering.intro")}</p>
      <div>
        <p className="font-medium text-mist-300">{t("settings.filtering.strippedTags")}</p>
        <p className="text-xs text-mist-500">{t("settings.filtering.strippedTagsHint")}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {defaults.stripped_tags.map((tag) => (
            <Badge key={tag} tone="neutral">
              {tag}
            </Badge>
          ))}
        </div>
      </div>
      <div>
        <p className="font-medium text-mist-300">{t("settings.filtering.volatile")}</p>
        <p className="text-xs text-mist-500">{t("settings.filtering.volatileHint")}</p>
        <ul className="mt-2 space-y-1 font-mono text-xs text-mist-500">
          {defaults.volatile_patterns.map((pattern) => (
            <li key={pattern} className="break-all">
              {pattern}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="font-medium text-mist-300">{t("settings.filtering.response")}</p>
        <p className="text-xs text-mist-500">{t("settings.filtering.responseHint")}</p>
        <ul className="mt-2 space-y-1">
          {Object.entries(defaults.response_fields).map(([name, description]) => (
            <li key={name}>
              <code className="text-mist-300">{name}</code> — {description}
            </li>
          ))}
        </ul>
      </div>
    </SettingsSection>
  );
}
