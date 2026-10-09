import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";

import { UsersPage } from "./Users";

const mocks = vi.hoisted(() => ({
  useCurrentUser: vi.fn(),
  useInOrgContext: vi.fn(),
  useOrg: vi.fn(),
  useOrganizations: vi.fn(),
  useUsers: vi.fn(),
}));

vi.mock("@/lib/orgContext", () => ({
  useInOrgContext: mocks.useInOrgContext,
  useOrg: mocks.useOrg,
}));

vi.mock("@/lib/queries", () => ({
  useCurrentUser: mocks.useCurrentUser,
  useOrganizations: mocks.useOrganizations,
  useUsers: mocks.useUsers,
}));

vi.mock("@/components/operators/OperatorIdentities", () => ({
  OperatorIdentities: ({ currentUserId }: { currentUserId: number }) => (
    <h1>Operator control plane for {currentUserId}</h1>
  ),
}));

describe("UsersPage instance scope", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
    mocks.useCurrentUser.mockReturnValue({
      data: {
        id: 1,
        email: "operator@example.com",
        is_admin: true,
        is_superadmin: true,
        organization_id: 7,
      },
      isLoading: false,
    });
    mocks.useInOrgContext.mockReturnValue(false);
    mocks.useOrg.mockReturnValue({ actingOrg: null });
    mocks.useOrganizations.mockReturnValue({ data: [], isLoading: false });
    mocks.useUsers.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it("routes instance access to the dedicated operator control plane", () => {
    render(
      <MemoryRouter initialEntries={["/users"]}>
        <I18nProvider>
          <ToastProvider>
            <UsersPage />
          </ToastProvider>
        </I18nProvider>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: "Operator control plane for 1" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add user" })).not.toBeInTheDocument();
    expect(mocks.useUsers).toHaveBeenCalledWith(false, { scope: "instance" });
    expect(mocks.useOrganizations).toHaveBeenCalledWith(false);
  });
});
