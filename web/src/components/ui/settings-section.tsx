import { ChevronDown } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { DisclosurePanel } from "./disclosure-panel";

interface SettingsSectionProps {
  title: string;
  icon?: ReactNode;
  /** One-line summary shown under the title, so a collapsed section still says
   * what it holds. */
  description?: string;
  defaultOpen?: boolean;
  /** Classes for the body wrapper (e.g. the field grid), so a section keeps the
   * card body's original layout. */
  bodyClassName?: string;
  children: ReactNode;
}

/** A collapsible settings group: a card whose header is a real toggle button.
 * Lets the long settings page collapse to a scannable list of sections that the
 * admin expands on demand, instead of one long scroll. */
export function SettingsSection({
  title,
  icon,
  description,
  defaultOpen = false,
  bodyClassName,
  children,
}: SettingsSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  return (
    <div className="glass overflow-hidden rounded-lg">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-ink-800/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
      >
        {icon ? (
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-line bg-ink-850 text-brand-700">
            {icon}
          </span>
        ) : null}
        <span className="min-w-0 flex-1">
          <span className="block font-semibold text-mist-100">{title}</span>
          {description ? (
            <span className="mt-0.5 block truncate text-xs text-mist-500">{description}</span>
          ) : null}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn(
            "h-5 w-5 shrink-0 text-mist-400 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      <DisclosurePanel
        id={panelId}
        label={title}
        open={open}
        className={cn("border-t border-line/60 px-5 py-5", bodyClassName)}
      >
        {children}
      </DisclosurePanel>
    </div>
  );
}
