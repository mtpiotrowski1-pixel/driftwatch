import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  assertRequestContextCurrent,
  api,
  organizationRequestContext,
} from "./api";

export interface SupportAccessState {
  required: boolean;
  access_enabled: boolean;
  organization_id: number;
  expires_at: string | null;
}

export interface SupportAccessGrant {
  reason: string;
  ticket?: string;
}

const supportAccessKey = (organizationId: number) => [
  "support-access",
  organizationId,
] as const;

const SUPPORT_INDEPENDENT_QUERIES = new Set([
  "support-access",
  "me",
  "auth-capabilities",
  "public-plans",
]);

export function clearSupportTenantCache(client: QueryClient): void {
  client.removeQueries({
    predicate: (query) => !SUPPORT_INDEPENDENT_QUERIES.has(String(query.queryKey[0])),
  });
}

export function useSupportAccess(organizationId: number) {
  const context = organizationRequestContext(organizationId);
  return useQuery({
    queryKey: supportAccessKey(organizationId),
    queryFn: () => api.get<SupportAccessState>("/api/support-access", undefined, { context }),
    refetchOnWindowFocus: true,
  });
}

export function useGrantSupportAccess(organizationId: number) {
  const client = useQueryClient();
  const context = organizationRequestContext(organizationId);
  return useMutation({
    mutationFn: async (grant: SupportAccessGrant) => {
      assertRequestContextCurrent(context);
      const state = await api.post<SupportAccessState>("/api/support-access", grant, { context });
      assertRequestContextCurrent(context);
      if (state.organization_id !== organizationId) {
        throw new Error("Support access response organization mismatch");
      }
      return state;
    },
    onSuccess: (state) => {
      client.setQueryData(supportAccessKey(organizationId), state);
      void client.invalidateQueries({
        predicate: (query) => !SUPPORT_INDEPENDENT_QUERIES.has(String(query.queryKey[0])),
      });
    },
  });
}

export function useRevokeSupportAccess(organizationId: number) {
  const client = useQueryClient();
  const context = organizationRequestContext(organizationId);
  return useMutation({
    mutationFn: async () => {
      assertRequestContextCurrent(context);
      await api.del("/api/support-access", { context });
      assertRequestContextCurrent(context);
    },
    onSuccess: () => {
      clearSupportTenantCache(client);
      client.setQueryData<SupportAccessState>(supportAccessKey(organizationId), (current) =>
        current
          ? {
              ...current,
              access_enabled: false,
              expires_at: null,
            }
          : current,
      );
    },
  });
}
