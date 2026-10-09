import type { Settings } from "@/lib/types";

export const MASKED = "********";

const TEXT_FIELDS = [
  "openai_model",
  "base_prompt",
  "email_provider",
  "email_language",
  "notification_from_email",
  "notification_from_name",
  "smtp_host",
  "smtp_port",
  "smtp_username",
  "smtp_security",
  "email_subject_template",
  "email_body_intro",
  "notification_webhook_format",
  "watch_linked_documents",
  "brand_name",
  "brand_accent_color",
  "landing_tagline",
  "landing_hero_title",
  "landing_hero_subtitle",
] as const;

export const SECRET_FIELDS = [
  "openai_api_key",
  "smtp_password",
  "brevo_api_key",
  "notification_webhook_url",
] as const;

const NUMBER_FIELDS = [
  "capture_timeout_seconds",
  "capture_settle_ms",
  "capture_min_interval_seconds",
  "capture_jitter_ms",
  "snapshot_retention",
  "openai_price_input_per_1m",
  "openai_price_output_per_1m",
  "site_down_failure_threshold",
] as const;

export type TextKey = (typeof TEXT_FIELDS)[number];
export type SecretKey = (typeof SECRET_FIELDS)[number];
export type NumberKey = (typeof NUMBER_FIELDS)[number];

export const STEP_UP_TEXT_FIELDS: readonly TextKey[] = [
  "email_provider",
  "notification_from_email",
  "smtp_host",
  "smtp_port",
  "smtp_username",
  "smtp_security",
];

export interface SettingsEdits {
  text: Record<string, string>;
  secrets: Record<string, string>;
  numbers: Record<string, string>;
  importanceRules: string | null;
  defaultMode: string | null;
  ignoreSelectors: string | null;
  technicalIds: number[] | null;
}

/** The fields whose edits differ from what's stored — the body sent on save,
 * and (when non-empty) the signal that there are unsaved changes. */
export function buildSettingsPayload(
  edits: SettingsEdits,
  stored: Settings,
  initialIgnore: string,
  initialTechnical: number[],
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};

  for (const key of TEXT_FIELDS) {
    const next = edits.text[key];
    if (next !== undefined && next !== (stored[key] ?? "")) payload[key] = next;
  }
  for (const key of SECRET_FIELDS) {
    const next = edits.secrets[key];
    if (next === "" && Object.prototype.hasOwnProperty.call(edits.secrets, key)) {
      if (stored[key] === MASKED) {
        const clearKeys = (payload.clear_secret_keys ?? []) as SecretKey[];
        clearKeys.push(key);
        payload.clear_secret_keys = clearKeys;
      }
    } else if (next && next !== MASKED) {
      payload[key] = next;
    }
  }
  for (const key of NUMBER_FIELDS) {
    const next = edits.numbers[key];
    if (next !== undefined && next !== (stored[key] ?? "")) payload[key] = Number(next);
  }
  if (edits.importanceRules !== null && edits.importanceRules !== (stored.importance_rules ?? "")) {
    payload.importance_rules = edits.importanceRules;
  }
  if (edits.defaultMode !== null && edits.defaultMode !== stored.default_notification_mode) {
    payload.default_notification_mode = edits.defaultMode;
  }
  if (edits.ignoreSelectors !== null && edits.ignoreSelectors !== initialIgnore) {
    payload.ignore_selectors = splitIgnore(edits.ignoreSelectors);
  }
  if (edits.technicalIds !== null && !sameIds(edits.technicalIds, initialTechnical)) {
    payload.technical_alert_recipient_ids = edits.technicalIds;
  }

  return payload;
}

export function parseIgnore(raw: string | undefined): string {
  if (!raw) return "";
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.filter((value) => typeof value === "string").join("\n");
  } catch {
    // Stored value may already be a plain newline- or comma-separated string.
  }
  return splitIgnore(raw).join("\n");
}

function splitIgnore(raw: string): string[] {
  return raw
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean);
}

export function parseIds(raw: string | undefined): number[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.map(Number).filter((value) => Number.isFinite(value));
    }
  } catch {
    // Stored value may be a comma-separated list of ids.
  }
  return raw
    .split(",")
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value));
}

function sameIds(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((value) => set.has(value));
}
