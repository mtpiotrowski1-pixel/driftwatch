import { AlertTriangle, MousePointerClick } from "lucide-react";
import { type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";

interface PickerActionPanelProps {
  title: string;
  explainer: string;
  actionLabel: string;
  onAction: () => void;
  disabled: boolean;
  /** Shown in amber when the picker cannot run on this host; nudges to manual entry. */
  unavailable?: string | null;
  /** A soft reason the action is blocked even though the picker is available. */
  blockedHint?: string | null;
  /** Current selection or recorded-step summary. */
  children?: ReactNode;
}

/** The prominent, point-and-click entry to the visual picker — promoted above
 * the manual fields it used to sit beside. Used for both "pick an area" and
 * "record steps" in the add and edit flows. */
export function PickerActionPanel({
  title,
  explainer,
  actionLabel,
  onAction,
  disabled,
  unavailable,
  blockedHint,
  children,
}: PickerActionPanelProps) {
  const t = useT();

  return (
    <div className="space-y-3 rounded-lg border border-line bg-ink-900/40 p-4">
      <div className="flex items-center gap-2 text-mist-200">
        <MousePointerClick className="h-4 w-4 text-brand-700" aria-hidden="true" />
        <h4 className="text-sm font-medium">{title}</h4>
      </div>
      <p className="text-xs text-mist-500">{explainer}</p>
      <Button type="button" onClick={onAction} disabled={disabled}>
        <MousePointerClick className="h-4 w-4" />
        {actionLabel}
      </Button>
      {children}
      {unavailable ? (
        <p role="status" className="flex items-start gap-1.5 text-xs text-amber-400">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>
            {unavailable} {t("picker.useManualInstead")}
          </span>
        </p>
      ) : blockedHint ? (
        <p className="text-xs text-mist-500">{blockedHint}</p>
      ) : null}
    </div>
  );
}
