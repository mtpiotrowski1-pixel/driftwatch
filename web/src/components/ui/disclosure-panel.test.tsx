import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { Collapsible } from "./collapsible";
import { SettingsSection } from "./settings-section";

vi.mock("motion/react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("motion/react")>()),
  useReducedMotion: () => true,
}));

beforeEach(() => localStorage.setItem("driftwatch_lang", "en"));

it.each(["collapsible", "settings"])("preserves unsaved fields and excludes collapsed %s controls from navigation", async (kind) => {
  const child = <input aria-label="Unfinished value" defaultValue="" />;
  render(kind === "settings"
    ? <SettingsSection title="Advanced options">{child}</SettingsSection>
    : <Collapsible label="Advanced options">{child}</Collapsible>);
  const toggle = screen.getByRole("button", { name: "Advanced options" });
  const field = screen.getByLabelText("Unfinished value");
  expect(field.closest('[role="region"]')).toHaveAttribute("inert");
  expect(screen.queryByRole("region", { name: "Advanced options" })).not.toBeInTheDocument();
  await userEvent.click(toggle);
  expect(screen.getByRole("region", { name: "Advanced options" })).not.toHaveAttribute("inert");
  await userEvent.type(field, "Do not discard me");
  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(field.closest('[role="region"]')).toHaveAttribute("aria-hidden", "true");
  expect(field.closest('[role="region"]')).toHaveAttribute("inert");
  await userEvent.click(toggle);
  expect(screen.getByLabelText("Unfinished value")).toBe(field);
  expect(field).toHaveValue("Do not discard me");
});
