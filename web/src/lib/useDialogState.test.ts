import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";

import { useDialogState } from "./useDialogState";

it("keeps an inert closing subject only until its own exit finishes", () => {
  const { result } = renderHook(() => useDialogState<{ id: number } | null>(null));
  act(() => result.current.setValue({ id: 1 }));
  act(() => result.current.close());
  expect(result.current.open).toBe(false);
  expect(result.current.value).toEqual({ id: 1 });
  act(() => result.current.onClosed());
  expect(result.current.value).toBeNull();
});

it("never lets an old exit clear a new subject, even if the new dialog is already closing", () => {
  const { result } = renderHook(() => useDialogState<{ id: number } | null>(null));
  act(() => result.current.setValue({ id: 1 }));
  act(() => result.current.close());
  const firstExit = result.current.onClosed;
  const firstKey = result.current.key;
  act(() => result.current.setValue({ id: 2 }));
  expect(result.current.key).not.toBe(firstKey);
  act(() => firstExit());
  expect(result.current.open).toBe(true);
  expect(result.current.value).toEqual({ id: 2 });
  act(() => result.current.close());
  act(() => firstExit());
  expect(result.current.value).toEqual({ id: 2 });
  act(() => result.current.onClosed());
  expect(result.current.value).toBeNull();
});

it("resets immediately and gives a reopened identical subject a fresh form key", () => {
  const { result } = renderHook(() => useDialogState(false));
  act(() => result.current.setValue(true));
  const originalKey = result.current.key;
  act(() => result.current.close());
  const oldExit = result.current.onClosed;
  act(() => result.current.setValue(false));
  expect(result.current.value).toBe(false);
  expect(result.current.key).toBeUndefined();
  act(() => result.current.setValue(true));
  expect(result.current.key).not.toBe(originalKey);
  act(() => oldExit());
  expect(result.current.value).toBe(true);
  expect(result.current.open).toBe(true);
});
