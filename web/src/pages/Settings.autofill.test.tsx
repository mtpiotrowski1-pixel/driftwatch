import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { ConfigurationInput } from "./Settings";

it.each(["password", "text"])("requires focus before editing a %s configuration input", async (type) => {
  render(<><ConfigurationInput id="provider-setting" aria-label="Provider setting" type={type} /><button>Other control</button></>);
  const input = screen.getByLabelText("Provider setting");
  expect(input).toHaveAttribute("readonly");
  expect(input).toHaveAttribute("autocomplete", type === "password" ? "new-password" : "off");
  expect(input).toHaveAttribute("name", "configuration_provider-setting");
  await userEvent.type(input, "intentionally-entered");
  expect(input).toHaveValue("intentionally-entered");
  expect(input).not.toHaveAttribute("readonly");
  await userEvent.click(screen.getByRole("button", { name: "Other control" }));
  expect(input).toHaveAttribute("readonly");
  expect(input).toHaveValue("intentionally-entered");
});
