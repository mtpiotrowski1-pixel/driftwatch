import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { api } from "@/lib/api";
import type { VerdictSummary } from "@/lib/types";
import { ReviewAgreement } from "./ReviewAgreement";

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.setItem("driftwatch_lang", "en");
});

function renderAgreement() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider><ReviewAgreement /></I18nProvider>
    </QueryClientProvider>,
  );
}

const reviewed: VerdictSummary = {
  reviewed: 4, agreed: 3, false_positives: 1, false_negatives: 0, agreement_rate: 0.75,
};

it("shows the actual reviewed denominator and explains that undetected changes are excluded", async () => {
  const get = vi.spyOn(api, "get").mockResolvedValue(reviewed);
  renderAgreement();
  expect(await screen.findByText("75% (3/4)")).toBeVisible();
  expect(screen.getByText(/only detected changes reviewed by a person/)).toBeVisible();
  expect(get).toHaveBeenCalledWith("/api/usage/verdicts");
});

it("distinguishes no reviews from zero agreement and keeps the limitation in Polish", async () => {
  localStorage.setItem("driftwatch_lang", "pl");
  vi.spyOn(api, "get").mockResolvedValue({ ...reviewed, reviewed: 0, agreed: 0, agreement_rate: 0 });
  renderAgreement();
  expect(await screen.findByText("Brak ocen człowieka.")).toBeVisible();
  expect(screen.getByText(/Nie mierzy pominiętych zmian/)).toBeVisible();
  expect(screen.queryByText("0% (0/0)")).toBeNull();
});

it("allows a failed summary to be retried without displaying a fabricated score", async () => {
  const get = vi.spyOn(api, "get").mockRejectedValueOnce(new Error("offline")).mockResolvedValue(reviewed);
  renderAgreement();
  await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
  expect(await screen.findByText("75% (3/4)")).toBeVisible();
  expect(get).toHaveBeenCalledTimes(2);
});
