import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  currentRequestContext,
  instanceRequestContext,
  organizationRequestContext,
} from "../api";
import type {
  BillingCatalog,
  BillingPrice,
  BillingPriceInput,
  BillingReconciliation,
  BillingStatus,
  HostedBillingSession,
  Plan,
  PlanInput,
  PriceSuggestion,
  PricingContext,
  PublicPlan,
} from "../types";
import { keys } from "./cache";
import { requestInContext, requiredOrganizationContext } from "./request-context";

export function usePlans(enabled = true) {
  return useQuery({
    queryKey: keys.plans,
    queryFn: () =>
      api.get<Plan[]>("/api/plans", undefined, { context: instanceRequestContext }),
    enabled,
  });
}

export function usePublicPlans() {
  return useQuery({
    queryKey: keys.publicPlans,
    queryFn: () => api.get<PublicPlan[]>("/api/plans/public"),
  });
}

export function useBillingCatalog(enabled = true, organizationId?: number | null) {
  return useQuery({
    queryKey: [...keys.billingCatalog, organizationId ?? "current"],
    queryFn: () => {
      const context = organizationId === undefined
        ? currentRequestContext
        : requiredOrganizationContext(organizationId);
      return api.get<BillingCatalog>("/api/billing/catalog", undefined, { context });
    },
    enabled,
  });
}

export function useBillingStatus(enabled = true, organizationId?: number | null) {
  return useQuery({
    queryKey: [...keys.billingStatus, organizationId ?? "current"],
    queryFn: () => {
      const context = organizationId === undefined
        ? currentRequestContext
        : requiredOrganizationContext(organizationId);
      return api.get<BillingStatus>("/api/billing/status", undefined, { context });
    },
    enabled,
  });
}

export function useBillingPrices(enabled = true) {
  return useQuery({
    queryKey: keys.billingPrices,
    queryFn: () =>
      api.get<BillingPrice[]>("/api/billing/prices", undefined, {
        context: instanceRequestContext,
      }),
    enabled,
  });
}

export function useCreateBillingPrice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: BillingPriceInput) =>
      requestInContext(instanceRequestContext, () =>
        api.post<BillingPrice>("/api/billing/prices", body, {
          context: instanceRequestContext,
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.billingPrices });
      void client.invalidateQueries({ queryKey: keys.billingCatalog });
      void client.invalidateQueries({ queryKey: keys.publicPlans });
    },
  });
}

export function useCreateBillingCheckout(organizationId?: number | null) {
  return useMutation({
    mutationFn: (body: {
      billing_price_id: number;
      idempotency_key: string;
      accepted_terms_version: string;
      accepted_privacy_version: string;
      accepted_terms_sha256: string;
      accepted_privacy_sha256: string;
    }) => {
      const context = organizationId === undefined
        ? currentRequestContext
        : requiredOrganizationContext(organizationId);
      return requestInContext(context, () =>
        api.post<HostedBillingSession>("/api/billing/checkout", body, { context }),
      );
    },
  });
}

export function useCreateBillingPortal(organizationId?: number | null) {
  return useMutation({
    mutationFn: (idempotencyKey: string) => {
      const context = organizationId === undefined
        ? currentRequestContext
        : requiredOrganizationContext(organizationId);
      return requestInContext(context, () =>
        api.post<HostedBillingSession>(
          "/api/billing/portal",
          { idempotency_key: idempotencyKey },
          { context },
        ),
      );
    },
  });
}

export function useReconcileBilling() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (organizationId: number) =>
      requestInContext(organizationRequestContext(organizationId), () =>
        api.post<BillingReconciliation>(
          `/api/billing/reconcile/${organizationId}`,
          undefined,
          { context: organizationRequestContext(organizationId) },
        ),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.billingStatus });
    },
  });
}

export function useCreatePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PlanInput) =>
      requestInContext(instanceRequestContext, () =>
        api.post<Plan>("/api/plans", body, { context: instanceRequestContext }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.plans }),
  });
}

export function useUpdatePlan(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<PlanInput>) =>
      requestInContext(instanceRequestContext, () =>
        api.patch<Plan>(`/api/plans/${id}`, body, { context: instanceRequestContext }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.plans });
      void client.invalidateQueries({ queryKey: keys.billingCatalog });
      void client.invalidateQueries({ queryKey: keys.publicPlans });
    },
  });
}

export function useDeletePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      requestInContext(instanceRequestContext, () =>
        api.del(`/api/plans/${id}`, { context: instanceRequestContext }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.plans }),
  });
}

export function usePricing(enabled = true) {
  return useQuery({
    queryKey: keys.pricing,
    queryFn: () =>
      api.get<PricingContext>("/api/plans/pricing", undefined, {
        context: instanceRequestContext,
      }),
    enabled,
  });
}

export function useUpdatePricing() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<PricingContext>) =>
      requestInContext(instanceRequestContext, () =>
        api.put<PricingContext>("/api/plans/pricing", body, {
          context: instanceRequestContext,
        }),
      ),
    onSuccess: (data) => {
      client.setQueryData(keys.pricing, data);
      // The suggested prices shift with the knobs, so refresh the catalog too.
      client.invalidateQueries({ queryKey: keys.plans });
    },
  });
}

export function useSuggestPrice(
  maxSites: number | null,
  monthlyAiCheckLimit: number | null,
  enabled: boolean,
) {
  const params = new URLSearchParams();
  if (maxSites !== null) params.set("max_sites", String(maxSites));
  if (monthlyAiCheckLimit !== null) params.set("monthly_ai_check_limit", String(monthlyAiCheckLimit));
  const query = params.toString();
  return useQuery({
    queryKey: ["plan-suggest", maxSites, monthlyAiCheckLimit],
    queryFn: () =>
      api.get<PriceSuggestion>(
        `/api/plans/suggest${query ? `?${query}` : ""}`,
        undefined,
        { context: instanceRequestContext },
      ),
    enabled,
  });
}
