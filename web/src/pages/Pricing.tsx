import { ArrowLeft, Gauge, LockKeyhole, UsersRound } from "lucide-react";
import { Link } from "@/lib/navigation";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { Wordmark } from "@/components/brand/Logo";
import { BrandBackground } from "@/components/brand/BrandBackground";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { useAuthCapabilities } from "@/lib/queries";

export function Pricing() {
  const t = useT();
  const { data: authCapabilities } = useAuthCapabilities();
  const registrationEnabled = authCapabilities?.registration_enabled === true;
  const initialSetup = registrationEnabled && authCapabilities?.initial_setup_required === true;

  return (
    <div className="min-h-screen bg-ink-950">
      <header className="border-b border-white/10 bg-[#111511] text-white">
        <div className="mx-auto flex h-[4.5rem] w-full max-w-[90rem] items-center justify-between gap-4 px-5 sm:px-8">
          <Link to="/" className="rounded-md" aria-label={t("plans.public.backHome")}>
            <Wordmark className="text-lg !text-white" compactOnNarrow />
          </Link>
          <div className="flex items-center gap-2">
            <div className="[&_label]:gap-1 [&_label]:text-[#d7dfd8] [&_svg]:text-[#d7dfd8]">
              <LanguageSwitcher compact short />
            </div>
            <Button asChild size="sm">
              <Link to="/login">{t("common.signIn")}</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="relative isolate">
        <BrandBackground variant="ambient" />
        <section className="relative isolate overflow-hidden border-b border-[#303730] bg-[#111511] text-white">
          <BrandBackground variant="hero" eager />
          <div className="relative mx-auto w-full max-w-[90rem] animate-fade-rise px-5 py-12 sm:px-8 sm:py-16">
            <div className="dw-art-copy max-w-4xl">
              <p className="text-xs font-bold uppercase text-brand-300">
                {t(initialSetup ? "plans.public.setupEyebrow" : "plans.public.eyebrow")}
              </p>
              <h1 className="mt-4 max-w-4xl text-4xl font-semibold leading-tight text-white sm:text-5xl">
                {t(initialSetup ? "plans.public.setupTitle" : registrationEnabled ? "plans.public.title" : "plans.public.closedTitle")}
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-on-art-muted sm:text-lg">
                {t(initialSetup ? "plans.public.setupSubtitle" : registrationEnabled ? "plans.public.subtitle" : "plans.public.closedSubtitle")}
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                <Button asChild size="lg">
                  <Link to={registrationEnabled ? "/login?mode=register" : "/login"}>
                    {t(initialSetup ? "login.createAdministrator" : registrationEnabled ? "plans.public.cta" : "common.signIn")}
                  </Link>
                </Button>
                <Button
                  asChild
                  size="lg"
                  variant="ghost"
                  className="text-[#d7dfd8] hover:bg-white/10 hover:text-white"
                >
                  <Link to="/">
                    <ArrowLeft className="h-4 w-4" />
                    {t("plans.public.backHome")}
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </section>

        <section
          aria-labelledby="public-access-status"
          className={`relative mx-auto grid w-full gap-10 px-5 py-12 sm:px-8 sm:py-16 ${registrationEnabled && !initialSetup
              ? "max-w-[90rem] lg:grid-cols-[minmax(0,1fr)_minmax(20rem,0.7fr)] lg:items-center"
              : "max-w-4xl"
            }`}
        >
          <div className="max-w-2xl rounded-xl border border-white/80 bg-white/95 p-6 shadow-card">
            <LockKeyhole className="h-7 w-7 text-brand-700" aria-hidden="true" />
            <h2 id="public-access-status" className="mt-5 text-2xl font-semibold text-mist-100">
              {t(
                initialSetup
                  ? "plans.public.setupStatusTitle"
                  : registrationEnabled
                    ? "plans.public.statusTitle"
                    : "plans.public.closedStatusTitle",
              )}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-mist-400 sm:text-base">
              {t(
                initialSetup
                  ? "login.initialSetupNotice"
                  : registrationEnabled
                    ? "plans.public.statusBody"
                    : "plans.public.closedStatusBody",
              )}
            </p>
            <p className="mt-5 border-l-2 border-brand-500 pl-4 text-sm leading-relaxed text-mist-300">
              {t(
                initialSetup
                  ? "plans.public.setupNote"
                  : registrationEnabled
                    ? "plans.public.manualNote"
                    : "plans.public.closedManualNote",
              )}
            </p>
          </div>

          {registrationEnabled && !initialSetup ? (
            <dl className="glass grid grid-cols-3 rounded-xl !bg-white/95">
              <div className="border-r border-line px-4 py-6 sm:px-6">
                <dt className="flex min-h-10 items-start gap-2 text-xs leading-5 text-mist-500">
                  <Gauge className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  {t("plans.public.defaultSites")}
                </dt>
                <dd className="mt-3 text-3xl font-semibold tabular-nums text-mist-100">1</dd>
              </div>
              <div className="border-r border-line px-4 py-6 sm:px-6">
                <dt className="flex min-h-10 items-start gap-2 text-xs leading-5 text-mist-500">
                  <UsersRound className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  {t("plans.public.defaultMembers")}
                </dt>
                <dd className="mt-3 text-3xl font-semibold tabular-nums text-mist-100">1</dd>
              </div>
              <div className="px-4 py-6 sm:px-6">
                <dt className="flex min-h-10 items-start gap-2 text-xs leading-5 text-mist-500">
                  <Gauge className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  {t("plans.public.defaultAi")}
                </dt>
                <dd className="mt-3 text-3xl font-semibold tabular-nums text-mist-100">0</dd>
              </div>
            </dl>
          ) : null}
        </section>
      </main>
    </div>
  );
}
