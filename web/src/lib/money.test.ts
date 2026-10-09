import { describe, expect, it } from "vitest";

import { amountToCents, centsToAmount, formatMoney } from "./money";

describe("money helpers", () => {
  it("renders cents as a two-decimal amount", () => {
    expect(centsToAmount(1900)).toBe("19.00");
    expect(centsToAmount(0)).toBe("0.00");
    expect(centsToAmount(5)).toBe("0.05");
  });

  it("parses an amount into rounded cents", () => {
    expect(amountToCents("19.99")).toBe(1999);
    expect(amountToCents("0.1")).toBe(10);
  });

  it("treats blank or negative input as zero", () => {
    expect(amountToCents("")).toBe(0);
    expect(amountToCents("-5")).toBe(0);
    expect(amountToCents("abc")).toBe(0);
  });

  it("labels an amount with its currency", () => {
    expect(formatMoney(2500, "USD")).toBe("25.00 USD");
  });
});
