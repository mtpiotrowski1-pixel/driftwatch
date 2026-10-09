import { Slot } from "@radix-ui/react-slot";
import { type ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg" | "icon";

const VARIANTS: Record<Variant, string> = {
  primary:
    "border border-brand-600/60 bg-brand-500 text-[#151915] shadow-sm hover:bg-brand-400 active:bg-brand-600",
  secondary:
    "border border-line-strong bg-ink-900 text-mist-100 shadow-sm hover:border-mist-500 hover:bg-ink-850",
  ghost: "text-mist-300 hover:bg-ink-800 hover:text-mist-100",
  danger: "border border-rose-400/35 bg-rose-400/10 text-rose-400 hover:bg-rose-400/15",
};

const SIZES: Record<Size, string> = {
  sm: "h-10 px-3 text-sm gap-1.5",
  md: "h-11 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2",
  icon: "h-10 w-10",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", asChild = false, ...props },
  ref,
) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      ref={ref}
      className={cn(
        "dw-button inline-flex shrink-0 items-center justify-center rounded-md font-semibold",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
});
