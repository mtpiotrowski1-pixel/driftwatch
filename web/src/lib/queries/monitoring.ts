import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, currentRequestContext, type ApiRequestContext } from "../api";
import type {
  AnalysisPreview,
  Change,
  ChangeDetail,
  EffectiveRules,
  Project,
  RunResult,
  Site,
  UsageSummary,
  VerdictSummary,
} from "../types";
import { keys, liveQueryOptions } from "./cache";
import { requestInContext } from "./request-context";
import { useSensitiveMutation } from "./sensitive-mutation";

export function useSites() {
  return useQuery({
    queryKey: keys.sites,
    queryFn: () => api.get<Site[]>("/api/sites"),
    ...liveQueryOptions,
  });
}

export function useSite(id: number) {
  return useQuery({
    queryKey: keys.site(id),
    queryFn: () => api.get<Site>(`/api/sites/${id}`),
    ...liveQueryOptions,
  });
}

export function useCreateSite(context: ApiRequestContext = currentRequestContext) {
  const client = useQueryClient();
  return useSensitiveMutation({
    mutationFn: (body: Partial<Site>) =>
      requestInContext(context, () => api.post<Site>("/api/sites", body, { context })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.projects });
    },
  });
}

export function useUpdateSite(id: number) {
  const client = useQueryClient();
  return useSensitiveMutation({
    mutationFn: (body: Partial<Site>) => api.patch<Site>(`/api/sites/${id}`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.site(id) });
      void client.invalidateQueries({ queryKey: ["effective-rules"] });
      void client.invalidateQueries({ queryKey: keys.projects });
      void client.invalidateQueries({ queryKey: keys.usage });
      void client.invalidateQueries({ queryKey: keys.verdicts });
    },
  });
}

export function useDeleteSite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/sites/${id}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.projects });
      void client.invalidateQueries({ queryKey: keys.changesAll });
      void client.invalidateQueries({ queryKey: keys.changeAll });
      void client.invalidateQueries({ queryKey: keys.notificationsAll });
      void client.invalidateQueries({ queryKey: keys.usage });
      void client.invalidateQueries({ queryKey: keys.verdicts });
      void client.invalidateQueries({ queryKey: ["substitutions"] });
      void client.invalidateQueries({ queryKey: ["effective-rules"] });
    },
  });
}

export function useCheckSite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, analyze = true }: { id: number; analyze?: boolean }) =>
      api.post<RunResult>(`/api/sites/${id}/check?analyze=${analyze}`),
    onSuccess: (_result, { id }) => {
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.site(id) });
      void client.invalidateQueries({ queryKey: keys.changesAll });
      void client.invalidateQueries({ queryKey: keys.changeAll });
      void client.invalidateQueries({ queryKey: keys.notificationsAll });
      void client.invalidateQueries({ queryKey: keys.usage });
    },
  });
}

export function useSnapshotSite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post<RunResult>(`/api/sites/${id}/snapshot`),
    onSuccess: (_result, id) => {
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.site(id) });
    },
  });
}

export function useProjects() {
  return useQuery({
    queryKey: keys.projects,
    queryFn: () => api.get<Project[]>("/api/projects"),
  });
}

export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Project>) => api.post<Project>("/api/projects", body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.projects }),
  });
}

export function useUpdateProject(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Project>) => api.patch<Project>(`/api/projects/${id}`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.projects });
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.usage });
      void client.invalidateQueries({ queryKey: keys.verdicts });
      void client.invalidateQueries({ queryKey: ["effective-rules"] });
    },
  });
}

export function useDeleteProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/projects/${id}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.projects });
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.usage });
      void client.invalidateQueries({ queryKey: keys.verdicts });
      void client.invalidateQueries({ queryKey: ["substitutions"] });
      void client.invalidateQueries({ queryKey: ["effective-rules"] });
    },
  });
}

