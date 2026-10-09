import { Check } from "lucide-react";

import { useT } from "@/i18n";
import { THEMES, useTheme } from "@/theme";
import { cn } from "@/lib/utils";

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const t = useT();

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {THEMES.map((option) => {
        const selected = option.value === theme;
        const [a, b, c] = option.swatch;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => setTheme(option.value)}
            aria-pressed={selected}
            className={cn(
              "group flex items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors",
              selected
                ? "border-brand-400/60 bg-brand-500/10"
                : "border-line bg-ink-900/40 hover:border-line-strong hover:bg-ink-800/60",
            )}
          >
            <span className="relative flex h-8 w-8 shrink-0 overflow-hidden rounded-lg ring-1 ring-inset ring-black/10">
              <span className="flex-1" style={{ backgroundColor: a }} />
              <span className="flex-1" style={{ backgroundColor: b }} />
              <span className="flex-1" style={{ backgroundColor: c }} />
              {selected ? (
                <span className="absolute inset-0 grid place-items-center bg-white/35">
                  <Check className="h-4 w-4 text-[#151915]" />
                </span>
              ) : null}
            </span>
            <span
              className={cn(
                "truncate text-sm font-medium",
                selected ? "text-mist-100" : "text-mist-300",
              )}
            >
              {t(option.labelKey)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
