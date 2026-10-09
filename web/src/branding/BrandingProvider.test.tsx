import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Branding } from "@/lib/types";

const state = vi.hoisted(() => ({
  data: undefined as Branding | undefined,
  isFetched: false,
}));

vi.mock("@/lib/queries", () => ({
  useBranding: () => ({ data: state.data, isFetched: state.isFetched }),
}));

import { BrandingProvider, useBrand } from "./index";

const TENANT_BRAND: Branding = {
  brand_name: "Northstar",
  logo_url: "",
  accent_color: "#3f6dff",
  tagline: "",
  hero_title: "",
  hero_subtitle: "",
  hero_background_url: "",
};

function BrandName() {
  const brand = useBrand();
  return (
    <>
      <span>{brand.name}</span>
      <span>{brand.isReady ? "resolved" : "pending"}</span>
    </>
  );
}

describe("BrandingProvider tenant isolation", () => {
  beforeEach(() => {
    state.data = undefined;
    state.isFetched = false;
    document.documentElement.removeAttribute("style");
    document.title = "";
  });

  it("clears tenant branding synchronously when the scoped query disappears", () => {
    state.data = TENANT_BRAND;
    state.isFetched = true;
    const view = render(
      <BrandingProvider>
        <BrandName />
      </BrandingProvider>,
    );

    expect(screen.getByText("Northstar")).toBeInTheDocument();
    expect(document.documentElement.style.getPropertyValue("--color-brand-500")).not.toBe("");
    expect(document.title).toBe("Northstar");

    state.data = undefined;
    view.rerender(
      <BrandingProvider>
        <BrandName />
      </BrandingProvider>,
    );

    expect(screen.getByText("Driftwatch")).toBeInTheDocument();
    expect(document.documentElement.style.getPropertyValue("--color-brand-500")).toBe("");
    expect(document.title).toBe("Driftwatch");
  });

  it("keeps default artwork pending until branding resolves", () => {
    const view = render(
      <BrandingProvider>
        <BrandName />
      </BrandingProvider>,
    );

    expect(screen.getByText("pending")).toBeInTheDocument();

    state.isFetched = true;
    view.rerender(
      <BrandingProvider>
        <BrandName />
      </BrandingProvider>,
    );

    expect(screen.getByText("resolved")).toBeInTheDocument();
  });
});
