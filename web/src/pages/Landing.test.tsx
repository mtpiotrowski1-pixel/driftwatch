import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { Landing } from "./Landing";

vi.mock("@/lib/queries", () => ({ useAuthCapabilities: () => ({ data: { registration_enabled: false } }) }));
vi.mock("motion/react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("motion/react")>()),
  useReducedMotion: () => true,
}));

beforeEach(() => localStorage.setItem("driftwatch_lang", "en"));

it("lets a keyboard visitor compare the real demo before/after values without claiming live data", async () => {
  const user = userEvent.setup();
  render(<I18nProvider><MemoryRouter><Landing /></MemoryRouter></I18nProvider>);
  expect(screen.getByText("Demo data")).toBeVisible();
  expect(screen.getByText(/fictional demo data, without a live AI analysis/)).toBeInTheDocument();
  const compare = screen.getByRole("tab", { name: "Compare" });
  expect(compare).toHaveAttribute("aria-selected", "true");
  compare.focus();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Before" })).toHaveFocus();
  let panel = screen.getByRole("tabpanel");
  expect(within(panel).getByText("$20 per seat / month")).toBeVisible();
  expect(within(panel).queryByText("$25 per seat / month")).not.toBeInTheDocument();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "After" })).toHaveFocus();
  panel = screen.getByRole("tabpanel");
  expect(within(panel).getByText("$25 per seat / month")).toBeVisible();
  expect(within(panel).queryByText("$20 per seat / month")).not.toBeInTheDocument();
  await user.keyboard("{Home}");
  panel = screen.getByRole("tabpanel");
  expect(within(panel).getByText("- $20 per seat / month")).toBeVisible();
  expect(within(panel).getByText("+ $25 per seat / month")).toBeVisible();
});
