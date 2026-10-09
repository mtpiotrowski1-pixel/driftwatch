import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { Billing } from "./Billing";

const mocks = vi.hoisted(() => ({
  checkoutMutate: vi.fn(),
  portalMutate: vi.fn(),
  reconcileMutate: vi.fn(),
  reconcileReset: vi.fn(),
  reset: vi.fn(),
  useBillingCatalog: vi.fn(),
  useBillingStatus: vi.fn(),
  useCreateBillingCheckout: vi.fn(),
  useCreateBillingPortal: vi.fn(),
  useCurrentUser: vi.fn(),
  useInOrgContext: vi.fn(),
  useOrg: vi.fn(),
  useReconcileBilling: vi.fn(),
}));

vi.mock("@/lib/queries", () => ({
  useBillingCatalog: mocks.useBillingCatalog,
  useBillingStatus: mocks.useBillingStatus,
  useCreateBillingCheckout: mocks.useCreateBillingCheckout,
  useCreateBillingPortal: mocks.useCreateBillingPortal,
  useCurrentUser: mocks.useCurrentUser,
  useReconcileBilling: mocks.useReconcileBilling,
}));

vi.mock("@/lib/orgContext", () => ({
  useInOrgContext: mocks.useInOrgContext,
  useOrg: mocks.useOrg,
}));

vi.mock("@/components/StepUpDialog", () => ({
  StepUpDialog: ({ onVerified }: { onVerified: () => void }) => (
    <button type="button" onClick={onVerified}>
      Verify billing action
    </button>
  ),
}));

const queryResult = (data: object) => ({
  data,
  isLoading: false,
  isError: false,
  isFetching: false,
  refetch: vi.fn(),
});

