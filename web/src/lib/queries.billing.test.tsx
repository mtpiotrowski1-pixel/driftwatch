import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ACTING_ORG_STORAGE_KEY, api } from "./api";
import {
  keys,
  useBillingPrices,
  useCreateBillingPrice,
  useReconcileBilling,
} from "./queries";
import type { BillingPriceInput } from "./types";

function createClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper(client: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

const PRICE_INPUT: BillingPriceInput = {
  plan_id: 8,
  provider: "stripe",
  provider_price_id: "price_verified",
  unit_amount_minor: 5900,
  currency: "USD",
  recurring_interval: "month",
  interval_count: 1,
};

describe("billing administration queries", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("loads the operator's versioned provider price mappings", async () => {
    const client = createClient();
    const get = vi.spyOn(api, "get").mockResolvedValue([]);
    const { result } = renderHook(() => useBillingPrices(), { wrapper: wrapper(client) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(get).toHaveBeenCalledWith(
      "/api/billing/prices",
      undefined,
      { context: { scope: "instance" } },
    );
  });

  it("registers an exact provider price and invalidates every public catalog projection", async () => {
    const client = createClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const post = vi.spyOn(api, "post").mockResolvedValue({ id: 11 });
    const { result } = renderHook(() => useCreateBillingPrice(), {
      wrapper: wrapper(client),
    });

    await act(async () => {
      await result.current.mutateAsync(PRICE_INPUT);
    });

    expect(post).toHaveBeenCalledWith(
      "/api/billing/prices",
      PRICE_INPUT,
      { context: { scope: "instance" } },
    );
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.billingPrices });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.billingCatalog });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.publicPlans });
  });

  it("reconciles only the selected organization path and refreshes local billing status", async () => {
    const client = createClient();
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 42, name: "Selected org" }),
    );
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const post = vi.spyOn(api, "post").mockResolvedValue({
      organization_id: 42,
      subscriptions_seen: 1,
      subscriptions_updated: 1,
    });
    const { result } = renderHook(() => useReconcileBilling(), {
      wrapper: wrapper(client),
    });

    await act(async () => {
      await result.current.mutateAsync(42);
    });

    expect(post).toHaveBeenCalledWith(
      "/api/billing/reconcile/42",
      undefined,
      { context: { scope: "organization", organizationId: 42 } },
    );
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.billingStatus });
  });
});
