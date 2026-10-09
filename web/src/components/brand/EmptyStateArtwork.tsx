import { cn } from "@/lib/utils";

type EmptyStateArtworkProps = {
  variant: "workspace" | "delivery";
  className?: string;
};

export function EmptyStateArtwork({ variant, className }: EmptyStateArtworkProps) {
  const artwork = `/brand/illustrations/empty-${variant}`;
  const sizes = "(max-width: 640px) min(304px, calc(100vw - 96px)), 304px";

  return (
    <picture className={cn("block h-auto w-full", className)} aria-hidden="true">
      <source
        type="image/webp"
        srcSet={`${artwork}-480.webp 480w, ${artwork}-960.webp 960w`}
        sizes={sizes}
      />
      <img
        src={`${artwork}-480.png`}
        srcSet={`${artwork}-480.png 480w, ${artwork}-960.png 960w`}
        sizes={sizes}
        width={480}
        height={320}
        alt=""
        loading="lazy"
        decoding="async"
        className="block h-auto w-full"
      />
    </picture>
  );
}
