import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { EmptyState, ErrorState } from "./feedback";

describe("ErrorState", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
  });

  it("shows the error copy and retries when the button is pressed", async () => {
    const onRetry = vi.fn();
    render(
      <I18nProvider>
        <ErrorState onRetry={onRetry} />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { name: /something went wrong/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("EmptyState", () => {
  it("uses the compact icon when no illustration is provided", () => {
    const { container } = render(
      <EmptyState icon={<span data-testid="compact-icon" />} title="Nothing here" description="Yet" />,
    );

    expect(screen.getByTestId("compact-icon")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeInTheDocument();
  });

  it("renders a decorative illustration instead of the compact icon", () => {
    render(
      <EmptyState
        icon={<span data-testid="compact-icon" />}
        visual={<svg data-testid="empty-visual" aria-hidden="true" />}
        title="Nothing here"
        description="Yet"
      />,
    );

    expect(screen.getByTestId("empty-visual")).toBeInTheDocument();
    expect(screen.queryByTestId("compact-icon")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Nothing here" })).toBeInTheDocument();
  });
});
