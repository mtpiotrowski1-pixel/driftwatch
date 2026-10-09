import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { MobileNav } from "./MobileNav";
import { visibleNavItems } from "./nav";

function renderMobileNav(onLogout = vi.fn()) {
  render(
    <I18nProvider>
      <MemoryRouter>
        <MobileNav
          items={visibleNavItems({ is_admin: true, is_superadmin: false })}
          userName="Anna Kowalska"
          userEmail="anna@example.com"
          onLogout={onLogout}
        />
      </MemoryRouter>
    </I18nProvider>,
  );
  return onLogout;
}

describe("MobileNav", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
  });

  it("keeps the menu collapsed until the toggle is pressed", async () => {
    const user = userEvent.setup();
    renderMobileNav();
    expect(screen.queryByText("Anna Kowalska")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /menu/i }));
    expect(screen.getByText("Anna Kowalska")).toBeInTheDocument();
    expect(screen.getByText("anna@example.com")).toBeInTheDocument();
  });

  it("traps keyboard focus and restores it after Escape", async () => {
    const user = userEvent.setup();
    renderMobileNav();
    const toggle = screen.getByRole("button", { name: /menu/i });

    await user.click(toggle);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
  });

  it("signs out from the open menu", async () => {
    const user = userEvent.setup();
    const onLogout = renderMobileNav();
    await user.click(screen.getByRole("button", { name: /menu/i }));
    await user.click(screen.getByRole("button", { name: /sign out/i }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });
});
