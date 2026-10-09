import { useRef } from "react";
import { ImageUp, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNote, Spinner } from "@/components/ui/feedback";
import { Field } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import type { ApiRequestContext } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { useDeleteBrandingAsset, useUploadBrandingAsset, type BrandingAssetKind } from "@/lib/queries";
import { cn } from "@/lib/utils";

export function BrandingAssetField({
  kind,
  requestContext,
  label,
  hint,
  currentUrl,
}: {
  kind: BrandingAssetKind;
  requestContext: ApiRequestContext;
  label: string;
  hint: string;
  currentUrl: string;
}) {
  const t = useT();
  const upload = useUploadBrandingAsset(kind, requestContext);
  const remove = useDeleteBrandingAsset(kind, requestContext);
  const input = useRef<HTMLInputElement>(null);
  const { notify } = useToast();
  const id = `branding-${kind}-upload`;
  const visibleUrl =
    currentUrl.startsWith("/") && !currentUrl.startsWith("//") && !currentUrl.includes("\\")
      ? currentUrl
      : "";
  const pending = upload.isPending || remove.isPending;
  const error = upload.error
    ? errorMessage(upload.error, t)
    : remove.error
      ? errorMessage(remove.error, t)
      : null;

  async function handleFile(file: File | undefined) {
    if (!file) return;
    try {
      await upload.mutateAsync(file);
      notify(t("settings.branding.assetSaved"));
    } catch {
      // The mutation exposes the localized API error below the control.
    } finally {
      if (input.current) input.current.value = "";
    }
  }

  async function handleRemove() {
    try {
      await remove.mutateAsync();
      notify(t("settings.branding.assetRemoved"));
    } catch {
      // The mutation exposes the localized API error below the control.
    }
  }

  return (
    <Field label={label} hint={hint} htmlFor={id}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div
          className={cn(
            "grid shrink-0 place-items-center overflow-hidden rounded-md border border-line bg-ink-900/60",
            kind === "logo" ? "h-20 w-20" : "aspect-[16/7] w-full sm:w-56",
          )}
        >
          {visibleUrl ? (
            <img
              src={visibleUrl}
              alt=""
              className={cn(
                "h-full w-full",
                kind === "logo" ? "object-contain p-2" : "object-cover",
              )}
            />
          ) : (
            <ImageUp className="h-5 w-5 text-mist-500" aria-hidden="true" />
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            ref={input}
            id={id}
            type="file"
            accept="image/png,image/jpeg"
            className="sr-only"
            onChange={(event) => void handleFile(event.target.files?.[0])}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={pending}
            onClick={() => input.current?.click()}
          >
            {upload.isPending ? <Spinner /> : <Upload className="h-4 w-4" />}
            {t(visibleUrl ? "settings.branding.replace" : "settings.branding.upload")}
          </Button>
          {visibleUrl ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={pending}
              onClick={() => void handleRemove()}
            >
              {remove.isPending ? <Spinner /> : <Trash2 className="h-4 w-4" />}
              {t("settings.branding.remove")}
            </Button>
          ) : null}
        </div>
      </div>
      {error ? <ErrorNote>{error}</ErrorNote> : null}
    </Field>
  );
}
