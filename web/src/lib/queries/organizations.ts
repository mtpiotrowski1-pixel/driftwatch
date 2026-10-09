import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, instanceRequestContext } from "../api";
import type { Organization } from "../types";
import { keys } from "./cache";
import { requestInContext } from "./request-context";

export function useOrganizations(enabled = true) {
  return useQuery({
    queryKey: keys.organizations,
    queryFn: () =>
      api.get<Organization[]>("/api/organizations", undefined, {
        context: instanceRequestContext,
      }),
    enabled,
  });
}

export function useCreateOrganization() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string }) =>
      requestInContext(instanceRequestContext, () =>
        api.post<Organization>("/api/organizations", body, {
          context: instanceRequestContext,
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.organizations }),
  });
}

export function useUpdateOrganization(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      name?: string;
      is_active?: boolean;
      plan?: string;
      plan_id?: number | null;
      max_sites?: number | null;
      max_members?: number | null;
      monthly_ai_check_limit?: number | null;
    }) =>
      requestInContext(instanceRequestContext, () =>
        api.patch<Organization>(`/api/organizations/${id}`, body, {
          context: instanceRequestContext,
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.organizations }),
  });
}
