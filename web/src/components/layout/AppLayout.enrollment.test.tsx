import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";

import { AppLayout } from "./AppLayout";

const state = vi.hoisted(() => ({ mfaRequired: true, supportRead: vi.fn() }));

vi.mock("@/lib/queries", () => ({
  useCurrentUser: () => ({ data: {
    id: 1, name: "Owner", email: "owner@example.com", is_admin: true,
    is_superadmin: true, organization_id: 12, mfa_enrollment_required: state.mfaRequired,
  } }),
  useLogout: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("@/lib/orgContext", () => ({
  useOrg: () => ({ actingOrg: { id: 12, name: "My workspace" }, exitOrg: vi.fn() }),
  useInOrgContext: () => true,
  OrganizationTransitionCancelledError: class extends Error {},
}));
vi.mock("@/lib/supportAccess", () => ({
  useSupportAccess: state.supportRead,
  useRevokeSupportAccess: () => ({ isPending: false, error: null, mutateAsync: vi.fn() }),
  clearSupportTenantCache: vi.fn(),
}));

function renderLayout() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}><I18nProvider><ToastProvider><MemoryRouter initialEntries={["/settings"]}>
      <AppLayout />
    </MemoryRouter></ToastProvider></I18nProvider></QueryClientProvider>,
  );
}

describe("administrator enrollment layout", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
    state.mfaRequired = true;
    state.supportRead.mockReset().mockReturnValue({
      data: { required: false, access_enabled: true, organization_id: 12, expires_at: null },
      isLoading: false, isError: false, refetch: vi.fn(),
    });
  });

  it("keeps the MFA action without requesting the unavailable support-access API", () => {
    renderLayout();
    expect(screen.getByRole("main").querySelector('a[href="/settings"]')).toBeInTheDocument();
    expect(state.supportRead).not.toHaveBeenCalled();
    expect(screen.queryByText(/Managing organization/)).not.toBeInTheDocument();
  });

  it("resumes the canonical own-workspace banner after enrollment", () => {
    state.mfaRequired = false;
    renderLayout();
    expect(state.supportRead).toHaveBeenCalledWith(12);
    expect(screen.getByText(/My workspace/)).toBeInTheDocument();
  });
});
