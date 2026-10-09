import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { I18nProvider } from "@/i18n";
import { useAnalyzePreview } from "@/lib/queries";
import { RulesTester } from "./RulesTester";
import type { AnalysisPreview } from "@/lib/types";

vi.mock("@/lib/queries", () => ({ useAnalyzePreview: vi.fn() }));

beforeEach(() => localStorage.setItem("driftwatch_lang", "en"));

it("binds a verdict to the tested rules and hides it after editing", async () => {
  const mutate = vi.fn((_variables: unknown, callbacks: { onSuccess: (data: AnalysisPreview) => void }) => callbacks.onSuccess({ model: "test-model", cost_usd: null, significant: true, headline: "Rules A verdict", summary: "Test result" } as AnalysisPreview));
  vi.mocked(useAnalyzePreview).mockReturnValue({ mutate, isPending: false, data: { model: "test-model", cost_usd: null, significant: true, headline: "Rules A verdict", summary: "Test result" } } as unknown as ReturnType<typeof useAnalyzePreview>);
  const view = render(<I18nProvider><RulesTester changeId={1} rules="Rules A" /></I18nProvider>);
  await userEvent.click(screen.getByRole("button"));
  expect(screen.getByText("Rules A verdict")).toBeVisible();
  expect(screen.getByText("Model: test-model · Cost: Unknown")).toBeVisible();
  view.rerender(<I18nProvider><RulesTester changeId={1} rules="Rules B" /></I18nProvider>);
  expect(screen.queryByText("Rules A verdict")).toBeNull();
  view.rerender(<I18nProvider><RulesTester changeId={2} rules="Rules A" /></I18nProvider>);
  expect(screen.queryByText("Rules A verdict")).toBeNull();
});

it("discards a response that arrives after its draft rules changed", async () => {
  const finishes: Array<(data: AnalysisPreview) => void> = [];
  const mutate = vi.fn((_variables: unknown, callbacks: { onSuccess: (data: AnalysisPreview) => void }) => {
    finishes.push(callbacks.onSuccess);
  });
  vi.mocked(useAnalyzePreview).mockReturnValue({ mutate, isPending: false } as unknown as ReturnType<typeof useAnalyzePreview>);
  const view = render(<I18nProvider><RulesTester changeId={1} rules="Rules A" /></I18nProvider>);
  await userEvent.click(screen.getByRole("button"));
  view.rerender(<I18nProvider><RulesTester changeId={1} rules="Rules B" /></I18nProvider>);
  act(() => finishes[0]({ model: "test-model", cost_usd: null, significant: true, headline: "Late A", summary: "Old draft" } as AnalysisPreview));
  expect(screen.queryByText("Late A")).toBeNull();
  await userEvent.click(screen.getByRole("button"));
  act(() => finishes[1]({ model: "test-model", cost_usd: 0, significant: false, headline: "Current B", summary: "Current draft" } as AnalysisPreview));
  expect(screen.getByText("Current B")).toBeVisible();
  expect(screen.getByText("Model: test-model · Cost: $0.00")).toBeVisible();
});
