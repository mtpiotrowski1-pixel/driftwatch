import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ClickableCard } from "./clickable-card";

it("keeps the primary card action and secondary controls as siblings", async () => {
  const onOpen = vi.fn();
  const onEdit = vi.fn();
  render(
    <ClickableCard label="Open project" onOpen={onOpen}>
      <p>Project Atlas</p>
      <div className="pointer-events-auto">
        <button type="button" onClick={onEdit}>
          Edit project
        </button>
      </div>
    </ClickableCard>,
  );

  const primary = screen.getByRole("button", { name: "Open project" });
  const secondary = screen.getByRole("button", { name: "Edit project" });
  expect(primary.contains(secondary)).toBe(false);

  await userEvent.click(secondary);
  expect(onEdit).toHaveBeenCalledOnce();
  expect(onOpen).not.toHaveBeenCalled();

  await userEvent.click(primary);
  expect(onOpen).toHaveBeenCalledOnce();
});
