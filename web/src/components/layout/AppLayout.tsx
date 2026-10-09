import { LogOut, ShieldAlert } from "lucide-react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { NavLink, useNavigate } from "@/lib/navigation";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { BrandBackground } from "@/components/brand/BrandBackground";
import { Wordmark } from "@/components/brand/Logo";
import { SupportAccessBanner } from "@/components/support/SupportAccessBanner";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { errorMessage } from "@/lib/errors";
import { canCreateSite } from "@/lib/capabilities";
import { useT } from "@/i18n";
import { ApiError, RequestContextChangedError } from "@/lib/api";
import { OrganizationTransitionCancelledError, useInOrgContext, useOrg } from "@/lib/orgContext";
import { useCurrentUser, useLogout } from "@/lib/queries";
import { cn } from "@/lib/utils";

import { MobileNav } from "./MobileNav";
import { isInstanceOnlyOperatorNavPath, visibleNavItems, type NavItem } from "./nav";

export function AppLayout() {
  const { data: user } = useCurrentUser();
  const { actingOrg, exitOrg } = useOrg();
  const inOrgContext = useInOrgContext();
  const logout = useLogout();
  const navigate = useNavigate();
  const location = useLocation();
  const t = useT();
  const { notify } = useToast();

  const items = visibleNavItems(user, actingOrg !== null)
    .filter((item) => item.to !== "/sites/new" || (inOrgContext && canCreateSite(user)))
    .filter((item) => !user?.mfa_enrollment_required || item.to === "/settings");
  const addSiteItem = items.find((item) => item.to === "/sites/new");
  const mainItems = items.filter((item) => item.group !== "operator" && item.to !== "/sites/new");
  const operatorItems = items.filter((item) => item.group === "operator");
  const homePath = user?.is_superadmin && !actingOrg ? "/operations" : "/dashboard";

  if (actingOrg && isInstanceOnlyOperatorNavPath(location.pathname)) {
    return <Navigate to="/dashboard" replace />;
  }

  async function handleLogout() {
    try {
      await logout.mutateAsync();
      navigate("/login");
    } catch (error) {
      notify(errorMessage(error, t), "error");
    }
  }

  async function handleExitOrganization() {
    if (!actingOrg) return;
    try {
      await exitOrg(actingOrg.id);
    } catch (error) {
      if (error instanceof OrganizationTransitionCancelledError) return;
      notify(
        error instanceof RequestContextChangedError
          ? t("common.contextChanged")
          : error instanceof ApiError
            ? error.message
            : t("common.requestFailed"),
        "error",
      );
    }
  }

  const renderLink = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.to === "/sites/new"}
      className={({ isActive }) =>
        cn(
          "dw-nav-link flex min-h-10 items-center gap-3 rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
          isActive
            ? "bg-brand-500 text-[#151915]"
            : "text-[#cbd4cc] hover:bg-[#252b25] hover:text-white",
        )
      }
    >
      {item.icon}
      {t(item.labelKey)}
    </NavLink>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-brand-500 focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-[#151915]"
      >
        {t("common.skipToContent")}
      </a>

      <aside className="dw-sidebar focus-on-dark sticky top-0 isolate hidden h-screen flex-col overflow-hidden border-r border-[#2b322c] bg-[#141814] p-4 lg:flex">
        <BrandBackground variant="dark" className="dw-sidebar-art" />
        <NavLink to={homePath} className="mb-6 rounded-lg px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus">
          <Wordmark className="text-lg !text-white" />
        </NavLink>
        {addSiteItem ? (
          <Button asChild className="mb-5 w-full justify-start shadow-none">
            <NavLink to={addSiteItem.to}>
              {addSiteItem.icon}
              {t(addSiteItem.labelKey)}
            </NavLink>
          </Button>
        ) : null}
        <nav className="dw-sidebar-nav flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
          {mainItems.map(renderLink)}
          {operatorItems.length > 0 ? (
            <>
              <p className="mt-5 px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-on-art-muted">
                {t("nav.operatorSection")}
              </p>
              {operatorItems.map(renderLink)}
            </>
          ) : null}
        </nav>
        <div className="dw-sidebar-account mt-4 space-y-3 border border-white/10">
          <div className="flex items-center gap-3 px-1">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-500 text-sm font-bold text-[#151915]">
              {(user?.name ?? user?.email ?? "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-white">
                {user?.name ?? t("common.member")}
              </p>
              <p className="truncate text-xs text-on-art-muted">{user?.email}</p>
            </div>
          </div>
          <LanguageSwitcher compact />
          <Button variant="ghost" size="sm" className="w-full justify-start !text-[#cbd4cc] hover:!bg-[#252b25] hover:!text-white" onClick={handleLogout}>
            <LogOut className="h-4 w-4" aria-hidden="true" />
            {t("common.signOut")}
          </Button>
        </div>
      </aside>

      <MobileNav
        items={items}
        userName={user?.name ?? t("common.member")}
        userEmail={user?.email}
        onLogout={handleLogout}
      />

      <main id="main-content" className="dw-workspace relative min-h-screen border-t-[3px] border-brand-500 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <BrandBackground variant="ambient" className="dw-workspace-art" eager />
        <div className="dw-workspace-content relative mx-auto w-full max-w-[90rem] animate-fade-rise">
          {actingOrg && !user?.mfa_enrollment_required ? (
            <SupportAccessBanner
              organizationId={actingOrg.id}
              organizationName={actingOrg.name}
              onExit={handleExitOrganization}
            />
          ) : null}
          {user?.mfa_enrollment_required ? (
            <NavLink
              to="/settings"
              className="mb-6 flex items-center gap-3 rounded-lg border border-amber-400/30 bg-ink-900 px-4 py-3 text-sm text-amber-400 transition-colors hover:bg-ink-850 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            >
              <ShieldAlert className="h-4 w-4 shrink-0" />
              <span className="flex-1">{t("twofa.nudge.required")}</span>
              <span className="shrink-0 font-medium underline">{t("twofa.nudge.action")}</span>
            </NavLink>
          ) : null}
          <Outlet key={`${user?.id ?? "anonymous"}:${actingOrg?.id ?? user?.organization_id ?? "instance"}`} />
        </div>
      </main>
    </div>
  );
}
