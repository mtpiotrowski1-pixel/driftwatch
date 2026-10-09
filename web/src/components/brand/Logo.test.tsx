import { fireEvent, render } from "@testing-library/react";
import { vi } from "vitest";

const state = vi.hoisted(() => ({
  logoUrl: "",
}));

vi.mock("@/branding", () => ({
  useBrand: () => ({
    isReady: true,
    name: "Driftwatch",
    logoUrl: state.logoUrl,
    accentColor: "",
    tagline: "",
    heroTitle: "",
    heroSubtitle: "",
    heroBackgroundUrl: "",
  }),
}));

import { Logo } from "@/components/brand/Logo";

describe("Logo", () => {
  beforeEach(() => {
    state.logoUrl = "";
  });

  it("renders the generated decorative logo by default", () => {
    const { container } = render(<Logo />);

    expect(container.querySelector("picture")).toBeInTheDocument();
    expect(container.querySelector("img")).toHaveAttribute("alt", "");
    expect(container.querySelector("img")).toHaveAttribute("src", "/brand/driftwatch-emblem-64.png");
    expect(container.querySelector("source")).toHaveAttribute("type", "image/webp");
  });

  it("uses the accessible native monogram when the generated logo cannot load", () => {
    const { container } = render(<Logo />);

    fireEvent.error(container.querySelector("img")!);

    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector("svg")).toHaveAttribute("focusable", "false");
    expect(container.querySelector("rect")).toHaveAttribute(
      "fill",
      "var(--color-brand-500)",
    );
  });

  it("prioritizes a decorative tenant logo and falls back after an error", () => {
    state.logoUrl = "/tenant/logo.png";
    const { container } = render(<Logo />);
    const image = container.querySelector("img");

    expect(image).toHaveAttribute("src", "/tenant/logo.png");
    expect(image).toHaveAttribute("alt", "");

    fireEvent.error(image!);
    expect(container.querySelector("img")).toHaveAttribute("src", "/brand/driftwatch-emblem-64.png");
  });

  it("tries again when the tenant logo URL changes", () => {
    state.logoUrl = "/tenant/old.png";
    const view = render(<Logo />);
    fireEvent.error(view.container.querySelector("img")!);

    state.logoUrl = "/tenant/new.png";
    view.rerender(<Logo />);

    expect(view.container.querySelector("img")).toHaveAttribute("src", "/tenant/new.png");
  });
});
