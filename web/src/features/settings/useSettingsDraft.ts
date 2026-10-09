import { useMemo, useState, type FormEvent } from "react";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import type { ApiRequestContext } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { useUpdateSettings } from "@/lib/queries";
import type { Settings } from "@/lib/types";
import { useUnsavedChanges } from "@/lib/useUnsavedChanges";
import {
  buildSettingsPayload,
  parseIds,
  parseIgnore,
  SECRET_FIELDS,
  STEP_UP_TEXT_FIELDS,
  type TextKey,
  type SecretKey,
  type NumberKey,
} from "./model";

/** Keep uncommitted configuration and the step-up snapshot out of the query cache.
 * Failed saves retain the draft for retry; successful saves discard secrets. */
export function useSettingsDraft(stored: Settings, requestContext: ApiRequestContext) {
  const t = useT();
  const { notify } = useToast();
  const updateSettings = useUpdateSettings(requestContext);
  const [text, setText] = useState<Record<string, string>>({});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [numbers, setNumbers] = useState<Record<string, string>>({});
  const [importanceRules, setImportanceRules] = useState<string | null>(null);
  const [defaultMode, setDefaultMode] = useState<string | null>(null);
  const [ignoreSelectors, setIgnoreSelectors] = useState<string | null>(null);
  const [technicalIds, setTechnicalIds] = useState<number[] | null>(null);
  const [saved, setSaved] = useState(false);
  const [pendingSecretSave, setPendingSecretSave] = useState<Record<string, unknown> | null>(null);

  const initialIgnore = useMemo(() => parseIgnore(stored.ignore_selectors), [stored.ignore_selectors]);
  const initialTechnical = useMemo(
    () => parseIds(stored.technical_alert_recipient_ids),
    [stored.technical_alert_recipient_ids],
  );

  const dirty =
    Object.keys(
      buildSettingsPayload(
        { text, secrets, numbers, importanceRules, defaultMode, ignoreSelectors, technicalIds },
        stored,
        initialIgnore,
        initialTechnical,
      ),
    ).length > 0;
  const blocker = useUnsavedChanges(dirty);

  const textValue = (key: TextKey) => text[key] ?? stored[key] ?? "";
  const numberValue = (key: NumberKey) => numbers[key] ?? stored[key] ?? "";
  const rulesValue = importanceRules ?? stored.importance_rules ?? "";
  const modeValue = defaultMode ?? stored.default_notification_mode ?? "only_significant";
  const ignoreValue = ignoreSelectors ?? initialIgnore;
  const technicalValue = technicalIds ?? initialTechnical;
  const error = updateSettings.error ? errorMessage(updateSettings.error, t) : null;

  function setTextField(key: TextKey, value: string) {
    setText((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  function setSecretField(key: SecretKey, value: string) {
    setSecrets((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  function setNumberField(key: NumberKey, value: string) {
    setNumbers((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  function toggleTechnical(id: number) {
    setSaved(false);
    setTechnicalIds((current) => {
      const base = current ?? initialTechnical;
      return base.includes(id) ? base.filter((value) => value !== id) : [...base, id];
    });
  }

  async function saveSettings(payload: Record<string, unknown>) {
    try {
      await updateSettings.mutateAsync(payload);
      setSecrets({});
      setPendingSecretSave(null);
      setSaved(true);
      notify(t("settings.toast.saved"));
    } catch (error) {
      notify(errorMessage(error, t), "error");
    }
  }

  function removeSecretField(key: SecretKey) {
    setSecrets((current) => ({ ...current, [key]: "" }));
    setSaved(false);
  }

  function undoSecretRemoval(key: SecretKey) {
    setSecrets((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setSaved(false);
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const payload = buildSettingsPayload(
      { text, secrets, numbers, importanceRules, defaultMode, ignoreSelectors, technicalIds },
      stored,
      initialIgnore,
      initialTechnical,
    );

    if (Object.keys(payload).length === 0) {
      setSaved(true);
      return;
    }
    if (
      "clear_secret_keys" in payload ||
      SECRET_FIELDS.some((key) => key in payload) ||
      STEP_UP_TEXT_FIELDS.some((key) => key in payload)
    ) {
      setPendingSecretSave(payload);
      return;
    }
    void saveSettings(payload);
  }

  return {
    textValue,
    setTextField,
    numberValue,
    setNumberField,
    rulesValue,
    setImportanceRules: (value: string) => {
      setImportanceRules(value);
      setSaved(false);
    },
    modeValue,
    setDefaultMode: (value: string) => {
      setDefaultMode(value);
      setSaved(false);
    },
    ignoreValue,
    setIgnoreSelectors: (value: string) => {
      setIgnoreSelectors(value);
      setSaved(false);
    },
    technicalValue,
    toggleTechnical,
    secrets,
    setSecretField,
    removeSecretField,
    undoSecretRemoval,
    saved,
    dirty,
    blocker,
    error,
    isPending: updateSettings.isPending,
    pendingSecretSave,
    cancelSensitiveSave: () => setPendingSecretSave(null),
    confirmSensitiveSave: () => pendingSecretSave ? saveSettings(pendingSecretSave) : undefined,
    handleSubmit,
  };
}

export type SettingsDraft = ReturnType<typeof useSettingsDraft>;
export type TextSettingsFields = Pick<SettingsDraft, "textValue" | "setTextField">;
export type SecretSettingsFields = Pick<
  SettingsDraft,
  "secrets" | "setSecretField" | "removeSecretField" | "undoSecretRemoval"
>;
export type NumberSettingsFields = Pick<SettingsDraft, "numberValue" | "setNumberField">;
