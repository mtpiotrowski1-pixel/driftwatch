import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import type { PickerCapabilities, PickerResult, PickerStatus } from "./types";

const pickerKeys = {
  capabilities: ["picker", "capabilities"] as const,
  status: (sessionId: string) => ["picker", "session", sessionId] as const,
  result: (sessionId: string) => ["picker", "session", sessionId, "result"] as const,
};

export function usePickerCapabilities() {
  return useQuery({
    queryKey: pickerKeys.capabilities,
    queryFn: () => api.get<PickerCapabilities>("/api/picker/capabilities"),
    staleTime: 300_000,
  });
}

export function usePickerStatus(sessionId: string | null) {
  return useQuery({
    queryKey: pickerKeys.status(sessionId ?? ""),
    queryFn: () => api.get<PickerStatus>(`/api/picker/sessions/${sessionId}`),
    enabled: !!sessionId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 4000),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "starting" || state === "waiting" ? 1000 : false;
    },
  });
}

export function usePickerResult(sessionId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: pickerKeys.result(sessionId ?? ""),
    queryFn: () => api.get<PickerResult>(`/api/picker/sessions/${sessionId}/result`),
    enabled: enabled && !!sessionId,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 4000),
  });
}

