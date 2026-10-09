import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { AuditLog } from "./AuditLog";

const refetch = vi.fn();

vi.mock("@/lib/queries", () => ({
  useCurrentUser: () => ({ data: { is_admin: true }, isLoading: false }),
  useAuditEvents: () => ({
    data: {
      pages: [{
        id: 7,
        occurred_at: "2026-07-17T10:30:00Z",
        actor_user_id: 1,
        actor_email: "operator@example.com",
        actor_is_superadmin: true,
        organization_id: 12,
        action: "organization.updated",
        target_type: "organization",
        target_id: "12",
        target_label: "Acme",
        source_ip: "127.0.0.1",
        details: { changes: { max_sites: { from: 3, to: 10 } } },
      }],
    },
    isLoading: false,
    isError: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    refetch,
  }),
}));

describe("AuditLog", () => {
  beforeEach(() => localStorage.setItem("driftwatch_lang", "en"));

  it("renders the actor, target, and structured change without raw JSON", () => {
    render(
      <I18nProvider>
        <AuditLog />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { name: "Audit log" })).toBeInTheDocument();
    expect(screen.getByText("Organization updated")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText(/operator@example.com/)).toHaveTextContent("127.0.0.1");
    expect(
      screen.getByText(
        (_, element) =>
          element?.classList.contains("rounded-md") === true &&
          element.textContent === "site limit: 3 -> 10",
      ),
    ).toBeInTheDocument();
  });
});
