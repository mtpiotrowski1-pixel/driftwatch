import { describe, expect, it } from "vitest";

import { compactSteps } from "./InteractionStepsEditor";

describe("compactSteps", () => {
  it("round-trips an existing fill by opaque reference only", () => {
    expect(
      compactSteps([
        {
          action: "fill",
          selector: " #token ",
          secret_ref: "5a530db0-181d-438b-98df-df6ab4f66c78",
          has_secret: true,
          timeout_ms: 10_000,
        },
      ]),
    ).toEqual([
      {
        action: "fill",
        selector: "#token",
        secret_ref: "5a530db0-181d-438b-98df-df6ab4f66c78",
        timeout_ms: 10_000,
      },
    ]);
  });

  it("does not normalize a newly entered secret", () => {
    expect(
      compactSteps([
        {
          action: "fill",
          selector: "#password",
          secret_value: "  spaces-are-part-of-the-secret  ",
        },
      ])[0]?.secret_value,
    ).toBe("  spaces-are-part-of-the-secret  ");
  });
});
