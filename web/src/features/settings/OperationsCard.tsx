import { useState } from "react";
import { Database, ScrollText, Upload } from "lucide-react";
import { StepUpDialog } from "@/components/StepUpDialog";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { ErrorNote, Spinner } from "@/components/ui/feedback";
import { SettingsSection } from "@/components/ui/settings-section";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { instanceRequestContext } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { Link } from "@/lib/navigation";
import { useAdminCapabilities, useRestoreBackup } from "@/lib/queries";

function triggerDownload(url: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function RestoreControl() {
  const t = useT();
  const { notify } = useToast();
  const restore = useRestoreBackup();
  const [step, setStep] = useState<"idle" | "auth" | "pick">("idle");
  const [file, setFile] = useState<File | null>(null);
  const error = restore.error ? errorMessage(restore.error, t) : null;

  function handleRestore() {
    if (!file) return;
    restore.mutate(file, {
      onSuccess: () => {
        notify(t("settings.ops.restoreDone"));
        setStep("idle");
        setFile(null);
        // A restored database can invalidate this session; send the operator to
        // log in again against the new data.
        window.setTimeout(() => window.location.assign("/login"), 1500);
      },
    });
  }

  return (
    <>
      <Button variant="secondary" onClick={() => setStep("auth")}>
        <Upload className="h-4 w-4" />
        {t("settings.ops.restore")}
      </Button>
      {step === "auth" ? (
        <StepUpDialog
          title={t("settings.ops.restore")}
          description={t("settings.ops.restoreConfirm")}
          submitLabel={t("settings.ops.restore")}
          submitVariant="danger"
          requestContext={instanceRequestContext}
          onVerified={() => setStep("pick")}
          onClose={() => setStep("idle")}
        />
      ) : null}
      {step === "pick" ? (
        <Dialog
          open
          onOpenChange={(open) => !open && setStep("idle")}
          title={t("settings.ops.restore")}
          description={t("settings.ops.restorePick")}
        >
          <div className="space-y-4">
            <input
              type="file"
              accept=".db,application/octet-stream,application/x-sqlite3"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="block w-full text-sm text-mist-300 file:mr-4 file:rounded-lg file:border-0 file:bg-ink-800 file:px-4 file:py-2 file:text-sm file:text-mist-100 hover:file:bg-ink-700"
            />
            {error ? <ErrorNote>{error}</ErrorNote> : null}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setStep("idle")}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="danger"
                disabled={!file || restore.isPending}
                onClick={handleRestore}
              >
                {restore.isPending ? <Spinner /> : null}
                {t("settings.ops.restoreSubmit")}
              </Button>
            </div>
          </div>
        </Dialog>
      ) : null}
    </>
  );
}

export function OperationsCard() {
  const t = useT();
  const [confirmBackup, setConfirmBackup] = useState(false);
  const capabilities = useAdminCapabilities();
  const sqliteBackup = capabilities.data?.sqlite_backup_restore ?? false;

  return (
    <SettingsSection title={t("settings.ops.title")} icon={<Database className="h-4 w-4" />} bodyClassName="space-y-5">
      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" asChild>
          <Link to="/audit">
            <ScrollText className="h-4 w-4" />
            {t("settings.ops.openAudit")}
          </Link>
        </Button>
        {sqliteBackup ? (
          <>
            {/* The backup holds password hashes and secrets, so it is gated behind
                  a fresh re-authentication before the download is triggered. */}
            <Button variant="secondary" onClick={() => setConfirmBackup(true)}>
              <Database className="h-4 w-4" />
              {t("settings.ops.downloadBackup")}
            </Button>
            <RestoreControl />
          </>
        ) : null}
      </div>

      {capabilities.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-mist-500">
          <Spinner />
          {t("settings.ops.detectingCapabilities")}
        </div>
      ) : capabilities.isError ? (
        <ErrorNote>{t("settings.ops.capabilitiesUnavailable")}</ErrorNote>
      ) : !sqliteBackup ? (
        <p className="text-sm leading-6 text-mist-500">
          {t("settings.ops.providerManagedBackup")}
        </p>
      ) : null}

      {confirmBackup && sqliteBackup ? (
        <StepUpDialog
          title={t("settings.ops.downloadBackup")}
          description={t("settings.ops.backupConfirm")}
          submitLabel={t("settings.ops.downloadBackup")}
          requestContext={instanceRequestContext}
          onVerified={() => triggerDownload("/api/admin/backup")}
          onClose={() => setConfirmBackup(false)}
        />
      ) : null}
    </SettingsSection>
  );
}
