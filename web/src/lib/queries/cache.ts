import type { QueryClient } from "@tanstack/react-query";

import { ACTING_ORG_STORAGE_KEY, bindRequestSession } from "../api";
import type { User } from "../types";

export const keys = {
  me: ["me"] as const,
  sites: ["sites"] as const,
  site: (id: number) => ["sites", id] as const,
  projects: ["projects"] as const,
  recipients: ["recipients"] as const,
  changes: (siteId?: number) => ["changes", siteId ?? "all"] as const,
  actionRequired: ["changes", "action-required"] as const,
  auditEvents: ["audit-events"] as const,
  adminCapabilities: ["admin-capabilities"] as const,
  authCapabilities: ["auth-capabilities"] as const,
  changesAll: ["changes"] as const,
  change: (id: number) => ["change", id] as const,
  changeAll: ["change"] as const,
  notifications: (status?: string) => ["notifications", status ?? "all"] as const,
  notificationsForChange: (changeId: number) => ["notifications", "change", changeId] as const,
  notificationsAll: ["notifications"] as const,
  settings: ["settings"] as const,
  usage: ["usage"] as const,
  verdicts: ["verdicts"] as const,
  users: ["users"] as const,
  operators: ["operators"] as const,
  organizations: ["organizations"] as const,
  plans: ["plans"] as const,
  pricing: ["pricing"] as const,
  substitutions: (recipientId: number) => ["substitutions", recipientId] as const,
  branding: ["branding"] as const,
  publicBranding: ["branding", "public"] as const,
  workspaceBranding: ["branding", "workspace"] as const,
  publicPlans: ["public-plans"] as const,
  billingCatalog: ["billing", "catalog"] as const,
  billingPrices: ["billing", "prices"] as const,
  billingStatus: ["billing", "status"] as const,
};

export const ACTING_ORG_CLEARED_EVENT = "driftwatch:acting-org-cleared";

function isContextIndependentQuery(queryKey: readonly unknown[]): boolean {
  return queryKey[0] === keys.publicPlans[0] || queryKey[0] === keys.authCapabilities[0];
}

/**
 * Drop data whose response can depend on the authenticated user or acting org.
 * resetQueries clears observed data synchronously before refetching, so mounted
 * screens cannot render the previous tenant while the new request is in flight.
 */
export function resetOrganizationQueryCache(client: QueryClient): void {
  void client.resetQueries({
    predicate: (query) =>
      !isContextIndependentQuery(query.queryKey) && query.queryKey[0] !== keys.me[0],
  });
}

export function replaceSession(client: QueryClient, user: User | null): void {
  localStorage.removeItem(ACTING_ORG_STORAGE_KEY);
  bindRequestSession(user);
  window.dispatchEvent(new Event(ACTING_ORG_CLEARED_EVENT));
  resetOrganizationQueryCache(client);
  client.setQueryData(keys.me, user);
}

export const liveQueryOptions = {
  refetchInterval: 15_000,
  refetchOnWindowFocus: true,
  refetchIntervalInBackground: false,
} as const;
