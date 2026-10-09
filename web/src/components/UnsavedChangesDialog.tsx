import type { Blocker } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useT } from "@/i18n";

export function UnsavedChangesDialog({ blocker }: { blocker: Blocker }) {
  const t = useT();
  return (
    <Dialog
      open={blocker.state === "blocked"}
      onOpenChange={(open) => { if (!open) blocker.reset?.(); }}
      title={t("common.unsaved.title")}
      description={t("common.unsaved.body")}
    >
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={() => blocker.reset?.()}>
          {t("common.unsaved.stay")}
        </Button>
        <Button variant="danger" onClick={() => blocker.proceed?.()}>
          {t("common.unsaved.leave")}
        </Button>
      </div>
    </Dialog>
  );
}
