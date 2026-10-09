import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";
import { ACTING_ORG_STORAGE_KEY, ApiError } from "@/lib/api";

import { Operations } from "./Operations";

const mocks = vi.hoisted(() => ({
  useOperationsOverview: vi.fn(),
  useDeadCheckIncidents: vi.fn(),
  useRedriveDeadCheck: vi.fn(),
  useCurrentUser: vi.fn(),
  useOrganizations: vi.fn(),
  useStepUp: vi.fn(),
  useOrg: vi.fn(),
  refetch: vi.fn(),
  incidentRefetch: vi.fn(),
  fetchNextPage: vi.fn(),
  enterOrg: vi.fn(),
  stepUpMutate: vi.fn(),
  redriveMutate: vi.fn(),
  stepUpReset: vi.fn(),
  redriveReset: vi.fn(),
}));

vi.mock("@/components/operations/data", () => ({
  useOperationsOverview: mocks.useOperationsOverview,
  useDeadCheckIncidents: mocks.useDeadCheckIncidents,
  useRedriveDeadCheck: mocks.useRedriveDeadCheck,
}));

vi.mock("@/lib/queries", () => ({
  useCurrentUser: mocks.useCurrentUser,
  useOrganizations: mocks.useOrganizations,
  useStepUp: mocks.useStepUp,
}));

vi.mock("@/lib/orgContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/orgContext")>()),
  useOrg: mocks.useOrg,
}));

const currentOverview = {
  generated_at: "2026-07-17T12:30:00Z",
  version: "1.4.0",
  status: "ok" as const,
  database: { backend: "postgresql" as const, reachable: true },
  scheduler: {
    expected: true,
    running: true,
    stale: false,
    last_tick_at: "2026-07-17T12:29:30Z",
  },
  capture: {
    mode: "isolated_worker" as const,
    status: "ready" as const,
    active: 2,
    queued: 3,
    active_capacity: 8,
    queue_capacity: 100,
  },
  check_queue: {
    pending: 12,
    running: 4,
    dead: 1,
    oldest_pending_seconds: 90,
    capacity: 500,
    at_capacity: false,
  },
  delivery_queue: {
    pending: 5,
    failed: 1,
    sent: 1_240,
    exhausted: 0,
    leased: 2,
    oldest_unsent_seconds: 3_600,
  },
  account_email_queue: {
    pending: 2,
    failed_total: 4,
    failed_recent: 0,
    sent: 860,
    cancelled: 12,
    leased: 1,
    oldest_pending_seconds: 45,
    stale_pending: false,
    pending_stale_after_seconds: 300,
    recent_failure_window_seconds: 3_600,
  },
  billing_webhooks: {
    total: 1_250,
    received: 2,
    processing: 1,
    stale_processing: 0,
    completed: 1_247,
    failed: 0,
    stale_after_seconds: 300,
    last_processed_at: "2026-07-17T12:29:45Z",
    last_failed_at: null,
  },
  storage: {
    db_bytes: 1_610_612_736,
    wal_bytes: 1_572_864,
    disk_free_bytes: 85_899_345_920,
    last_backup_at: "2026-07-17T03:00:00Z",
    last_backup_file: "C:\\backups\\driftwatch-20260717.db",
  },
  maintenance: {
    enabled: false,
    active_requests: 7,
  },
};

function queryResult(data: typeof currentOverview | Record<string, unknown> = currentOverview) {
  return {
    data,
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: mocks.refetch,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <I18nProvider>
        <ToastProvider>
          <Operations />
        </ToastProvider>
      </I18nProvider>
    </MemoryRouter>,
  );
}

const deadIncident = {
  id: 91,
  organization_id: 7,
  site_id: 22,
  original_job_id: null,
  kind: "check" as const,
  source: "scheduled" as const,
  status: "dead" as const,
  analyze: true,
  attempt_count: 3,
  enqueued_at: "2026-07-17T11:00:00Z",
  started_at: "2026-07-17T11:01:00Z",
  completed_at: "2026-07-17T11:02:00Z",
};

