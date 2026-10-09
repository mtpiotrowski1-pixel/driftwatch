import { fireEvent, render } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { BrandBackground } from "./BrandBackground";

const context = vi.hoisted(() => ({
  brand: { isReady: true, accentColor: "", heroBackgroundUrl: "" },
}));
vi.mock("@/branding", () => ({ useBrand: () => context.brand }));

beforeEach(() => {
  context.brand = { isReady: true, accentColor: "", heroBackgroundUrl: "" };
});

it("honors a customer's hero URL and falls back to generated artwork when it cannot load", () => {
  context.brand.heroBackgroundUrl = "https://assets.example/customer-hero.jpg";
  const { container } = render(<BrandBackground variant="hero" />);
  expect(container.firstChild).toHaveAttribute("data-custom-art", "true");
  const custom = container.querySelector("img")!;
  expect(custom).toHaveAttribute("src", context.brand.heroBackgroundUrl);
  fireEvent.error(custom);
  expect(container.querySelector("img")?.src).toContain("portal-hero-v3");
  expect(container.querySelector("picture")).toBeInTheDocument();
});

it("clears the previous customer's artwork and color treatment when branding is reset", () => {
  context.brand = { isReady: true, accentColor: "#8844ff", heroBackgroundUrl: "https://assets.example/previous-tenant.jpg" };
  const view = render(<BrandBackground variant="dark" />);
  expect(view.container.querySelector("img")?.src).toContain("previous-tenant");
  context.brand = { isReady: false, accentColor: "", heroBackgroundUrl: "" };
  view.rerender(<BrandBackground variant="dark" />);
  const fallback = view.container.querySelector("img")!;
  expect(fallback.src).toContain("portal-hero-v3");
  expect(fallback.src).not.toContain("previous-tenant");
  expect(fallback).not.toHaveClass("saturate-0");
  expect(view.container.firstChild).not.toHaveAttribute("data-custom-art");
});

it("keeps a custom accent clear of a strongly green default workspace image", () => {
  context.brand = { isReady: true, accentColor: "#8844ff", heroBackgroundUrl: "https://assets.example/customer-hero.jpg" };
  const { container } = render(<BrandBackground variant="ambient" />);
  const ambient = container.querySelector("img")!;
  expect(ambient.src).toContain("portal-ambient-v3");
  expect(ambient).toHaveClass("saturate-0");
  expect(ambient).toHaveAttribute("alt", "");
  expect(container.firstChild).not.toHaveAttribute("data-custom-art");
});
