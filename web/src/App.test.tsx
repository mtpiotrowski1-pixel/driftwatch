import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("./branding", () => ({
  BrandingProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("./lib/orgContext", () => ({
  OrgProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("./pages/Landing", () => ({
  Landing: () => {
    throw new Error("Failed to fetch dynamically imported module: synthetic-old-chunk.js");
  },
}));

import { App } from "./App";

afterEach(() => vi.restoreAllMocks());

it("offers a localized recovery action when a routed page cannot load", async () => {
  localStorage.setItem("driftwatch_lang", "pl");
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  render(<App />);

  const recovery = await screen.findByRole("alert");
  expect(recovery).toHaveTextContent("Odśwież");
  expect(screen.getByRole("button", { name: "Odśwież" })).toBeEnabled();
  expect(recovery).not.toHaveTextContent("synthetic-old-chunk");
  expect(screen.queryByText("Unexpected Application Error!")).not.toBeInTheDocument();
});
