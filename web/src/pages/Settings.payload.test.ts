import { describe, expect, it } from "vitest";

import { buildSettingsPayload } from "./Settings";

const NO_EDITS = {
  text: {},
  secrets: {},
  numbers: {},
  importanceRules: null,
  defaultMode: null,
  ignoreSelectors: null,
  technicalIds: null,
};

describe("buildSettingsPayload", () => {
  it("is empty when nothing was touched", () => {
    expect(buildSettingsPayload(NO_EDITS, {}, "", [])).toEqual({});
  });

  it("treats an edit back to the stored value as no change", () => {
    const stored = { openai_model: "gpt-4o-mini" };
    expect(
      buildSettingsPayload({ ...NO_EDITS, text: { openai_model: "gpt-4o-mini" } }, stored, "", []),
    ).toEqual({});
  });

  it("includes a text field that differs from what is stored", () => {
    const stored = { openai_model: "gpt-4o-mini" };
    expect(
      buildSettingsPayload({ ...NO_EDITS, text: { openai_model: "gpt-4o" } }, stored, "", []),
    ).toEqual({ openai_model: "gpt-4o" });
  });

  it("never sends a secret left at its masked placeholder", () => {
    expect(
      buildSettingsPayload({ ...NO_EDITS, secrets: { openai_api_key: "********" } }, {}, "", []),
    ).toEqual({});
    expect(
      buildSettingsPayload({ ...NO_EDITS, secrets: { openai_api_key: "sk-live" } }, {}, "", []),
    ).toEqual({ openai_api_key: "sk-live" });
  });

  it("uses an explicit clear contract for a configured secret", () => {
    expect(
      buildSettingsPayload(
        { ...NO_EDITS, secrets: { notification_webhook_url: "" } },
        { notification_webhook_url: "********" },
        "",
        [],
      ),
    ).toEqual({ clear_secret_keys: ["notification_webhook_url"] });

    expect(
      buildSettingsPayload(
        { ...NO_EDITS, secrets: { notification_webhook_url: "" } },
        {},
        "",
        [],
      ),
    ).toEqual({});
  });

  it("coerces number fields to numbers", () => {
    expect(
      buildSettingsPayload({ ...NO_EDITS, numbers: { snapshot_retention: "10" } }, {}, "", []),
    ).toEqual({ snapshot_retention: 10 });
  });

  it("only sends the technical recipients when the selection actually changed", () => {
    expect(buildSettingsPayload({ ...NO_EDITS, technicalIds: [1, 2] }, {}, "", [2, 1])).toEqual({});
    expect(buildSettingsPayload({ ...NO_EDITS, technicalIds: [1, 3] }, {}, "", [1, 2])).toEqual({
      technical_alert_recipient_ids: [1, 3],
    });
  });
});
