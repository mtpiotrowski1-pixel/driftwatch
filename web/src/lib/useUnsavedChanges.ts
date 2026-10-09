import { useEffect } from "react";
import { useBlocker } from "react-router-dom";
import { useT } from "@/i18n";

export const BEFORE_ORGANIZATION_CHANGE = "driftwatch:before-organization-change";

/**
 * Warn before losing in-progress edits. Blocks in-app navigation (returning a
 * react-router blocker the caller renders a prompt for) and the browser's own
 * unload while `dirty` is true.
 */
export function useUnsavedChanges(dirty: boolean, saved?: () => boolean) {
  const blocker = useBlocker(() => dirty && !saved?.());
  const t = useT();

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      if (saved?.()) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    const checkContext = (event: Event) => {
      if (saved?.()) return;
      if (!window.confirm(t("common.unsaved.body"))) event.preventDefault();
    };
    window.addEventListener(BEFORE_ORGANIZATION_CHANGE, checkContext);
    return () => {
      window.removeEventListener("beforeunload", warn);
      window.removeEventListener(BEFORE_ORGANIZATION_CHANGE, checkContext);
    };
  }, [dirty, saved, t]);

  return blocker;
}
