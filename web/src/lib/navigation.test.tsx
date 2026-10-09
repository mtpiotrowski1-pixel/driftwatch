import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { createBrowserRouter, RouterProvider, useBlocker, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Link, useNavigate } from "./navigation";

const preferences = vi.hoisted(() => ({ reduceMotion: false }));
vi.mock("motion/react", () => ({ useReducedMotion: () => preferences.reduceMotion }));

const originalTransition = Object.getOwnPropertyDescriptor(document, "startViewTransition");

beforeEach(() => {
  preferences.reduceMotion = false;
  window.history.replaceState({}, "", "/motion-editor");
});

afterEach(() => {
  if (originalTransition) Object.defineProperty(document, "startViewTransition", originalTransition);
  else Reflect.deleteProperty(document, "startViewTransition");
});

function installSnapshotApi() {
  const start = vi.fn((update: () => Promise<void>) => {
    const finished = Promise.resolve().then(update);
    return { ready: Promise.resolve(), finished, updateCallbackDone: finished, skipTransition: vi.fn() };
  });
  Object.defineProperty(document, "startViewTransition", { configurable: true, value: start });
  return start;
}

function Editor() {
  const [draft, setDraft] = useState("");
  const blocker = useBlocker(draft !== "");
  const navigate = useNavigate();
  return (
    <>
      <input aria-label="Draft" value={draft} onChange={(event) => setDraft(event.target.value)} />
      <Link to="/motion-destination?change=7" state={{ fromDemo: true }}>Open detail</Link>
      <button onClick={() => void navigate("/motion-destination?change=9", { replace: true, state: { saved: true } })}>
        Replace route
      </button>
      {blocker.state === "blocked" ? (
        <>
          <button onClick={() => blocker.reset()}>Stay</button>
          <button onClick={() => blocker.proceed()}>Leave</button>
        </>
      ) : null}
    </>
  );
}

function Destination() {
  const location = useLocation();
  return <p>Destination {location.search} {JSON.stringify(location.state)}</p>;
}

function renderRouter() {
  const router = createBrowserRouter([
    { path: "/motion-editor", element: <Editor /> },
    { path: "/motion-destination", element: <Destination /> },
  ]);
  const view = render(<RouterProvider router={router} />);
  return { router, view };
}

it("starts a snapshot only after the draft guard allows the route and preserves link state", async () => {
  const start = installSnapshotApi();
  const user = userEvent.setup();
  const { router, view } = renderRouter();
  await user.type(screen.getByLabelText("Draft"), "Keep this draft");
  await user.click(screen.getByRole("link", { name: "Open detail" }));
  expect(start).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Stay" }));
  expect(screen.getByLabelText("Draft")).toHaveValue("Keep this draft");
  expect(router.state.location.pathname).toBe("/motion-editor");
  await user.click(screen.getByRole("link", { name: "Open detail" }));
  await user.click(screen.getByRole("button", { name: "Leave" }));
  expect(await screen.findByText(/Destination \?change=7/)).toHaveTextContent('"fromDemo":true');
  await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
  view.unmount();
  router.dispose();
});

it("keeps state and replacement semantics while reduced motion avoids snapshots", async () => {
  preferences.reduceMotion = true;
  const start = installSnapshotApi();
  const { router, view } = renderRouter();
  await userEvent.click(screen.getByRole("button", { name: "Replace route" }));
  expect(await screen.findByText(/Destination \?change=9/)).toHaveTextContent('"saved":true');
  expect(router.state.historyAction).toBe("REPLACE");
  expect(start).not.toHaveBeenCalled();
  view.unmount();
  router.dispose();
});

it("navigates normally when the browser has no snapshot API", async () => {
  Reflect.deleteProperty(document, "startViewTransition");
  const { router, view } = renderRouter();
  await userEvent.click(screen.getByRole("link", { name: "Open detail" }));
  expect(await screen.findByText(/Destination \?change=7/)).toBeVisible();
  view.unmount();
  router.dispose();
});
