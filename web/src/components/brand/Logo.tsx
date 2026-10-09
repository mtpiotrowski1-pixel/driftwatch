import { useState } from "react";

import { useBrand } from "@/branding";
import { cn } from "@/lib/utils";

/** The generated glass D, with a lightweight native fallback.
 * Uploaded workspace branding always takes precedence over the built-in mark. */
export function Logo({ className }: { className?: string }) {
  const { logoUrl } = useBrand();
  const [failedLogoUrl, setFailedLogoUrl] = useState("");
  const [failedBuiltin, setFailedBuiltin] = useState(false);
  if (logoUrl && logoUrl !== failedLogoUrl) {
    return (
      <img
        src={logoUrl}
        alt=""
        className={cn("h-8 w-8 shrink-0 object-contain", className)}
        decoding="async"
        onError={() => setFailedLogoUrl(logoUrl)}
      />
    );
  }
  if (!failedBuiltin) {
    return (
      <picture className={cn("dw-logo h-8 w-8 shrink-0", className)}>
        <source
          type="image/webp"
          srcSet="/brand/driftwatch-emblem-64.webp 1x, /brand/driftwatch-emblem-128.webp 2x, /brand/driftwatch-emblem-256.webp 3x"
        />
        <img
          src="/brand/driftwatch-emblem-64.png"
          alt=""
          width="64"
          height="64"
          className="h-full w-full object-contain"
          decoding="async"
          onError={() => setFailedBuiltin(true)}
        />
      </picture>
    );
  }
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("dw-logo h-8 w-8 shrink-0", className)}
      aria-hidden="true"
      focusable="false"
    >
      <rect x="1" y="1" width="30" height="30" rx="9" fill="var(--color-brand-500)" />
      <path
        d="M9 8H15C20.5 8 24 11 24 16S20.5 24 15 24H9Z"
        fill="none"
        stroke="#151915"
        strokeWidth="3.2"
        strokeLinejoin="round"
      />
      <path
        className="dw-logo-trace"
        d="M9 17.5H13.5L16.5 14.5H20"
        fill="none"
        stroke="#151915"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Wordmark({
  className,
  compactOnNarrow = false,
}: {
  className?: string;
  compactOnNarrow?: boolean;
}) {
  const { name } = useBrand();
  return (
    <span
      className={cn(
        "dw-wordmark flex items-center gap-2.5 font-display font-semibold tracking-[-0.025em] text-mist-100",
        className,
      )}
    >
      <Logo />
      <span className={cn(compactOnNarrow && "hidden min-[360px]:inline")}>{name}</span>
    </span>
  );
}
