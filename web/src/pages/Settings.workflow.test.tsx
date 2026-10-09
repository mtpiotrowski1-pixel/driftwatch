import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";
import { ApiError, api, bindRequestSession, organizationRequestContext } from "@/lib/api";
import { Link } from "@/lib/navigation";
import { keys } from "@/lib/queries";
import type { Settings, User } from "@/lib/types";
import { ThemeProvider } from "@/theme";

import { SettingsPage } from "./Settings";

const ADMIN: User = {
  id: 1,
  email: "admin@example.com",
  name: "Administrator",
  is_admin: true,
  is_superadmin: false,
  organization_id: 12,
  totp_enabled: false,
  mfa_enrollment_required: false,
  organization_suspended: false,
  acting_organization_id: null,
  acting_organization_name: null,
};
const CONTEXT = organizationRequestContext(12);
const clients: QueryClient[] = [];

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("driftwatch_lang", "en");
  bindRequestSession(ADMIN);
  vi.restoreAllMocks();
  vi.stubGlobal("ResizeObserver", class { observe() { } unobserve() { } disconnect() { } });
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
});

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear());
  vi.unstubAllGlobals();
});

async function openSettings(initial: Settings = {}) {
  let stored = initial;
  vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => {
    if (path === "/api/auth/me") return ADMIN as T;
    if (path === "/api/settings") return stored as T;
    if (path === "/api/recipients") return [] as T;
    if (path === "/api/settings/factory-defaults" || path === "/api/usage/summary") return null as T;
    throw new Error(`Unexpected GET ${path}`);
  });
  const put = vi.spyOn(api, "put").mockImplementation(async <T,>(path: string, body: unknown) => {
    if (path !== "/api/settings") throw new Error(`Unexpected PUT ${path}`);
    const payload = body as Record<string, unknown>;
    const updates = Object.fromEntries(Object.entries(payload)
      .filter(([key]) => key !== "clear_secret_keys")
      .map(([key, value]) => [key, key === "notification_webhook_url" ? "********" : String(value)]));
    stored = { ...stored, ...updates };
    for (const key of (payload.clear_secret_keys ?? []) as string[]) delete stored[key];
    return stored as T;
  });
  const post = vi.spyOn(api, "post").mockImplementation(async <T,>(path: string) => {
    if (path === "/api/auth/step-up") return undefined as T;
    throw new Error(`Unexpected POST ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(client);
  const router = createMemoryRouter([
    { path: "/settings", element: <><Link to="/other" viewTransition={false}>Leave settings</Link><SettingsPage /></> },
    { path: "/other", element: <h1>Other page</h1> },
  ], { initialEntries: ["/settings"] });
  render(
    <QueryClientProvider client={client}><I18nProvider><ThemeProvider><ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider></ThemeProvider></I18nProvider></QueryClientProvider>,
  );
  await screen.findByLabelText("Brand name");
  return { client, router, put, post, user: userEvent.setup() };
}

async function authorize(user: ReturnType<typeof userEvent.setup>) {
  const dialog = await screen.findByRole("dialog", { name: "Authorize protected changes" });
  await user.type(within(dialog).getByLabelText("Password"), "test-password");
  await user.click(within(dialog).getByRole("button", { name: "Save protected settings" }));
}

it("keeps an ordinary organization draft when navigation is cancelled and unblocks after saving", async () => {
  const { router, put, post, user } = await openSettings({ brand_name: "Original" });
  const name = screen.getByLabelText("Brand name");
  await user.clear(name);
  await user.type(name, "Updated workspace");
  await user.click(screen.getByRole("link", { name: "Leave settings" }));
  const warning = await screen.findByRole("dialog", { name: "Discard unsaved changes?" });
  expect(router.state.location.pathname).toBe("/settings");
  await user.click(within(warning).getByRole("button", { name: "Stay" }));
  expect(name).toHaveValue("Updated workspace");
  await user.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() => expect(put).toHaveBeenCalledWith("/api/settings", { brand_name: "Updated workspace" }, { context: CONTEXT }));
  expect(post).not.toHaveBeenCalled();
  await user.click(screen.getByRole("link", { name: "Leave settings" }));
  await screen.findByRole("heading", { name: "Other page" });
  expect(screen.queryByRole("dialog", { name: "Discard unsaved changes?" })).not.toBeInTheDocument();
});

it("requires step-up for a private endpoint, retains a failed draft for retry, and clears it on success", async () => {
  const { client, put, post, user } = await openSettings();
  await user.click(screen.getByRole("button", { name: "Email delivery" }));
  const endpoint = screen.getByLabelText("Webhook URL");
  const privateEndpoint = "https://example.invalid/private-endpoint";
  await user.type(endpoint, privateEndpoint);
  await user.click(screen.getByRole("button", { name: "Save settings" }));
  const firstConfirmation = await screen.findByRole("dialog", { name: "Authorize protected changes" });
  expect(put).not.toHaveBeenCalled();
  await user.click(within(firstConfirmation).getByRole("button", { name: "Cancel" }));
  expect(endpoint).toHaveValue(privateEndpoint);
  expect(post).not.toHaveBeenCalled();

  put.mockRejectedValueOnce(new ApiError(503, "Temporary save failure"));
  await user.click(screen.getByRole("button", { name: "Save settings" }));
  await authorize(user);
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Authorize protected changes" })).not.toBeInTheDocument());
  expect(screen.getAllByText("Temporary save failure").length).toBeGreaterThan(0);
  expect(endpoint).toHaveValue(privateEndpoint);
  expect(JSON.stringify(client.getMutationCache().getAll())).not.toContain(privateEndpoint);
  expect(JSON.stringify(client.getQueryCache().getAll())).not.toContain(privateEndpoint);
  expect(JSON.stringify(localStorage)).not.toContain(privateEndpoint);
  expect(JSON.stringify(sessionStorage)).not.toContain(privateEndpoint);

  await user.click(screen.getByRole("button", { name: "Save settings" }));
  await authorize(user);
  await waitFor(() => expect(endpoint).toHaveValue(""));
  expect(put).toHaveBeenCalledTimes(2);
  expect(put).toHaveBeenLastCalledWith("/api/settings", { notification_webhook_url: privateEndpoint }, { context: CONTEXT });
  expect(post).toHaveBeenCalledTimes(2);
  expect(client.getQueryData([...keys.settings, "organization", 12])).toEqual({ notification_webhook_url: "********" });
  expect(JSON.stringify(client.getMutationCache().getAll())).not.toContain(privateEndpoint);
}, 10_000);

it("undoes a configured secret removal and sends the explicit removal contract after authorization", async () => {
  const { put, post, user } = await openSettings({ notification_webhook_url: "********" });
  await user.click(screen.getByRole("button", { name: "Email delivery" }));
  await user.click(screen.getByRole("button", { name: "Remove stored credential" }));
  expect(screen.getByText("This credential will be removed when you save.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await user.click(screen.getByRole("button", { name: "Save settings" }));
  expect(put).not.toHaveBeenCalled();
  expect(post).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog", { name: "Authorize protected changes" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Remove stored credential" }));
  await user.click(screen.getByRole("button", { name: "Save settings" }));
  await authorize(user);
  await waitFor(() => expect(put).toHaveBeenCalledWith("/api/settings", { clear_secret_keys: ["notification_webhook_url"] }, { context: CONTEXT }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Remove stored credential" })).not.toBeInTheDocument());
});
