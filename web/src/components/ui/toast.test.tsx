import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./toast";

function NotifyButton() {
  const { notify } = useToast();
  return <button onClick={() => notify("Saved")}>Notify</button>;
}

describe("ToastProvider", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("clears pending expiry timers when the provider unmounts", () => {
    vi.useFakeTimers();
    const clearTimeout = vi.spyOn(window, "clearTimeout");
    const view = render(
      <ToastProvider>
        <NotifyButton />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Notify" }));
    expect(screen.getByText("Saved")).toBeInTheDocument();

    view.unmount();
    expect(clearTimeout).toHaveBeenCalled();
    act(() => vi.runOnlyPendingTimers());
  });
});
