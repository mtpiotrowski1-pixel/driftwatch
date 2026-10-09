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
    onVerified: () => void;
    onClose: () => void;
  }) => (
    <button
      type="button"
      onClick={() => {
        onVerified();
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
      mutate: mocks.updateMutate,
      isPending: false,
      error: null,
    });
    mocks.useInviteOperator.mockReturnValue({
      mutate: mocks.inviteMutate,
      isPending: false,
      error: null,
    });
    mocks.useRevokeOperatorSessions.mockReturnValue({
      mutate: mocks.revokeSessionsMutate,
      isPending: false,
      error: null,
    });
    mocks.useResetOperatorTotp.mockReturnValue({
      mutate: mocks.resetTotpMutate,
      isPending: false,
      error: null,
    });
  });

  it("shows truthful operator, MFA, activation, and onboarding states", () => {
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

  it("step-up gates invitation resend and reactivation", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getAllByRole("button", { name: "Send setup link" })[0]);
    await user.click(screen.getByRole("button", { name: "Verify Queue a new setup link?" }));
    expect(mocks.inviteMutate).toHaveBeenCalledWith(undefined, {
      onSuccess: expect.any(Function),
      onError: expect.any(Function),
    });

    await user.click(screen.getByRole("button", { name: "Reactivate" }));
    await user.click(screen.getByRole("button", { name: "Verify Reactivate this operator?" }));
    expect(mocks.updateMutate).toHaveBeenCalledWith(
      { is_active: true },
      { onSuccess: expect.any(Function), onError: expect.any(Function) },
    );
  });

  it("step-up gates operator session revocation and two-factor recovery", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getAllByRole("button", { name: "Revoke sessions" })[0]);
    await user.click(screen.getByRole("button", { name: "Verify Revoke all sessions?" }));
    expect(mocks.useRevokeOperatorSessions).toHaveBeenCalledWith(1, true);
    expect(mocks.revokeSessionsMutate).toHaveBeenCalledWith(undefined, {
      onSuccess: expect.any(Function),
      onError: expect.any(Function),
    });

    await user.click(screen.getByRole("button", { name: "Reset two-factor" }));
    await user.click(
      screen.getByRole("button", { name: "Verify Reset two-factor authentication?" }),
    );
    expect(mocks.useResetOperatorTotp).toHaveBeenCalledWith(1, true);
    expect(mocks.resetTotpMutate).toHaveBeenCalledWith(undefined, {
      onSuccess: expect.any(Function),
      onError: expect.any(Function),
    });
  });
});
