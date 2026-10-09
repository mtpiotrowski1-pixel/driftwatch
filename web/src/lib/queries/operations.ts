import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";

import { api, instanceRequestContext } from "../api";
import type { AdminCapabilities, AuditEvent } from "../types";
import { keys } from "./cache";
import { requestInContext } from "./request-context";

export function useRestoreBackup() {
  return useMutation({
    mutationFn: (file: File) =>
      requestInContext(instanceRequestContext, () =>
        api.uploadRaw<{ safety_copy: string }>(
          "/api/admin/restore",
          file,
          undefined,
          { context: instanceRequestContext },
        ),
      ),
  });
}

export function useAdminCapabilities(enabled = true) {
  return useQuery({
    queryKey: keys.adminCapabilities,
    queryFn: () => api.get<AdminCapabilities>("/api/admin/capabilities"),
    enabled,
  });
}

export function useAuditEvents(enabled = true) {
  const pageSize = 100;
  return useInfiniteQuery({
    queryKey: keys.auditEvents,
    queryFn: ({ pageParam }) =>
      api.get<AuditEvent[]>("/api/audit-events", {
        limit: pageSize,
        ...(pageParam > 0 ? { before_id: pageParam } : {}),
      }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.length === pageSize ? lastPage.at(-1)?.id : undefined,
    enabled,
  });
}
