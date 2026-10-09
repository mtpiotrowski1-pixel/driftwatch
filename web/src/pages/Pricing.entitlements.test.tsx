import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { Pricing } from "./Pricing";

const state = vi.hoisted(() => ({ registrationEnabled: true, initialSetup: false }));

vi.mock("@/lib/queries", () => ({
  useAuthCapabilities: () => ({
    data: { registration_enabled: state.registrationEnabled, initial_setup_required: state.initialSetup },
  }),
}));

describe("public access page", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
    state.registrationEnabled = true;
    state.initialSetup = false;
  });

  it("offers only the bounded signup and never a plan purchase", () => {
    render(
      <I18nProvider>
        <MemoryRouter>
          <Pricing />
        </MemoryRouter>
      </I18nProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Paid plans are not available for self-service" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Monitored site limit").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Team member limit").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Monthly AI-check limit").nextElementSibling).toHaveTextContent("0");

    const signup = screen.getByRole("link", { name: "Create limited workspace" });
    expect(signup).toHaveAttribute("href", "/login?mode=register");
    expect(document.querySelector('a[href*="plan="]')).not.toBeInTheDocument();
  });

  it("shows an honest invite-only state when registration is closed", () => {
    state.registrationEnabled = false;
    render(
      <I18nProvider>
        <MemoryRouter>
          <Pricing />
        </MemoryRouter>
      </I18nProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Workspace access is currently invite-only" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Monitored site limit")).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Sign in" }).at(-1)).toHaveAttribute(
      "href",
      "/login",
    );
    expect(document.querySelector('a[href*="mode=register"]')).not.toBeInTheDocument();
  });

  it("presents initial setup as your own installation without signup limits", () => {
    state.initialSetup = true;
    render(
      <I18nProvider><MemoryRouter><Pricing /></MemoryRouter></I18nProvider>,
    );
    expect(screen.getByRole("heading", { name: "You manage your monitoring workspace" })).toBeInTheDocument();
    expect(screen.getByText(/The first account becomes the administrator/)).toBeInTheDocument();
    expect(screen.queryByText("Monitored site limit")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create administrator account" })).toHaveAttribute("href", "/login?mode=register");
  });
});
