import { fireEvent, render } from "@testing-library/react";

import { DecorativeBrandArtwork } from "@/components/brand/BrandArtwork";

describe("DecorativeBrandArtwork", () => {
  it("provides responsive WebP sources and a JPEG fallback", () => {
    const { container } = render(
      <DecorativeBrandArtwork
        desktop={{ jpg: "/brand/hero.jpg", webp: "/brand/hero.webp" }}
        mobile={{ jpg: "/brand/hero-mobile.jpg", webp: "/brand/hero-mobile.webp" }}
        eager
      />,
    );

    const wrapper = container.firstElementChild;
    const sources = Array.from(container.querySelectorAll("source"));
    const image = container.querySelector("img");

    expect(wrapper).toHaveAttribute("aria-hidden", "true");
    expect(sources.map((source) => source.getAttribute("srcset"))).toEqual([
      "/brand/hero-mobile.webp",
      "/brand/hero-mobile.jpg",
      "/brand/hero.webp",
    ]);
    expect(image).toHaveAttribute("src", "/brand/hero.jpg");
    expect(image).toHaveAttribute("alt", "");
    expect(image).toHaveAttribute("loading", "eager");
    expect(image).toHaveAttribute("fetchpriority", "high");
  });

  it("lets tenant artwork replace the default asset", () => {
    const { container } = render(
      <DecorativeBrandArtwork
        customUrl="/tenant/hero.png"
        desktop={{ jpg: "/brand/hero.jpg", webp: "/brand/hero.webp" }}
      />,
    );

    expect(container.querySelector("picture")).not.toBeInTheDocument();
    expect(container.querySelectorAll("source")).toHaveLength(0);
    expect(container.querySelector("img")).toHaveAttribute("src", "/tenant/hero.png");
  });

  it("falls back to the default picture when tenant artwork fails", () => {
    const { container } = render(
      <DecorativeBrandArtwork
        customUrl="/tenant/missing.png"
        desktop={{ jpg: "/brand/hero.jpg", webp: "/brand/hero.webp" }}
      />,
    );

    fireEvent.error(container.querySelector("img")!);

    expect(container.querySelector("picture")).toBeInTheDocument();
    expect(container.querySelector("img")).toHaveAttribute("src", "/brand/hero.jpg");
  });
});
