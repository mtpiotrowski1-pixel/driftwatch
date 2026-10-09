import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useRef, type ReactNode } from "react";

import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export interface DialogVisibilityProps {
  open: boolean;
  onClosed?: () => void;
}

interface DialogProps extends DialogVisibilityProps {
  onOpenChange: (open: boolean) => void;
  dismissible?: boolean;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}

export function Dialog({ open, onOpenChange, dismissible = true, title, description, children, className, onClosed }: DialogProps) {
  const t = useT();
  const opener = useRef<HTMLElement | null>(null);
  const content = useRef<HTMLElement | null>(null);
  return (
    <DialogPrimitive.Root open={open} onOpenChange={(next) => { if (next || dismissible) onOpenChange(next); }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dw-overlay fixed inset-0 z-40 bg-[#111511]/70 backdrop-blur-sm" />
        <DialogPrimitive.Content
          ref={(element) => { if (element) content.current = element; }}
          inert={!open}
          aria-hidden={open ? undefined : true}
          onEscapeKeyDown={(event) => { if (!dismissible) event.preventDefault(); }}
          onInteractOutside={(event) => { if (!dismissible) event.preventDefault(); }}
          onOpenAutoFocus={() => {
            opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
          }}
          onCloseAutoFocus={(event) => {
            if (!open) onClosed?.();
            const target = opener.current;
            const active = document.activeElement;
            const activeDialogs = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"][data-state="open"]'))
              .filter((dialog) => dialog.getAttribute("aria-hidden") !== "true" && !dialog.closest("[inert]"));
            const topDialog = activeDialogs.at(-1);
            // Closing a child may restore its parent, but an old exit must
            // never pull focus out of a newly opened/replacement dialog.
            const focusStillBelongsHere = active === document.body || active === document.documentElement || Boolean(active && content.current?.contains(active));
            if (focusStillBelongsHere && target?.isConnected && !target.closest("[inert]") && (!topDialog || topDialog.contains(target))) {
              event.preventDefault();
              target.focus();
            }
          }}
          className={cn(
            "fixed left-1/2 top-1/2 z-50 max-h-[calc(100dvh-2rem)] w-[min(94vw,32rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto",
            "dw-dialog glass rounded-lg p-6 shadow-2xl focus:outline-none",
            className,
          )}
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <DialogPrimitive.Title className="text-lg font-semibold text-mist-100">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1 text-sm text-mist-400">
                  {description}
                </DialogPrimitive.Description>
              ) : null}
            </div>
            {dismissible ? <DialogPrimitive.Close
              aria-label={t("common.close")}
              className="dw-button grid h-10 w-10 shrink-0 place-items-center rounded-lg text-mist-400 hover:bg-ink-700 hover:text-mist-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </DialogPrimitive.Close> : null}
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
