import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/ui/feedback";
import { useT } from "@/i18n";
import type { ApiRequestContext } from "@/lib/api";
import type { FactoryDefaults, Recipient, Settings } from "@/lib/types";
import { AiSection } from "./AiSection";
import { BrandingSection } from "./BrandingSection";
import { CaptureSection } from "./CaptureSection";
import { EmailSection } from "./EmailSection";
import { FilteringSection, FilteringReferenceCard } from "./FilteringSection";
import type { SettingsDraft } from "./useSettingsDraft";

interface ConfigurationFormProps {
  draft: SettingsDraft;
  stored: Settings;
  requestContext: ApiRequestContext;
  isPlatformScope: boolean;
  factoryDefaults?: FactoryDefaults;
  recipients: Recipient[];
}

/** Domain sections share one draft and submit atomically to the selected scope. */
export function ConfigurationForm({
  draft, stored, requestContext, isPlatformScope, factoryDefaults, recipients,
}: ConfigurationFormProps) {
  const t = useT();
  return (
    <form onSubmit={draft.handleSubmit} autoComplete="off" className="space-y-6">
      <div className="flex items-start gap-3 rounded-lg border border-line-strong bg-ink-900 px-4 py-3 text-sm text-mist-400 shadow-card">
        <Lock className="h-4 w-4 shrink-0 text-mist-500" />
        <span>{isPlatformScope ? t("settings.scope.instance") : t("settings.scope.org")}</span>
      </div>
      <BrandingSection
        draft={draft}
        stored={stored}
        settingsContext={requestContext}
        isPlatformScope={isPlatformScope}
      />
      <AiSection
        draft={draft}
        stored={stored}
        factoryDefaults={factoryDefaults}
        isPlatformScope={isPlatformScope}
      />
      <EmailSection
        draft={draft}
        stored={stored}
        settingsContext={requestContext}
        isPlatformScope={isPlatformScope}
        recipients={recipients}
      />
      {isPlatformScope ? <CaptureSection draft={draft} /> : null}
      <FilteringSection draft={draft} />
      {factoryDefaults ? <FilteringReferenceCard defaults={factoryDefaults} /> : null}
      {draft.error ? <ErrorNote>{draft.error}</ErrorNote> : null}
      <div className="flex items-center gap-3">
        <Button type="submit" size="lg" disabled={draft.isPending}>
          <Lock className="h-4 w-4" />
          {t("settings.save")}
        </Button>
      </div>
    </form>
  );
}