export function useChanges(siteId?: number) {
  return useQuery({
    queryKey: keys.changes(siteId),
    queryFn: () => api.get<Change[]>("/api/changes", siteId ? { site_id: siteId } : undefined),
    ...liveQueryOptions,
  });
}

export function useChangeHistory(siteId?: number) {
  const pageSize = 50;
  return useInfiniteQuery({
    queryKey: [...keys.changes(siteId), "history"],
    queryFn: ({ pageParam }) => api.get<Change[]>("/api/changes", {
      site_id: siteId,
      limit: pageSize,
      before_id: pageParam || undefined,
    }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.length === pageSize ? lastPage.at(-1)?.id : undefined,
    ...liveQueryOptions,
  });
}

export function useActionRequired() {
  return useQuery({
    queryKey: keys.actionRequired,
    queryFn: () => api.get<Change[]>("/api/changes/action-required"),
    ...liveQueryOptions,
  });
}

export function useChange(id: number) {
  return useQuery({
    queryKey: keys.change(id),
    queryFn: () => api.get<ChangeDetail>(`/api/changes/${id}`),
    // A change is immutable apart from its retry/analysis status, which the
    // mutations below invalidate; cache it so clicking through history is instant.
    staleTime: 30_000,
    ...liveQueryOptions,
  });
}

export function useUsage() {
  return useQuery({
    queryKey: keys.usage,
    queryFn: () => api.get<UsageSummary>("/api/usage/summary"),
    ...liveQueryOptions,
  });
}

export function useVerdictSummary(enabled = true) {
  return useQuery({
    queryKey: keys.verdicts,
    queryFn: () => api.get<VerdictSummary>("/api/usage/verdicts"),
    enabled,
    ...liveQueryOptions,
  });
}

function useChangeAction(path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post<RunResult>(`/api/changes/${id}/${path}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.changesAll });
      void client.invalidateQueries({ queryKey: keys.changeAll });
      void client.invalidateQueries({ queryKey: keys.notificationsAll });
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.usage });
      void client.invalidateQueries({ queryKey: keys.verdicts });
    },
  });
}

export function useRetryChange() {
  return useChangeAction("retry");
}

export function useReanalyzeChange() {
  return useChangeAction("analyze");
}

/** The rules currently in effect for a site (site -> project -> global -> default). */
export function useSiteEffectiveRules(id: number) {
  return useQuery({
    queryKey: ["effective-rules", "site", id],
    queryFn: () => api.get<EffectiveRules>(`/api/sites/${id}/effective-rules`),
  });
}

/** The rules a project's sites inherit unless they override them. */
export function useProjectEffectiveRules(id: number | null) {
  return useQuery({
    queryKey: ["effective-rules", "project", id],
    queryFn: () => api.get<EffectiveRules>(`/api/projects/${id}/effective-rules`),
    enabled: id !== null,
  });
}

/** The rules a brand-new site would inherit before a project is chosen. */
export function useInheritedEffectiveRules(enabled = true) {
  return useQuery({
    queryKey: ["effective-rules", "inherited"],
    queryFn: () => api.get<EffectiveRules>("/api/sites/effective-rules"),
    enabled,
  });
}

/** Dry-run draft importance rules against a past change. Read-only on the
 * change itself, so no cache invalidation is needed. */
export function useAnalyzePreview() {
  return useMutation({
    mutationFn: ({ id, rules }: { id: number; rules: string }) =>
      api.post<AnalysisPreview>(`/api/changes/${id}/analyze-preview`, { rules }),
  });
}

/** Record or clear the human review of a change's AI verdict. */
export function useSetVerdict() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, verdict }: { id: number; verdict: boolean | null }) =>
      api.post<Change>(`/api/changes/${id}/verdict`, { verdict }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.changesAll });
      void client.invalidateQueries({ queryKey: keys.changeAll });
      void client.invalidateQueries({ queryKey: keys.verdicts });
    },
  });
}
