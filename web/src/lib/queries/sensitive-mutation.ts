import { useCallback, useEffect, useRef, useState } from "react";

interface SensitiveMutationCallbacks<TData, TVariables> {
  onSuccess?: (data: TData, variables: TVariables) => void | Promise<void>;
  onError?: (error: unknown, variables: TVariables) => void | Promise<void>;
  onSettled?: (
    data: TData | undefined,
    error: unknown | null,
    variables: TVariables,
  ) => void | Promise<void>;
}

interface SensitiveMutationOptions<TData, TVariables>
  extends SensitiveMutationCallbacks<TData, TVariables> {
  mutationFn: (variables: TVariables) => Promise<TData>;
}

/**
 * Mutation state for credentials and provider secrets must never enter TanStack's
 * shared mutation cache. This local observer keeps the familiar mutation API but
 * deliberately does not retain variables after the request settles.
 */
export function useSensitiveMutation<TData, TVariables>(
  options: SensitiveMutationOptions<TData, TVariables>,
) {
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const mounted = useRef(true);
  const sequence = useRef(0);
  const [state, setState] = useState<{
    data: TData | undefined;
    error: unknown | null;
    status: "idle" | "pending" | "success" | "error";
  }>({ data: undefined, error: null, status: "idle" });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      sequence.current += 1;
    };
  }, []);

  const execute = useCallback(
    async (
      variables: TVariables,
      callbacks?: SensitiveMutationCallbacks<TData, TVariables>,
    ): Promise<TData> => {
      const call = ++sequence.current;
      setState({ data: undefined, error: null, status: "pending" });
      try {
        const data = await optionsRef.current.mutationFn(variables);
        if (mounted.current && sequence.current === call) {
          setState({ data, error: null, status: "success" });
          await optionsRef.current.onSuccess?.(data, variables);
          await callbacks?.onSuccess?.(data, variables);
          await optionsRef.current.onSettled?.(data, null, variables);
          await callbacks?.onSettled?.(data, null, variables);
        }
        return data;
      } catch (error) {
        if (mounted.current && sequence.current === call) {
          setState({ data: undefined, error, status: "error" });
          await optionsRef.current.onError?.(error, variables);
          await callbacks?.onError?.(error, variables);
          await optionsRef.current.onSettled?.(undefined, error, variables);
          await callbacks?.onSettled?.(undefined, error, variables);
        }
        throw error;
      }
    },
    [],
  );

  const mutateAsync = useCallback(
    (variables: TVariables, callbacks?: SensitiveMutationCallbacks<TData, TVariables>) =>
      execute(variables, callbacks),
    [execute],
  );
  const mutate = useCallback(
    (variables: TVariables, callbacks?: SensitiveMutationCallbacks<TData, TVariables>) => {
      void execute(variables, callbacks).catch(() => undefined);
    },
    [execute],
  );
  const reset = useCallback(() => {
    sequence.current += 1;
    if (mounted.current) setState({ data: undefined, error: null, status: "idle" });
  }, []);

  return {
    data: state.data,
    error: state.error,
    isError: state.status === "error",
    isIdle: state.status === "idle",
    isPending: state.status === "pending",
    isSuccess: state.status === "success",
    mutate,
    mutateAsync,
    reset,
  };
}
