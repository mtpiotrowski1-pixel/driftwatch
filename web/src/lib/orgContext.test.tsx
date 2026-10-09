import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ACTING_ORG_STORAGE_KEY,
  ApiError,
  api,
  type ApiRequestOptions,
} from "./api";
import { OrgProvider, useOrg } from "./orgContext";
import { keys, useLogout, useSites } from "./queries";
import type { Branding, Site, User } from "./types";

const USER: User = {
  id: 1,
  email: "operator@example.com",
  name: "Operator",
  is_admin: true,
  is_superadmin: true,
  organization_id: null,
  totp_enabled: true,
  mfa_enrollment_required: false,
  organization_suspended: false,
  acting_organization_id: null,
  acting_organization_name: null,
};

const OLD_SITES = [{ id: 1, name: "Previous org site" }] as Site[];
const NEW_SITES = [{ id: 2, name: "New org site" }] as Site[];
const BRANDING = { brand_name: "Public brand" } as Branding;

function createClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
}

function renderWithOrg(client: QueryClient, child: React.ReactNode) {
  return render(
    <QueryClientProvider client={client}>
      <OrgProvider>{child}</OrgProvider>
    </QueryClientProvider>,
  );
}

function OrgSwitchProbe() {
  const { actingOrg, enterOrg, exitOrg } = useOrg();
  const { data: sites } = useSites();
  return (
    <>
      <span>{actingOrg?.name ?? "Instance"}</span>
      <span>{sites?.[0]?.name ?? "Loading"}</span>
      <button type="button" onClick={() => void enterOrg({ id: 22, name: "New org" })}>
        Enter
      </button>
      <button type="button" onClick={() => void exitOrg()}>
        Exit
      </button>
    </>
  );
}

function LogoutProbe() {
  const { actingOrg } = useOrg();
  const logout = useLogout();
  return (
    <>
      <span>{actingOrg?.name ?? "No acting org"}</span>
      <button type="button" onClick={() => logout.mutate()}>
        Logout
      </button>
    </>
  );
}

function ConfirmedNavigationProbe() {
  const { enterOrg } = useOrg();
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => {
        void enterOrg({ id: 22, name: "Requested name" }).then(() => navigate("/dashboard"));
      }}
    >
      Manage organization
    </button>
  );
}

function RejectedTransitionProbe() {
  const { actingOrg, enterOrg } = useOrg();
  const [error, setError] = useState(false);
  return (
    <>
      <span>{actingOrg?.name ?? "Instance"}</span>
      {error ? <span>Transition rejected</span> : null}
      <button
        type="button"
        onClick={() => {
          void enterOrg({ id: 22, name: "Rejected org" }).catch(() => setError(true));
        }}
      >
        Reject transition
      </button>
    </>
  );
}

