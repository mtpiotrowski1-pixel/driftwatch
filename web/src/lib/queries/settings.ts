import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, currentRequestContext, type ApiRequestContext } from "../api";
import type { Branding, FactoryDefaults, Settings } from "../types";
import { useCurrentUser } from "./auth";
import { keys } from "./cache";
import { requestInContext } from "./request-context";
import { useSensitiveMutation } from "./sensitive-mutation";

export function useSettings(
  context: ApiRequestContext = currentRequestContext,
  enabled = true,
) {
  return useQuery({
    queryKey: [
      ...keys.settings,
      context.scope,
      context.scope === "organization" ? context.organizationId : null,
    ],
    queryFn: () => api.get<Settings>("/api/settings", undefined, { context }),
    enabled,
  });
}

export function useFactoryDefaults(enabled = true) {
  return useQuery({
    queryKey: ["settings", "factory-defaults"],
    queryFn: () => api.get<FactoryDefaults>("/api/settings/factory-defaults"),
    staleTime: Infinity, // built-in constants; they don't change at runtime
    enabled,
  });
}

export function useUpdateSettings(context: ApiRequestContext = currentRequestContext) {
  const client = useQueryClient();
  return useSensitiveMutation({
    mutationFn: (body: Record<string, unknown>) =>
      requestInContext(context, () => api.put<Settings>("/api/settings", body, { context })),
    onSuccess: (settings) => {
      client.setQueryData(
        [
          ...keys.settings,
          context.scope,
          context.scope === "organization" ? context.organizationId : null,
        ],
        settings,
      );
      // Branding rides on the same settings; refetch it so the shell repaints the
      // name, logo, and accent immediately instead of after the staleTime.
      void client.invalidateQueries({ queryKey: keys.branding });
      void client.invalidateQueries({ queryKey: ["effective-rules"] });
    },
  });
}

export type BrandingAssetKind = "logo" | "hero";

export function useUploadBrandingAsset(
  kind: BrandingAssetKind,
  context: ApiRequestContext = currentRequestContext,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      api.uploadRaw<{ url: string; media_type: string }>(
        `/api/branding/assets/${kind}`,
        file,
        file.type,
        { context },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.settings });
      void client.invalidateQueries({ queryKey: keys.branding });
      void client.invalidateQueries({ queryKey: ["effective-rules"] });
    },
  });
}

export function useDeleteBrandingAsset(
  kind: BrandingAssetKind,
  context: ApiRequestContext = currentRequestContext,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.del(`/api/branding/assets/${kind}`, { context }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.settings });
      void client.invalidateQueries({ queryKey: keys.branding });
      void client.invalidateQueries({ queryKey: ["effective-rules"] });
    },
  });
}

export function useTestEmail(context: ApiRequestContext = currentRequestContext) {
  return useMutation({
    mutationFn: (to: string) =>
      api.post<{ channel: string; delivered: boolean; detail: string | null }>(
        "/api/settings/test-email",
        { to },
        { context },
      ),
  });
}

export function useTestWebhook(context: ApiRequestContext = currentRequestContext) {
  return useMutation({
    mutationFn: () =>
      api.post<{ delivered: boolean; detail: string | null }>(
        "/api/settings/test-webhook",
        undefined,
        { context },
      ),
  });
}

export function useBranding() {
  const { data: user } = useCurrentUser();
  const workspace = user != null;
  return useQuery({
    queryKey: workspace ? keys.workspaceBranding : keys.publicBranding,
    queryFn: () =>
      api.get<Branding>(workspace ? "/api/branding/workspace" : "/api/branding"),
    staleTime: 5 * 60 * 1000,
  });
}