describe("Billing", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
    sessionStorage.clear();
    mocks.checkoutMutate.mockReset();
    mocks.portalMutate.mockReset();
    mocks.reconcileMutate.mockReset();
    mocks.reconcileReset.mockReset();
    mocks.reset.mockReset();
    mocks.useCurrentUser.mockReturnValue({
      data: { is_admin: true, is_superadmin: false, organization_id: 7 },
      isLoading: false,
    });
    mocks.useInOrgContext.mockReturnValue(true);
    mocks.useOrg.mockReturnValue({ actingOrg: null });
    mocks.useBillingStatus.mockReturnValue(
      queryResult({
        provider: "stripe",
        provider_configured: true,
        self_serve_ready: false,
        customer_exists: true,
        subscription: {
          status: "active",
          plan_id: 1,
          plan_key: "paid",
          plan_name: "Paid",
          current_period_end: "2026-08-19T12:00:00Z",
          trial_end: null,
          cancel_at_period_end: false,
          entitlement_active: true,
          entitlement_valid_until: "2026-08-19T12:00:00Z",
          access_suspended_at: null,
        },
      }),
    );
    mocks.useBillingCatalog.mockReturnValue(
      queryResult({
        self_serve_ready: false,
        terms_version: null,
        privacy_version: null,
        terms_url: null,
        privacy_url: null,
        terms_sha256: null,
        privacy_sha256: null,
        prices: [],
      }),
    );
    mocks.useCreateBillingCheckout.mockReturnValue({
      isPending: false,
      error: null,
      reset: mocks.reset,
      mutate: mocks.checkoutMutate,
    });
    mocks.useCreateBillingPortal.mockReturnValue({
      isPending: false,
      error: null,
      reset: mocks.reset,
      mutate: mocks.portalMutate,
    });
    mocks.useReconcileBilling.mockReturnValue({
      data: null,
      isPending: false,
      error: null,
      reset: mocks.reconcileReset,
      mutate: mocks.reconcileMutate,
    });
  });

  it("keeps the cancellation portal available when new self-serve purchases are closed", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/billing"]}>
        <I18nProvider>
          <Billing />
        </I18nProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText("New purchases stay closed", { exact: false })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Manage billing" }));
    await user.click(screen.getByRole("button", { name: "Verify billing action" }));

    expect(mocks.portalMutate).toHaveBeenCalledWith(
      expect.stringMatching(/^portal-/),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(mocks.checkoutMutate).not.toHaveBeenCalled();
  });

  it("does not treat an operator home organization as an active billing tenant", () => {
    mocks.useCurrentUser.mockReturnValue({
      data: { is_admin: true, is_superadmin: true, organization_id: 7 },
      isLoading: false,
    });
    mocks.useInOrgContext.mockReturnValue(false);
    mocks.useOrg.mockReturnValue({ actingOrg: null });

    render(
      <MemoryRouter initialEntries={["/billing"]}>
        <I18nProvider>
          <Billing />
        </I18nProvider>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Organization context required" }),
    ).toBeInTheDocument();
    expect(mocks.useBillingStatus).toHaveBeenLastCalledWith(false, null);
    expect(mocks.useBillingCatalog).toHaveBeenLastCalledWith(false, null);
  });

  it("step-up gates tenant reconciliation and states its read-only Stripe boundary", async () => {
    const user = userEvent.setup();
    mocks.useCurrentUser.mockReturnValue({
      data: { is_admin: true, is_superadmin: true, organization_id: 1 },
      isLoading: false,
    });
    mocks.useOrg.mockReturnValue({ actingOrg: { id: 42, name: "Acme" } });

    render(
      <MemoryRouter initialEntries={["/billing"]}>
        <I18nProvider>
          <Billing />
        </I18nProvider>
      </MemoryRouter>,
    );

    expect(
      screen.getByText(/does not charge, refund, cancel or modify anything in Stripe/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sync from Stripe" }));
    expect(mocks.reconcileMutate).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Verify billing action" }));

    expect(mocks.reconcileReset).toHaveBeenCalledOnce();
    expect(mocks.reconcileMutate).toHaveBeenCalledWith(42);
  });

  it("links the accepted legal documents and submits their exact fingerprints", async () => {
    const user = userEvent.setup();
    mocks.useBillingStatus.mockReturnValue(
      queryResult({
        provider: "stripe",
        provider_configured: true,
        self_serve_ready: true,
        customer_exists: false,
        subscription: null,
      }),
    );
    mocks.useBillingCatalog.mockReturnValue(
      queryResult({
        self_serve_ready: true,
        terms_version: "terms-2026-01",
        privacy_version: "privacy-2026-01",
        terms_url: "https://legal.example.test/terms/2026-01",
        privacy_url: "https://legal.example.test/privacy/2026-01",
        terms_sha256: "a".repeat(64),
        privacy_sha256: "b".repeat(64),
        prices: [
          {
            billing_price_id: 1,
            price_version: 1,
            plan_id: 1,
            plan_key: "paid",
            plan_name: "Paid",
            max_sites: 10,
            max_members: 5,
            monthly_ai_check_limit: 100,
            unit_amount_minor: 1900,
            currency: "USD",
            recurring_interval: "month",
            interval_count: 1,
          },
        ],
      }),
    );
    const view = render(
      <MemoryRouter initialEntries={["/billing"]}>
        <I18nProvider>
          <Billing />
        </I18nProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText("5 team members")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Choose Paid" }));
    expect(screen.getByRole("link", { name: "Terms (version terms-2026-01)" })).toHaveAttribute(
      "href",
      "https://legal.example.test/terms/2026-01",
    );
    expect(
      screen.getByRole("link", { name: "Privacy Policy (version privacy-2026-01)" }),
    ).toHaveAttribute("href", "https://legal.example.test/privacy/2026-01");
    await user.click(screen.getByRole("checkbox", { name: "I accept" }));
    await user.click(screen.getByRole("button", { name: "Continue securely" }));
    await user.click(screen.getByRole("button", { name: "Verify billing action" }));

    expect(mocks.checkoutMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        accepted_terms_version: "terms-2026-01",
        accepted_privacy_version: "privacy-2026-01",
        accepted_terms_sha256: "a".repeat(64),
        accepted_privacy_sha256: "b".repeat(64),
      }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );

    const firstKey = mocks.checkoutMutate.mock.calls[0][0].idempotency_key;
    view.unmount();
    render(
      <MemoryRouter initialEntries={["/billing"]}>
        <I18nProvider>
          <Billing />
        </I18nProvider>
      </MemoryRouter>,
    );
    await user.click(screen.getByRole("button", { name: "Choose Paid" }));
    await user.click(screen.getByRole("checkbox", { name: "I accept" }));
    await user.click(screen.getByRole("button", { name: "Continue securely" }));
    await user.click(screen.getByRole("button", { name: "Verify billing action" }));

    expect(mocks.checkoutMutate.mock.calls[1][0].idempotency_key).toBe(firstKey);
  });

  it("discards checkout and portal state when the active organization changes", async () => {
    const user = userEvent.setup();
    mocks.useCurrentUser.mockReturnValue({
      data: { is_admin: true, is_superadmin: true, organization_id: 1 },
      isLoading: false,
    });
    mocks.useOrg.mockReturnValue({ actingOrg: { id: 42, name: "Acme" } });
    mocks.useBillingStatus.mockReturnValue(
      queryResult({
        provider: "stripe",
        provider_configured: true,
        self_serve_ready: true,
        customer_exists: false,
        subscription: null,
      }),
    );
    mocks.useBillingCatalog.mockReturnValue(
      queryResult({
        self_serve_ready: true,
        terms_version: "terms-1",
        privacy_version: "privacy-1",
        terms_url: "https://legal.example.test/terms",
        privacy_url: "https://legal.example.test/privacy",
        terms_sha256: "a".repeat(64),
        privacy_sha256: "b".repeat(64),
        prices: [
          {
            billing_price_id: 1,
            price_version: 1,
            plan_id: 1,
            plan_key: "paid",
            plan_name: "Paid",
            max_sites: 10,
            max_members: 5,
            monthly_ai_check_limit: 100,
            unit_amount_minor: 1900,
            currency: "USD",
            recurring_interval: "month",
            interval_count: 1,
          },
        ],
      }),
    );
    const view = render(
      <MemoryRouter initialEntries={["/billing"]}>
        <I18nProvider>
          <Billing />
        </I18nProvider>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: "Choose Paid" }));
    expect(screen.getByRole("dialog", { name: "Confirm plan and consent" })).toBeInTheDocument();
    mocks.reset.mockClear();
    mocks.reconcileReset.mockClear();

    mocks.useOrg.mockReturnValue({ actingOrg: { id: 43, name: "Other org" } });
    view.rerender(
      <MemoryRouter initialEntries={["/billing"]}>
        <I18nProvider>
          <Billing />
        </I18nProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "Confirm plan and consent" }),
      ).not.toBeInTheDocument();
    });
    expect(mocks.reset).toHaveBeenCalledTimes(2);
    expect(mocks.reconcileReset).toHaveBeenCalledOnce();
    expect(mocks.useBillingStatus).toHaveBeenLastCalledWith(true, 43);
    expect(mocks.useBillingCatalog).toHaveBeenLastCalledWith(true, 43);
  });
});
