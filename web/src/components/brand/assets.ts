import ambientJpg from "@/assets/brand/portal-ambient-v3.jpg";
import ambientWebp from "@/assets/brand/portal-ambient-v3.webp";
import heroMobileJpg from "@/assets/brand/portal-hero-mobile-v3.jpg";
import heroMobileWebp from "@/assets/brand/portal-hero-mobile-v3.webp";
import heroJpg from "@/assets/brand/portal-hero-v3.jpg";
import heroWebp from "@/assets/brand/portal-hero-v3.webp";

export const BRAND_ARTWORK = {
  ambient: { jpg: ambientJpg, webp: ambientWebp },
  auth: { jpg: heroJpg, webp: heroWebp },
  hero: { jpg: heroJpg, webp: heroWebp },
  heroMobile: { jpg: heroMobileJpg, webp: heroMobileWebp },
} as const;
