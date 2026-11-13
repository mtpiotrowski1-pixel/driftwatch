import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";

import { OperatorIdentities } from "./OperatorIdentities";

const mocks = vi.hoisted(() => ({
  createMutate: vi.fn(),
  inviteMutate: vi.fn(),
  resetTotpMutate: vi.fn(),
  revokeSessionsMutate: vi.fn(),
  updateMutate: vi.fn(),
  useCreateOperator: vi.fn(),
  useInviteOperator: vi.fn(),
  useOperators: vi.fn(),
  useResetOperatorTotp: vi.fn(),
  useRevokeOperatorSessions: vi.fn(),
  useUpdateOperator: vi.fn(),
}));

vi.mock("@/lib/queries", () => ({
  useCreateOperator: mocks.useCreateOperator,
  useInviteOperator: mocks.useInviteOperator,
  useOperators: mocks.useOperators,
  useResetOperatorTotp: mocks.useResetOperatorTotp,
  useRevokeOperatorSessions: mocks.useRevokeOperatorSessions,
  useUpdateOperator: mocks.useUpdateOperator,
}));

vi.mock("@/components/StepUpDialog", () => ({
  StepUpDialog: ({
    title,
    onVerified,
    onClose,
  }: {
    title: string;
    onVerified: () => void | Promise<void>;
    onClose: () => void;
  }) => (
    // Same order as the real dialog: await the action, then close and unmount.
    <button
      type="button"
      onClick={async () => {
        await onVerified();
        onClose();
      }}
    >
      Verify {title}
    </button>
  ),
}));

const operators = [
  {
    id: 1,
    email: "owner@example.com",
    name: "Owner",
    is_active: true,
    totp_enabled: true,
    created_at: "2026-01-01T10:00:00Z",
    last_login_at: "2026-07-19T10:00:00Z",
  },
  {
    id: 2,
    email: "recovery@example.com",
    name: "Recovery",
    is_active: false,
    totp_enabled: false,
    created_at: "2026-07-01T10:00:00Z",
    last_login_at: null,
  },
];

function renderPanel() {
  return render(
    <I18nProvider>
      <ToastProvider>
        <OperatorIdentities currentUserId={1} />
      </ToastProvider>
    </I18nProvider>,
  );
}

describe("OperatorIdentities", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
    mocks.createMutate.mockReset();
    mocks.inviteMutate.mockReset();
    mocks.resetTotpMutate.mockReset();
    mocks.revokeSessionsMutate.mockReset();
    mocks.updateMutate.mockReset();
    for (const mutate of [
      mocks.inviteMutate,
      mocks.resetTotpMutate,
      mocks.revokeSessionsMutate,
      mocks.updateMutate,
    ]) {
      mutate.mockResolvedValue(undefined);
    }
    mocks.useOperators.mockReturnValue({
      data: operators,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mocks.useCreateOperator.mockReturnValue({
      mutate: mocks.createMutate,
      isPending: false,
      error: null,
    });
    mocks.useUpdateOperator.mockReturnValue({
      mutateAsync: mocks.updateMutate,
      isPending: false,
      error: null,
    });
    mocks.useInviteOperator.mockReturnValue({
      mutateAsync: mocks.inviteMutate,
      isPending: false,
      error: null,
    });
    mocks.useRevokeOperatorSessions.mockReturnValue({
      mutateAsync: mocks.revokeSessionsMutate,
      isPending: false,
      error: null,
    });
    mocks.useResetOperatorTotp.mockReturnValue({
      mutateAsync: mocks.resetTotpMutate,
      isPending: false,
      error: null,
    });
  });

  it("shows each operator's MFA, activation and onboarding state", () => {
    renderPanel();

    expect(screen.getByRole("heading", { name: "Operator identities" })).toBeInTheDocument();
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("2FA active")).toBeInTheDocument();
    expect(screen.getByText("2FA not enrolled")).toBeInTheDocument();
    expect(screen.getByText("First sign-in pending")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    const setupLinks = screen.getAllByRole("button", { name: "Send setup link" });
    expect(setupLinks).toHaveLength(2);
    expect(setupLinks[1]).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Revoke sessions" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Reset two-factor" })).toHaveLength(1);
  });

  it("step-up gates creation and queues an invitation without claiming delivery", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Add operator" }));
    await user.type(screen.getByLabelText("Email"), "new-operator@example.com");
    await user.type(screen.getByLabelText("Name"), "New operator");
    await user.click(screen.getByRole("button", { name: "Create operator" }));
    expect(mocks.createMutate).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Verify Confirm operator creation",
        hidden: true,
      }),
    );
    expect(mocks.createMutate).toHaveBeenCalledWith(
      { email: "new-operator@example.com", name: "New operator" },
      { onSuccess: expect.any(Function) },
    );
    expect(screen.queryByText(/setup link sent/i)).not.toBeInTheDocument();
  });

  it("confirms a resent invitation and a reactivation after the dialog closes", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getAllByRole("button", { name: "Send setup link" })[0]);
    await user.click(screen.getByRole("button", { name: "Verify Queue a new setup link?" }));
    expect(mocks.inviteMutate).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Setup link queued")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reactivate" }));
    await user.click(screen.getByRole("button", { name: "Verify Reactivate this operator?" }));
    expect(mocks.updateMutate).toHaveBeenCalledWith({ is_active: true });
    expect(await screen.findByText("Operator reactivated")).toBeInTheDocument();
  });

  it("confirms session revocation and two-factor reset for the current operator", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getAllByRole("button", { name: "Revoke sessions" })[0]);
    await user.click(screen.getByRole("button", { name: "Verify Revoke all sessions?" }));
    expect(mocks.useRevokeOperatorSessions).toHaveBeenCalledWith(1, true);
    expect(mocks.revokeSessionsMutate).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("All sessions revoked")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reset two-factor" }));
    await user.click(
      screen.getByRole("button", { name: "Verify Reset two-factor authentication?" }),
    );
    expect(mocks.useResetOperatorTotp).toHaveBeenCalledWith(1, true);
    expect(mocks.resetTotpMutate).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Two-factor authentication reset")).toBeInTheDocument();
  });
});
