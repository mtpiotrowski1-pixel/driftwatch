import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ACTING_ORG_STORAGE_KEY,
  RequestContextChangedError,
  api,
  organizationRequestContext,
} from "./api";
import {
  useCreateBillingCheckout,
  useCreateSite,
  useLogin,
  useSensitiveMutation,
  useStepUp,
  useUpdateSettings,
  useUpdateSite,
} from "./queries";
import type { HostedBillingSession, User } from "./types";

const USER = {
  id: 4,
  email: "admin@example.com",
  name: "Admin",
  is_admin: true,
  is_superadmin: false,
  organization_id: 7,
  totp_enabled: true,
  mfa_enrollment_required: false,
  organization_suspended: false,
  acting_organization_id: null,
  acting_organization_name: null,
} satisfies User;

function createClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper(client: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function expectNoCachedMutations(client: QueryClient): void {
  expect(client.getMutationCache().getAll()).toHaveLength(0);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("sensitive mutation isolation", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("never stores step-up credentials in TanStack Mutation Cache", async () => {
    const client = createClient();
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 7, name: "Acme" }),
    );
    vi.spyOn(api, "post").mockResolvedValue(undefined);
    const { result } = renderHook(
      () => useStepUp(organizationRequestContext(7)),
      { wrapper: wrapper(client) },
    );

    await act(async () => {
      await result.current.mutateAsync({
        password: "plain-password",
        totp_code: "123456",
      });
    });

    expectNoCachedMutations(client);
  });

  it("keeps login passwords and settings provider secrets out of the shared cache", async () => {
    const client = createClient();
    vi.spyOn(api, "post").mockResolvedValue({ totp_required: false, user: USER });
    vi.spyOn(api, "put").mockResolvedValue({ openai_api_key_configured: true });

    const login = renderHook(() => useLogin(), { wrapper: wrapper(client) });
    await act(async () => {
      await login.result.current.mutateAsync({
        email: USER.email,
        password: "login-secret",
      });
    });
    expectNoCachedMutations(client);
    login.unmount();

    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 7, name: "Acme" }),
    );
    const settings = renderHook(
      () => useUpdateSettings(organizationRequestContext(7)),
      { wrapper: wrapper(client) },
    );
    await act(async () => {
      await settings.result.current.mutateAsync({
        openai_api_key: "sk-plain-provider-secret",
        smtp_password: "smtp-plain-secret",
      });
    });

    expectNoCachedMutations(client);
  });

  it("keeps browser fill secrets out of the shared create and update mutation cache", async () => {
    const client = createClient();
    const payload = { interaction_steps: [{ action: "fill" as const, selector: "#password", secret_value: "synthetic-fill-password" }] };
    vi.spyOn(api, "post").mockResolvedValue({ id: 1 });
    vi.spyOn(api, "patch").mockResolvedValue({ id: 1 });
    const create = renderHook(() => useCreateSite(), { wrapper: wrapper(client) });
    const update = renderHook(() => useUpdateSite(1), { wrapper: wrapper(client) });
    await act(async () => { await create.result.current.mutateAsync(payload); await update.result.current.mutateAsync(payload); });
    expectNoCachedMutations(client);
  });

  it("rejects a pending organization result when another tab changes context", async () => {
    const client = createClient();
    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 7, name: "Acme" }),
    );
    let finishRequest!: (session: HostedBillingSession) => void;
    const post = vi.spyOn(api, "post").mockImplementation(
      () => new Promise<HostedBillingSession>((resolve) => {
        finishRequest = resolve;
      }),
    );
    const { result } = renderHook(() => useCreateBillingCheckout(7), {
      wrapper: wrapper(client),
    });

    const pending = result.current.mutateAsync({
      billing_price_id: 11,
      idempotency_key: "checkout-fixed",
      accepted_terms_version: "terms-1",
      accepted_privacy_version: "privacy-1",
      accepted_terms_sha256: "a".repeat(64),
      accepted_privacy_sha256: "b".repeat(64),
    });
    await waitFor(() => expect(post).toHaveBeenCalledOnce());

    localStorage.setItem(
      ACTING_ORG_STORAGE_KEY,
      JSON.stringify({ id: 8, name: "Other org" }),
    );
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: ACTING_ORG_STORAGE_KEY,
        oldValue: JSON.stringify({ id: 7, name: "Acme" }),
        newValue: JSON.stringify({ id: 8, name: "Other org" }),
      }),
    );

    await act(async () => {
      finishRequest({
        url: "https://billing.example.test/session",
        expires_at: null,
      });
      await expect(pending).rejects.toBeInstanceOf(RequestContextChangedError);
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(post).toHaveBeenCalledWith(
      "/api/billing/checkout",
      expect.any(Object),
      { context: { scope: "organization", organizationId: 7 } },
    );
  });

  it("keeps the latest response when an older sensitive request finishes later", async () => {
    const client = createClient();
    const older = deferred<string>();
    const newer = deferred<string>();
    const onSuccess = vi.fn();
    const onSettled = vi.fn();
    const olderCallback = vi.fn();
    const newerCallback = vi.fn();
    const mutationFn = vi.fn<(_: string) => Promise<string>>()
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);
    const { result } = renderHook(() => useSensitiveMutation({
      mutationFn,
      onSuccess,
      onSettled,
    }), { wrapper: wrapper(client) });

    let first!: Promise<string>;
    let second!: Promise<string>;
    act(() => {
      first = result.current.mutateAsync("older request", { onSuccess: olderCallback });
      second = result.current.mutateAsync("newer request", { onSuccess: newerCallback });
    });
    await act(async () => {
      newer.resolve("latest response");
      await expect(second).resolves.toBe("latest response");
    });
    await act(async () => {
      older.resolve("stale response");
      await expect(first).resolves.toBe("stale response");
    });

    expect(result.current.data).toBe("latest response");
    expect(result.current.isSuccess).toBe(true);
    expect(onSuccess).toHaveBeenCalledExactlyOnceWith("latest response", "newer request");
    expect(onSettled).toHaveBeenCalledExactlyOnceWith("latest response", null, "newer request");
    expect(newerCallback).toHaveBeenCalledExactlyOnceWith("latest response", "newer request");
    expect(olderCallback).not.toHaveBeenCalled();
    expectNoCachedMutations(client);
  });

  it("does not restore a dismissed sensitive result when its request completes", async () => {
    const client = createClient();
    const request = deferred<string>();
    const onSuccess = vi.fn();
    const onSettled = vi.fn();
    const { result } = renderHook(() => useSensitiveMutation<string, void>({
      mutationFn: () => request.promise,
      onSuccess,
      onSettled,
    }), { wrapper: wrapper(client) });

    let pending!: Promise<string>;
    act(() => { pending = result.current.mutateAsync(); });
    expect(result.current.isPending).toBe(true);
    act(() => { result.current.reset(); });
    await act(async () => {
      request.resolve("dismissed response");
      await expect(pending).resolves.toBe("dismissed response");
    });

    expect(result.current.isIdle).toBe(true);
    expect(result.current.data).toBeUndefined();
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onSettled).not.toHaveBeenCalled();
    expectNoCachedMutations(client);
  });

  it("does not run late error callbacks after leaving the sensitive form", async () => {
    const client = createClient();
    const request = deferred<void>();
    const onError = vi.fn();
    const onSettled = vi.fn();
    const formCallback = vi.fn();
    const { result, unmount } = renderHook(() => useSensitiveMutation<void, void>({
      mutationFn: () => request.promise,
      onError,
      onSettled,
    }), { wrapper: wrapper(client) });

    let pending!: Promise<void>;
    act(() => { pending = result.current.mutateAsync(undefined, { onError: formCallback }); });
    unmount();
    const failure = new Error("Request failed after navigation");
    await act(async () => {
      request.reject(failure);
      await expect(pending).rejects.toBe(failure);
    });

    expect(onError).not.toHaveBeenCalled();
    expect(onSettled).not.toHaveBeenCalled();
    expect(formCallback).not.toHaveBeenCalled();
    expectNoCachedMutations(client);
  });
});
