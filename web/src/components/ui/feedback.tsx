import { AlertTriangle, Loader2, RotateCw } from "lucide-react";
import { type ComponentProps, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export function Spinner({ className, ...props }: ComponentProps<typeof Loader2>) {
  return <Loader2 className={cn("h-4 w-4 animate-spin", className)} {...props} />;
}

export function PageLoader({ label }: { label?: string }) {
  const t = useT();
  return (
    <div
      className="panel flex h-64 flex-col items-center justify-center gap-3 rounded-xl text-mist-500"
      role="status"
      aria-live="polite"
    >
      <Spinner className="h-6 w-6 text-brand-700" aria-hidden="true" />
      <span className="text-sm">{label ?? t("common.loading")}…</span>
    </div>
  );
}

export function EmptyState({
  icon,
  visual,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  visual?: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center gap-3 rounded-lg border-dashed px-6 py-12 text-center">
      {visual ? (
        <div className="mb-1 w-full max-w-[19rem]" aria-hidden="true">
          {visual}
        </div>
      ) : (
        <div
          className="grid h-11 w-11 place-items-center rounded-md border border-line bg-ink-900 text-brand-700"
          aria-hidden="true"
        >
          {icon}
        </div>
      )}
      <h3 className="text-lg font-semibold text-mist-100">{title}</h3>
      <p className="max-w-sm text-sm text-mist-400">{description}</p>
      {action}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-lg border border-rose-400/30 bg-rose-400/10 px-3.5 py-2.5 text-sm text-rose-400">
      {children}
    </p>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-ink-800", className)} />;
}

export function CardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }, (_, index) => (
        <Skeleton key={index} className="h-36" />
      ))}
    </div>
  );
}

export function ErrorState({ onRetry }: { onRetry: () => void }) {
  const t = useT();
  return (
    <div
      className="panel flex flex-col items-center gap-3 rounded-lg border-dashed px-6 py-12 text-center"
      role="alert"
    >
      <div
        className="grid h-12 w-12 place-items-center rounded-lg bg-rose-400/10 text-rose-400"
        aria-hidden="true"
      >
        <AlertTriangle className="h-6 w-6" />
      </div>
      <h3 className="text-lg font-semibold text-mist-100">{t("common.errorTitle")}</h3>
      <p className="max-w-sm text-sm text-mist-400">{t("common.loadErrorBody")}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        <RotateCw className="h-4 w-4" />
        {t("common.retry")}
      </Button>
    </div>
  );
}
