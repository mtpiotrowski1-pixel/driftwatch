import {
  ArrowRight,
  Check,
  ChevronDown,
  Globe2,
  MailCheck,
  Play,
  ScanSearch,
  UserRoundPlus,
} from "lucide-react";
import { useId, useState, type ComponentType, type SVGProps } from "react";
import { Link } from "@/lib/navigation";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/feedback";
import { useToast } from "@/components/ui/toast";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api";
import {
  useCheckSite,
  useNotifications,
  useProjects,
  useRecipients,
} from "@/lib/queries";
import type { Notification, Project, Recipient, Site } from "@/lib/types";
import { cn } from "@/lib/utils";

interface OnboardingProgressProps {
  sites: Site[];
}

interface OnboardingSignals {
  hasSite: boolean;
  hasBaseline: boolean;
  hasRecipient: boolean;
  hasDelivery: boolean;
}

type StepKey = keyof OnboardingSignals;
type StepIcon = ComponentType<SVGProps<SVGSVGElement>>;

const STEP_DEFINITIONS: Array<{ key: StepKey; icon: StepIcon }> = [
  { key: "hasSite", icon: Globe2 },
  { key: "hasBaseline", icon: ScanSearch },
  { key: "hasRecipient", icon: UserRoundPlus },
  { key: "hasDelivery", icon: MailCheck },
];

export function deriveOnboardingSignals(
  sites: Site[],
  recipients: Recipient[],
  projects: Project[],
  sentNotifications: Notification[],
): OnboardingSignals {
  const activeRecipientIds = new Set(
    recipients.filter((recipient) => recipient.active).map((recipient) => recipient.id),
  );
  const projectById = new Map(projects.map((project) => [project.id, project]));
  const hasConfiguredDelivery = sites.some((site) => {
    const direct = site.recipient_ids.some((id) => activeRecipientIds.has(id));
    const project = site.project_id == null ? undefined : projectById.get(site.project_id);
    const inherited = project?.recipient_ids.some((id) => activeRecipientIds.has(id)) ?? false;
    return direct || inherited;
  });

  return {
    hasSite: sites.length > 0,
    hasBaseline: sites.some((site) => site.last_checked_at !== null),
    hasRecipient: activeRecipientIds.size > 0,
    hasDelivery: hasConfiguredDelivery || sentNotifications.length > 0,
  };
}

