import { SlidersHorizontal } from "lucide-react";
import { useBrand } from "@/branding";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ThemeSwitcher } from "@/components/ThemeSwitcher";
import { SettingsSection } from "@/components/ui/settings-section";
import { useT } from "@/i18n";

export function PreferencesCard() {
  const t = useT();
  const brand = useBrand();
  return (
    <SettingsSection title={t("common.preferences")} icon={<SlidersHorizontal className="h-4 w-4" />} defaultOpen bodyClassName="space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium text-mist-200">{t("common.language")}</p>
        <LanguageSwitcher />
        <p className="text-sm text-mist-500">{t("common.languageHint")}</p>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium text-mist-200">{t("common.theme")}</p>
        {brand.accentColor ? (
          <div className="flex items-center gap-3 rounded-lg border border-line bg-ink-850 px-3 py-3">
            <span
              aria-hidden="true"
              className="h-8 w-8 shrink-0 rounded-md border border-black/10"
              style={{ backgroundColor: brand.accentColor }}
            />
            <p className="text-sm text-mist-400">{t("common.themeManaged")}</p>
          </div>
        ) : (
          <>
            <ThemeSwitcher />
            <p className="text-sm text-mist-500">{t("common.themeHint")}</p>
          </>
        )}
      </div>
    </SettingsSection>
  );
}
