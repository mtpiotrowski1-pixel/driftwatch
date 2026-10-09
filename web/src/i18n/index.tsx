import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { en } from "./en";
import { pl } from "./pl";

export type Lang = "en" | "pl";

export const LANGUAGES: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "pl", label: "Polski" },
];

const STORAGE_KEY = "driftwatch_lang";
const DICTIONARIES: Record<Lang, Record<string, string>> = { en, pl };

export type Translate = (key: string, vars?: Record<string, string | number>) => string;
export type TranslatePlural = (
  base: string,
  count: number,
  vars?: Record<string, string | number>,
) => string;

type PluralCategory = "one" | "few" | "many" | "other";

// English has two forms; Polish has three (one / few / many) selected by the
// CLDR rules. Callers store keys as `base.one`, `base.few`/`base.many` (PL) or
// `base.other` (EN), and tp() picks the right one.
function pluralCategory(lang: Lang, count: number): PluralCategory {
  const n = Math.abs(count);
  if (lang === "pl") {
    if (n === 1) return "one";
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return "few";
    return "many";
  }
  return n === 1 ? "one" : "other";
}

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Translate;
  tp: TranslatePlural;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function initialLang(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "pl") return stored;
  return navigator.language.toLowerCase().startsWith("pl") ? "pl" : "en";
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match,
  );
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    localStorage.setItem(STORAGE_KEY, next);
    // Date/number formatters read html.lang outside React. Update their source
    // before children render the new translation context, rather than one effect later.
    document.documentElement.lang = next;
    setLangState(next);
  }, []);

  const t = useCallback<Translate>(
    (key, vars) => {
      const value = DICTIONARIES[lang][key] ?? en[key] ?? key;
      return interpolate(value, vars);
    },
    [lang],
  );

  const tp = useCallback<TranslatePlural>(
    (base, count, vars) => {
      const category = pluralCategory(lang, count);
      const dict = DICTIONARIES[lang];
      const template =
        dict[`${base}.${category}`] ??
        dict[`${base}.other`] ??
        en[`${base}.${category}`] ??
        en[`${base}.other`] ??
        base;
      return interpolate(template, { count, ...vars });
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t, tp }), [lang, setLang, t, tp]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used within an I18nProvider");
  return value;
}

export function useT(): Translate {
  return useI18n().t;
}

export function useTp(): TranslatePlural {
  return useI18n().tp;
}

/** Translate outside the React tree (e.g. the top-level error boundary, which
 * renders above the provider). Reads the persisted language directly. */
export function translateStatic(key: string): string {
  let lang: Lang = "en";
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "pl") lang = "pl";
  } catch {
    lang = "en";
  }
  return DICTIONARIES[lang][key] ?? en[key] ?? key;
}
