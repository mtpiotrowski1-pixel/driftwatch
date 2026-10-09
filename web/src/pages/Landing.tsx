import * as TabsPrimitive from "@radix-ui/react-tabs";
import {
  ArrowRight,
  Bell,
  CalendarClock,
  Camera,
  Check,
  FolderTree,
  GitCompareArrows,
  Receipt,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { Link } from "@/lib/navigation";

import { useBrand } from "@/branding";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { BrandBackground } from "@/components/brand/BrandBackground";
import { Wordmark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/ui/reveal";
import { useT } from "@/i18n";
import { useAuthCapabilities } from "@/lib/queries";

const STEPS: { titleKey: string; descriptionKey: string; icon: ReactNode }[] = [
  {
    titleKey: "landing.step.capture.title",
    descriptionKey: "landing.step.capture.description",
    icon: <Camera className="h-5 w-5" />,
  },
  {
    titleKey: "landing.step.detect.title",
    descriptionKey: "landing.step.detect.description",
    icon: <GitCompareArrows className="h-5 w-5" />,
  },
  {
    titleKey: "landing.step.notify.title",
    descriptionKey: "landing.step.notify.description",
    icon: <Bell className="h-5 w-5" />,
  },
];

const FEATURES: { titleKey: string; descriptionKey: string; icon: ReactNode }[] = [
  {
    titleKey: "landing.feature.diffing.title",
    descriptionKey: "landing.feature.diffing.description",
    icon: <GitCompareArrows className="h-5 w-5" />,
  },
  {
    titleKey: "landing.feature.significance.title",
    descriptionKey: "landing.feature.significance.description",
    icon: <SlidersHorizontal className="h-5 w-5" />,
  },
  {
    titleKey: "landing.feature.projects.title",
    descriptionKey: "landing.feature.projects.description",
    icon: <FolderTree className="h-5 w-5" />,
  },
  {
    titleKey: "landing.feature.alerts.title",
    descriptionKey: "landing.feature.alerts.description",
    icon: <Users className="h-5 w-5" />,
  },
  {
    titleKey: "landing.feature.scheduling.title",
    descriptionKey: "landing.feature.scheduling.description",
    icon: <CalendarClock className="h-5 w-5" />,
  },
  {
    titleKey: "landing.feature.cost.title",
    descriptionKey: "landing.feature.cost.description",
    icon: <Receipt className="h-5 w-5" />,
  },
];

const TRUST_KEYS = [
  "landing.trust.intel",
  "landing.trust.legal",
  "landing.trust.pricing",
  "landing.trust.stock",
];

const NOISE_KEYS = [
  "landing.noise.trivial1",
  "landing.noise.trivial2",
  "landing.noise.trivial3",
  "landing.noise.trivial4",
];

export function Landing() {
  const reduceMotion = useReducedMotion();
  const t = useT();
  const brand = useBrand();
  const { data: authCapabilities } = useAuthCapabilities();
  const registrationEnabled = authCapabilities?.registration_enabled === true;
  const eyebrow = brand.tagline || t("landing.badge");
  const heroTitle = brand.heroTitle || t("landing.heroTitle");
  const heroSubtitle = brand.heroSubtitle || t("landing.heroSubtitle");
  const footerTagline = brand.tagline || t("landing.footerTagline");

  return (
    <div className="min-h-screen bg-ink-950">
      <header className="focus-on-dark sticky top-0 z-40 border-b border-white/10 bg-[#111511]/95 text-white backdrop-blur-lg">
        <div className="mx-auto flex h-[4.5rem] w-full max-w-[90rem] items-center justify-between gap-4 px-5 sm:px-8">
          <Wordmark className="text-lg !text-white" compactOnNarrow />
          <nav className="hidden items-center gap-7 text-sm text-[#aeb8af] md:flex">
            <a href="#how-it-works" className="transition-colors hover:text-white">
              {t("landing.nav.howItWorks")}
            </a>
            <a href="#features" className="transition-colors hover:text-white">
              {t("landing.nav.features")}
            </a>
            <Link to="/pricing" className="transition-colors hover:text-white">
              {t("common.pricing")}
            </Link>
          </nav>
          <div className="flex items-center gap-2">
            <div className="[&_label]:gap-1 [&_svg]:text-[#d7dfd8]">
              <LanguageSwitcher compact short />
            </div>
            <Button asChild size="sm">
              <Link to="/login">{t("common.signIn")}</Link>
            </Button>
          </div>
        </div>
      </header>

      <main>
        <section className="focus-on-dark relative overflow-hidden bg-[#111511] text-white">
          <BrandBackground variant="hero" eager />
          <div className="relative mx-auto grid min-h-[calc(100svh-8rem)] w-full max-w-[90rem] items-center gap-10 px-5 py-14 sm:px-8 sm:py-20 lg:grid-cols-[minmax(0,1.08fr)_minmax(0,0.92fr)] lg:gap-14">
            <motion.div
              initial={reduceMotion ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reduceMotion ? 0 : 0.38, ease: [0.22, 1, 0.36, 1] }}
              className="dw-art-copy max-w-5xl"
            >
              <p className="flex items-center gap-2 text-xs font-bold uppercase text-brand-300">
                <span className="h-2 w-2 rounded-full bg-brand-500 animate-signal-ping" />
                {eyebrow}
              </p>
              <h1 className="mt-5 text-5xl font-semibold leading-none tracking-tight text-white sm:text-6xl lg:text-7xl">
                {brand.name}
              </h1>
              <p className="mt-5 max-w-4xl text-xl font-medium leading-snug text-[#dce4dd] sm:text-2xl lg:text-3xl">
                {heroTitle}
              </p>
              <p className="mt-4 max-w-2xl text-base leading-relaxed text-on-art-muted sm:text-lg">
                {heroSubtitle}
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <Button size="lg" asChild>
                  <Link to={registrationEnabled ? "/login?mode=register" : "/login"}>
                    {registrationEnabled ? t("landing.startWatching") : t("common.signIn")}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button size="lg" variant="secondary" asChild>
                  <a href="#how-it-works">{t("landing.seeHowItWorks")}</a>
                </Button>
              </div>
            </motion.div>

            <WatchScene />
          </div>
        </section>

        <section className="border-b border-line bg-ink-900">
          <div className="mx-auto flex w-full max-w-[90rem] flex-col gap-4 px-5 py-5 sm:px-8 lg:flex-row lg:items-center lg:justify-between">
            <p className="text-sm font-medium text-mist-400">{t("landing.trust.title")}</p>
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm font-semibold text-mist-300">
              {TRUST_KEYS.map((key) => (
                <span key={key} className="inline-flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent-soft" aria-hidden="true" />
                  {t(key)}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="mx-auto w-full max-w-[90rem] px-5 py-20 sm:px-8 lg:py-28">
          <SectionHeading title={t("landing.howItWorksTitle")} subtitle={t("landing.howItWorksSubtitle")} />
          <div className="mt-12 grid border-y border-line md:grid-cols-3 md:divide-x md:divide-line">
            {STEPS.map((step, index) => (
              <Reveal
                key={step.titleKey}
                className="border-b border-line py-7 md:border-b-0 md:px-7 md:first:pl-0 md:last:pr-0"
              >
                <article>
                  <div className="flex items-center justify-between">
                    <span className="grid h-10 w-10 place-items-center rounded-md bg-[#151915] text-brand-400">
                      {step.icon}
                    </span>
                    <span className="font-mono text-xs text-mist-500">
                      {t("landing.stepLabel", { number: index + 1 })}
                    </span>
                  </div>
                  <h2 className="mt-7 text-xl font-semibold text-mist-100">{t(step.titleKey)}</h2>
                  <p className="mt-2 max-w-sm text-sm leading-relaxed text-mist-400">
                    {t(step.descriptionKey)}
                  </p>
                </article>
              </Reveal>
            ))}
          </div>
        </section>

        <section className="focus-on-dark bg-[#161a16] py-20 text-white lg:py-28">
          <div className="mx-auto grid w-full max-w-[90rem] gap-12 px-5 sm:px-8 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:items-start">
            <SectionHeading
              dark
              title={t("landing.noise.title")}
              subtitle={t("landing.noise.subtitle")}
            />
            <Reveal className="border-y border-white/15">
              <div className="grid gap-0 md:grid-cols-2 md:divide-x md:divide-white/15">
                <div className="py-6 md:pr-7">
                  <p className="text-xs font-bold uppercase text-[#c2cec5]">
                    {t("landing.noise.withoutLabel")}
                  </p>
                  <ul className="mt-5 space-y-3 text-sm text-[#bdc9c0]">
                    {NOISE_KEYS.map((key) => (
                      <li key={key} className="flex items-center gap-3 line-through decoration-[#616a62]">
                        <span className="h-px w-4 bg-[#616a62]" aria-hidden="true" />
                        {t(key)}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="border-t border-white/15 py-6 md:border-t-0 md:pl-7">
                  <p className="text-xs font-bold uppercase text-brand-300">
                    {t("landing.noise.withLabel")}
                  </p>
                  <div className="mt-5 border-l-2 border-brand-500 pl-4">
                    <span className="inline-flex items-center gap-2 text-xs font-semibold text-brand-300">
                      <Check className="h-4 w-4" />
                      {t("landing.noise.signalTag")}
                    </span>
                    <p className="mt-3 text-lg font-semibold leading-snug text-white">
                      {t("landing.noise.signal")}
                    </p>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        <section id="features" className="relative isolate overflow-hidden border-y border-line">
          <BrandBackground variant="ambient" />
          <div className="relative mx-auto w-full max-w-[90rem] px-5 py-20 sm:px-8 lg:py-28">
            <div className="max-w-4xl rounded-xl border border-white/80 bg-white/95 p-6 shadow-card">
              <SectionHeading title={t("landing.featuresTitle")} subtitle={t("landing.featuresSubtitle")} />
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((feature) => (
                <Reveal
                  key={feature.titleKey}
                  className="rounded-xl border border-white/95 bg-white/95 p-6 shadow-card"
                >
                  <article>
                    <span className="text-brand-700">{feature.icon}</span>
                    <h3 className="mt-5 text-lg font-semibold text-mist-100">{t(feature.titleKey)}</h3>
                    <p className="mt-2 max-w-sm text-sm leading-relaxed text-mist-400">
                      {t(feature.descriptionKey)}
                    </p>
                  </article>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="focus-on-dark border-y border-[#2e352f] bg-[#111511] text-white">
          <div className="mx-auto flex w-full max-w-[90rem] flex-col items-start justify-between gap-7 px-5 py-14 sm:px-8 lg:flex-row lg:items-center">
            <h2 className="max-w-2xl text-3xl font-semibold leading-tight sm:text-4xl">
              {t("landing.ctaTitle")}
            </h2>
            <Button size="lg" asChild>
              <Link to={registrationEnabled ? "/login?mode=register" : "/login"}>
                {registrationEnabled ? t("common.getStarted") : t("common.signIn")}
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </section>
      </main>

      <footer className="bg-ink-900">
        <div className="mx-auto flex w-full max-w-[90rem] flex-col items-start justify-between gap-3 px-5 py-8 sm:flex-row sm:items-center sm:px-8">
          <Wordmark />
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-mist-500">
            <p>{footerTagline}</p>
            <a
              href="/driftwatch-source.tar.gz"
              className="font-medium text-mist-300 underline decoration-line-strong underline-offset-4 hover:text-mist-100"
            >
              {t("landing.footerSource")}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

function SectionHeading({
  title,
  subtitle,
  dark = false,
}: {
  title: string;
  subtitle: string;
  dark?: boolean;
}) {
  return (
    <Reveal>
      <h2 className={`max-w-3xl text-3xl font-semibold sm:text-4xl ${dark ? "text-white" : "text-mist-100"}`}>
        {title}
      </h2>
      <p className={`mt-3 max-w-2xl leading-relaxed ${dark ? "text-[#9fa9a1]" : "text-mist-400"}`}>
        {subtitle}
      </p>
    </Reveal>
  );
}

function WatchScene() {
  const t = useT();
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.38, ease: [0.22, 1, 0.36, 1] }}
      className="watch-scene overflow-hidden rounded-2xl border border-white/25 bg-[#10251f]/95 shadow-halo"
    >
      <div className="flex items-center justify-between gap-4 border-b border-white/10 px-4 py-3 sm:px-5">
        <span className="truncate font-mono text-xs text-[#bdc9c0]">competitor.example/pricing</span>
        <span className="inline-flex shrink-0 items-center gap-2 text-xs font-semibold text-brand-300">
          <span className="h-2 w-2 rounded-full bg-brand-500" />
          {t("landing.mock.live")}
        </span>
      </div>
      <div>
        <div className="relative min-h-28 overflow-hidden border-b border-white/10 bg-white/5 px-5 py-5">
          <p className="text-xs font-semibold uppercase text-[#bdc9c0]">
            {t("landing.mock.baseline")}
          </p>
          <div className="relative mt-5 h-10" aria-hidden="true">
            <span className="absolute left-0 right-0 top-2 h-px bg-[#59635b]" />
            <span className="absolute left-0 top-9 h-0.5 w-[43%] bg-brand-400" />
            <span className="absolute left-[43%] top-5 h-4 w-0.5 bg-brand-400" />
            <span className="absolute left-[43%] top-5 h-0.5 w-[10%] -rotate-[24deg] origin-left bg-brand-400" />
            <span className="absolute left-[52%] top-5 h-0.5 w-[10%] rotate-[24deg] origin-right bg-brand-400" />
            <span className="absolute right-0 top-9 h-0.5 w-[39%] bg-brand-400" />
          </div>
        </div>
        <div className="p-3 sm:p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold text-white">{t("landing.mock.verdict")}</span>
            <span className="hidden text-xs text-[#bdc9c0] min-[360px]:inline">
              {t("landing.mock.caption")}
            </span>
          </div>
          <TabsPrimitive.Root defaultValue="compare">
            <TabsPrimitive.List
              aria-label={t("landing.mock.views")}
              className="mb-3 flex w-fit max-w-full flex-wrap gap-1 rounded-md border border-white/15 p-1"
            >
              {[
                ["compare", "landing.mock.compareTab"],
                ["before", "landing.mock.beforeTab"],
                ["after", "landing.mock.afterTab"],
              ].map(([value, label]) => (
                <TabsPrimitive.Trigger
                  key={value}
                  value={value}
                  className="dw-button min-h-8 rounded px-2.5 py-1.5 text-xs font-semibold text-[#adb8af] hover:bg-white/10 hover:text-white data-[state=active]:bg-brand-500 data-[state=active]:text-[#151915]"
                >
                  {t(label)}
                </TabsPrimitive.Trigger>
              ))}
            </TabsPrimitive.List>
            <TabsPrimitive.Content value="compare" className="dw-demo-panel diff min-h-[5.25rem] text-xs">
              <div className="diff-line diff-context hidden sm:block">{t("landing.mock.plan")}</div>
              <div className="diff-line diff-removed">{t("landing.mock.before")}</div>
              <div className="diff-line diff-added">{t("landing.mock.after")}</div>
              <div className="diff-line diff-context hidden sm:block">{t("landing.mock.billing")}</div>
            </TabsPrimitive.Content>
            <TabsPrimitive.Content value="before" className="dw-demo-panel diff min-h-[5.25rem] text-xs">
              <div className="diff-line diff-context">{t("landing.mock.plan")}</div>
              <div className="diff-line">{t("landing.mock.beforePrice")}</div>
              <div className="diff-line diff-context">{t("landing.mock.billing")}</div>
            </TabsPrimitive.Content>
            <TabsPrimitive.Content value="after" className="dw-demo-panel diff min-h-[5.25rem] text-xs">
              <div className="diff-line diff-context">{t("landing.mock.plan")}</div>
              <div className="diff-line">{t("landing.mock.afterPrice")}</div>
              <div className="diff-line diff-context">{t("landing.mock.billing")}</div>
            </TabsPrimitive.Content>
          </TabsPrimitive.Root>
        </div>
      </div>
    </motion.div>
  );
}
