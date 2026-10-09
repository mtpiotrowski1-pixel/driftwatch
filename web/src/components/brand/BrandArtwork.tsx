import { useState } from "react";

import { cn } from "@/lib/utils";

type ArtworkSource = {
  jpg: string;
  webp: string;
};

type DecorativeBrandArtworkProps = {
  customUrl?: string;
  desktop: ArtworkSource;
  mobile?: ArtworkSource;
  className?: string;
  imageClassName?: string;
  eager?: boolean;
};

/**
 * Responsive, decorative brand photography with a JPEG fallback.
 *
 * Keeping this in one component makes the public surfaces consistent and
 * prevents marketing artwork from leaking into product data views.
 */
export function DecorativeBrandArtwork({
  customUrl,
  desktop,
  mobile,
  className,
  imageClassName,
  eager = false,
}: DecorativeBrandArtworkProps) {
  const [failedCustomUrl, setFailedCustomUrl] = useState("");
  const activeCustomUrl = customUrl && customUrl !== failedCustomUrl ? customUrl : "";
  const imageClasses = cn("h-full w-full object-cover", imageClassName);

  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
    >
      {activeCustomUrl ? (
        <img
          src={activeCustomUrl}
          alt=""
          className={imageClasses}
          decoding="async"
          loading={eager ? "eager" : "lazy"}
          fetchPriority={eager ? "high" : "auto"}
          onError={() => setFailedCustomUrl(activeCustomUrl)}
        />
      ) : (
        <picture className="block h-full w-full">
          {mobile ? (
            <>
              <source
                media="(max-width: 639px)"
                srcSet={mobile.webp}
                type="image/webp"
              />
              <source
                media="(max-width: 639px)"
                srcSet={mobile.jpg}
                type="image/jpeg"
              />
            </>
          ) : null}
          <source srcSet={desktop.webp} type="image/webp" />
          <img
            src={desktop.jpg}
            alt=""
            className={imageClasses}
            decoding="async"
            loading={eager ? "eager" : "lazy"}
            fetchPriority={eager ? "high" : "auto"}
          />
        </picture>
      )}
    </div>
  );
}
