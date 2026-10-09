import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, RouterProvider, createBrowserRouter, useLocation } from "react-router-dom";

import { BrandingProvider } from "./branding";
import { ApplicationErrorScreen, ErrorBoundary } from "./components/ErrorBoundary";
import { AppLayout } from "./components/layout/AppLayout";
import { ErrorState, PageLoader } from "./components/ui/feedback";
import { ToastProvider } from "./components/ui/toast";
import { I18nProvider, useT } from "./i18n";
import { requiredAuthenticatedRoute } from "./lib/authRouting";
import { OrgProvider } from "./lib/orgContext";
import { useCurrentUser } from "./lib/queries";
import { routerWindow } from "./lib/routerWindow";
import { ThemeProvider } from "./theme";

const AddSite = lazy(() => import("./pages/AddSite").then(({ AddSite }) => ({ default: AddSite })));
const AuditLog = lazy(() =>
  import("./pages/AuditLog").then(({ AuditLog }) => ({ default: AuditLog })),
);
const Billing = lazy(() =>
  import("./pages/Billing").then(({ Billing }) => ({ default: Billing })),
);
const Dashboard = lazy(() =>
  import("./pages/Dashboard").then(({ Dashboard }) => ({ default: Dashboard })),
);
const ForgotPassword = lazy(() =>
  import("./pages/ForgotPassword").then(({ ForgotPassword }) => ({ default: ForgotPassword })),
);
const Landing = lazy(() => import("./pages/Landing").then(({ Landing }) => ({ default: Landing })));
const Login = lazy(() => import("./pages/Login").then(({ Login }) => ({ default: Login })));
const Notifications = lazy(() =>
  import("./pages/Notifications").then(({ Notifications }) => ({ default: Notifications })),
);
const Operations = lazy(() =>
  import("./pages/Operations").then(({ Operations }) => ({ default: Operations })),
);
const Organizations = lazy(() =>
  import("./pages/Organizations").then(({ Organizations }) => ({ default: Organizations })),
);
const Plans = lazy(() => import("./pages/Plans").then(({ Plans }) => ({ default: Plans })));
const Pricing = lazy(() => import("./pages/Pricing").then(({ Pricing }) => ({ default: Pricing })));
const ProjectDetail = lazy(() =>
  import("./pages/ProjectDetail").then(({ ProjectDetail }) => ({ default: ProjectDetail })),
);
const Projects = lazy(() =>
  import("./pages/Projects").then(({ Projects }) => ({ default: Projects })),
);
const Recipients = lazy(() =>
  import("./pages/Recipients").then(({ Recipients }) => ({ default: Recipients })),
);
const ResetPassword = lazy(() =>
  import("./pages/ResetPassword").then(({ ResetPassword }) => ({ default: ResetPassword })),
);
const SettingsPage = lazy(() =>
  import("./pages/Settings").then(({ SettingsPage }) => ({ default: SettingsPage })),
);
const SiteDetail = lazy(() =>
  import("./pages/SiteDetail").then(({ SiteDetail }) => ({ default: SiteDetail })),
);
const UsersPage = lazy(() =>
  import("./pages/Users").then(({ UsersPage }) => ({ default: UsersPage })),
);

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

function RequireAuth({ children }: { children: ReactNode }) {
  const { data: user, isLoading, isError, refetch } = useCurrentUser();
  const t = useT();
  const location = useLocation();
  if (isLoading) return <PageLoader label={t("common.checkingSession")} />;
  if (isError) return <ErrorState onRetry={() => void refetch()} />;
  // Remember where the visitor was headed (e.g. an email deep link) so the
  // login page can return there instead of the dashboard.
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  const requiredRoute = requiredAuthenticatedRoute(user, location.pathname);
  if (requiredRoute) return <Navigate to={requiredRoute} replace />;
  return <>{children}</>;
}

const router = createBrowserRouter([
  {
    errorElement: <ApplicationErrorScreen />,
    children: [
      { path: "/", element: <Landing /> },
      { path: "/login", element: <Login /> },
      { path: "/pricing", element: <Pricing /> },
      { path: "/forgot-password", element: <ForgotPassword /> },
      { path: "/reset-password", element: <ResetPassword /> },
      {
        element: (
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        ),
        children: [
          { path: "/dashboard", element: <Dashboard /> },
          { path: "/sites/new", element: <AddSite /> },
          { path: "/sites/:siteId", element: <SiteDetail /> },
          { path: "/projects", element: <Projects /> },
          { path: "/projects/:projectId", element: <ProjectDetail /> },
          { path: "/recipients", element: <Recipients /> },
          { path: "/notifications", element: <Notifications /> },
          { path: "/operations", element: <Operations /> },
          { path: "/organizations", element: <Organizations /> },
          { path: "/plans", element: <Plans /> },
          { path: "/users", element: <UsersPage /> },
          { path: "/audit", element: <AuditLog /> },
          { path: "/billing", element: <Billing /> },
          { path: "/settings", element: <SettingsPage /> },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
], { window: routerWindow(window) });

function RouteFallback() {
  const t = useT();
  return <PageLoader label={t("common.loading")} />;
}

export function App() {
  return (
    <ErrorBoundary>
      <MotionConfig reducedMotion="user">
        <ThemeProvider>
          <I18nProvider>
            <QueryClientProvider client={queryClient}>
              <BrandingProvider>
                <OrgProvider>
                  <ToastProvider>
                    <Suspense fallback={<RouteFallback />}>
                      <RouterProvider router={router} />
                    </Suspense>
                  </ToastProvider>
                </OrgProvider>
              </BrandingProvider>
            </QueryClientProvider>
          </I18nProvider>
        </ThemeProvider>
      </MotionConfig>
    </ErrorBoundary>
  );
}
