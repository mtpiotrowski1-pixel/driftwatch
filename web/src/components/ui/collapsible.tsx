import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { DisclosurePanel } from "./disclosure-panel";

interface CollapsibleProps {
  label: string;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
}

/** A labeled disclosure used to demote power-user fields below the primary,
 * point-and-click actions. Native state and a real button keep it accessible
 * without pulling in another dependency. */
export function Collapsible({ label, defaultOpen = false, children, className }: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 rounded-md border border-line bg-ink-900/50 px-3.5 py-2.5 text-sm text-mist-300 transition-colors hover:border-brand-500/40 hover:text-mist-100"
      >
        <ChevronRight
          aria-hidden="true"
          className={cn("h-4 w-4 shrink-0 transition-transform", open && "rotate-90")}
        />
        <span className="text-left">{label}</span>
      </button>
      <DisclosurePanel id={panelId} label={label} open={open} className="space-y-5 pt-2">
        {children}
      </DisclosurePanel>
    </div>
  );
}
