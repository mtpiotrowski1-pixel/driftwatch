import { describe, expect, it } from "vitest";

import { resolveActiveChangeId } from "./SiteDetail";

const CHANGES = [{ id: 30 }, { id: 20 }, { id: 10 }]; // newest first

describe("resolveActiveChangeId", () => {
  it("defaults to the newest change", () => {
    expect(resolveActiveChangeId(null, null, CHANGES)).toBe(30);
  });

  it("is null when there are no changes", () => {
    expect(resolveActiveChangeId(null, null, [])).toBeNull();
  });

  it("seeds from a ?change= param that exists in the list", () => {
    expect(resolveActiveChangeId(null, "20", CHANGES)).toBe(20);
  });

  it("fetches an older deep link independently of the loaded list", () => {
    expect(resolveActiveChangeId(null, "999", CHANGES)).toBe(999);
  });

  it("falls back to the newest change for a malformed ?change= param", () => {
    expect(resolveActiveChangeId(null, "abc", CHANGES)).toBe(30);
  });

  it("lets an explicit selection override the deep link", () => {
    expect(resolveActiveChangeId(10, "20", CHANGES)).toBe(10);
  });

  it("drops a stale selection after navigating to another site", () => {
    expect(resolveActiveChangeId(999, null, CHANGES)).toBe(30);
  });
});
