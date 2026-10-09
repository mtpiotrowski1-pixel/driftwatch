import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "../api";
import type { Notification, Recipient, Substitution } from "../types";
import { keys, liveQueryOptions } from "./cache";

export function useRecipients() {
  return useQuery({
    queryKey: keys.recipients,
    queryFn: () => api.get<Recipient[]>("/api/recipients"),
  });
}

export function useCreateRecipient() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; name?: string }) =>
      api.post<Recipient>("/api/recipients", body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.recipients }),
  });
}

export function useUpdateRecipient(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name?: string | null; active?: boolean }) =>
      api.patch<Recipient>(`/api/recipients/${id}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.recipients }),
  });
}

export function useDeleteRecipient() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/recipients/${id}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.recipients });
      void client.invalidateQueries({ queryKey: keys.sites });
      void client.invalidateQueries({ queryKey: keys.projects });
      void client.invalidateQueries({ queryKey: ["substitutions"] });
    },
  });
}

export function useNotifications(status?: string) {
  const pageSize = 100;
  return useInfiniteQuery({
    queryKey: keys.notifications(status),
    queryFn: ({ pageParam }) => api.get<Notification[]>("/api/notifications", {
      status,
      limit: pageSize,
      before_id: pageParam || undefined,
    }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.length === pageSize ? lastPage.at(-1)?.id : undefined,
    placeholderData: keepPreviousData,
    ...liveQueryOptions,
  });
}

/** The delivery audit rows for one change — who was mailed and what happened.
 * Shares the "notifications" key prefix so retry/re-analyze invalidation
 * refreshes this list too. */
export function useNotificationsForChange(changeId: number) {
  return useQuery({
    queryKey: keys.notificationsForChange(changeId),
    queryFn: () => api.get<Notification[]>("/api/notifications", { change_id: changeId }),
    ...liveQueryOptions,
  });
}

export function useSubstitutions(recipientId: number) {
  return useQuery({
    queryKey: keys.substitutions(recipientId),
    queryFn: () => api.get<Substitution[]>(`/api/recipients/${recipientId}/substitutions`),
  });
}

export function useAddSubstitution(recipientId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      substitute_email: string;
      substitute_name?: string;
      start_date: string;
      end_date: string;
      project_id?: number;
      site_id?: number;
    }) => api.post<Substitution>(`/api/recipients/${recipientId}/substitutions`, body),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: keys.substitutions(recipientId) }),
  });
}

export function useDeleteSubstitution(recipientId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (substitutionId: number) =>
      api.del(`/api/recipients/substitutions/${substitutionId}`),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: keys.substitutions(recipientId) }),
  });
}
