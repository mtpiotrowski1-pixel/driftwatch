import { afterEach, expect, it, vi } from "vitest";

import { routerWindow } from "./routerWindow";

const original = Object.getOwnPropertyDescriptor(document, "startViewTransition");

afterEach(() => {
  if (original) Object.defineProperty(document, "startViewTransition", original);
  else Reflect.deleteProperty(document, "startViewTransition");
});

function nativeTransition(ready: Promise<void>) {
  const finished = Promise.resolve();
  const view = {
    ready,
    finished,
    updateCallbackDone: finished,
    skipTransition() { expect(this).toBe(view); },
  };
  const start = vi.fn(function (this: Document) { expect(this).toBe(document); return view; });
  Object.defineProperty(document, "startViewTransition", { configurable: true, value: start });
  return view;
}

it("settles a cancelled snapshot without swallowing its finished/update promises or replacing the global API", async () => {
  const native = nativeTransition(Promise.reject(new DOMException("Transition was skipped", "AbortError")));
  const globalApi = document.startViewTransition;
  const adapted = routerWindow(window).document.startViewTransition(() => undefined);
  await expect(adapted.ready).resolves.toBeUndefined();
  expect(adapted.finished).toBe(native.finished);
  expect(adapted.updateCallbackDone).toBe(native.updateCallbackDone);
  adapted.skipTransition();
  expect(document.startViewTransition).toBe(globalApi);
});

it.each([
  new DOMException("Invalid snapshot", "InvalidStateError"),
  new Error("A genuine update callback failure"),
])("keeps real transition errors observable: %s", async (failure) => {
  nativeTransition(Promise.reject(failure));
  const adapted = routerWindow(window).document.startViewTransition(() => undefined);
  await expect(adapted.ready).rejects.toBe(failure);
});

it("preserves ordinary native window/document APIs in browsers without transitions", () => {
  Reflect.deleteProperty(document, "startViewTransition");
  const adapted = routerWindow(window);
  expect(adapted.document.startViewTransition).toBeUndefined();
  expect(adapted.location).toBe(window.location);
  expect(adapted.document.createElement("button")).toBeInstanceOf(HTMLButtonElement);
});
