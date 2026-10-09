import { Sheet } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { useI18n, useT } from "@/i18n";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";

interface ExportChangesButtonProps {
  siteId?: number;
  projectId?: number;
  iconOnly?: boolean;
}

export function ExportChangesButton({ siteId, projectId, iconOnly = false }: ExportChangesButtonProps) {
  const t = useT();
  const { lang } = useI18n();
  const { notify } = useToast();
  const [pending, setPending] = useState(false);
  async function download() {
    setPending(true);
    try {
      await api.download("/api/exports/changes.xlsx", "driftwatch-changes.xlsx", {
        lang, site_id: siteId, project_id: projectId,
      });
    } catch (error) {
      notify(errorMessage(error, t), "error");
    } finally {
      setPending(false);
    }
  }
  return (
    <Button
      type="button"
      variant={iconOnly ? "ghost" : "secondary"}
      size={iconOnly ? "icon" : "sm"}
      aria-label={t("common.exportExcel")}
      disabled={pending}
      onClick={() => void download()}
    >
      {pending ? <Spinner /> : <Sheet className="h-4 w-4" />}
      {!iconOnly ? t("common.exportExcel") : null}
    </Button>
  );
}
