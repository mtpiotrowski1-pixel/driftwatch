import * as LabelPrimitive from "@radix-ui/react-label";
import {
  cloneElement,
  forwardRef,
  isValidElement,
  type InputHTMLAttributes,
  type LabelHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useId,
} from "react";

import { cn } from "@/lib/utils";

const CONTROL =
  "min-h-11 w-full rounded-md border border-line-strong bg-ink-900 px-3.5 py-2.5 text-base text-mist-100 sm:text-sm " +
  "placeholder:text-mist-500 transition-colors focus-visible:outline-none " +
  "focus-visible:border-focus focus-visible:ring-2 focus-visible:ring-focus";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(CONTROL, className)} {...props} />;
  },
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(CONTROL, "min-h-24 resize-y", className)} {...props} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, ...props }, ref) {
    return <select ref={ref} className={cn(CONTROL, className)} {...props} />;
  },
);

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <LabelPrimitive.Root
      className={cn("text-sm font-medium text-mist-300", className)}
      {...props}
    />
  );
}

export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  const hintId = useId();
  const describedControl =
    hint && isValidElement(children)
      ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, {
          "aria-describedby": [
            (children.props as { "aria-describedby"?: string })["aria-describedby"],
            hintId,
          ]
            .filter(Boolean)
            .join(" "),
        })
      : children;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {describedControl}
      {hint ? (
        <p id={hintId} className="text-xs leading-relaxed text-mist-500">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
