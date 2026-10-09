import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/field";
import { useT } from "@/i18n";
import type { InteractionStep } from "@/lib/types";

const ACTIONS: InteractionStep["action"][] = ["click", "fill", "wait_for", "wait"];

const ACTION_KEY: Record<InteractionStep["action"], string> = {
  click: "picker.actionClick",
  fill: "picker.actionFill",
  wait_for: "picker.actionWaitFor",
  wait: "picker.actionWait",
};

const EMPTY_STEP: InteractionStep = { action: "click", selector: "", timeout_ms: 10_000 };

// Plaintext is deliberately kept only in component state and the write request.
// Existing secrets round-trip by opaque reference without being read back.
export function compactSteps(steps: InteractionStep[]): InteractionStep[] {
  return steps
    .filter((step) => step.action === "wait" || !!step.selector?.trim())
    .map((step) => {
      const compact: InteractionStep = {
        action: step.action,
        selector: step.action === "wait" ? null : step.selector?.trim() || null,
        timeout_ms: step.timeout_ms ?? 10_000,
      };
      if (step.action === "fill") {
        if (step.secret_value) compact.secret_value = step.secret_value;
        else if (step.secret_ref) compact.secret_ref = step.secret_ref;
      }
      return compact;
    });
}

export function InteractionStepsEditor({
  steps,
  onChange,
}: {
  steps: InteractionStep[];
  onChange: (steps: InteractionStep[]) => void;
}) {
  const t = useT();

  function update(index: number, patch: Partial<InteractionStep>) {
    onChange(steps.map((step, i) => (i === index ? { ...step, ...patch } : step)));
  }

  function setAction(index: number, action: InteractionStep["action"]) {
    onChange(
      steps.map((step, i) =>
        i === index
          ? {
              action,
              selector: action === "wait" ? null : step.selector,
              timeout_ms: step.timeout_ms ?? 10_000,
            }
          : step,
      ),
    );
  }

  function remove(index: number) {
    onChange(steps.filter((_, i) => i !== index));
  }

  function add() {
    onChange([...steps, { ...EMPTY_STEP }]);
  }

  return (
    <div className="space-y-2">
      {steps.map((step, index) => (
        <div key={index} className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-lg border border-line p-3 sm:flex sm:border-0 sm:p-0">
          <Select
            aria-label={t("picker.action")}
            className="col-span-2 w-full shrink-0 sm:w-32"
            value={step.action}
            onChange={(event) => setAction(index, event.target.value as InteractionStep["action"])}
          >
            {ACTIONS.map((action) => (
              <option key={action} value={action}>
                {t(ACTION_KEY[action])}
              </option>
            ))}
          </Select>
          <Input
            className="col-span-2 min-w-0 sm:flex-1"
            aria-label={t("picker.selector")}
            placeholder={t("picker.selector")}
            value={step.selector ?? ""}
            disabled={step.action === "wait"}
            onChange={(event) => update(index, { selector: event.target.value })}
          />
          {step.action === "fill" ? (
            <Input
              className="min-w-0 sm:flex-1"
              type="password"
              autoComplete="off"
              required={!step.secret_ref}
              aria-label={t("picker.value")}
              placeholder={step.secret_ref ? "********" : t("picker.value")}
              value={step.secret_value ?? ""}
              onChange={(event) =>
                update(index, {
                  secret_value: event.target.value,
                  secret_ref: null,
                  has_secret: false,
                })
              }
            />
          ) : step.action === "wait" ? (
            <Input
              className="min-w-0 sm:flex-1"
              type="number"
              min={0}
              max={120_000}
              aria-label={t("picker.milliseconds")}
              placeholder={t("picker.milliseconds")}
              value={step.timeout_ms ?? 10_000}
              onChange={(event) => update(index, { timeout_ms: Number(event.target.value) })}
            />
          ) : (
            <span className="hidden min-w-0 flex-1 sm:block" />
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={t("picker.removeStep")}
            onClick={() => remove(index)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button type="button" variant="secondary" size="sm" onClick={add}>
        <Plus className="h-3.5 w-3.5" />
        {t("picker.addStep")}
      </Button>
    </div>
  );
}
