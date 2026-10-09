import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNote, Spinner } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import {
  usePickerResult,
  usePickerStatus,
} from "@/lib/picker";
import type { InteractionStep, PickerState, PickerStatus } from "@/lib/types";

const TERMINAL_STATES: PickerState[] = ["saved", "cancelled", "timed_out", "error"];

const FAILURE_KEY: Record<"cancelled" | "timed_out" | "error", string> = {
  cancelled: "picker.selectionCancelled",
  timed_out: "picker.timedOut",
  error: "picker.failed",
};

interface VisualPickerDialogProps {
  open: boolean;
  onClose: () => void;
  url: string;
  mode: "select" | "record";
  siteId?: number | null;
  onSelect?: (cssSelector: string) => void;
  onSteps?: (steps: InteractionStep[]) => void;
}

export function VisualPickerDialog({
  open,
  onClose,
  url,
  mode,
  siteId,
  onSelect,
  onSteps,
}: VisualPickerDialogProps) {
  const t = useT();
  const { notify } = useToast();
  const [startingRequest, setStartingRequest] = useState(false);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  const status = usePickerStatus(sessionId);
  const state = status.data?.state ?? null;
  const result = usePickerResult(sessionId, state === "saved");

  const handled = useRef(false);
  const operation = useRef<{ key: string; promise: Promise<PickerStatus>; disposed: boolean; id: string | null; cancelled: boolean; state: PickerState | null } | null>(null);
  if (operation.current && operation.current.id === sessionId) operation.current.state = state;
  // Read through a ref so changing the UI language doesn't restart the session.
  const tRef = useRef(t);
  tRef.current = t;

  useEffect(() => {
    if (!open) return;
    handled.current = false;
    setStartError(null);
    setSessionId(null);
    setStartingRequest(true);
    const key = JSON.stringify([url, mode, siteId]);
    // Reuse the same pending operation during React's development effect replay.
    // A disposed operation still owns its eventual server id and cleans it up.
    if (!operation.current || operation.current.key !== key || operation.current.cancelled) {
      operation.current = { key, promise: api.post<PickerStatus>("/api/picker/sessions", { url, mode, site_id: siteId ?? null }), disposed: false, id: null, cancelled: false, state: null };
    }
    const owned = operation.current;
    owned.disposed = false;
    const cancelOwned = () => {
      if (!owned.id || owned.cancelled) return;
      owned.cancelled = true;
      void api.del(`/api/picker/sessions/${owned.id}`).catch(() => undefined);
    };
    void owned.promise.then((started) => {
      owned.id = started.session_id;
      if (owned.disposed) { cancelOwned(); return; }
      setSessionId(started.session_id);
      setStartingRequest(false);
    }).catch((error) => {
      if (owned.disposed) return;
      setStartingRequest(false);
      setStartError(errorMessage(error, tRef.current));
    });
    return () => {
      owned.disposed = true;
      queueMicrotask(() => {
        if (owned.disposed && (!owned.state || !TERMINAL_STATES.includes(owned.state))) cancelOwned();
      });
    };
  }, [open, url, mode, siteId]);

  useEffect(() => {
    if (handled.current || !state) return;
    if (state === "saved") {
      if (!result.data) return;
      handled.current = true;
      if (mode === "select") onSelect?.(result.data.css_selector);
      else onSteps?.(result.data.steps);
      notify(mode === "select" ? t("picker.selectorCaptured") : t("picker.stepsRecorded"));
      onClose();
    } else if (state === "cancelled" || state === "timed_out" || state === "error") {
      handled.current = true;
      notify(status.data?.detail ?? t(FAILURE_KEY[state]), "error");
      onClose();
    }
  }, [state, result.data, mode, onSelect, onSteps, notify, onClose, status.data?.detail, t]);

  const current = status.data;
  const channel = current?.channel ?? null;
  const starting = startingRequest || state === "starting" || (!!sessionId && !current);
  const requestError = status.isError ? status.error : result.isError ? result.error : null;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !next && onClose()}
      title={mode === "select" ? t("picker.pickVisually") : t("picker.recordSteps")}
    >
      {startError || requestError ? (
        <div className="space-y-4">
          <ErrorNote>{startError ?? errorMessage(requestError, t)}</ErrorNote>
          <p className="text-sm text-mist-400">{t("picker.useManualInstead")}</p>
          <div className="flex justify-end">
            {requestError ? <Button variant="secondary" onClick={() => { if (status.isError) void status.refetch(); else void result.refetch(); }}>{t("common.retry")}</Button> : null}
            <Button variant="ghost" onClick={onClose}>
              {t("common.close")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-mist-300">{t("picker.dialogLead")}</p>
          {channel ? <Badge tone="brand">{t("picker.openedIn", { channel })}</Badge> : null}
          <p className="text-sm text-mist-300">
            {mode === "select"
              ? t("picker.instructionsSelect")
              : t("picker.instructionsRecord")}
          </p>
          <p className="rounded-lg border border-line bg-ink-900/50 px-3.5 py-2.5 text-sm text-mist-300">
            {t("picker.saveInWindow")}
          </p>
          <div className="flex items-center gap-2 text-sm text-mist-400">
            <Spinner className="text-brand-700" />
            <span>
              {starting
                ? t("picker.starting")
                : mode === "select"
                  ? t("picker.waitingSelected", { count: current?.selector_count ?? 0 })
                  : t("picker.waitingRecorded", { count: current?.step_count ?? 0 })}
            </span>
          </div>
          {!starting &&
          (mode === "select"
            ? (current?.selector_count ?? 0) === 0
            : (current?.step_count ?? 0) === 0) ? (
            <p className="text-xs text-mist-500">
              {mode === "select" ? t("picker.selectNothingYet") : t("picker.recordNothingYet")}
            </p>
          ) : null}
          <div className="flex justify-end">
            <Button variant="ghost" onClick={onClose}>
              {t("picker.closePicker")}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
