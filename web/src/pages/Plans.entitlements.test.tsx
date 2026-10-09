import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";

import { Plans } from "./Plans";

const mocks = vi.hoisted(() => ({
  billingPricesQuery: vi.fn(),
  createBillingPrice: vi.fn(),
  createBillingPriceReset: vi.fn(),
  createPlan: vi.fn(),
  deletePlan: vi.fn(),
  stepUp: vi.fn(),
  updatePricing: vi.fn(),
  updatePlan: vi.fn(),
}));

const legacyPlan = {
  id: 1,
  key: "legacy-public",
  name: "Legacy public",
  max_sites: null,
  max_members: null,
  monthly_ai_check_limit: null,
  price_override_cents: null,
  currency: "USD",
  is_active: true,
  is_self_serve: true,
  sort_order: 0,
  suggested_price_cents: 4900,
  effective_price_cents: 4900,
};

const activeBillingPrice = {
  id: 4,
  plan_id: legacyPlan.id,
  provider: "stripe",
  provider_price_id: "price_existing",
  version: 1,
  unit_amount_minor: 4900,
  currency: "USD",
  recurring_interval: "month",
  interval_count: 1,
  is_active: true,
  created_at: "2026-07-01T10:00:00Z",
  retired_at: null,
};

vi.mock("@/lib/queries", () => ({
  useCurrentUser: () => ({ data: { is_superadmin: true }, isLoading: false }),
  usePlans: () => ({ data: [legacyPlan], isError: false, isLoading: false, refetch: vi.fn() }),
  useBillingPrices: mocks.billingPricesQuery,
  usePricing: () => ({
    data: {
      base_fee: 10,
      per_site_fee: 2,
      ai_margin: 1.5,
      unlimited_sites: 100,
      unlimited_checks: 10000,
      currency: "USD",
      model: "gpt-test",
      input_price_per_1m: 1,
      output_price_per_1m: 2,
      avg_prompt_tokens: 100,
      avg_completion_tokens: 50,
      cost_per_check: 0.001,
    },
    isLoading: false,
  }),
  useSuggestPrice: () => ({ data: undefined }),
  useStepUp: () => ({
    error: null,
    isError: false,
    isPending: false,
    mutate: mocks.stepUp,
    reset: vi.fn(),
  }),
  useCreateBillingPrice: () => ({
    error: null,
    isPending: false,
    mutate: mocks.createBillingPrice,
    reset: mocks.createBillingPriceReset,
  }),
  useCreatePlan: () => ({ error: null, isPending: false, mutate: mocks.createPlan }),
  useUpdatePlan: () => ({ error: null, isPending: false, mutate: mocks.updatePlan }),
  useDeletePlan: () => ({ error: null, isPending: false, mutate: mocks.deletePlan }),
  useUpdatePricing: () => ({ error: null, isPending: false, mutate: mocks.updatePricing }),
}));

