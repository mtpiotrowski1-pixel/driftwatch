import { useState, type InputHTMLAttributes } from "react";
import { RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { useT } from "@/i18n";

interface SecretSettingControlProps {
  id: string;
  value: string;
  placeholder: string;
  configured: boolean;
  removalPending: boolean;
  onChange: (value: string) => void;
  onRemove: () => void;
  onUndo: () => void;
}

/** Configuration credentials are not the signed-in account's password.
 * Keep collapsed fields read-only until intentional focus so browser login
 * autofill cannot silently place account credentials in a provider setting. */
export function ConfigurationInput(props: InputHTMLAttributes<HTMLInputElement>) {
  const [editing, setEditing] = useState(false);
  return (
    <Input
      {...props}
      name={`configuration_${props.id}`}
      autoComplete={props.type === "password" ? "new-password" : "off"}
      readOnly={!editing}
      onFocus={(event) => {
        setEditing(true);
        props.onFocus?.(event);
      }}
      onBlur={(event) => {
        setEditing(false);
        props.onBlur?.(event);
      }}
    />
  );
}

export function SecretSettingControl({
  id,
  value,
  placeholder,
  configured,
  removalPending,
  onChange,
  onRemove,
  onUndo,
}: SecretSettingControlProps) {
  const t = useT();
  return (
    <div className="space-y-2">
      <ConfigurationInput
        id={id}
        type="password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
      {removalPending ? (
        <div className="flex min-h-10 items-center justify-between gap-3 rounded-md border border-rose-400/30 bg-rose-400/5 px-3">
          <span className="text-xs text-rose-300">{t("settings.security.removePending")}</span>
          <Button type="button" variant="ghost" size="sm" onClick={onUndo}>
            {t("settings.security.undoRemove")}
          </Button>
        </div>
      ) : configured ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-rose-300 hover:text-rose-200"
          onClick={onRemove}
        >
          <Trash2 className="h-4 w-4" />
          {t("settings.security.removeStored")}
        </Button>
      ) : null}
    </div>
  );
}

export function RestoreDefault({ onClick }: { onClick: () => void }) {
  const t = useT();
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-2 inline-flex items-center gap-1 text-xs text-mist-500 transition-colors hover:text-mist-300"
    >
      <RotateCcw className="h-3 w-3" />
      {t("settings.restoreDefault")}
    </button>
  );
}
