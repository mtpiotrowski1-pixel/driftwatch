import { Globe } from "lucide-react";

import { Select } from "@/components/ui/field";
import { LANGUAGES, type Lang, useI18n } from "@/i18n";

export function LanguageSwitcher({
  compact = false,
  short = false,
}: {
  compact?: boolean;
  short?: boolean;
}) {
  const { lang, setLang, t } = useI18n();
  return (
    <label className="dw-language-switcher flex items-center gap-2 text-sm text-mist-400">
      <Globe className="h-4 w-4 shrink-0" />
      <span className="sr-only">{t("common.language")}</span>
      <Select
        aria-label={t("common.language")}
        value={lang}
        onChange={(event) => setLang(event.target.value as Lang)}
        className={
          compact ? (short ? "h-9 w-20 py-1.5 pl-2 pr-7" : "h-9 py-1.5") : undefined
        }
      >
        {LANGUAGES.map((option) => (
          <option key={option.value} value={option.value}>
            {short ? option.value.toUpperCase() : option.label}
          </option>
        ))}
      </Select>
    </label>
  );
}
