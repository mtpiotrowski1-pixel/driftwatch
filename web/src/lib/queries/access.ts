import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, currentRequestContext, instanceRequestContext, type ApiRequestContext } from "../api";
import type { OperatorIdentity, UserDetail } from "../types";
import { keys, replaceSession } from "./cache";
import { requestInContext } from "./request-context";

export function useUsers(
  enabled = true,
  context: ApiRequestContext = currentRequestContext,
) {
  return useQuery({
    queryKey: keys.users,
    queryFn: () => api.get<UserDetail[]>("/api/users", undefined, { context }),
    enabled,
  });
}

export function useOperators(enabled = true) {
  return useQuery({
    queryKey: keys.operators,
    queryFn: () =>
      api.get<OperatorIdentity[]>("/api/operators", undefined, {
        context: instanceRequestContext,
      }),
    enabled,
  });
}

export function useCreateOperator() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; name?: string }) =>
      requestInContext(instanceRequestContext, () =>
        api.post<OperatorIdentity>("/api/operators", body, {
          context: instanceRequestContext,
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.operators }),
  });
}

export function useUpdateOperator(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email?: string; name?: string | null; is_active?: boolean }) =>
      requestInContext(instanceRequestContext, () =>
        api.patch<OperatorIdentity>(`/api/operators/${id}`, body, {
          context: instanceRequestContext,
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.operators }),
  });
}

export function useInviteOperator(id: number) {
  return useMutation({
    mutationFn: () =>
      requestInContext(instanceRequestContext, () =>
        api.post<void>(`/api/operators/${id}/invite`, undefined, {
          context: instanceRequestContext,
        }),
      ),
  });
}

export function useRevokeOperatorSessions(id: number, clearsCurrentSession = false) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      requestInContext(instanceRequestContext, () =>
        api.post<void>(`/api/operators/${id}/revoke-sessions`, undefined, {
          context: instanceRequestContext,
        }),
      ),
    onSuccess: () => {
      if (clearsCurrentSession) replaceSession(client, null);
    },
  });
}

export function useResetOperatorTotp(id: number, clearsCurrentSession = false) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      requestInContext(instanceRequestContext, () =>
        api.post<void>(`/api/operators/${id}/reset-totp`, undefined, {
          context: instanceRequestContext,
        }),
      ),
    onSuccess: () => {
      if (clearsCurrentSession) {
        replaceSession(client, null);
        return;
      }
      void client.invalidateQueries({ queryKey: keys.operators });
    },
  });
}

export function useCreateUser(context: ApiRequestContext = currentRequestContext) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; name?: string; is_admin?: boolean }) =>
      requestInContext(context, () => api.post<UserDetail>("/api/users", body, { context })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useUpdateUser(
  id: number,
  context: ApiRequestContext = currentRequestContext,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      email?: string;
      name?: string | null;
      is_admin?: boolean;
      is_active?: boolean;
    }) =>
      requestInContext(context, () =>
        api.patch<UserDetail>(`/api/users/${id}`, body, { context }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useInviteUser(id: number, context: ApiRequestContext = currentRequestContext) {
  return useMutation({
    mutationFn: () =>
      requestInContext(context, () =>
        api.post<void>(`/api/users/${id}/invite`, undefined, { context }),
      ),
  });
}

export function useRevokeUserSessions(
  id: number,
  context: ApiRequestContext = currentRequestContext,
) {
  return useMutation({
    mutationFn: () =>
      requestInContext(context, () =>
        api.post<void>(`/api/users/${id}/revoke-sessions`, undefined, { context }),
      ),
  });
}

export function useResetUserTotp(
  id: number,
  context: ApiRequestContext = currentRequestContext,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      requestInContext(context, () =>
        api.post<void>(`/api/users/${id}/reset-totp`, undefined, { context }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useSetPermissions(
  id: number,
  context: ApiRequestContext = currentRequestContext,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { project_ids: number[]; site_ids: number[] }) =>
      requestInContext(context, () =>
        api.put<UserDetail>(`/api/users/${id}/permissions`, body, { context }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}

export function useDeleteUser(context: ApiRequestContext = currentRequestContext) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      requestInContext(context, () => api.del(`/api/users/${id}`, { context })),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.users }),
  });
}
