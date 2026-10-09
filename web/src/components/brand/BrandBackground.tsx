import { useBrand } from "@/branding";
import { cn } from "@/lib/utils";

import { DecorativeBrandArtwork } from "./BrandArtwork";
import { BRAND_ARTWORK } from "./assets";

type BackgroundVariant = "hero" | "dark" | "ambient";

/** Generated artwork stays a decorative layer. Content, controls and measured
 * results remain real DOM above a variant-specific contrast scrim. */
export function BrandBackground({
  variant = "ambient",
  className,
  eager = false,
}: {
  variant?: BackgroundVariant;
  className?: string;
  eager?: boolean;
}) {
  const brand = useBrand();
  const ambient = variant === "ambient";
  const customArtwork = !ambient && brand.isReady && Boolean(brand.heroBackgroundUrl);
  return (
    <div aria-hidden="true" data-custom-art={customArtwork || undefined} className={cn("dw-brand-background", `dw-brand-background-${variant}`, className)}>
      <DecorativeBrandArtwork
        customUrl={!ambient && brand.isReady ? brand.heroBackgroundUrl : undefined}
        desktop={ambient ? BRAND_ARTWORK.ambient : BRAND_ARTWORK.hero}
        mobile={ambient ? undefined : BRAND_ARTWORK.heroMobile}
        imageClassName={brand.accentColor && (ambient || !brand.heroBackgroundUrl) ? "saturate-0" : undefined}
        eager={eager}
      />
      <div className="dw-brand-scrim" />
    </div>
  );
}
