import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ACTING_ORG_STORAGE_KEY, api } from "@/lib/api";

import {
  operationsKeys,
  useDeadCheckIncidents,
  useRedriveDeadCheck,
  type DeadCheckIncident,
} from "./data";

const INCIDENT: DeadCheckIncident = {
  id: 88,
  organization_id: 7,
  site_id: 21,
  original_job_id: null,
  kind: "check",
  source: "scheduled",
  status: "dead",
  analyze: true,
  attempt_count: 3,
  enqueued_at: "2026-07-17T10:00:00Z",
  started_at: "2026-07-17T10:01:00Z",
  completed_at: "2026-07-17T10:02:00Z",
};

function createClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper(client: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("operations incident data", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("keeps tenant scope in the key and follows the server cursor", async () => {
    const client = createClient();
    const get = vi
      .spyOn(api, "get")
      .mockResolvedValueOnce({ items: [INCIDENT], next_before_id: 70 })
      .mockResolvedValueOnce({ items: [{ ...INCIDENT, id: 69 }], next_before_id: null });
    const scope = { kind: "tenant", organizationId: 7 } as const;
    const { result } = renderHook(() => useDeadCheckIncidents(scope, true), {
      wrapper: wrapper(client),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryState(operationsKeys.deadChecks(scope))).toBeDefined();
    expect(get).toHaveBeenNthCalledWith(
      1,
      "/api/operations/tenant/check-jobs/dead",
      { limit: 25, before_id: undefined },
      { context: { scope: "organization", organizationId: 7 } },
    );

    let nextPageResult: Awaited<ReturnType<typeof result.current.fetchNextPage>> | undefined;
    await act(async () => {
      nextPageResult = await result.current.fetchNextPage();
    });

    expect(get).toHaveBeenNthCalledWith(
      2,
      "/api/operations/tenant/check-jobs/dead",
      { limit: 25, before_id: 70 },
      { context: { scope: "organization", organizationId: 7 } },
    );
    expect(nextPageResult?.data?.pages.flatMap((page) => page.items).map((item) => item.id))
      .toEqual([88, 69]);
  });

  it("redrives only through the tenant endpoint and refreshes incidents and overview", async () => {
    const client = createClient();
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 7, name: "Tenant" }),
    );
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const post = vi.spyOn(api, "post").mockResolvedValue({
      created: true,
      job: { ...INCIDENT, id: 89, original_job_id: 88, status: "pending" },
    });
    const { result } = renderHook(() => useRedriveDeadCheck(7), {
      wrapper: wrapper(client),
    });
    const input = {
      jobId: 88,
      idempotency_key: "6aa3beb8-1e2b-48f8-a567-ec91c815cf7b",
      reason: "Capture worker capacity restored",
      ticket: "INC-2048",
    };

    await act(async () => {
      await result.current.mutateAsync(input);
    });

    expect(post).toHaveBeenCalledWith(
      "/api/operations/tenant/check-jobs/dead/88/redrive",
      {
        idempotency_key: input.idempotency_key,
        reason: input.reason,
        ticket: input.ticket,
      },
      { context: { scope: "organization", organizationId: 7 } },
    );
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: operationsKeys.deadChecks({ kind: "tenant", organizationId: 7 }),
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: operationsKeys.overview });
  });
});
