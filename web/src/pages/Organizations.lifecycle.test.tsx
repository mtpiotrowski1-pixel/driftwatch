import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider, type Lang } from "@/i18n";

import { Organizations } from "./Organizations";

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  enterOrg: vi.fn(),
  stepUp: vi.fn(),
  update: vi.fn(),
}));

const organization = {
  id: 42,
  name: "Acme Platform",
  is_active: true,
  plan: "business",
  plan_id: null,
  max_sites: 20,
  max_members: 10,
  monthly_ai_check_limit: 500,
  created_at: "2026-07-19T10:00:00Z",
  member_count: 4,
  site_count: 7,
  ai_checks_this_month: 18,
  billing_managed: false,
  billing_suspended: false,
};

vi.mock("@/lib/queries", () => ({
  useCreateOrganization: () => ({ error: null, isPending: false, mutate: mocks.create }),
  useCurrentUser: () => ({
    data: {
      id: 1,
      organization_id: 1,
      is_superadmin: true,
      totp_enabled: false,
    },
    isLoading: false,
  }),
  useOrganizations: () => ({
    data: [organization],
    isError: false,
    isLoading: false,
    refetch: vi.fn(),
  }),
  usePlans: () => ({ data: [], isLoading: false }),
  useStepUp: () => ({
    error: null,
    isError: false,
    isPending: false,
    mutate: mocks.stepUp,
    reset: vi.fn(),
  }),
  useUpdateOrganization: () => ({ error: null, isPending: false, mutate: mocks.update }),
}));

vi.mock("@/lib/orgContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/orgContext")>()),
  useOrg: () => ({ enterOrg: mocks.enterOrg }),
}));

function renderPage(lang: Lang) {
  localStorage.setItem("driftwatch_lang", lang);
  return render(
    <MemoryRouter>
      <I18nProvider>
        <ToastProvider>
          <Organizations />
        </ToastProvider>
      </I18nProvider>
    </MemoryRouter>,
  );
}

describe("organization lifecycle controls", () => {
  beforeEach(() => {
    localStorage.clear();
    organization.is_active = true;
    organization.billing_managed = false;
    organization.billing_suspended = false;
    mocks.create.mockReset();
    mocks.enterOrg.mockReset().mockResolvedValue(undefined);
    mocks.stepUp.mockReset();
    mocks.stepUp.mockImplementation(
      (_body: unknown, options?: { onSuccess?: () => void }) => options?.onSuccess?.(),
    );
    mocks.update.mockReset();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it.each([
    {
      lang: "en" as const,
      edit: "Rename Acme Platform",
      hint: "Suspension locks members out while preserving customer data, audit records, and billing history.",
    },
    {
      lang: "pl" as const,
      edit: "Zmień nazwę Acme Platform",
      hint: "Zawieszenie blokuje użytkowników, ale zachowuje dane klienta, audyt i historię rozliczeń.",
    },
  ])(
    "offers reversible offboarding without a destructive action in $lang",
    async ({ lang, edit, hint }) => {
      const user = userEvent.setup();
      renderPage(lang);

      expect(screen.queryByRole("button", { name: /delete|usuń/i })).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: edit }));
      expect(screen.getByText(hint)).toBeInTheDocument();
      expect(screen.queryByText(/permanently deleted|trwale usuni/i)).not.toBeInTheDocument();
    },
  );

  it("step-up gates organization creation", async () => {
    const user = userEvent.setup();
    renderPage("en");

    await user.click(screen.getByRole("button", { name: "New organization" }));
    await user.type(screen.getByLabelText("Name"), "Northstar Labs");
    await user.click(screen.getByRole("button", { name: "Create organization" }));
    expect(mocks.create).not.toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: "Confirm organization creation" }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Create organization" }));
    expect(mocks.create).toHaveBeenCalledWith(
      { name: "Northstar Labs" },
      { onSuccess: expect.any(Function) },
    );
  });

  it("step-up gates organization entitlement changes", async () => {
    const user = userEvent.setup();
    renderPage("en");
    await user.click(screen.getByRole("button", { name: "Rename Acme Platform" }));
    await user.click(screen.getByRole("switch"));
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(mocks.update).not.toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: "Confirm entitlement change" }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(mocks.update).toHaveBeenCalledWith(
      { is_active: false },
      { onSuccess: expect.any(Function) },
    );
  });

  it("saves a name-only edit without unnecessary step-up", async () => {
    const user = userEvent.setup();
    renderPage("en");

    await user.click(screen.getByRole("button", { name: "Rename Acme Platform" }));
    const name = screen.getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Acme Monitoring");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(mocks.stepUp).not.toHaveBeenCalled();
    expect(mocks.update).toHaveBeenCalledWith(
      { name: "Acme Monitoring" },
      { onSuccess: expect.any(Function) },
    );
  });

  it("makes provider-owned entitlements explicit and non-editable", async () => {
    organization.is_active = false;
    organization.billing_managed = true;
    organization.billing_suspended = true;
    const user = userEvent.setup();
    renderPage("en");

    expect(screen.getByText("Suspended by billing")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rename Acme Platform" }));

    expect(screen.getByLabelText("Plan (from catalog)")).toBeDisabled();
    expect(screen.getByLabelText("Plan")).toBeDisabled();
    expect(screen.getByLabelText("Site limit")).toBeDisabled();
    expect(screen.getByLabelText("Member limit")).toBeDisabled();
    expect(screen.getByLabelText("AI checks / month")).toBeDisabled();
    expect(screen.getByRole("switch")).toBeDisabled();
    expect(
      screen.getByText(
        "Access can only be restored by a current subscription event from the payment provider.",
      ),
    ).toBeInTheDocument();
  });
});
