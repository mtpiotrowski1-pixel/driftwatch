import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";
import { ACTING_ORG_STORAGE_KEY } from "@/lib/api";

import { SupportAccessBanner } from "./SupportAccessBanner";

const mocks = vi.hoisted(() => ({
  useSupportAccess: vi.fn(),
  useGrantSupportAccess: vi.fn(),
  useRevokeSupportAccess: vi.fn(),
  useCurrentUser: vi.fn(),
  useStepUp: vi.fn(),
  refetch: vi.fn(),
  grant: vi.fn(),
  revoke: vi.fn(),
  stepUp: vi.fn(),
  clearTenantCache: vi.fn(),
  reset: vi.fn(),
}));

vi.mock("@/lib/supportAccess", () => ({
  useSupportAccess: mocks.useSupportAccess,
  useGrantSupportAccess: mocks.useGrantSupportAccess,
  useRevokeSupportAccess: mocks.useRevokeSupportAccess,
  clearSupportTenantCache: mocks.clearTenantCache,
}));

vi.mock("@/lib/queries", () => ({
  useCurrentUser: mocks.useCurrentUser,
  useStepUp: mocks.useStepUp,
}));

const ORGANIZATION = { id: 42, name: "Northwind Operations" };

function accessState(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      required: true,
      access_enabled: false,
      organization_id: ORGANIZATION.id,
      expires_at: null,
    },
    isLoading: false,
    isError: false,
    refetch: mocks.refetch,
    ...overrides,
  };
}

function renderBanner(onExit = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ToastProvider>
          <SupportAccessBanner
            organizationId={ORGANIZATION.id}
            organizationName={ORGANIZATION.name}
            onExit={onExit}
          />
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return onExit;
}

