import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";
import { useCreateSite } from "@/lib/queries";
import { AddSite } from "./AddSite";

vi.mock("@/lib/orgContext", () => ({ useInOrgContext: () => true }));
vi.mock("@/lib/picker", () => ({ usePickerCapabilities: () => ({ data: { available: false }, isLoading: false }) }));
vi.mock("@/lib/queries", () => ({
  useCurrentUser: () => ({ data: { id: 1, is_admin: true, is_superadmin: false, organization_id: 1 } }),
  useProjects: () => ({ data: [], isLoading: false, isError: false }),
  useRecipients: () => ({ data: [], isLoading: false, isError: false }),
  useCreateSite: vi.fn(),
  useProjectEffectiveRules: () => ({}),
  useInheritedEffectiveRules: () => ({}),
}));

beforeEach(() => {
  localStorage.setItem("driftwatch_lang", "en");
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});

it("retries only failed bulk URLs and allows navigation after complete success", async () => {
  const mutateAsync = vi.fn().mockResolvedValueOnce({ id: 1 }).mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce({ id: 2 });
  vi.mocked(useCreateSite).mockReturnValue({ mutateAsync, isPending: false, error: null } as unknown as ReturnType<typeof useCreateSite>);
  const router = createMemoryRouter([{ path: "/sites/new", element: <AddSite /> }, { path: "/dashboard", element: <div>Dashboard destination</div> }], { initialEntries: ["/sites/new"] });
  render(<I18nProvider><ToastProvider><RouterProvider router={router} /></ToastProvider></I18nProvider>);
  await userEvent.click(screen.getByRole("switch", { name: "Bulk add" }));
  const urls = await screen.findByLabelText("URLs");
  await userEvent.type(urls, "https://first.example\nhttps://second.example");
  await userEvent.selectOptions(screen.getByLabelText("Change analysis"), "disabled");
  expect(screen.getByLabelText("Notifications")).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Create sites" }));
  await waitFor(() => expect(urls).toHaveValue("https://second.example"));
  expect(mutateAsync).toHaveBeenCalledTimes(2);
  await userEvent.click(screen.getByRole("button", { name: "Create sites" }));
  expect(await screen.findByText("Dashboard destination")).toBeVisible();
  expect(mutateAsync.mock.calls.map(([body]) => body.url)).toEqual(["https://first.example", "https://second.example", "https://second.example"]);
  for (const [body] of mutateAsync.mock.calls) {
    expect(body).toMatchObject({ analysis_mode: "disabled", notification_mode: "always" });
  }
});

it.each(["interval", "analysis"])("protects a draft with only its %s option changed", async (option) => {
  vi.mocked(useCreateSite).mockReturnValue({ isPending: false, error: null } as unknown as ReturnType<typeof useCreateSite>);
  const router = createMemoryRouter([{ path: "/sites/new", element: <AddSite /> }, { path: "/dashboard", element: <div>Dashboard destination</div> }], { initialEntries: ["/sites/new"] });
  render(<I18nProvider><ToastProvider><RouterProvider router={router} /></ToastProvider></I18nProvider>);
  if (option === "analysis") {
    await userEvent.selectOptions(screen.getByLabelText("Change analysis"), "disabled");
  } else {
    const interval = screen.getByLabelText("Check interval (minutes)");
    await userEvent.clear(interval);
    await userEvent.type(interval, "120");
  }
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(await screen.findByRole("dialog", { name: "Discard unsaved changes?" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Stay" }));
  expect(router.state.location.pathname).toBe("/sites/new");
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await userEvent.click(await screen.findByRole("button", { name: "Leave" }));
  expect(await screen.findByText("Dashboard destination")).toBeVisible();
});
