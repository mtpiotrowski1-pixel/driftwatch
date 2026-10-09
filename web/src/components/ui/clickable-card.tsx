import { type ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * A card whose surface opens a detail view. The primary action is an absolute
 * sibling of the content, not an interactive role wrapped around secondary
 * controls. Action toolbars inside children must opt back into pointer events.
 */
export function ClickableCard({
  onOpen,
  label,
  className,
  children,
}: {
  onOpen: () => void;
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card
      hover
      className={cn("relative overflow-hidden", className)}
    >
      <button
        type="button"
        aria-label={label}
        onClick={onOpen}
        className="absolute inset-0 z-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
      />
      <div className="pointer-events-none relative z-[1]">{children}</div>
    </Card>
  );
}
