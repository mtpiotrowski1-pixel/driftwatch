import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";

import { OperationsCard } from "./OperationsCard";

const mocks = vi.hoisted(() => ({
  useAdminCapabilities: vi.fn(),
  useRestoreBackup: vi.fn(),
}));

vi.mock("@/lib/queries", () => ({
  useAdminCapabilities: mocks.useAdminCapabilities,
  useRestoreBackup: mocks.useRestoreBackup,
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
    // Same order as the real dialog: run the action, then close.
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

function renderCard() {
  return render(
    <MemoryRouter>
      <I18nProvider>
        <ToastProvider>
          <OperationsCard />
        </ToastProvider>
      </I18nProvider>
    </MemoryRouter>,
  );
}

describe("OperationsCard", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
    mocks.useAdminCapabilities.mockReturnValue({
      data: { database_backend: "sqlite", sqlite_backup_restore: true, raw_logs_in_product: false },
      isLoading: false,
      isError: false,
    });
    mocks.useRestoreBackup.mockReturnValue({ mutate: vi.fn(), isPending: false, error: null });
  });

  it("opens the file picker once the restore is re-authenticated", async () => {
    const user = userEvent.setup();
    const { container } = renderCard();

    await user.click(screen.getByRole("button", { name: /operations/i, expanded: false }));
    await user.click(screen.getByRole("button", { name: "Restore backup" }));
    await user.click(screen.getByRole("button", { name: /^Verify/ }));

    expect(container.ownerDocument.querySelector('input[type="file"]')).not.toBeNull();
  });
});
