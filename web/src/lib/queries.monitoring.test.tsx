import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { useChange, useChangeHistory, useCheckSite, useCreateSite, useDeleteSite, useNotificationsForChange, useProjects, useSiteEffectiveRules, useUpdateProject, useUsage } from "./queries";

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function QueryWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("monitoring read-model refresh", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("refreshes mounted usage, delivery and change details after a check", async () => {
    let completed = false;
    vi.spyOn(api, "get").mockImplementation(async (path) => {
      if (path === "/api/usage/summary") return { total_cost_usd: completed ? 0.01 : 0 };
      if (path === "/api/notifications") return completed ? [{ id: 1, status: "sent" }] : [];
      return { id: 1, site_id: 1, notified_at: completed ? "2026-10-08T10:00:00Z" : null };
    });
    vi.spyOn(api, "post").mockImplementation(async () => { completed = true; return {}; });
    const { result } = renderHook(() => ({ usage: useUsage(), deliveries: useNotificationsForChange(1), change: useChange(1), check: useCheckSite() }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.change.isSuccess).toBe(true));
    await act(async () => { await result.current.check.mutateAsync({ id: 1 }); });
    await waitFor(() => expect(result.current.usage.data?.total_cost_usd).toBe(0.01));
    expect(result.current.deliveries.data?.[0]?.status).toBe("sent");
    expect(result.current.change.data?.notified_at).toBe("2026-10-08T10:00:00Z");
  });

  it("uses the last loaded id to retrieve older history", async () => {
    const get = vi.spyOn(api, "get").mockImplementation(async (_path, query) => {
      const first = query?.before_id ? 50 : 100;
      return Array.from({ length: 50 }, (_, index) => ({ id: first - index }));
    });
    const { result } = renderHook(() => ({ ...useChangeHistory(1) }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(true);
    await act(async () => { await result.current.fetchNextPage(); });
    expect(get.mock.calls).toEqual([["/api/changes", { site_id: 1, limit: 50, before_id: undefined }], ["/api/changes", { site_id: 1, limit: 50, before_id: 51 }]]);
    await waitFor(() => expect(result.current.data?.pages.flat().at(-1)?.id).toBe(1));
    expect(get).toHaveBeenLastCalledWith("/api/changes", { site_id: 1, limit: 50, before_id: 51 });
  });

  it("updates a mounted inherited rule panel after editing its project", async () => {
    let rules = "Old rules";
    vi.spyOn(api, "get").mockImplementation(async () => ({ source: "project", text: rules }));
    vi.spyOn(api, "patch").mockImplementation(async () => { rules = "New rules"; return {}; });
    const { result } = renderHook(() => ({ rules: useSiteEffectiveRules(1), update: useUpdateProject(10) }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.rules.data?.text).toBe("Old rules"));
    await act(async () => { await result.current.update.mutateAsync({ prompt: "New rules" }); });
    await waitFor(() => expect(result.current.rules.data?.text).toBe("New rules"));
  });

  it("refreshes project site counts on create/delete and removes deleted event rows", async () => {
    let siteCount = 0;
    vi.spyOn(api, "get").mockImplementation(async (path) => {
      if (path === "/api/projects") return [{ id: 10, site_count: siteCount }];
      return siteCount > 0 ? [{ id: 1, site_id: 1 }] : [];
    });
    vi.spyOn(api, "post").mockImplementation(async () => { siteCount = 1; return { id: 1 }; });
    vi.spyOn(api, "del").mockImplementation(async () => { siteCount = 0; });
    const { result } = renderHook(() => ({
      // Consume query fields during render as the real list does; assertions
      // outside render alone do not subscribe to TanStack's tracked props.
      projects: { ...useProjects() }, history: { ...useChangeHistory() },
      create: useCreateSite(), remove: useDeleteSite(),
    }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.projects.data?.[0]?.site_count).toBe(0));
    await act(async () => { await result.current.create.mutateAsync({ url: "https://example.com", project_id: 10 }); });
    await waitFor(() => expect(result.current.projects.data?.[0]?.site_count).toBe(1));
    // The created site can subsequently produce an event; make the open history current.
    await act(async () => { await result.current.history.refetch(); });
    await waitFor(() => expect(result.current.history.data?.pages.flat()).toHaveLength(1));
    await act(async () => { await result.current.remove.mutateAsync(1); });
    await waitFor(() => expect(result.current.projects.data?.[0]?.site_count).toBe(0));
    await waitFor(() => expect(result.current.history.data?.pages.flat()).toHaveLength(0));
  });
});
