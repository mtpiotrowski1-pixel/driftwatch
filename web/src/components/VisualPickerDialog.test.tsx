import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";
import { api } from "@/lib/api";
import { usePickerResult, usePickerStatus } from "@/lib/picker";
import type { PickerStatus } from "@/lib/types";
import { VisualPickerDialog } from "./VisualPickerDialog";

vi.mock("@/lib/picker", () => ({ usePickerStatus: vi.fn(), usePickerResult: vi.fn() }));

const STARTED = { session_id: "test-session", state: "starting" } as PickerStatus;
const noResult = { data: undefined, isError: false } as ReturnType<typeof usePickerResult>;

function renderPicker() {
  return render(<StrictMode><I18nProvider><ToastProvider><VisualPickerDialog open mode="select" url="https://example.test" onClose={vi.fn()} /></ToastProvider></I18nProvider></StrictMode>);
}

describe("picker session ownership", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("driftwatch_lang", "en");
    vi.mocked(usePickerStatus).mockReturnValue({ data: undefined, isError: false } as ReturnType<typeof usePickerStatus>);
    vi.mocked(usePickerResult).mockReturnValue(noResult);
  });

  it("starts once during effect replay and cancels a late server session after closing", async () => {
    let finish!: (value: PickerStatus) => void;
    const post = vi.spyOn(api, "post").mockImplementation(() => new Promise((resolve) => { finish = resolve as (value: PickerStatus) => void; }));
    const cancel = vi.spyOn(api, "del").mockResolvedValue(undefined);
    const view = renderPicker();
    expect(post).toHaveBeenCalledOnce();
    view.unmount();
    await act(async () => finish(STARTED));
    expect(cancel).toHaveBeenCalledExactlyOnceWith("/api/picker/sessions/test-session");
  });

  it("cancels a known session even before its first status has returned", async () => {
    vi.spyOn(api, "post").mockResolvedValue(STARTED);
    const cancel = vi.spyOn(api, "del").mockResolvedValue(undefined);
    const view = renderPicker();
    await waitFor(() => expect(usePickerStatus).toHaveBeenCalledWith("test-session"));
    view.unmount();
    await act(async () => undefined);
    expect(cancel).toHaveBeenCalledExactlyOnceWith("/api/picker/sessions/test-session");
  });

  it("shows a failed first poll with an explicit retry instead of a starting spinner", async () => {
    const retry = vi.fn();
    vi.spyOn(api, "post").mockResolvedValue(STARTED);
    vi.spyOn(api, "del").mockResolvedValue(undefined);
    vi.mocked(usePickerStatus).mockImplementation((sessionId) => ({ data: undefined, isError: !!sessionId, error: new TypeError("offline"), refetch: retry }) as unknown as ReturnType<typeof usePickerStatus>);
    renderPicker();
    const button = await screen.findByRole("button", { name: "Try again" });
    expect(screen.getByRole("alert")).toHaveTextContent("request");
    await userEvent.click(button);
    expect(retry).toHaveBeenCalledOnce();
  });
});
