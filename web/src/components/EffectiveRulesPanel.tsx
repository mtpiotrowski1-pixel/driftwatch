import { Badge } from "@/components/ui/badge";
import { Collapsible } from "@/components/ui/collapsible";
import { useT } from "@/i18n";
import type { EffectiveRules } from "@/lib/types";

/** Read-only, collapsed view of the importance rules currently in effect for
 * the surrounding scope, with a badge naming the inheritance level that
 * supplies them — so an editor knows what a blank rules field falls back to. */
export function EffectiveRulesPanel({ rules }: { rules: EffectiveRules | undefined }) {
  const t = useT();
  if (!rules) return null;
  const overridden = rules.source === "site" || rules.source === "project";
  return (
    <Collapsible label={t("effective.title")}>
      <div className="space-y-2 rounded-lg border border-line bg-ink-900/50 px-3.5 py-3">
        <Badge tone={overridden ? "brand" : "neutral"}>
          {t(`effective.source.${rules.source}`)}
        </Badge>
        <p className="whitespace-pre-wrap text-xs leading-relaxed text-mist-400">{rules.text}</p>
      </div>
    </Collapsible>
  );
}
