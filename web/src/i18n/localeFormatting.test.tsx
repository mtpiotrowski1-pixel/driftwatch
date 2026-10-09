import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { relativeTime } from "@/lib/utils";

import { I18nProvider, useI18n } from "./index";

function LocaleProbe() {
  const { t, setLang } = useI18n();
  return <><button onClick={() => setLang("pl")}>Polski</button><p>{t("common.refresh")}</p><output>{relativeTime("2026-10-09T12:00:00Z")}</output></>;
}

describe("language and external formatter synchronization", () => {
  beforeEach(() => {
    localStorage.setItem("driftwatch_lang", "en");
    document.documentElement.lang = "en";
    vi.spyOn(Date, "now").mockReturnValue(new Date("2026-10-09T12:05:00Z").getTime());
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the selected translation and relative date in the same language immediately", async () => {
    render(<I18nProvider><LocaleProbe /></I18nProvider>);
    expect(screen.getByRole("status")).toHaveTextContent("5 minutes ago");
    await userEvent.click(screen.getByRole("button", { name: "Polski" }));
    expect(screen.getByText("Odśwież")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("5 minut temu");
    expect(document.documentElement.lang).toBe("pl");
  });

  it.each([
    [null, "pl-PL", "pl"],
    ["en", "pl-PL", "en"],
    ["invalid", "en-US", "en"],
  ])("sets a valid locale before first render for saved=%s browser=%s", (saved, browser, expected) => {
    const initialDocument = { documentElement: { lang: "en", dataset: {} } };
    runInNewContext(readFileSync(path.resolve("public/theme-init.js"), "utf8"), {
      document: initialDocument, navigator: { language: browser },
      localStorage: { getItem: (key: string) => key === "driftwatch_lang" ? saved : null },
    });
    expect(initialDocument.documentElement.lang).toBe(expected);
  });
});
