import { describe, expect, it } from "vitest";

import { accentRamp, parseHex } from "./index";

type Rgb = [number, number, number];

function rgbOf(value: string): Rgb {
  const parts = value.match(/\d+/g);
  if (!parts || parts.length < 3) throw new Error(`not an rgb() value: ${value}`);
  return [Number(parts[0]), Number(parts[1]), Number(parts[2])];
}

function luma([r, g, b]: Rgb): number {
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

function relativeLuminance([r, g, b]: Rgb): number {
  const linear = (channel: number) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const [lighter, darker] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("parseHex", () => {
  it("parses a 6-digit hex into rgb channels", () => {
    expect(parseHex("#1d4ed8")).toEqual([29, 78, 216]);
  });

  it("expands a 3-digit shorthand the same as its 6-digit form", () => {
    expect(parseHex("#abc")).toEqual(parseHex("#aabbcc"));
  });

  it("is case-insensitive and tolerates a missing hash", () => {
    expect(parseHex("AABBCC")).toEqual([170, 187, 204]);
  });

  it.each(["red", "#12", "#1234567", "rgb(0,0,0)", "#12g", "", "#abc;}url("])(
    "rejects non-hex input %j so the caller can clear the accent",
    (bad) => {
      expect(parseHex(bad)).toBeNull();
    },
  );
});

describe("accentRamp", () => {
  it.each(["#ff0000", "#0000ff", "#800080", "#000000", "#ffffff"])("keeps the pressed button readable for tenant accent %s", (accent) => {
    const ramp = accentRamp(accent)!;
    for (const token of ["--color-brand-400", "--color-brand-500", "--color-brand-600"]) {
      expect(contrast(rgbOf(ramp[token]), [21, 25, 21])).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("returns null for an invalid accent so callers clear the brand variables", () => {
    expect(accentRamp("not-a-color")).toBeNull();
  });

  it("lifts a dark accent toward white so dark button text stays legible", () => {
    const input = parseHex("#15163a")!; // a very dark navy
    const five = rgbOf(accentRamp("#15163a")!["--color-brand-500"]);
    expect(luma(five)).toBeGreaterThan(luma(input));
  });

  it("leaves a light accent unchanged — it already carries dark text", () => {
    const input = parseHex("#fde047")!; // a bright yellow
    expect(rgbOf(accentRamp("#fde047")!["--color-brand-500"])).toEqual(input);
  });

  it("derives light and dark stops on both sides of 500", () => {
    const ramp = accentRamp("#3f6dff")!;
    const at = (token: string) => luma(rgbOf(ramp[token]));
    expect(at("--color-brand-300")).toBeGreaterThan(at("--color-brand-500"));
    expect(at("--color-brand-600")).toBeLessThan(at("--color-brand-500"));
    expect(at("--color-brand-700")).toBeLessThan(at("--color-brand-600"));
  });

  it("emits only integer rgb() values, never the raw input string", () => {
    for (const value of Object.values(accentRamp("#7c3aed")!)) {
      expect(value).toMatch(/^rgb\(\d{1,3} \d{1,3} \d{1,3}\)$/);
    }
  });

  it.each(["#ffffff", "#fde047", "#3f6dff", "#15163a"])(
    "keeps the 700 stop readable on the light workspace for %s",
    (accent) => {
      const darkText = rgbOf(accentRamp(accent)!["--color-brand-700"]);
      expect(contrast(darkText, [255, 255, 255])).toBeGreaterThanOrEqual(4.5);
    },
  );
});
