import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";
import { api, bindRequestSession } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { User } from "@/lib/types";
import { ThemeProvider } from "@/theme";

import { SettingsPage } from "./Settings";

const OWNER: User = {
  id: 1, email: "owner@example.com", name: "Owner", is_admin: true,
  is_superadmin: true, organization_id: 12, totp_enabled: false,
  mfa_enrollment_required: true, organization_suspended: false,
  acting_organization_id: 12, acting_organization_name: "My workspace",
};
const RECOVERY_CODES = ["test-code-one", "test-code-two"];

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("driftwatch_lang", "en");
  bindRequestSession(OWNER);
  vi.restoreAllMocks();
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
});

afterEach(() => vi.unstubAllGlobals());

it("keeps one-time recovery codes visible across required MFA completion until explicit acknowledgement", async () => {
  let enabled = false;
  const get = vi.spyOn(api, "get").mockImplementation(async <T,>(path: string) => {
    if (path === "/api/auth/me") return {
      ...OWNER, totp_enabled: enabled, mfa_enrollment_required: !enabled,
    } as T;
    if (path === "/api/settings") return {} as T;
    if (path === "/api/recipients") return [] as T;
    if (path === "/api/settings/factory-defaults" || path === "/api/usage/summary") return null as T;
    throw new Error(`Unexpected GET ${path}`);
  });
  const post = vi.spyOn(api, "post").mockImplementation(async <T,>(path: string) => {
    if (path === "/api/auth/step-up") return undefined as T;
    if (path === "/api/auth/totp/setup") return {
      secret: "test-enrollment-key", qr_svg_data_uri: "data:image/svg+xml,<svg />",
    } as T;
    if (path === "/api/auth/totp/enable") {
      enabled = true;
      return { recovery_codes: RECOVERY_CODES } as T;
    }
    throw new Error(`Unexpected POST ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter([{ path: "/settings", element: <SettingsPage /> }], { initialEntries: ["/settings"] });
  render(
    <QueryClientProvider client={client}><I18nProvider><ThemeProvider><ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider></ThemeProvider></I18nProvider></QueryClientProvider>,
  );
  const user = userEvent.setup();
  await screen.findByRole("heading", { name: "Secure your administrator account" });
  await user.click(screen.getByRole("button", { name: "Two-factor authentication" }));
  await user.click(screen.getByRole("button", { name: "Enable two-factor authentication" }));
  const stepUp = screen.getByRole("dialog");
  await user.type(within(stepUp).getByLabelText("Password"), "test-password");
  await user.click(within(stepUp).getByRole("button", { name: "Enable two-factor authentication" }));
  await user.type(await screen.findByLabelText("Enter the code from the app to confirm"), "123456");
  await user.click(screen.getByRole("button", { name: "Confirm and enable" }));

  const recovery = await screen.findByRole("dialog", { name: "Save your recovery codes" });
  await waitFor(() => expect(client.getQueryData<User>(keys.me)?.mfa_enrollment_required).toBe(false));
  expect(screen.getByRole("heading", { name: "Settings", hidden: true })).toBeInTheDocument();
  expect(screen.queryByText("Secure your administrator account")).not.toBeInTheDocument();
  expect(get.mock.calls.filter(([path]) => path === "/api/auth/me")).toHaveLength(2);
  expect(post).toHaveBeenCalledWith("/api/auth/totp/enable", { code: "123456" });
  for (const code of RECOVERY_CODES) expect(within(recovery).getByText(code)).toBeVisible();
  expect(within(recovery).queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(recovery).toBeVisible();
  expect(JSON.stringify(client.getMutationCache().getAll())).not.toContain(RECOVERY_CODES[0]);
  expect(JSON.stringify(localStorage)).not.toContain(RECOVERY_CODES[0]);
  expect(JSON.stringify(sessionStorage)).not.toContain(RECOVERY_CODES[0]);

  await user.click(within(recovery).getByRole("button", { name: "I've saved them" }));
  expect(screen.queryByRole("dialog", { name: "Save your recovery codes" })).not.toBeInTheDocument();
  for (const code of RECOVERY_CODES) expect(screen.queryByText(code)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Two-factor authentication" }));
  expect(screen.getByText("Enabled")).toBeVisible();
  for (const code of RECOVERY_CODES) expect(screen.queryByText(code)).not.toBeInTheDocument();
  client.clear();
}, 10_000);
