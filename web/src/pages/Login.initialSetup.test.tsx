import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { ACTING_ORG_STORAGE_KEY, ApiError, api, bindRequestSession, type ApiRequestOptions } from "@/lib/api";
import { OrgProvider, useOrg } from "@/lib/orgContext";
import { useCurrentUser } from "@/lib/queries";
import type { User } from "@/lib/types";

import { Login } from "./Login";

const OWNER: User = {
  id: 1, email: "owner@example.com", name: "Owner", is_admin: true,
  is_superadmin: true, organization_id: 12, totp_enabled: false,
  mfa_enrollment_required: false, organization_suspended: false,
  acting_organization_id: null, acting_organization_name: null,
};

function Destination({ title }: { title: string; }) {
  const { actingOrg } = useOrg();
  const { data: user } = useCurrentUser();
  return <><h1>{title}</h1><p>{actingOrg?.name}</p><p>{user?.acting_organization_id}</p></>;
}

function setup({ mfaRequired = false, rejectWorkspace = false, rejectSignup = false } = {}) {
  let registered = false;
  let claimed = false;
  let rejected = rejectWorkspace;
  const account = { ...OWNER, mfa_enrollment_required: mfaRequired };
  const transitions: ApiRequestOptions[] = [];
  const get = vi.spyOn(api, "get").mockImplementation(async <T,>(path: string, _query?: Record<string, string | number | boolean | undefined>, options?: ApiRequestOptions) => {
    if (path === "/api/auth/capabilities") return { registration_enabled: !claimed, initial_setup_required: !claimed } as T;
    if (path !== "/api/auth/me") throw new Error(`Unexpected GET ${path}`);
    if (!registered) throw new ApiError(401, "Not authenticated");
    if (options?.context?.scope === "organization") {
      transitions.push(options);
      if (rejected) throw new ApiError(403, "Workspace access was not confirmed");
      return { ...account, acting_organization_id: options.context.organizationId, acting_organization_name: "Server-confirmed workspace" } as T;
    }
    return account as T;
  });
  const post = vi.spyOn(api, "post").mockImplementation(async <T,>(path: string) => {
    if (path !== "/api/auth/register") throw new Error(`Unexpected POST ${path}`);
    claimed = true;
    if (rejectSignup) throw new ApiError(403, "Another account has already configured this installation");
    registered = true;
    return account as T;
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}><OrgProvider><I18nProvider>
      <MemoryRouter initialEntries={["/login"]}><Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<Destination title="Your monitoring workspace" />} />
        <Route path="/settings" element={<Destination title="Enroll administrator MFA" />} />
        <Route path="/operations" element={<Destination title="Instance operations" />} />
      </Routes></MemoryRouter>
    </I18nProvider></OrgProvider></QueryClientProvider>,
  );
  return { get, post, transitions, allowWorkspace: () => { rejected = false; } };
}

async function createAdministrator() {
  const user = userEvent.setup();
  await screen.findByRole("heading", { name: "Set up your installation" });
  await user.type(screen.getByLabelText("Workspace name"), "My requested name");
  await user.type(screen.getByLabelText("Email"), "owner@example.com");
  await user.type(screen.getByLabelText("Password"), "password123");
  await user.click(screen.getAllByRole("button", { name: "Create administrator account" }).at(-1)!);
  return user;
}

describe("initial administrator workspace transition", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("driftwatch_lang", "en");
    bindRequestSession(null);
    vi.restoreAllMocks();
  });

  it("opens the owned workspace only after the canonical server confirmation", async () => {
    const probe = setup();
    await createAdministrator();
    expect(await screen.findByRole("heading", { name: "Your monitoring workspace" })).toBeInTheDocument();
    expect(screen.getByText("Server-confirmed workspace")).toBeInTheDocument();
    expect(probe.transitions).toEqual([{ context: { scope: "organization", organizationId: 12 }, allowContextTransition: true }]);
    expect(JSON.parse(localStorage.getItem(ACTING_ORG_STORAGE_KEY)!)).toEqual({ id: 12, name: "Server-confirmed workspace" });
    expect(probe.post.mock.calls[0]?.slice(0, 2)).toEqual(["/api/auth/register", {
      email: "owner@example.com", password: "password123", name: undefined, organization_name: "My requested name",
    }]);
  });

  it("keeps required MFA enrollment ahead of monitoring after confirming the workspace", async () => {
    setup({ mfaRequired: true });
    await createAdministrator();
    expect(await screen.findByRole("heading", { name: "Enroll administrator MFA" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Your monitoring workspace" })).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(ACTING_ORG_STORAGE_KEY)!).id).toBe(12);
  });

  it("retains the created account and retries a rejected confirmation without registering again", async () => {
    const probe = setup({ rejectWorkspace: true });
    const user = await createAdministrator();
    expect(await screen.findByRole("alert")).toHaveTextContent("Workspace access was not confirmed");
    expect(localStorage.getItem(ACTING_ORG_STORAGE_KEY)).toBeNull();
    expect(screen.queryByRole("heading", { name: "Instance operations" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    probe.allowWorkspace();
    await user.click(screen.getByRole("button", { name: "Open my workspace" }));
    expect(await screen.findByRole("heading", { name: "Your monitoring workspace" })).toBeInTheDocument();
    expect(probe.post).toHaveBeenCalledTimes(1);
    expect(probe.transitions).toHaveLength(2);
  });

  it("refreshes a consumed claim and offers sign-in when another first signup wins", async () => {
    const probe = setup({ rejectSignup: true });
    await createAdministrator();
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Another account has already configured this installation");
    expect(screen.queryByRole("button", { name: "Create administrator account" })).not.toBeInTheDocument();
    expect(screen.queryByText(/The first account becomes/)).not.toBeInTheDocument();
    expect(probe.transitions).toHaveLength(0);
    expect(probe.get.mock.calls.filter(call => call[0] === "/api/auth/capabilities")).toHaveLength(2);
  });
});
