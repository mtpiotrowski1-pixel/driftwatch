import { createContext, useContext, useLayoutEffect, type ReactNode } from "react";

import { useBranding } from "@/lib/queries";

/** Resolved branding with defaults applied — what the shell and landing render. */
export interface Brand {
  isReady: boolean;
  name: string;
  logoUrl: string;
  accentColor: string;
  tagline: string;
  heroTitle: string;
  heroSubtitle: string;
  heroBackgroundUrl: string;
}

const DEFAULT_NAME = "Driftwatch";

const DEFAULT_BRAND: Brand = {
  isReady: true,
  name: DEFAULT_NAME,
  logoUrl: "",
  accentColor: "",
  tagline: "",
  heroTitle: "",
  heroSubtitle: "",
  heroBackgroundUrl: "",
};

// The brand-ramp and accent variables the runtime accent repaints — the same ones
// the index.css palettes override, so writing them inline on :root wins cleanly.
const BRAND_VARS = [
  "--color-brand-300",
  "--color-brand-400",
  "--color-brand-500",
  "--color-brand-600",
  "--color-brand-700",
  "--color-accent",
  "--color-accent-soft",
] as const;

const BrandContext = createContext<Brand | null>(null);

type Rgb = [number, number, number];

export function parseHex(hex: string): Rgb | null {
  const value = hex.trim().replace(/^#/, "");
  const full = value.length === 3 ? value.replace(/./g, (c) => c + c) : value;
  // Strict: reject anything but exactly six hex digits, so a malformed or
  // tampered value (e.g. from the cached pre-paint) can never reach the DOM.
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null;
  const n = Number.parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Perceived lightness (0..1) via Rec. 709 luma. */
function luma(rgb: Rgb): number {
  return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
}

function luminance(rgb: Rgb): number {
  const linear = (channel: number) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * linear(rgb[0]) + 0.7152 * linear(rgb[1]) + 0.0722 * linear(rgb[2]);
}

function contrast(a: Rgb, b: Rgb): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** Blend ``rgb`` toward white (target 255) or black (target 0) by ``amount`` (0..1). */
function blend(rgb: Rgb, target: 0 | 255, amount: number): Rgb {
  return [
    Math.round(rgb[0] + (target - rgb[0]) * amount),
    Math.round(rgb[1] + (target - rgb[1]) * amount),
    Math.round(rgb[2] + (target - rgb[2]) * amount),
  ];
}

function css(rgb: Rgb): string {
  return `rgb(${rgb[0]} ${rgb[1]} ${rgb[2]})`;
}

/** The brand-ramp CSS variables for one operator accent, or null if it isn't a
 * valid hex (callers then clear the variables). Computed entirely in JS so only
 * integer rgb() values reach the DOM. The primary button carries dark text on the
 * brand gradient and ``text-brand-300`` is light text on dark surfaces, so both
 * need a light ramp: a dark accent is lifted toward white until it carries that
 * contrast, while a light accent already does. Pure — unit-tested. */
export function accentRamp(hex: string): Record<string, string> | null {
  const rgb = parseHex(hex);
  if (!rgb) return null;
  const light = luma(rgb);
  let base = light < 0.5 ? blend(rgb, 255, Math.min((0.5 - light) * 1.2, 0.6)) : rgb;
  // Check the darkest pressed state too; perceived luma alone does not predict
  // WCAG contrast for saturated tenant colors.
  while (contrast(blend(base, 0, 0.16), [21, 25, 21]) < 4.5) base = blend(base, 255, 0.03);
  return {
    "--color-brand-500": css(base),
    "--color-brand-400": css(blend(base, 255, 0.14)),
    "--color-brand-300": css(blend(base, 255, 0.34)),
    "--color-brand-600": css(blend(base, 0, 0.16)),
    "--color-brand-700": css(blend(base, 0, 0.56)),
    "--color-accent": css(blend(base, 255, 0.06)),
    "--color-accent-soft": css(base),
  };
}

function applyAccent(hex: string): void {
  const root = document.documentElement.style;
  const ramp = accentRamp(hex);
  if (!ramp) {
    for (const name of BRAND_VARS) root.removeProperty(name);
    return;
  }
  for (const [name, value] of Object.entries(ramp)) root.setProperty(name, value);
}

export function BrandingProvider({ children }: { children: ReactNode }) {
  const { data, isFetched } = useBranding();

  // Branding is tenant-scoped. Clear inline variables as soon as its query is
  // removed during logout or organization switching so one tenant's accent can
  // never bleed into another workspace or the public landing page.
  useLayoutEffect(() => {
    applyAccent(data?.accent_color ?? "");
    document.title = data?.brand_name || DEFAULT_NAME;
  }, [data]);

  const brand: Brand = {
    isReady: isFetched,
    name: data?.brand_name || DEFAULT_NAME,
    logoUrl: data?.logo_url ?? "",
    accentColor: data?.accent_color ?? "",
    tagline: data?.tagline ?? "",
    heroTitle: data?.hero_title ?? "",
    heroSubtitle: data?.hero_subtitle ?? "",
    heroBackgroundUrl: data?.hero_background_url ?? "",
  };

  return <BrandContext.Provider value={brand}>{children}</BrandContext.Provider>;
}

export function useBrand(): Brand {
  // Fall back to defaults outside a provider so the brand mark can render
  // anywhere (including in isolation under test) without crashing.
  return useContext(BrandContext) ?? DEFAULT_BRAND;
}
