import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider, useT } from "@/i18n";
import { ThemeProvider } from "@/theme";

import { readStorage, writeStorage } from "./storage";

function blockStorage() {
  const denied = () => {
    throw new DOMException("Storage is disabled", "SecurityError");
  };
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(denied);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(denied);
}

function Greeting() {
  const t = useT();
  return <p>{t("common.cancel")}</p>;
}

describe("storage helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fall back instead of throwing when site storage is blocked", () => {
    blockStorage();

    expect(readStorage("driftwatch_lang")).toBeNull();
    expect(() => writeStorage("driftwatch_lang", "pl")).not.toThrow();
  });

  it("let the theme and language providers start with storage blocked", () => {
    blockStorage();

    render(
      <ThemeProvider>
        <I18nProvider>
          <Greeting />
        </I18nProvider>
      </ThemeProvider>,
    );

    expect(screen.getByRole("paragraph")).not.toBeEmptyDOMElement();
  });
});
