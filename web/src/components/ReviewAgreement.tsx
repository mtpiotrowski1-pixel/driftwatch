import { ErrorState, Spinner } from "@/components/ui/feedback";
import { useT } from "@/i18n";
import { useVerdictSummary } from "@/lib/queries";

/** Human labels cover detected events only; they cannot establish recall. */
export function ReviewAgreement() {
  const t = useT();
  const verdicts = useVerdictSummary();

  return (
    <div className="border-t border-line pt-4">
      <p className="text-sm font-medium text-mist-200">{t("common.reviewAgreement")}</p>
      {verdicts.isLoading ? (
        <Spinner />
      ) : verdicts.isError ? (
        <ErrorState onRetry={() => void verdicts.refetch()} />
      ) : verdicts.data ? (
        <p className="mt-1 text-sm text-mist-300">
          {verdicts.data.reviewed > 0
            ? `${Math.round(verdicts.data.agreement_rate * 100)}% (${verdicts.data.agreed}/${verdicts.data.reviewed})`
            : t("common.noReviews")}
        </p>
      ) : null}
      <p className="mt-1 text-xs text-mist-500">{t("common.reviewAgreementLimit")}</p>
    </div>
  );
}
