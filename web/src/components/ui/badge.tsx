import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type Tone = "neutral" | "brand" | "amber" | "emerald" | "rose";

const TONES: Record<Tone, string> = {
  neutral: "bg-ink-700 text-mist-300 border-line",
  brand: "bg-brand-300/40 text-mist-100 border-brand-600/40",
  amber: "bg-amber-400/15 text-amber-400 border-amber-400/30",
  emerald: "bg-emerald-400/15 text-emerald-400 border-emerald-400/30",
  rose: "bg-rose-400/15 text-rose-400 border-rose-400/30",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}
