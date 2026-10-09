import { describe, expect, it } from "vitest";

import { formatCost, normalizeUrl, passwordsMismatch } from "./utils";

it("keeps missing model prices unknown instead of displaying zero", () => {
  document.documentElement.lang = "en";
  expect(formatCost(null)).toBe("Unknown");
  expect(formatCost(0)).toBe("$0.00");
});

describe("passwordsMismatch", () => {
  it("stays quiet until the confirmation field is filled in", () => {
    expect(passwordsMismatch("correct-horse", "")).toBe(false);
  });

  it("flags a divergent confirmation", () => {
    expect(passwordsMismatch("correct-horse", "correct-house")).toBe(true);
  });

  it("clears once the two values match", () => {
    expect(passwordsMismatch("correct-horse", "correct-horse")).toBe(false);
  });
});

describe("normalizeUrl", () => {
  it("adds https:// when no scheme is present", () => {
    expect(normalizeUrl("example.com/pricing")).toBe("https://example.com/pricing");
  });

  it("leaves an existing scheme untouched", () => {
    expect(normalizeUrl("http://example.com")).toBe("http://example.com");
    expect(normalizeUrl("https://example.com")).toBe("https://example.com");
  });

  it("trims and keeps a blank value blank", () => {
    expect(normalizeUrl("  example.com  ")).toBe("https://example.com");
    expect(normalizeUrl("   ")).toBe("");
  });
});
