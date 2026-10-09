import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const cssSource = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

function token(name: string): string {
  const match = cssSource.match(new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`Missing color token: ${name}`);
  return match[1];
}

function luminance(hex: string): number {
  const channel = (offset: number) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255;
  const linear = (value: number) =>
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  return (
    0.2126 * linear(channel(1)) +
    0.7152 * linear(channel(3)) +
    0.0722 * linear(channel(5))
  );
}

function contrast(foreground: string, background: string): number {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

describe("workspace text palette", () => {
  it.each(["amber-400", "rose-400", "emerald-400"])("keeps small status text readable on its tinted card", (foreground) => {
    const color = token(foreground);
    const channels = [1, 3, 5].map((offset) => Math.round(Number.parseInt(color.slice(offset, offset + 2), 16) * 0.15 + 255 * 0.85));
    const background = `#${channels.map((value) => value.toString(16).padStart(2, "0")).join("")}`;
    expect(contrast(color, background)).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps primary button text readable in every theme and pressed state", () => {
    const colors = [...cssSource.matchAll(/--color-brand-(?:400|500|600):\s*(#[0-9a-fA-F]{6})/g)].map((match) => match[1]);
    for (const color of colors) expect(contrast("#151915", color), color).toBeGreaterThanOrEqual(4.5);
  });
  it.each(["mist-400", "mist-500", "mist-600"])(
    "keeps %s at WCAG AA contrast on every light workspace surface",
    (foreground) => {
      for (const background of [
        "ink-950",
        "ink-900",
        "ink-850",
        "ink-800",
        "ink-750",
        "ink-700",
      ]) {
        expect(
          contrast(token(foreground), token(background)),
          `${foreground} on ${background}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    },
  );
});
