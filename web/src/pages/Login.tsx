import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useSearchParams, type Location } from "react-router-dom";
import { Link, useNavigate } from "@/lib/navigation";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { BrandBackground } from "@/components/brand/BrandBackground";
import { Wordmark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { ErrorNote } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { useT } from "@/i18n";
import { errorMessage } from "@/lib/errors";
import { ApiError } from "@/lib/api";
import { authenticatedDestination } from "@/lib/authRouting";
import { useOrg } from "@/lib/orgContext";
import {
  useCurrentUser,
  useAuthCapabilities,
  useLogin,
  useLoginTotp,
  useRegister,
} from "@/lib/queries";
import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

type Mode = "signin" | "register";

export function Login() {
  const t = useT();
  const navigate = useNavigate();
  const location = useLocation();
  const { enterOrg } = useOrg();
  const [searchParams] = useSearchParams();
  // Where RequireAuth sent us from — return there after signing in (an email
  // deep link keeps its ?change= query), falling back to the dashboard.
  const from = (location.state as { from?: Location; } | null)?.from;
  const requestedDestination = from
    ? `${from.pathname}${from.search}${from.hash}`
    : "/dashboard";
  const { data: user } = useCurrentUser();
  const { data: authCapabilities } = useAuthCapabilities();
  const registrationEnabled = authCapabilities?.registration_enabled === true;
  const initialSetup = registrationEnabled && authCapabilities?.initial_setup_required === true;
  const login = useLogin();
  const loginTotp = useLoginTotp();
  const register = useRegister();

  // Public account-creation links may select the form, but URL parameters never
  // select or grant an entitlement.
  const requestedMode = searchParams.get("mode");
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  // Set once the password is accepted but a TOTP code is still required.
  const [awaitingCode, setAwaitingCode] = useState(false);
  const [code, setCode] = useState("");
  const [setupRouting, setSetupRouting] = useState(false);
  const [setupAccount, setSetupAccount] = useState<User | null>(null);
  const [openingWorkspace, setOpeningWorkspace] = useState(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);

  useEffect(() => {
    if (user && !setupRouting) navigate(authenticatedDestination(user, requestedDestination), { replace: true });
  }, [user, navigate, requestedDestination, setupRouting]);

  useEffect(() => {
    if (!registrationEnabled) {
      setMode("signin");
    } else if (requestedMode === "register" || (initialSetup && requestedMode !== "signin")) {
      setMode("register");
    }
  }, [initialSetup, registrationEnabled, requestedMode]);

  const mutation = mode === "signin" ? login : register;
  const mutationError = awaitingCode ? loginTotp.error : mutation.error;
  const error = workspaceError ?? (mutationError ? errorMessage(mutationError, t) : null);
  const setupCopy = setupAccount !== null || (mode === "register" && initialSetup);
  const titleKey = setupCopy
    ? "login.initialSetupTitle"
    : mode === "signin" ? "login.signinTitle" : "login.registerTitle";
  const subtitleKey = setupCopy
    ? "login.initialSetupSubtitle"
    : mode === "signin" ? "login.signinSubtitle" : "login.registerSubtitle";
  const createAccountLabel = t(initialSetup ? "login.createAdministrator" : "login.createAccount");

  async function openInitialWorkspace(account: User) {
    setOpeningWorkspace(true);
    setWorkspaceError(null);
    try {
      if (!account.is_superadmin || !account.organization_id) {
        throw new Error(t("login.initialWorkspaceFailed"));
      }
      // Use the normal server-confirmed organization transition. It binds the
      // real session and clears context-sensitive queries before any tenant UI.
      const confirmed = await enterOrg({
        id: account.organization_id,
        name: company.trim() || t("login.workspacePlaceholder"),
      });
      navigate(authenticatedDestination(confirmed, "/dashboard"), { replace: true });
    } catch (failure) {
      setWorkspaceError(errorMessage(failure, t));
    } finally {
      setOpeningWorkspace(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setWorkspaceError(null);
    const goHome = (authenticatedUser?: User | null) =>
      navigate(
        authenticatedUser
          ? authenticatedDestination(authenticatedUser, requestedDestination)
          : requestedDestination,
        { replace: true },
      );
    if (mode === "register") {
      if (initialSetup) setSetupRouting(true);
      register.mutate(
        {
          email,
          password,
          name: name.trim() || undefined,
          organization_name: company.trim() || undefined,
        },
        {
          onSuccess: (registeredUser) => {
            if (initialSetup) {
              setSetupAccount(registeredUser);
              void openInitialWorkspace(registeredUser);
            } else {
              goHome(registeredUser);
            }
          },
          ...(initialSetup ? {
            onError: (failure: unknown) => {
              setSetupRouting(false);
              if (failure instanceof ApiError && failure.status === 403) {
                setWorkspaceError(errorMessage(failure, t));
              }
            },
          } : {}),
        },
      );
      return;
    }
    if (awaitingCode) {
      loginTotp.mutate(code.trim(), { onSuccess: (verifiedUser) => goHome(verifiedUser) });
      return;
    }
    login.mutate(
      { email, password },
      {
        onSuccess: (result) => {
          if (result.totp_required) setAwaitingCode(true);
          else goHome(result.user);
        },
      },
    );
  }

  function switchMode(value: Mode) {
    setMode(value);
    setAwaitingCode(false);
    setCode("");
  }

  return (
    <div className="grid min-h-screen bg-ink-950 lg:grid-cols-[minmax(0,1.05fr)_minmax(28rem,0.95fr)]">
      <aside className="focus-on-dark relative hidden min-h-screen flex-col overflow-hidden bg-[#141814] p-10 text-white lg:flex xl:p-14">
        <BrandBackground variant="dark" eager />
        <Wordmark className="relative z-10 text-xl !text-white" />
        <div className="dw-art-copy relative z-10 my-auto max-w-xl">
          <p className="text-xs font-bold uppercase text-brand-300">{t("landing.mock.verdict")}</p>
          <p className="mt-5 text-4xl font-semibold leading-tight text-white">
            {t("landing.noise.signal")}
          </p>
          <div className="mt-10 border-y border-white/15 py-6">
            <div className="relative h-16" aria-hidden="true">
              <span className="absolute left-0 right-0 top-3 h-px bg-[#535d55]" />
              <span className="absolute left-0 top-11 h-0.5 w-[46%] bg-brand-400" />
              <span className="absolute left-[46%] top-7 h-4 w-0.5 bg-brand-400" />
              <span className="absolute left-[46%] top-7 h-0.5 w-[9%] -rotate-[28deg] origin-left bg-brand-400" />
              <span className="absolute left-[54%] top-7 h-0.5 w-[9%] rotate-[28deg] origin-right bg-brand-400" />
              <span className="absolute right-0 top-11 h-0.5 w-[38%] bg-brand-400" />
            </div>
            <div className="diff mt-3 text-xs">
              <div className="diff-line diff-removed">{t("landing.mock.before")}</div>
              <div className="diff-line diff-added">{t("landing.mock.after")}</div>
            </div>
          </div>
        </div>
        <p className="dw-art-copy relative z-10 text-sm text-on-art-muted">{t("landing.footerTagline")}</p>
      </aside>

      <main className="relative isolate flex min-h-screen items-center justify-center overflow-hidden px-5 pb-10 pt-24 sm:px-8 lg:py-12">
        <BrandBackground variant="ambient" eager />
        <div className="absolute inset-x-5 top-5 z-10 flex items-center justify-between sm:inset-x-8 lg:justify-end">
          <Link to="/" className="dw-auth-brand lg:hidden">
            <Wordmark className="text-lg" />
          </Link>
          <LanguageSwitcher compact short />
        </div>

        <section className="dw-auth-card relative w-full max-w-md animate-fade-rise">
          <div className="mb-7">
            <h1 className="text-3xl font-semibold text-mist-100">
              {t(titleKey)}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-mist-400">
              {t(subtitleKey)}
            </p>
          </div>

          <div className="border-t border-line pt-6">
            {setupAccount ? (
              <div className="space-y-4">
                <p className="text-sm text-mist-300">{t("login.administratorCreated")}</p>
                {workspaceError ? <ErrorNote>{workspaceError}</ErrorNote> : null}
                <Button className="w-full" disabled={openingWorkspace} onClick={() => void openInitialWorkspace(setupAccount)}>
                  {t(openingWorkspace ? "login.openingWorkspace" : "login.openWorkspace")}
                </Button>
              </div>
            ) : (
              <>
                {registrationEnabled ? (
                  <div
                    className="mb-6 grid grid-cols-2 gap-1 rounded-md border border-line bg-ink-800 p-1"
                    role="group"
                    aria-label={t("login.modeLabel")}
                  >
                    {(["signin", "register"] as const).map((value) => (
                      <button
                        key={value}
                        type="button"
                        disabled={mutation.isPending}
                        aria-pressed={mode === value}
                        onClick={() => switchMode(value)}
                        className={cn(
                          "min-h-10 rounded-lg px-3 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
                          mode === value
                            ? "bg-ink-900 text-mist-100 shadow-sm"
                            : "text-mist-400 hover:text-mist-100",
                        )}
                      >
                        {value === "signin" ? t("common.signIn") : initialSetup ? t("login.initialSetupTab") : createAccountLabel}
                      </button>
                    ))}
                  </div>
                ) : null}

                {awaitingCode ? (
                  <form onSubmit={handleSubmit} className="space-y-4">
                    <p className="text-sm text-mist-400">{t("twofa.login.prompt")}</p>
                    <Field label={t("twofa.login.codeLabel")} hint={t("twofa.login.codeHint")} htmlFor="code">
                      <Input
                        id="code"
                        inputMode="text"
                        autoComplete="one-time-code"
                        autoFocus
                        required
                        value={code}
                        onChange={(event) => setCode(event.target.value)}
                        placeholder="123456"
                      />
                    </Field>
                    {error ? <ErrorNote>{error}</ErrorNote> : null}
                    <Button type="submit" size="lg" className="w-full" disabled={loginTotp.isPending}>
                      {t("twofa.login.verify")}
                    </Button>
                    <button
                      type="button"
                      onClick={() => switchMode("signin")}
                      className="w-full text-center text-xs text-mist-500 hover:text-mist-300"
                    >
                      {t("twofa.login.useAnotherAccount")}
                    </button>
                  </form>
                ) : (
                  <form onSubmit={handleSubmit} className="space-y-4">
                    {mode === "register" ? (
                      <div className="rounded-lg border border-brand-600/30 bg-brand-300/30 px-4 py-3 text-sm text-mist-200">
                        {t(initialSetup ? "login.initialSetupNotice" : "login.signupEntitlement")}
                      </div>
                    ) : null}

                    {mode === "register" ? (
                      <Field label={t(initialSetup ? "login.workspaceLabel" : "login.companyLabel")} hint={t(initialSetup ? "login.workspaceHint" : "login.companyHint")} htmlFor="company">
                        <Input
                          id="company"
                          value={company}
                          onChange={(event) => setCompany(event.target.value)}
                          placeholder={t(initialSetup ? "login.workspacePlaceholder" : "login.companyPlaceholder")}
                          autoComplete="organization"
                        />
                      </Field>
                    ) : null}

                    {mode === "register" ? (
                      <Field label={t("login.nameLabel")} hint={t("login.nameHint")} htmlFor="name">
                        <Input
                          id="name"
                          value={name}
                          onChange={(event) => setName(event.target.value)}
                          placeholder={t("login.namePlaceholder")}
                          autoComplete="name"
                        />
                      </Field>
                    ) : null}

                    <Field label={t("login.emailLabel")} htmlFor="email">
                      <Input
                        id="email"
                        type="email"
                        required
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        placeholder={t("login.emailPlaceholder")}
                        autoComplete="email"
                      />
                    </Field>

                    <Field label={t("login.passwordLabel")} htmlFor="password">
                      <Input
                        id="password"
                        type="password"
                        required
                        minLength={mode === "register" ? 8 : undefined}
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        placeholder={
                          mode === "register"
                            ? t("login.passwordPlaceholderRegister")
                            : t("login.passwordPlaceholderSignIn")
                        }
                        autoComplete={mode === "register" ? "new-password" : "current-password"}
                      />
                    </Field>

                    {error ? <ErrorNote>{error}</ErrorNote> : null}

                    <Button type="submit" size="lg" className="w-full px-3" disabled={mutation.isPending}>
                      {mode === "signin" ? t("common.signIn") : createAccountLabel}
                    </Button>

                    {mode === "signin" ? (
                      <Link
                        to="/forgot-password"
                        className="block text-center text-xs text-mist-500 hover:text-mist-300"
                      >
                        {t("login.forgotPassword")}
                      </Link>
                    ) : null}
                  </form>
                )}
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