export function OnboardingProgress({ sites }: OnboardingProgressProps) {
  const t = useT();
  const { notify } = useToast();
  const recipients = useRecipients();
  const projects = useProjects();
  const sentNotifications = useNotifications("sent");
  const check = useCheckSite();
  const [open, setOpen] = useState(true);
  const panelId = useId();

  if (recipients.isLoading || projects.isLoading || sentNotifications.isLoading) return null;
  // Onboarding is secondary to the operational dashboard. A supporting query
  // failure must not block or replace the user's primary workspace.
  if (recipients.isError || projects.isError || sentNotifications.isError) return null;

  const signals = deriveOnboardingSignals(
    sites,
    recipients.data ?? [],
    projects.data ?? [],
    sentNotifications.data?.pages.flat() ?? [],
  );
  const steps = STEP_DEFINITIONS.map((definition) => ({
    ...definition,
    complete: signals[definition.key],
  }));
  const completed = steps.filter((step) => step.complete).length;
  const currentIndex = steps.findIndex((step) => !step.complete);
  const checkTarget =
    sites.find((site) => site.last_checked_at === null && site.enabled) ??
    sites.find((site) => site.last_checked_at === null) ??
    sites[0];
  const deliveryTarget =
    sites.find((site) => site.last_checked_at !== null && site.enabled) ??
    sites.find((site) => site.enabled) ??
    sites[0];

  if (completed === steps.length) return null;

  async function runFirstCheck() {
    if (!checkTarget) return;
    try {
      const result = await check.mutateAsync({ id: checkTarget.id });
      if (result.capture_error) {
        notify(result.capture_error, "error");
        return;
      }
      notify(t("onboarding.checkComplete"));
    } catch (error) {
      notify(error instanceof ApiError ? error.message : t("common.errorTitle"), "error");
    }
  }

  function stepAction(key: StepKey) {
    if (key === "hasSite") {
      return (
        <Button asChild size="sm" className="mt-3 rounded-md">
          <Link to="/sites/new">
            {t("onboarding.hasSite.action")}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      );
    }
    if (key === "hasBaseline" && checkTarget) {
      return (
        <Button
          size="sm"
          className="mt-3 rounded-md"
          onClick={() => void runFirstCheck()}
          disabled={check.isPending}
        >
          {check.isPending ? <Spinner /> : <Play className="h-3.5 w-3.5" />}
          {t("onboarding.hasBaseline.action")}
        </Button>
      );
    }
    if (key === "hasRecipient") {
      return (
        <Button asChild size="sm" className="mt-3 rounded-md">
          <Link to="/recipients">
            {t("onboarding.hasRecipient.action")}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      );
    }
    if (key === "hasDelivery" && deliveryTarget) {
      return (
        <Button asChild size="sm" className="mt-3 rounded-md">
          <Link to={`/sites/${deliveryTarget.id}`}>
            {t("onboarding.hasDelivery.action")}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      );
    }
    return null;
  }

  return (
    <section className="overflow-hidden rounded-lg border border-line-strong bg-ink-900 shadow-card">
      <div className="flex items-center gap-3 bg-ink-850 px-4 py-3.5 sm:px-5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 className="text-base font-semibold text-mist-100">{t("onboarding.title")}</h2>
            <span className="text-xs tabular-nums text-mist-500">
              {t("onboarding.progress", { completed, total: steps.length })}
            </span>
          </div>
          <p className="mt-0.5 truncate text-xs text-mist-400">
            {t(`onboarding.${steps[currentIndex].key}.next`)}
          </p>
        </div>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          aria-label={open ? t("onboarding.collapse") : t("onboarding.expand")}
          title={open ? t("onboarding.collapse") : t("onboarding.expand")}
          onClick={() => setOpen((value) => !value)}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-md text-mist-400 transition-colors hover:bg-ink-800 hover:text-mist-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <ChevronDown
            className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
          />
        </button>
      </div>
      <div
        className="h-1 bg-ink-800"
        role="progressbar"
        aria-label={t("onboarding.progressLabel")}
        aria-valuemin={0}
        aria-valuemax={steps.length}
        aria-valuenow={completed}
      >
        <div
          className="h-full bg-brand-500 transition-[width] duration-300"
          style={{ width: `${(completed / steps.length) * 100}%` }}
        />
      </div>
      <ol id={panelId} hidden={!open} className="grid border-t border-line-strong lg:grid-cols-4">
        {steps.map((step, index) => {
          const Icon = step.icon;
          const current = index === currentIndex;
          return (
            <li
              key={step.key}
              aria-current={current ? "step" : undefined}
              className={cn(
                "flex gap-3 border-t border-line-strong px-4 py-4 first:border-t-0 lg:min-h-40 lg:border-l lg:border-t-0 lg:first:border-l-0",
                current && "bg-brand-500/10 shadow-[inset_0_3px_0_var(--color-brand-700)]",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full border",
                  step.complete
                    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-400"
                    : current
                      ? "border-brand-500/40 bg-brand-500/10 text-brand-700"
                      : "border-line bg-ink-850 text-mist-500",
                )}
              >
                {step.complete ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
              </span>
              <div className="min-w-0 flex-1">
                <span className="font-mono text-[11px] text-mist-500">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-1 text-sm font-semibold text-mist-100">
                  {t(`onboarding.${step.key}.title`)}
                </h3>
                <p
                  className={cn(
                    "mt-1 text-xs leading-relaxed text-mist-400",
                    !current && "hidden lg:block",
                  )}
                >
                  {t(`onboarding.${step.key}.description`)}
                </p>
                {current ? stepAction(step.key) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
