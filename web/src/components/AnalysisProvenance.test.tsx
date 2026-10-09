import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";
import type { AnalysisRun } from "@/lib/types";
import { AnalysisProvenance } from "./AnalysisProvenance";

beforeEach(() => localStorage.setItem("driftwatch_lang", "en"));

const run: AnalysisRun = {
  id: 4, significant: true, headline: "Changed price", summary: "Price changed",
  created_at: "2026-10-08T12:00:00Z", model: "original-model", rules_source: "project",
  rules_version: "rules-hash", system_prompt: "Original prompt: <img src=x onerror=alert(1)>",
  input_sha256: "input-hash", input_truncated: false, usage_id: 7,
};

it("discloses the stored run inputs, including false truncation, and treats the prompt as text", async () => {
  render(<I18nProvider><AnalysisProvenance run={run} /></I18nProvider>);
  await userEvent.click(screen.getByRole("button", { name: "Completed analysis provenance" }));
  expect(screen.getByText("original-model")).toBeVisible();
  expect(screen.getByText("rules-hash")).toBeVisible();
  expect(screen.getByText("input-hash")).toBeVisible();
  expect(screen.getByText("No")).toBeVisible();
  await userEvent.click(screen.getByText("System prompt used in this analysis"));
  expect(screen.getByText(run.system_prompt!)).toBeVisible();
  expect(screen.queryByRole("img")).toBeNull();
});

it("shows unknown legacy metadata rather than borrowing present-day configuration", async () => {
  render(<I18nProvider><AnalysisProvenance run={{ ...run,
    model: null, rules_source: null, rules_version: null, system_prompt: null,
    input_sha256: null, input_truncated: null, usage_id: null,
  }} /></I18nProvider>);
  await userEvent.click(screen.getByRole("button", { name: "Completed analysis provenance" }));
  expect(screen.getAllByText("Unknown")).toHaveLength(6);
  expect(screen.getByText("This legacy analysis does not contain full provenance.")).toBeVisible();
  expect(screen.queryByText("original-model")).toBeNull();
  expect(screen.queryByText("No")).toBeNull();
});
