import { errorMessage } from "@/lib/errors";
import { FlaskConical } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorNote, Spinner } from "@/components/ui/feedback";
import { useT } from "@/i18n";
import { useAnalyzePreview } from "@/lib/queries";
import type { AnalysisPreview } from "@/lib/types";
import { formatCost } from "@/lib/utils";

/** Dry-run the draft rules in the surrounding editor against a past change.
 * The verdict renders inline and nothing is persisted, so an operator can
 * iterate on rules without rewriting the change history. */
export function RulesTester({
  changeId,
  rules,
}: {
  /** The change to test against, or null when the scope has none yet. */
  changeId: number | null;
  /** The draft rules text currently in the editor. */
  rules: string;
}) {
  const t = useT();
  const preview = useAnalyzePreview();
  const [testedInput, setTestedInput] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<{ input: string; data: AnalysisPreview } | null>(null);
  const currentInput = JSON.stringify([changeId, rules]);
  const resultCurrent = currentInput === testedInput;
  const error = resultCurrent && preview.error ? errorMessage(preview.error, t) : null;
  const result = verdict?.input === currentInput ? verdict.data : null;
  const noRules = !rules.trim();
  const disabled = changeId === null || noRules || preview.isPending;

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={disabled}
        title={noRules ? t("rulestest.emptyRules") : undefined}
        onClick={() => {
          if (changeId !== null) {
            setTestedInput(currentInput);
            setVerdict(null);
            preview.mutate(
              { id: changeId, rules },
              { onSuccess: (data) => setVerdict({ input: currentInput, data }) },
            );
          }
        }}
      >
        {preview.isPending ? <Spinner /> : <FlaskConical className="h-3.5 w-3.5" />}
        {t("rulestest.action")}
      </Button>
      {changeId === null ? (
        <p className="text-xs text-mist-500">{t("rulestest.noChange")}</p>
      ) : null}
      {result ? (
        <div className="space-y-1.5 rounded-lg border border-line bg-ink-900/50 px-3.5 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={result.significant ? "amber" : "neutral"}>
              {result.significant
                ? t("rulestest.significant")
                : t("rulestest.notSignificant")}
            </Badge>
            <span className="min-w-0 text-sm font-medium text-mist-100">
              {result.headline}
            </span>
          </div>
          <p className="text-sm text-mist-300">{result.summary}</p>
          <p className="text-xs text-mist-500">
            {t("common.model")}: {result.model} · {t("common.cost")}: {formatCost(result.cost_usd)}
          </p>
          <p className="text-xs text-mist-500">{t("rulestest.disclaimer")}</p>
        </div>
      ) : null}
      {error ? <ErrorNote>{error}</ErrorNote> : null}
    </div>
  );
}
