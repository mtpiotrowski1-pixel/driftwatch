import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

// The active language is mirrored onto <html lang> by the i18n provider, so
// these formatters localize without depending on React context.
export function activeLocale(): string {
  const lang = typeof document !== "undefined" ? document.documentElement.lang : "";
  return lang || "en";
}

const NEVER: Record<string, string> = { en: "never", pl: "nigdy" };
const JUST_NOW: Record<string, string> = { en: "just now", pl: "przed chwilą" };

/** API event timestamps represent UTC instants. SQLite can drop their timezone
 * on reload, so a complete ISO datetime without an offset still means UTC.
 * Explicit offsets and date-only/calendar inputs keep native Date semantics. */
export function parseApiTimestamp(iso: string): Date {
  const naiveTimestamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(iso);
  return new Date(naiveTimestamp ? `${iso}Z` : iso);
}

export function relativeTime(iso: string | null): string {
  const locale = activeLocale();
  if (!iso) return NEVER[locale] ?? NEVER.en;
  const then = parseApiTimestamp(iso).getTime();
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return JUST_NOW[locale] ?? JUST_NOW.en;
  // value starts in minutes; each step divides into the next-larger unit, so
  // the label is the unit reached *after* dividing.
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "hour"],
    [24, "day"],
    [7, "week"],
    [4.345, "month"],
    [12, "year"],
  ];
  let value = seconds / 60;
  let unit: Intl.RelativeTimeFormatUnit = "minute";
  for (const [factor, nextUnit] of units) {
    if (Math.abs(value) < factor) break;
    value /= factor;
    unit = nextUnit;
  }
  return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-Math.round(value), unit);
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return parseApiTimestamp(iso).toLocaleString(activeLocale(), {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatInterval(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  if (minutes % 60 === 0) return `${minutes / 60} h`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

export function formatCost(usd: number | null): string {
  if (usd === null) return activeLocale() === "pl" ? "Nieznany" : "Unknown";
  if (usd === 0) return "$0.00";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

/** The host of a URL, the raw string if it won't parse, or null when absent. */
export function hostOf(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** True once a confirmation field has been filled in but doesn't match. */
export function passwordsMismatch(password: string, confirm: string): boolean {
  return confirm.length > 0 && password !== confirm;
}

/** A limit input as a number, or null for "no limit" (an empty field). */
export function parseLimit(value: string): number | null {
  return value.trim() === "" ? null : Number(value);
}

/** Add a default https:// scheme so the user doesn't have to type it. Blank stays
 * blank, and an existing http(s):// scheme is left untouched. */
export function normalizeUrl(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

/** A textarea's value as trimmed, non-empty lines. */
export function splitLines(raw: string): string[] {
  return raw
    .split("\n")
    .map((value) => value.trim())
    .filter(Boolean);
}
