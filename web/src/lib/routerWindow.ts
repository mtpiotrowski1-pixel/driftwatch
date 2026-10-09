/** A native ViewTransition.ready can reject after its snapshot is cancelled.
 * A rapid second navigation may cause AbortError while the previous DOM
 * update still succeeds. Adapt only the router's window, never global promises
 * or error handlers, and preserve genuine callback/browser failures. */
export function routerWindow(browserWindow: Window): Window {
  const nativeDocument = browserWindow.document;
  const routerDocument = new Proxy(nativeDocument, {
    get(target, property) {
      const value: unknown = Reflect.get(target, property, target);
      if (property !== "startViewTransition" || typeof value !== "function") {
        return typeof value === "function" ? value.bind(target) : value;
      }
      return (update: ViewTransitionUpdateCallback) => {
        const transition = value.call(target, update) as ViewTransition;
        const ready = transition.ready.catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          throw error;
        });
        return new Proxy(transition, {
          get(view, key) {
            if (key === "ready") return ready;
            const member: unknown = Reflect.get(view, key, view);
            return typeof member === "function" ? member.bind(view) : member;
          },
        });
      };
    },
  });
  return new Proxy(browserWindow, {
    get(target, property) {
      if (property === "document") return routerDocument;
      const value: unknown = Reflect.get(target, property, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}
