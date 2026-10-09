import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { Login } from "./Login";

const mocks = vi.hoisted(() => ({
  register: vi.fn(),
  registrationEnabled: true,
  initialSetup: false,
}));

vi.mock("@/lib/queries", () => ({
  useCurrentUser: () => ({ data: null }),
  useAuthCapabilities: () => ({
    data: { registration_enabled: mocks.registrationEnabled, initial_setup_required: mocks.initialSetup },
  }),
  useLogin: () => ({ error: null, isPending: false, mutate: vi.fn() }),
  useLoginTotp: () => ({ error: null, isPending: false, mutate: vi.fn() }),
  useRegister: () => ({ error: null, isPending: false, mutate: mocks.register }),
}));
vi.mock("@/lib/orgContext", () => ({ useOrg: () => ({ enterOrg: vi.fn() }) }));

describe("public registration", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
    mocks.register.mockReset();
    mocks.registrationEnabled = true;
    mocks.initialSetup = false;
  });

  it("never forwards a plan URL parameter as an entitlement request", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <MemoryRouter initialEntries={["/login?mode=register&plan=enterprise"]}>
          <Login />
        </MemoryRouter>
      </I18nProvider>,
    );

    expect(screen.queryByText(/enterprise/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 monitored site and no AI checks/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Email"), "founder@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    const submit = screen.getAllByRole("button", { name: "Create account" }).at(-1);
    expect(submit).toBeDefined();
    await user.click(submit!);

    expect(mocks.register).toHaveBeenCalledWith(
      {
        email: "founder@example.com",
        password: "password123",
        name: undefined,
        organization_name: undefined,
      },
      { onSuccess: expect.any(Function) },
    );
  });

  it("fails closed when public account creation is disabled", async () => {
    mocks.registrationEnabled = false;
    render(
      <I18nProvider>
        <MemoryRouter initialEntries={["/login?mode=register"]}>
          <Login />
        </MemoryRouter>
      </I18nProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create account" })).not.toBeInTheDocument();
    expect(mocks.register).not.toHaveBeenCalled();
  });

  it("explains initial administrator setup without a free-tier or role request", async () => {
    mocks.initialSetup = true;
    localStorage.setItem("driftwatch_lang", "pl");
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <MemoryRouter initialEntries={["/login?plan=enterprise"]}>
          <Login />
        </MemoryRouter>
      </I18nProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Skonfiguruj swoją instalację" })).toBeInTheDocument();
    expect(screen.getByText(/Pierwsze konto zostaje administratorem tej instalacji/)).toBeInTheDocument();
    expect(screen.queryByText(/1 monitorowaną stroną/)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Nazwa przestrzeni"), "Moja instalacja");
    await user.type(screen.getByLabelText("E-mail"), "owner@example.com");
    await user.type(screen.getByLabelText("Hasło"), "password123");
    await user.click(screen.getAllByRole("button", { name: "Utwórz konto administratora" }).at(-1)!);
    expect(mocks.register).toHaveBeenCalledWith({
      email: "owner@example.com", password: "password123", name: undefined,
      organization_name: "Moja instalacja",
    }, { onSuccess: expect.any(Function), onError: expect.any(Function) });
  });
});