describe("organization cache isolation", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("removes observed tenant data before refetching under the new org header", async () => {
    const client = createClient();
    client.setQueryData(keys.me, USER);
    client.setQueryData(keys.sites, OLD_SITES);
    client.setQueryData(keys.branding, BRANDING);
    const requestContexts: Array<string | null> = [];
    vi.spyOn(api, "get").mockImplementation(<T,>(
      path: string,
      _query?: Record<string, string | number | boolean | undefined>,
      options?: ApiRequestOptions,
    ) => {
      const stored = localStorage.getItem(ACTING_ORG_STORAGE_KEY);
      if (path === "/api/auth/me") {
        const requestedId = options?.context?.scope === "organization"
          ? options.context.organizationId
          : null;
        return Promise.resolve({
          ...USER,
          acting_organization_id: requestedId,
          acting_organization_name: requestedId === 22 ? "New org" : null,
        } as T);
      }
      return new Promise<T>(() => {
        requestContexts.push(stored);
      });
    });

    renderWithOrg(client, <OrgSwitchProbe />);
    expect(screen.getByText("Previous org site")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Enter" }));

    expect(screen.queryByText("Previous org site")).not.toBeInTheDocument();
    expect(screen.getByText("Loading")).toBeInTheDocument();
    expect(await screen.findByText("New org")).toBeInTheDocument();
    expect(JSON.parse(requestContexts.at(-1) ?? "null")).toEqual({ id: 22, name: "New org" });
    expect(client.getQueryData(keys.me)).toEqual({
      ...USER,
      acting_organization_id: 22,
      acting_organization_name: "New org",
    });
    expect(client.getQueryData(keys.branding)).toBeUndefined();

    await act(async () => client.setQueryData(keys.sites, NEW_SITES));
    expect(await screen.findByText("New org site")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Exit" }));

    expect(screen.queryByText("New org site")).not.toBeInTheDocument();
    expect(screen.getByText("Instance")).toBeInTheDocument();
    expect(localStorage.getItem(ACTING_ORG_STORAGE_KEY)).toBeNull();
    expect(requestContexts.at(-1)).toBeNull();
  });

  it("navigates only after the server confirms the requested organization", async () => {
    const client = createClient();
    client.setQueryData(keys.me, USER);
    let confirm!: (user: User) => void;
    vi.spyOn(api, "get").mockImplementation(
      () => new Promise<User>((resolve) => {
        confirm = resolve;
      }),
    );

    render(
      <MemoryRouter initialEntries={["/organizations"]}>
        <QueryClientProvider client={client}>
          <OrgProvider>
            <Routes>
              <Route path="/organizations" element={<ConfirmedNavigationProbe />} />
              <Route path="/dashboard" element={<p>Confirmed dashboard</p>} />
            </Routes>
          </OrgProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Manage organization" }));
    expect(screen.queryByText("Confirmed dashboard")).not.toBeInTheDocument();
    expect(localStorage.getItem(ACTING_ORG_STORAGE_KEY)).toBeNull();

    await act(async () => {
      confirm({
        ...USER,
        acting_organization_id: 22,
        acting_organization_name: "Server-confirmed name",
      });
    });

    expect(await screen.findByText("Confirmed dashboard")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(ACTING_ORG_STORAGE_KEY) ?? "null")).toEqual({
      id: 22,
      name: "Server-confirmed name",
    });
  });

  it("rolls storage back when the server rejects an organization transition", async () => {
    const client = createClient();
    const previous = { id: 9, name: "Previous org" };
    localStorage.setItem(ACTING_ORG_STORAGE_KEY, JSON.stringify(previous));
    client.setQueryData(keys.me, {
      ...USER,
      acting_organization_id: previous.id,
      acting_organization_name: previous.name,
    });
    vi.spyOn(api, "get").mockRejectedValue(new ApiError(403, "Forbidden"));

    renderWithOrg(client, <RejectedTransitionProbe />);
    await userEvent.click(screen.getByRole("button", { name: "Reject transition" }));

    expect(await screen.findByText("Transition rejected")).toBeInTheDocument();
    expect(screen.getByText("Previous org")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(ACTING_ORG_STORAGE_KEY) ?? "null")).toEqual(previous);
  });

  it("clears the provider's acting org state when logout replaces the session", async () => {
    const client = createClient();
    client.setQueryData(keys.me, {
      ...USER,
      acting_organization_id: 9,
      acting_organization_name: "Old org",
    });
    client.setQueryData(keys.sites, OLD_SITES);
    client.setQueryData(keys.branding, BRANDING);
    localStorage.setItem(ACTING_ORG_STORAGE_KEY, JSON.stringify({ id: 9, name: "Old org" }));
    vi.spyOn(api, "post").mockResolvedValue(undefined);

    renderWithOrg(client, <LogoutProbe />);
    expect(screen.getByText("Old org")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Logout" }));

    expect(screen.getByText("No acting org")).toBeInTheDocument();
    expect(client.getQueryData(keys.me)).toBeNull();
    expect(client.getQueryData(keys.sites)).toBeUndefined();
    expect(client.getQueryData(keys.branding)).toBeUndefined();
  });

  it("clears a stale requested org after the server rejects it", async () => {
    const client = createClient();
    localStorage.setItem(ACTING_ORG_STORAGE_KEY, JSON.stringify({ id: 404, name: "Deleted org" }));
    let meCalls = 0;
    vi.spyOn(api, "get").mockImplementation(<T,>(path: string) => {
      if (path !== "/api/auth/me") return new Promise<T>(() => undefined);
      meCalls += 1;
      if (meCalls === 1) return Promise.reject(new ApiError(404, "Acting organization not found"));
      return Promise.resolve(USER as T);
    });

    renderWithOrg(client, <OrgSwitchProbe />);

    expect(await screen.findByText("Instance")).toBeInTheDocument();
    expect(meCalls).toBe(2);
    expect(localStorage.getItem(ACTING_ORG_STORAGE_KEY)).toBeNull();
  });
});
