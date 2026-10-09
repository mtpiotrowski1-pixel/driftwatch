import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import {
  ACTING_ORG_STORAGE_KEY,
  api,
  ApiError,
  bindRequestSession,
  currentRequestContext,
  type ApiRequestContext,
} from "../api";
import type { AuthCapabilities, LoginResult, TotpSetup, User } from "../types";
import { ACTING_ORG_CLEARED_EVENT, keys, replaceSession } from "./cache";
import { useSensitiveMutation } from "./sensitive-mutation";

export function useCurrentUser(): UseQueryResult<User | null> {
  return useQuery({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        const user = await api.get<User>("/api/auth/me");
        bindRequestSession(user);
        return user;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          bindRequestSession(null);
          return null;
        }
        // A stored acting-org id can become stale after tenant deletion in
        // another session. The server rejects it fail-closed; clear only that
        // local hint and retry once in the safe instance context.
        if (
          error instanceof ApiError &&
          (error.status === 400 || error.status === 404) &&
          localStorage.getItem(ACTING_ORG_STORAGE_KEY)
        ) {
          localStorage.removeItem(ACTING_ORG_STORAGE_KEY);
          window.dispatchEvent(new Event(ACTING_ORG_CLEARED_EVENT));
          const user = await api.get<User>("/api/auth/me");
          bindRequestSession(user);
          return user;
        }
        throw error;
      }
    },
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useAuthCapabilities() {
  return useQuery({
    queryKey: keys.authCapabilities,
    queryFn: () => api.get<AuthCapabilities>("/api/auth/capabilities"),
    // The first administrator may be created by another browser while this
    // page is open. Refresh the public hint on mount/focus; roles are server-owned.
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
}

export function useLogin() {
  const client = useQueryClient();
  return useSensitiveMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api.post<LoginResult>("/api/auth/login", body),
    // A 2FA challenge is also a session boundary: no data from a previously
    // authenticated account may remain visible while the code is requested.
    onSuccess: (result) => replaceSession(client, result.user),
  });
}

export function useLoginTotp() {
  const client = useQueryClient();
  return useSensitiveMutation({
    mutationFn: (code: string) => api.post<User>("/api/auth/login/totp", { code }),
    onSuccess: (user) => replaceSession(client, user),
  });
}

export function useRequestPasswordReset() {
  return useMutation({
    mutationFn: (email: string) => api.post<void>("/api/auth/request-password-reset", { email }),
  });
}

export function useResetPassword() {
  return useSensitiveMutation({
    mutationFn: (body: { token: string; new_password: string }) =>
      api.post<void>("/api/auth/reset-password", body),
  });
}

export function useTotpSetup() {
  return useSensitiveMutation<TotpSetup, void>({
    mutationFn: () => api.post<TotpSetup>("/api/auth/totp/setup"),
  });
}

export function useTotpEnable() {
  const client = useQueryClient();
  return useSensitiveMutation({
    mutationFn: (code: string) =>
      api.post<{ recovery_codes: string[] }>("/api/auth/totp/enable", { code }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.me }),
  });
}

export function useTotpDisable() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/api/auth/totp/disable"),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.me }),
  });
}

export function useStepUp(context: ApiRequestContext = currentRequestContext) {
  return useSensitiveMutation({
    mutationFn: (body: { password: string; totp_code?: string }) =>
      api.post<void>("/api/auth/step-up", body, { context }),
  });
}

export function useRegister() {
  const client = useQueryClient();
  return useSensitiveMutation({
    mutationFn: (body: {
      email: string;
      password: string;
      name?: string;
      organization_name?: string;
      plan_key?: string;
    }) => api.post<User>("/api/auth/register", body),
    onSuccess: (user) => {
      // A successful first signup consumes initial setup. Drop its old public
      // hint immediately, then ask the server about the remaining access mode.
      void client.resetQueries({ queryKey: keys.authCapabilities, exact: true });
      replaceSession(client, user);
    },
    onError: (error) => {
      // Another installer/browser can consume the first-account claim while
      // this form is open. Refresh only this public capability on a denial.
      if (error instanceof ApiError && error.status === 403) {
        void client.resetQueries({ queryKey: keys.authCapabilities, exact: true });
      }
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/api/auth/logout"),
    onSuccess: () => replaceSession(client, null),
  });
}

export function useChangePassword() {
  return useSensitiveMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api.post<void>("/api/auth/change-password", body),
  });
}
