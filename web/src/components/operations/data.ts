import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  assertRequestContextCurrent,
  api,
  instanceRequestContext,
  organizationRequestContext,
} from "@/lib/api";

export interface OperationsDatabase {
  backend: "sqlite" | "postgresql";
  reachable: boolean;
}

export interface OperationsScheduler {
  expected: boolean;
  running: boolean;
  stale: boolean;
  last_tick_at: string | null;
}

export interface OperationsCapture {
  mode: "isolated_worker" | "in_process" | "injected";
  status: "ready" | "unavailable" | "not_probed";
  active: number | null;
  queued: number | null;
  active_capacity: number | null;
  queue_capacity: number | null;
  message?: string | null;
}

export interface OperationsQueueOrganization {
  organization_id: number;
  organization_name?: string | null;
  pending: number;
  running: number;
  dead: number;
  retrying?: number;
  leased?: number;
}

export interface OperationsCheckQueue {
  pending: number;
  running: number;
  dead: number;
  oldest_pending_seconds: number | null;
  capacity: number;
  at_capacity: boolean;
  retrying?: number;
  leased?: number;
  per_organization?: OperationsQueueOrganization[];
}

export interface OperationsDeliveryQueue {
  pending: number;
  failed: number;
  sent: number;
  exhausted: number;
  leased: number;
  oldest_unsent_seconds: number | null;
}

export interface OperationsBillingWebhooks {
  total: number;
  received: number;
  processing: number;
  stale_processing: number;
  completed: number;
  failed: number;
  stale_after_seconds: number;
  last_processed_at: string | null;
  last_failed_at: string | null;
}

export interface OperationsAccountEmailQueue {
  pending: number;
  failed_total: number;
  failed_recent: number;
  sent: number;
  cancelled: number;
  leased: number;
  oldest_pending_seconds: number | null;
  stale_pending: boolean;
  pending_stale_after_seconds: number;
  recent_failure_window_seconds: number;
}

export interface OperationsStorage {
  db_bytes: number | null;
  wal_bytes: number | null;
  disk_free_bytes: number | null;
  last_backup_at: string | null;
  last_backup_file: string | null;
}

export interface OperationsMaintenance {
  enabled: boolean;
  active_requests: number;
  retry_after_seconds?: number | null;
  updated_at?: string | null;
}

export interface OperationsOverview {
  generated_at: string;
  version: string;
  status: "ok" | "degraded";
  database: OperationsDatabase;
  scheduler: OperationsScheduler;
  capture: OperationsCapture;
  check_queue: OperationsCheckQueue;
  delivery_queue: OperationsDeliveryQueue;
  account_email_queue: OperationsAccountEmailQueue;
  billing_webhooks: OperationsBillingWebhooks;
  storage: OperationsStorage;
  maintenance: OperationsMaintenance;
}

export type DeadCheckScope =
  | { kind: "instance" }
  | { kind: "tenant"; organizationId: number };

export interface DeadCheckIncident {
  id: number;
  organization_id: number;
  site_id: number;
  original_job_id: number | null;
  kind: "check" | "snapshot";
  source: "scheduled" | "manual" | "redrive";
  status: "pending" | "running" | "succeeded" | "dead" | "cancelled";
  analyze: boolean;
  attempt_count: number;
  enqueued_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface DeadCheckIncidentPage {
  items: DeadCheckIncident[];
  next_before_id: number | null;
}

export interface RedriveDeadCheckInput {
  jobId: number;
  idempotency_key: string;
  reason: string;
  ticket: string;
}

export interface RedriveDeadCheckResult {
  created: boolean;
  job: DeadCheckIncident;
}

export const operationsKeys = {
  overview: ["operations-overview"] as const,
  deadChecks: (scope: DeadCheckScope) =>
    [
      "operations-dead-checks",
      scope.kind,
      scope.kind === "tenant" ? scope.organizationId : "instance",
    ] as const,
};

export function useOperationsOverview(enabled: boolean) {
  return useQuery({
    queryKey: operationsKeys.overview,
    queryFn: () =>
      api.get<OperationsOverview>("/api/operations/overview", undefined, {
        context: instanceRequestContext,
      }),
    enabled,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
}

export function useDeadCheckIncidents(scope: DeadCheckScope, enabled: boolean) {
  const context = scope.kind === "instance"
    ? instanceRequestContext
    : organizationRequestContext(scope.organizationId);
  return useInfiniteQuery({
    queryKey: operationsKeys.deadChecks(scope),
    queryFn: ({ pageParam }) =>
      api.get<DeadCheckIncidentPage>(
        scope.kind === "instance"
          ? "/api/operations/check-jobs/dead"
          : "/api/operations/tenant/check-jobs/dead",
        { limit: 25, before_id: pageParam },
        { context },
      ),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => lastPage.next_before_id ?? undefined,
    enabled,
  });
}

export function useRedriveDeadCheck(organizationId: number) {
  const client = useQueryClient();
  const scope: DeadCheckScope = { kind: "tenant", organizationId };
  const context = organizationRequestContext(organizationId);
  return useMutation({
    mutationFn: async ({ jobId, ...body }: RedriveDeadCheckInput) => {
      assertRequestContextCurrent(context);
      const result = await api.post<RedriveDeadCheckResult>(
        `/api/operations/tenant/check-jobs/dead/${jobId}/redrive`,
        body,
        { context },
      );
      assertRequestContextCurrent(context);
      return result;
    },
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: operationsKeys.deadChecks(scope) }),
        client.invalidateQueries({ queryKey: operationsKeys.overview }),
      ]);
    },
  });
}
