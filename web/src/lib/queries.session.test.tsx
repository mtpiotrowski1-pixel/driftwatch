import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ACTING_ORG_STORAGE_KEY, api } from "./api";
import {
  keys,
  useLogin,
  useLoginTotp,
  useLogout,
  useRegister,
} from "./queries";
import type { Branding, PublicPlan, User } from "./types";

const OLD_USER: User = {
  id: 1,
  email: "old@example.com",
  name: "Old user",
  is_admin: true,
  is_superadmin: true,
  organization_id: null,
  totp_enabled: true,
  mfa_enrollment_required: false,
  organization_suspended: false,
  acting_organization_id: null,
  acting_organization_name: null,
};

const NEW_USER: User = {
  ...OLD_USER,
  id: 2,
  email: "new@example.com",
  name: "New user",
  is_superadmin: false,
  organization_id: 22,
};

const BRANDING = { brand_name: "Driftwatch" } as Branding;
const PUBLIC_PLANS = [{ key: "starter" }] as PublicPlan[];

function createClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper(client: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function seedPreviousSession(client: QueryClient): void {
  client.setQueryData(keys.me, OLD_USER);
  client.setQueryData(keys.sites, [{ id: 101, name: "Previous org site" }]);
  client.setQueryData(keys.settings, { smtp_host: "private.example.com" });
  client.setQueryData(keys.workspaceBranding, BRANDING);
  client.setQueryData(keys.publicPlans, PUBLIC_PLANS);
  localStorage.setItem(ACTING_ORG_STORAGE_KEY, JSON.stringify({ id: 9, name: "Previous org" }));
}

function expectIsolatedSession(client: QueryClient, user: User | null): void {
  expect(client.getQueryData(keys.me)).toEqual(user);
  expect(client.getQueryData(keys.sites)).toBeUndefined();
  expect(client.getQueryData(keys.settings)).toBeUndefined();
  expect(localStorage.getItem(ACTING_ORG_STORAGE_KEY)).toBeNull();

  // Public plans are context-free. Branding is org-aware and must disappear
  // until it has been fetched for the new principal.
  expect(client.getQueryData(keys.workspaceBranding)).toBeUndefined();
  expect(client.getQueryData(keys.publicPlans)).toEqual(PUBLIC_PLANS);
}

describe("authentication query isolation", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("clears a previous session as soon as password login enters a TOTP challenge", async () => {
    const client = createClient();
    seedPreviousSession(client);
    vi.spyOn(api, "post").mockResolvedValue({ totp_required: true, user: null });
    const { result } = renderHook(() => useLogin(), { wrapper: wrapper(client) });

    await act(async () => {
      await result.current.mutateAsync({ email: "new@example.com", password: "secret" });
    });

    expectIsolatedSession(client, null);
  });

  it("sets only the newly authenticated user after password login", async () => {
    const client = createClient();
    seedPreviousSession(client);
    vi.spyOn(api, "post").mockResolvedValue({ totp_required: false, user: NEW_USER });
    const { result } = renderHook(() => useLogin(), { wrapper: wrapper(client) });

    await act(async () => {
      await result.current.mutateAsync({ email: "new@example.com", password: "secret" });
    });

    expectIsolatedSession(client, NEW_USER);
  });

  it("isolates the cache when a TOTP login completes", async () => {
    const client = createClient();
    seedPreviousSession(client);
    vi.spyOn(api, "post").mockResolvedValue(NEW_USER);
    const { result } = renderHook(() => useLoginTotp(), { wrapper: wrapper(client) });

    await act(async () => {
      await result.current.mutateAsync("123456");
    });

    expectIsolatedSession(client, NEW_USER);
  });

  it("isolates the cache when registration creates a session", async () => {
    const client = createClient();
    seedPreviousSession(client);
    client.setQueryData(keys.authCapabilities, { registration_enabled: true, initial_setup_required: true });
    vi.spyOn(api, "post").mockResolvedValue(NEW_USER);
    const { result } = renderHook(() => useRegister(), { wrapper: wrapper(client) });

    await act(async () => {
      await result.current.mutateAsync({
        email: "new@example.com",
        password: "secret123",
        organization_name: "New org",
      });
    });

    expectIsolatedSession(client, NEW_USER);
    expect(client.getQueryData(keys.authCapabilities)).toBeUndefined();
  });

  it("removes all private query data on logout", async () => {
    const client = createClient();
    seedPreviousSession(client);
    vi.spyOn(api, "post").mockResolvedValue(undefined);
    const { result } = renderHook(() => useLogout(), { wrapper: wrapper(client) });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expectIsolatedSession(client, null);
  });
});
