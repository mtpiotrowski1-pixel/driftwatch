import { describe, expect, it } from "vitest";

import { changeStatus } from "./ChangeBadge";

const clean = {
  significant: false,
  ai_error: null,
  notification_error: null,
};

describe("changeStatus", () => {
  it("distinguishes a completed negative verdict from a missing analysis", () => {
    expect(changeStatus(clean).labelKey).toBe("sitedetail.badge.notSignificant");
    expect(changeStatus({ ...clean, significant: null }).labelKey).toBe(
      "sitedetail.badge.notAnalyzed",
    );
  });

  it("prioritizes analysis and delivery failures over the verdict", () => {
    expect(changeStatus({ ...clean, significant: true, ai_error: "model timeout" })).toEqual({
      tone: "rose",
      labelKey: "sitedetail.badge.needsAttention",
    });
    expect(changeStatus({ ...clean, notification_error: "SMTP rejected" }).tone).toBe("rose");
  });

  it("marks a positive AI verdict as significant", () => {
    expect(changeStatus({ ...clean, significant: true })).toEqual({
      tone: "amber",
      labelKey: "sitedetail.badge.significant",
    });
  });
});
