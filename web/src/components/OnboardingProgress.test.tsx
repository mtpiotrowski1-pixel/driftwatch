import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { I18nProvider } from "@/i18n";
import {
  useCheckSite,
  useNotifications,
  useProjects,
  useRecipients,
} from "@/lib/queries";
import type { Notification, Project, Recipient, RunResult, Site } from "@/lib/types";

import { deriveOnboardingSignals, OnboardingProgress } from "./OnboardingProgress";

vi.mock("@/lib/queries", () => ({
  useCheckSite: vi.fn(),
  useNotifications: vi.fn(),
  useProjects: vi.fn(),
  useRecipients: vi.fn(),
}));

const SITE: Site = {
  id: 7,
  url: "https://example.test",
  name: "Example",
  project_id: null,
  css_selector: null,
  prompt: null,
  interaction_steps: [],
  ignore_selectors: [],
  check_interval_minutes: 60,
  enabled: true,
  notification_mode: null,
  last_checked_at: null,
  last_alert_code: null,
  last_alert_at: null,
  last_alert_detail: null,
  consecutive_failure_count: 0,
  created_at: "2026-07-17T10:00:00Z",
  recipient_ids: [],
  change_count: 0,
  last_change_at: null,
};

const RECIPIENT: Recipient = {
  id: 11,
  email: "alerts@example.test",
  name: "Alerts",
  active: true,
};

const PROJECT: Project = {
  id: 4,
  name: "Main",
  prompt: null,
  notification_mode: null,
  site_count: 1,
  recipient_ids: [RECIPIENT.id],
};

const SENT_NOTIFICATION: Notification = {
  id: 31,
  change_id: 21,
  recipient_email: RECIPIENT.email,
  channel: "email",
  status: "sent",
  error: null,
  message_id: "message-1",
  sent_at: "2026-07-17T11:00:00Z",
  site_id: SITE.id,
  site_name: SITE.name,
  headline: "Changed",
};

const CHECK_RESULT: RunResult = {
  site_id: SITE.id,
  status: "baseline",
  change_id: null,
  significant: null,
  notified: false,
  recipients: 0,
  ai_error: null,
  capture_error: null,
};

function queryResult<T>(data: T) {
  return { data, isLoading: false, isError: false };
}

function mockQueries({
  recipients = [],
  projects = [],
  notifications = [],
  mutateAsync = vi.fn().mockResolvedValue(CHECK_RESULT),
}: {
  recipients?: Recipient[];
  projects?: Project[];
  notifications?: Notification[];
  mutateAsync?: ReturnType<typeof vi.fn>;
} = {}) {
  vi.mocked(useRecipients).mockReturnValue(
    queryResult(recipients) as unknown as ReturnType<typeof useRecipients>,
  );
  vi.mocked(useProjects).mockReturnValue(
    queryResult(projects) as unknown as ReturnType<typeof useProjects>,
  );
  vi.mocked(useNotifications).mockReturnValue(
    queryResult({ pages: [notifications], pageParams: [0] }) as unknown as ReturnType<typeof useNotifications>,
  );
  vi.mocked(useCheckSite).mockReturnValue({
    mutateAsync,
    isPending: false,
  } as unknown as ReturnType<typeof useCheckSite>);
  return mutateAsync;
}

function renderProgress(sites: Site[]) {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <ToastProvider>
          <OnboardingProgress sites={sites} />
        </ToastProvider>
      </MemoryRouter>
    </I18nProvider>,
  );
}

describe("OnboardingProgress", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("driftwatch_lang", "en");
  });

  it("starts with a direct add-page action and can be collapsed", async () => {
    mockQueries();
    renderProgress([]);

    expect(screen.getByRole("heading", { name: "Monitoring setup" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByRole("link", { name: /Add page/ })).toHaveAttribute(
      "href",
      "/sites/new",
    );

    await userEvent.click(screen.getByRole("button", { name: "Collapse setup" }));
    expect(screen.getByRole("list", { hidden: true })).not.toBeVisible();
    expect(screen.getByRole("button", { name: "Expand setup" })).toBeInTheDocument();
  });

  it("runs the first check directly when a page has no baseline", async () => {
    const mutateAsync = mockQueries();
    renderProgress([SITE]);

    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
    await userEvent.click(screen.getByRole("button", { name: "Run first check" }));

    expect(mutateAsync).toHaveBeenCalledWith({ id: SITE.id });
    expect(await screen.findByText("The first check is complete.")).toBeInTheDocument();
  });

  it("recognizes configured delivery inherited from a project", () => {
    const signals = deriveOnboardingSignals(
      [{ ...SITE, project_id: PROJECT.id, last_checked_at: "2026-07-17T10:30:00Z" }],
      [RECIPIENT],
      [PROJECT],
      [],
    );

    expect(signals).toEqual({
      hasSite: true,
      hasBaseline: true,
      hasRecipient: true,
      hasDelivery: true,
    });
  });

  it("opens the checked monitor when delivery still needs configuration", () => {
    const checkedSite = {
      ...SITE,
      id: 8,
      last_checked_at: "2026-07-17T10:30:00Z",
    };
    mockQueries({ recipients: [RECIPIENT] });
    renderProgress([SITE, checkedSite]);

    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3");
    expect(screen.getByRole("link", { name: /Configure site/ })).toHaveAttribute(
      "href",
      "/sites/8",
    );
  });

  it("accepts a confirmed sent delivery and hides after all milestones", () => {
    const checkedSite = { ...SITE, last_checked_at: "2026-07-17T10:30:00Z" };
    mockQueries({ recipients: [RECIPIENT], notifications: [SENT_NOTIFICATION] });
    renderProgress([checkedSite]);

    expect(useNotifications).toHaveBeenCalledWith("sent");
    expect(screen.queryByText("Monitoring setup")).not.toBeInTheDocument();
  });
});