describe("operator entitlement templates", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("driftwatch_lang", "en");
    mocks.billingPricesQuery.mockReset();
    mocks.billingPricesQuery.mockReturnValue({
      data: [activeBillingPrice],
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    });
    mocks.createBillingPrice.mockReset();
    mocks.createBillingPriceReset.mockReset();
    mocks.createPlan.mockReset();
    mocks.deletePlan.mockReset();
    mocks.stepUp.mockReset();
    mocks.stepUp.mockImplementation(
      (_body: unknown, options?: { onSuccess?: () => void }) => options?.onSuccess?.(),
    );
    mocks.updatePricing.mockReset();
    mocks.updatePlan.mockReset();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  afterEach(() => {
    legacyPlan.is_self_serve = true;
    vi.unstubAllGlobals();
  });

  it("preserves publication during an ordinary entitlement edit", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <ToastProvider>
          <Plans />
        </ToastProvider>
      </I18nProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Entitlement templates" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Self-service release controls")).toBeInTheDocument();
    expect(screen.getByText("Publication enabled")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete Legacy public" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit Legacy public" }));
    expect(screen.getAllByRole("switch")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Save template" }));
    expect(mocks.updatePlan).not.toHaveBeenCalled();
    expect(
      screen.getByRole("dialog", { name: "Confirm entitlement template change" }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Save template" }));

    expect(mocks.updatePlan).toHaveBeenCalledWith(
      expect.objectContaining({ is_self_serve: true }),
      { onSuccess: expect.any(Function) },
    );
  });

  it("step-up gates explicit archival without claiming to change Stripe", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <ToastProvider>
          <Plans />
        </ToastProvider>
      </I18nProvider>,
    );

    await user.click(
      screen.getByRole("button", { name: "Archive Legacy public from new purchases?" }),
    );
    expect(
      screen.getByText(/Existing subscriptions and the corresponding Stripe price remain unchanged/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Archive" }));
    expect(mocks.updatePlan).not.toHaveBeenCalled();

    expect(screen.getByRole("dialog", { name: "Confirm plan archival" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Archive" }));

    expect(mocks.updatePlan).toHaveBeenCalledWith(
      { is_self_serve: false },
      { onSuccess: expect.any(Function) },
    );
  });

  it("step-up gates publication when an active provider price exists", async () => {
    legacyPlan.is_self_serve = false;
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <ToastProvider>
          <Plans />
        </ToastProvider>
      </I18nProvider>,
    );

    await user.click(
      screen.getByRole("button", { name: "Publish Legacy public for new purchases?" }),
    );
    expect(screen.getByText(/does not create or modify a Stripe price/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Publish" }));
    expect(mocks.updatePlan).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Publish" }));

    expect(mocks.updatePlan).toHaveBeenCalledWith(
      { is_self_serve: true },
      { onSuccess: expect.any(Function) },
    );
  });

  it("verifies an existing Stripe price before registering a local version", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <ToastProvider>
          <Plans />
        </ToastProvider>
      </I18nProvider>,
    );

    expect(screen.getByText("price_existing")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Register price version" }));
    expect(
      screen.getByText(/does not create, update, activate or archive anything in Stripe/),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Stripe price ID"), "price_revised");
    await user.type(screen.getByLabelText("Exact recurring amount"), "59.00");
    await user.click(screen.getByRole("button", { name: "Verify and register" }));
    expect(mocks.createBillingPrice).not.toHaveBeenCalled();

    expect(
      screen.getByRole("dialog", { name: "Confirm provider price mapping" }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Verify and register" }));

    expect(mocks.createBillingPrice).toHaveBeenCalledWith(
      {
        plan_id: legacyPlan.id,
        provider: "stripe",
        provider_price_id: "price_revised",
        unit_amount_minor: 5900,
        currency: "USD",
        recurring_interval: "month",
        interval_count: 1,
      },
      { onSuccess: expect.any(Function) },
    );
  });

  it("step-up gates creation of a new entitlement template", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <ToastProvider>
          <Plans />
        </ToastProvider>
      </I18nProvider>,
    );

    await user.click(screen.getByRole("button", { name: "New template" }));
    await user.type(screen.getByLabelText("Name"), "Business");
    await user.type(screen.getByLabelText("Key"), "business");
    await user.click(screen.getByRole("button", { name: "Save template" }));
    expect(mocks.createPlan).not.toHaveBeenCalled();

    expect(
      screen.getByRole("dialog", { name: "Confirm entitlement template change" }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Save template" }));
    expect(mocks.createPlan).toHaveBeenCalledWith(
      expect.objectContaining({ key: "business", name: "Business" }),
      { onSuccess: expect.any(Function) },
    );
  });

  it("step-up gates deletion and the platform-wide cost model", async () => {
    mocks.billingPricesQuery.mockReturnValue({
      data: [],
      isError: false,
      isLoading: false,
      refetch: vi.fn(),
    });
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <ToastProvider>
          <Plans />
        </ToastProvider>
      </I18nProvider>,
    );

    expect(screen.getByText(/does not cancel subscriptions or change Stripe/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save cost model" }));
    expect(mocks.updatePricing).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Confirm cost model change" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Save cost model" }));
    expect(mocks.updatePricing).toHaveBeenCalledWith(
      expect.objectContaining({ currency: "USD" }),
      { onSuccess: expect.any(Function) },
    );

    await user.click(screen.getByRole("button", { name: "Delete Legacy public" }));
    await user.click(screen.getByRole("button", { name: "Delete template" }));
    expect(mocks.deletePlan).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Confirm template deletion" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Password"), "operator-password");
    await user.click(screen.getByRole("button", { name: "Delete template" }));
    expect(mocks.deletePlan).toHaveBeenCalledWith(legacyPlan.id, {
      onSuccess: expect.any(Function),
    });
  });
});