function incidentQuery(items: typeof deadIncident[] = []) {
  return {
    data: { pages: [{ items, next_before_id: null }], pageParams: [undefined] },
    error: null,
    isLoading: false,
    isError: false,
    isFetching: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    refetch: mocks.incidentRefetch,
    fetchNextPage: mocks.fetchNextPage,
  };
}

describe("Operations", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("driftwatch_lang", "en");
    mocks.refetch.mockReset().mockResolvedValue(undefined);
    mocks.incidentRefetch.mockReset().mockResolvedValue(undefined);
    mocks.fetchNextPage.mockReset().mockResolvedValue(undefined);
    mocks.enterOrg.mockReset().mockResolvedValue(undefined);
    mocks.stepUpReset.mockReset();
    mocks.redriveReset.mockReset();
    mocks.stepUpMutate.mockReset().mockResolvedValue(undefined);
    mocks.redriveMutate.mockReset().mockResolvedValue({
      created: true,
      job: { ...deadIncident, id: 92, original_job_id: 91, status: "pending" },
    });
    mocks.useCurrentUser.mockReset().mockReturnValue({
      data: { is_superadmin: true, totp_enabled: false },
      isLoading: false,
    });
    mocks.useOrg.mockReset().mockReturnValue({ actingOrg: null, enterOrg: mocks.enterOrg });
    mocks.useOrganizations.mockReset().mockReturnValue({
      data: [{ id: 7, name: "Northwind" }],
      isLoading: false,
      isError: false,
    });
    mocks.useStepUp.mockReset().mockReturnValue({
      mutateAsync: mocks.stepUpMutate,
      error: null,
      isError: false,
      isPending: false,
      reset: mocks.stepUpReset,
    });
    mocks.useRedriveDeadCheck.mockReset().mockReturnValue({
      mutateAsync: mocks.redriveMutate,
      error: null,
      isError: false,
      isPending: false,
      reset: mocks.redriveReset,
    });
    mocks.useDeadCheckIncidents.mockReset().mockReturnValue(incidentQuery());
    mocks.useOperationsOverview.mockReset().mockReturnValue(queryResult());
  });

  it("renders every metric from the current backend contract without optional placeholders", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Operations" })).toBeInTheDocument();
    expect(screen.getByText("Platform operating normally")).toBeInTheDocument();
    expect(screen.getByText("No unresolved check incidents")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Isolated worker")).toBeInTheDocument();
    expect(screen.getByText("1.5 GB")).toBeInTheDocument();
    expect(screen.getByText("C:\\backups\\driftwatch-20260717.db")).toBeInTheDocument();
    expect(screen.getByText("Billing webhooks")).toBeInTheDocument();
    expect(screen.getByText("Account email")).toBeInTheDocument();
    expect(screen.getByText("Failed historically").nextElementSibling).toHaveTextContent("4");
    expect(screen.getByText("Events recorded").nextElementSibling).toHaveTextContent("1,250");
    expect(screen.getAllByText("Stale threshold")).toHaveLength(2);
    expect(screen.getByText("1.5 min")).toBeInTheDocument();
    expect(screen.getAllByText("1 h")).toHaveLength(2);
    expect(screen.queryByText("Retrying")).not.toBeInTheDocument();
    expect(screen.queryByText("Service message")).not.toBeInTheDocument();
  });

  it("renders optional telemetry only when the API supplies it", () => {
    mocks.useOperationsOverview.mockReturnValue(
      queryResult({
        ...currentOverview,
        capture: {
          ...currentOverview.capture,
          message: "Worker pool connected through private network",
        },
        check_queue: {
          ...currentOverview.check_queue,
          retrying: 2,
          leased: 4,
          per_organization: [
            {
              organization_id: 18,
              organization_name: "Acme Platform",
              pending: 8,
              running: 3,
              retrying: 2,
              dead: 1,
              leased: 3,
            },
          ],
        },
        maintenance: {
          ...currentOverview.maintenance,
          retry_after_seconds: 120,
          updated_at: "2026-07-17T12:00:00Z",
        },
      }),
    );

    renderPage();

    expect(screen.getByText("Worker pool connected through private network")).toBeInTheDocument();
    expect(screen.getAllByText("Retrying").length).toBeGreaterThan(0);
    expect(screen.getByText("Queue by organization")).toBeInTheDocument();
    expect(screen.getByText("Acme Platform")).toBeInTheDocument();
    expect(screen.getByText("Retry after").nextElementSibling).toHaveTextContent("2 min");
    expect(screen.getByText("Last changed")).toBeInTheDocument();
  });

  it("does not describe externally managed PostgreSQL backups as never run", () => {
    mocks.useOperationsOverview.mockReturnValue(
      queryResult({
        ...currentOverview,
        storage: {
          ...currentOverview.storage,
          last_backup_at: null,
          last_backup_file: null,
        },
      }),
    );

    renderPage();

    expect(screen.getByText("Last backup").nextElementSibling).toHaveTextContent(
      "External / not reported",
    );
  });

  it("distinguishes recent account-email failures from historical failures", () => {
    mocks.useOperationsOverview.mockReturnValue(
      queryResult({
        ...currentOverview,
        status: "degraded",
        account_email_queue: {
          ...currentOverview.account_email_queue,
          failed_total: 19,
          failed_recent: 2,
        },
      }),
    );

    renderPage();

    expect(screen.getByText("Recent delivery failures")).toBeInTheDocument();
    expect(screen.getByText("Failed in current window").nextElementSibling).toHaveTextContent("2");
    expect(screen.getByText("Failed historically").nextElementSibling).toHaveTextContent("19");
  });

  it("shows the degraded signals returned by the platform", () => {
    mocks.useOperationsOverview.mockReturnValue(
      queryResult({
        ...currentOverview,
        status: "degraded",
        database: { backend: "sqlite", reachable: false },
        scheduler: {
          expected: true,
          running: false,
          stale: true,
          last_tick_at: null,
        },
        capture: {
          mode: "in_process",
          status: "unavailable",
          active: null,
          queued: null,
          active_capacity: null,
          queue_capacity: null,
          message: "Browser executable is not available",
        },
        check_queue: {
          ...currentOverview.check_queue,
          dead: 9,
          at_capacity: true,
        },
        delivery_queue: {
          ...currentOverview.delivery_queue,
          exhausted: 3,
        },
        billing_webhooks: {
          ...currentOverview.billing_webhooks,
          processing: 2,
          stale_processing: 1,
          failed: 2,
          last_failed_at: "2026-07-17T12:28:00Z",
        },
        maintenance: { enabled: true, active_requests: 0 },
      }),
    );

    renderPage();

    expect(screen.getByText("Platform service degraded")).toBeInTheDocument();
    expect(screen.getByText("Unreachable")).toBeInTheDocument();
    expect(screen.getAllByText("Stale")).toHaveLength(2);
    expect(screen.getByText("At capacity")).toBeInTheDocument();
    expect(screen.getAllByText("Needs attention")).toHaveLength(2);
    expect(screen.getByText("Stale processing").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Last current failure").nextElementSibling).not.toHaveTextContent("Never");
    expect(screen.getByText("Maintenance active")).toBeInTheDocument();
    expect(screen.getAllByText("Not reported")).toHaveLength(4);
  });

  it("does not request operations telemetry for a non-operator", () => {
    mocks.useCurrentUser.mockReturnValue({
      data: { is_superadmin: false },
      isLoading: false,
    });

    renderPage();

    expect(mocks.useOperationsOverview).toHaveBeenCalledWith(false);
    expect(mocks.useDeadCheckIncidents).not.toHaveBeenCalled();
    expect(screen.getByText("Operator access required")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Operations" })).not.toBeInTheDocument();
  });

  it("shows only tenant recovery when an operator is acting in an organization", () => {
    mocks.useOrg.mockReturnValue({
      actingOrg: { id: 7, name: "Customer" },
      enterOrg: mocks.enterOrg,
    });
    mocks.useDeadCheckIncidents.mockReturnValue(incidentQuery([deadIncident]));

    renderPage();

    expect(mocks.useOperationsOverview).toHaveBeenCalledWith(false);
    expect(mocks.useDeadCheckIncidents).toHaveBeenCalledWith(
      { kind: "tenant", organizationId: 7 },
      true,
    );
    expect(screen.getByRole("heading", { name: "Check recovery" })).toBeInTheDocument();
    expect(screen.getByText("Job #91")).toBeInTheDocument();
    expect(screen.queryByText("Platform operating normally")).not.toBeInTheDocument();
  });

  it("maps an incident to its organization and enters that workspace", async () => {
    mocks.useDeadCheckIncidents.mockReturnValue(incidentQuery([deadIncident]));
    const user = userEvent.setup();

    renderPage();

    expect(screen.getByText("Northwind")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open workspace" }));
    expect(mocks.enterOrg).toHaveBeenCalledWith({ id: 7, name: "Northwind" });
  });

  it("reauthenticates redrive, clears secrets, and reuses its UUID for an exact retry", async () => {
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 7, name: "Customer" }),
    );
    mocks.useCurrentUser.mockReturnValue({
      data: { is_superadmin: true, totp_enabled: true },
      isLoading: false,
    });
    mocks.useOrg.mockReturnValue({
      actingOrg: { id: 7, name: "Customer" },
      enterOrg: mocks.enterOrg,
    });
    mocks.useDeadCheckIncidents.mockReturnValue(incidentQuery([deadIncident]));
    mocks.redriveMutate
      .mockRejectedValueOnce(new ApiError(503, "Recovery queue is temporarily unavailable"))
      .mockResolvedValueOnce({
        created: true,
        job: { ...deadIncident, id: 92, original_job_id: 91, status: "pending" },
      });
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Recover" }));
    fireEvent.change(screen.getByLabelText("Recovery reason"), {
      target: { value: "Worker capacity restored" },
    });
    fireEvent.change(screen.getByLabelText("Incident ticket"), {
      target: { value: "INC-2048" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "operator-secret" },
    });
    fireEvent.change(screen.getByLabelText("Authentication code"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue recovery" }));

    await waitFor(() => expect(mocks.redriveMutate).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.getByLabelText("Authentication code")).toHaveValue("");

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "operator-secret" },
    });
    fireEvent.change(screen.getByLabelText("Authentication code"), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue recovery" }));

    await waitFor(() => expect(mocks.redriveMutate).toHaveBeenCalledTimes(2));
    expect(mocks.stepUpMutate).toHaveBeenNthCalledWith(1, {
      password: "operator-secret",
      totp_code: "123456",
    });
    expect(mocks.stepUpMutate).toHaveBeenNthCalledWith(2, {
      password: "operator-secret",
      totp_code: "654321",
    });
    const firstRequest = mocks.redriveMutate.mock.calls[0][0];
    const secondRequest = mocks.redriveMutate.mock.calls[1][0];
    expect(firstRequest.idempotency_key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
    expect(secondRequest).toEqual(firstRequest);
    expect(await screen.findByText("Recovery job queued")).toBeInTheDocument();
  });

  it("surfaces the support boundary's safe API error in tenant recovery", () => {
    mocks.useOrg.mockReturnValue({
      actingOrg: { id: 7, name: "Customer" },
      enterOrg: mocks.enterOrg,
    });
    mocks.useDeadCheckIncidents.mockReturnValue({
      ...incidentQuery(),
      data: undefined,
      error: new ApiError(403, "Tenant support access is locked"),
      isError: true,
    });

    renderPage();

    expect(screen.getByRole("alert")).toHaveTextContent("Tenant support access is locked");
  });

  it("shows a dedicated loading state while the first snapshot is pending", () => {
    mocks.useOperationsOverview.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      isFetching: true,
      refetch: mocks.refetch,
    });

    renderPage();

    expect(screen.getByText("Loading platform operations", { exact: false }))
      .toBeInTheDocument();
  });

  it("offers a real retry when the initial snapshot fails", async () => {
    mocks.useOperationsOverview.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      isFetching: false,
      refetch: mocks.refetch,
    });
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(mocks.refetch).toHaveBeenCalledTimes(1);
  });

  it("refreshes the real snapshot on demand", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Refresh status" }));

    expect(mocks.refetch).toHaveBeenCalledTimes(1);
  });
});