describe("SupportAccessBanner", () => {
  beforeEach(() => {
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: ORGANIZATION.id, name: ORGANIZATION.name }),
    );
    localStorage.setItem("driftwatch_lang", "en");
    mocks.refetch.mockReset().mockResolvedValue(undefined);
    mocks.grant.mockReset().mockResolvedValue(undefined);
    mocks.revoke.mockReset().mockResolvedValue(undefined);
    mocks.stepUp.mockReset().mockResolvedValue(undefined);
    mocks.clearTenantCache.mockReset();
    mocks.reset.mockReset();
    mocks.useSupportAccess.mockReset().mockReturnValue(accessState());
    mocks.useGrantSupportAccess.mockReset().mockReturnValue({
      mutateAsync: mocks.grant,
      isPending: false,
      error: null,
      reset: mocks.reset,
    });
    mocks.useRevokeSupportAccess.mockReset().mockReturnValue({
      mutateAsync: mocks.revoke,
      isPending: false,
      error: null,
      isError: false,
      reset: mocks.reset,
    });
    mocks.useCurrentUser.mockReset().mockReturnValue({
      data: { totp_enabled: true },
    });
    mocks.useStepUp.mockReset().mockReturnValue({
      mutateAsync: mocks.stepUp,
      isPending: false,
      error: null,
      isError: false,
      reset: mocks.reset,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("fails closed when the API response belongs to another organization", () => {
    mocks.useSupportAccess.mockReturnValue(
      accessState({
        data: {
          required: true,
          access_enabled: true,
          organization_id: 7,
          expires_at: new Date(Date.now() + 60_000).toISOString(),
        },
      }),
    );

    renderBanner();

    expect(screen.getByText("Support access could not be verified")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request support access" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("revokes before exit when the current grant state cannot be loaded", async () => {
    mocks.useSupportAccess.mockReturnValue(
      accessState({ data: undefined, isError: true }),
    );
    const onExit = vi.fn();
    const user = userEvent.setup();
    renderBanner(onExit);

    await user.click(screen.getByRole("button", { name: "Exit organization" }));

    await waitFor(() => expect(onExit).toHaveBeenCalledTimes(1));
    expect(mocks.revoke).toHaveBeenCalledTimes(1);
    expect(mocks.revoke.mock.invocationCallOrder[0]).toBeLessThan(
      onExit.mock.invocationCallOrder[0],
    );
  });

  it("preserves the local-instance workflow when a support grant is not required", () => {
    mocks.useSupportAccess.mockReturnValue(
      accessState({
        data: {
          required: false,
          access_enabled: true,
          organization_id: ORGANIZATION.id,
          expires_at: null,
        },
      }),
    );

    renderBanner();

    expect(screen.getByText(/Managing Northwind Operations/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request support access" })).not.toBeInTheDocument();
  });

  it("validates audit metadata and performs step-up before granting access", async () => {
    const user = userEvent.setup();
    renderBanner();

    expect(screen.getByText("Support access locked")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Request support access" }));

    const reason = screen.getByLabelText("Reason for access");
    await user.type(reason, "  123456789  ");
    await user.type(screen.getByLabelText("Support ticket"), "   ");
    await user.type(screen.getByLabelText("Password"), "operator-secret");
    await user.type(screen.getByLabelText("Authentication code"), "123456");
    await user.click(screen.getByRole("button", { name: "Enable temporary access" }));

    expect(screen.getByRole("alert")).toHaveTextContent("at least 10 characters");
    expect(mocks.stepUp).not.toHaveBeenCalled();

    await user.clear(reason);
    await user.type(reason, "  Investigating customer alert  ");
    await user.type(screen.getByLabelText("Password"), "operator-secret");
    await user.type(screen.getByLabelText("Authentication code"), "123456");
    await user.click(screen.getByRole("button", { name: "Enable temporary access" }));

    await waitFor(() => expect(mocks.grant).toHaveBeenCalledTimes(1));
    expect(mocks.stepUp).toHaveBeenCalledWith({
      password: "operator-secret",
      totp_code: "123456",
    });
    expect(mocks.grant).toHaveBeenCalledWith({
      reason: "Investigating customer alert",
      ticket: undefined,
    });
    expect(mocks.stepUp.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.grant.mock.invocationCallOrder[0],
    );
  });

  it("clears reauthentication secrets and stops when step-up fails", async () => {
    mocks.stepUp.mockRejectedValueOnce(new Error("step-up rejected"));
    const user = userEvent.setup();
    renderBanner();

    await user.click(screen.getByRole("button", { name: "Request support access" }));
    await user.type(screen.getByLabelText("Reason for access"), "Investigating customer alert");
    const password = screen.getByLabelText("Password");
    const code = screen.getByLabelText("Authentication code");
    await user.type(password, "operator-secret");
    await user.type(code, "123456");
    await user.click(screen.getByRole("button", { name: "Enable temporary access" }));

    await waitFor(() => expect(mocks.stepUp).toHaveBeenCalledTimes(1));
    expect(mocks.grant).not.toHaveBeenCalled();
    expect(password).toHaveValue("");
    expect(code).toHaveValue("");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("expires locally and revalidates the server state", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-17T10:00:00.000Z"));
    mocks.useSupportAccess.mockReturnValue(
      accessState({
        data: {
          required: true,
          access_enabled: true,
          organization_id: ORGANIZATION.id,
          expires_at: "2026-07-17T10:00:01.000Z",
        },
      }),
    );

    renderBanner();
    expect(screen.getByText("Support access active")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1_100));

    expect(screen.getByText("Support access locked")).toBeInTheDocument();
    expect(mocks.refetch).toHaveBeenCalledTimes(1);
    expect(mocks.clearTenantCache).toHaveBeenCalledTimes(1);
  });

  it("revokes an active grant before leaving and blocks exit on revoke failure", async () => {
    mocks.useSupportAccess.mockReturnValue(
      accessState({
        data: {
          required: true,
          access_enabled: true,
          organization_id: ORGANIZATION.id,
          expires_at: new Date(Date.now() + 60_000).toISOString(),
        },
      }),
    );
    const onExit = vi.fn();
    const user = userEvent.setup();
    renderBanner(onExit);

    await user.click(screen.getByRole("button", { name: "Exit organization" }));
    await waitFor(() => expect(onExit).toHaveBeenCalledTimes(1));
    expect(mocks.revoke).toHaveBeenCalledTimes(1);
    expect(mocks.revoke.mock.invocationCallOrder[0]).toBeLessThan(
      onExit.mock.invocationCallOrder[0],
    );

    onExit.mockClear();
    mocks.revoke.mockRejectedValueOnce(new Error("revoke failed"));
    await user.click(screen.getByRole("button", { name: "Exit organization" }));
    await waitFor(() => expect(mocks.revoke).toHaveBeenCalledTimes(2));
    expect(onExit).not.toHaveBeenCalled();
  });
});
