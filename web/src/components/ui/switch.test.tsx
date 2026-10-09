import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Switch } from "./switch";

describe("Switch", () => {
  it("forwards its accessible name to the interactive control", () => {
    render(
      <Switch
        aria-label="Organization active"
        checked
        onCheckedChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("switch", { name: "Organization active" })).toBeChecked();
  });
});
