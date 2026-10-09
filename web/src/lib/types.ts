export type NotificationMode = "only_significant" | "always";

export type CheckStatus = "baseline" | "unchanged" | "changed";

export interface User {
  id: number;
  email: string;
  name: string | null;
  is_admin: boolean;
  is_superadmin: boolean;
  organization_id: number | null;
  project_ids?: number[];
  site_ids?: number[];
  totp_enabled: boolean;
  mfa_enrollment_required: boolean;
  organization_suspended: boolean;
  acting_organization_id: number | null;
  acting_organization_name: string | null;
}

export interface LoginResult {
  totp_required: boolean;
  user: User | null;
}

export interface TotpSetup {
  secret: string;
  otpauth_uri: string;
  qr_svg_data_uri: string;
}

export interface UserDetail extends User {
  is_active: boolean;
  project_ids: number[];
  site_ids: number[];
}

export interface OperatorIdentity {
  id: number;
  email: string;
  name: string | null;
  is_active: boolean;
  project_ids?: number[];
  site_ids?: number[];
  totp_enabled: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuditEvent {
  id: number;
  occurred_at: string;
  actor_user_id: number;
  actor_email: string;
  actor_is_superadmin: boolean;
  organization_id: number | null;
  action: string;
  target_type: string;
  target_id: string | null;
  target_label: string | null;
  source_ip: string | null;
  details: Record<string, unknown>;
}

export interface AdminCapabilities {
  database_backend: "sqlite" | "postgresql";
  sqlite_backup_restore: boolean;
  raw_logs_in_product: false;
}

export interface Organization {
  id: number;
  name: string;
  is_active: boolean;
  plan: string;
  plan_id: number | null;
  max_sites: number | null;
  max_members: number | null;
  monthly_ai_check_limit: number | null;
  created_at: string;
  member_count: number;
  site_count: number;
  ai_checks_this_month: number;
  billing_managed: boolean;
  billing_suspended: boolean;
}

export interface Plan {
  id: number;
  key: string;
  name: string;
  max_sites: number | null;
  max_members: number | null;
  monthly_ai_check_limit: number | null;
  price_override_cents: number | null;
  currency: string;
  is_active: boolean;
  is_self_serve: boolean;
  sort_order: number;
  suggested_price_cents: number;
  effective_price_cents: number;
}

export interface PlanInput {
  key: string;
  name: string;
  max_sites: number | null;
  max_members: number | null;
  monthly_ai_check_limit: number | null;
  price_override_cents: number | null;
  currency: string;
  is_active: boolean;
  is_self_serve: boolean;
  sort_order: number;
}

export interface PricingContext {
  base_fee: number;
  per_site_fee: number;
  ai_margin: number;
  unlimited_sites: number;
  unlimited_checks: number;
  currency: string;
  model: string;
  input_price_per_1m: number;
  output_price_per_1m: number;
  avg_prompt_tokens: number;
  avg_completion_tokens: number;
  cost_per_check: number;
}

export interface PriceSuggestion {
  suggested_price_cents: number;
  currency: string;
}

export interface PublicPlan {
  key: string;
  name: string;
  max_sites: number | null;
  max_members: number | null;
  monthly_ai_check_limit: number | null;
  price_cents: number;
  currency: string;
}

export interface BillingCatalogPrice {
  billing_price_id: number;
  price_version: number;
  plan_id: number;
  plan_key: string;
  plan_name: string;
  max_sites: number | null;
  max_members: number | null;
  monthly_ai_check_limit: number | null;
  unit_amount_minor: number;
  currency: string;
  recurring_interval: string;
  interval_count: number;
}

export interface BillingCatalog {
  self_serve_ready: boolean;
  terms_version: string | null;
  privacy_version: string | null;
  terms_url: string | null;
  privacy_url: string | null;
  terms_sha256: string | null;
  privacy_sha256: string | null;
  prices: BillingCatalogPrice[];
}

export type BillingInterval = "day" | "week" | "month" | "year";

export interface BillingPrice {
  id: number;
  plan_id: number;
  provider: string;
  provider_price_id: string;
  version: number;
  unit_amount_minor: number;
  currency: string;
  recurring_interval: BillingInterval;
  interval_count: number;
  is_active: boolean;
  created_at: string;
  retired_at: string | null;
}

export interface BillingPriceInput {
  plan_id: number;
  provider: "stripe";
  provider_price_id: string;
  unit_amount_minor: number;
  currency: string;
  recurring_interval: BillingInterval;
  interval_count: number;
}

export interface BillingSubscriptionStatus {
  status: string;
  plan_id: number | null;
  plan_key: string | null;
  plan_name: string | null;
  current_period_end: string | null;
  trial_end: string | null;
  cancel_at_period_end: boolean;
  entitlement_active: boolean;
  entitlement_valid_until: string | null;
  access_suspended_at: string | null;
}

export interface BillingStatus {
  provider: string;
  provider_configured: boolean;
  self_serve_ready: boolean;
  customer_exists: boolean;
  subscription: BillingSubscriptionStatus | null;
}

export interface BillingReconciliation {
  organization_id: number;
  subscriptions_seen: number;
  subscriptions_updated: number;
}

export interface HostedBillingSession {
  url: string;
  expires_at: string | null;
}

export interface InteractionStep {
  action: "click" | "fill" | "wait_for" | "wait";
  selector?: string | null;
  /** Write-only; API responses never include this field. */
  secret_value?: string | null;
  /** Opaque reference returned for an already stored fill value. */
  secret_ref?: string | null;
  has_secret?: boolean;
  timeout_ms?: number;
}

export interface Site {
  analysis_mode?: "ai" | "disabled";
  id: number;
  url: string;
  name: string | null;
  project_id: number | null;
  css_selector: string | null;
  prompt: string | null;
  interaction_steps: InteractionStep[];
  ignore_selectors: string[];
  check_interval_minutes: number;
  enabled: boolean;
  notification_mode: NotificationMode | null;
  last_checked_at: string | null;
  last_alert_code: string | null;
  last_alert_at: string | null;
  /** The underlying error message behind the alert badge. */
  last_alert_detail: string | null;
  consecutive_failure_count: number;
  created_at: string;
  recipient_ids: number[];
  change_count: number;
  last_change_at: string | null;
}

export interface Project {
  id: number;
  name: string;
  prompt: string | null;
  notification_mode: NotificationMode | null;
  site_count: number;
  recipient_ids: number[];
}

export interface Recipient {
  id: number;
  email: string;
  name: string | null;
  active: boolean;
}

export interface Substitution {
  id: number;
  recipient_id: number;
  substitute_email: string;
  substitute_name: string | null;
  start_date: string;
  end_date: string;
  project_id: number | null;
  site_id: number | null;
}

export interface Change {
  analysis_status?: "pending" | "processing" | "succeeded" | "disabled" | "not_requested" | "skipped_no_delivery" | "error" | "quota_blocked";
  id: number;
  site_id: number;
  created_at: string;
  significant: boolean | null;
  headline: string | null;
  summary: string | null;
  ai_error: string | null;
  ai_retry_count: number;
  notification_error: string | null;
  notification_retry_count: number;
  retry_status: string | null;
  next_retry_at: string | null;
  notified_at: string | null;
  /** Human review of the AI verdict; null = not reviewed yet. */
  user_verdict: boolean | null;
  user_verdict_at: string | null;
}

export interface Notification {
  id: number;
  change_id: number;
  recipient_email: string;
  channel: string;
  status: "sent" | "failed" | "skipped";
  error: string | null;
  message_id: string | null;
  sent_at: string;
  site_id: number | null;
  site_name: string | null;
  headline: string | null;
}

/** One entry of a change's analysis history, newest first. */
export interface AnalysisRun {
  id: number;
  significant: boolean;
  headline: string;
  summary: string;
  created_at: string;
  model: string | null;
  rules_source: string | null;
  rules_version: string | null;
  system_prompt: string | null;
  input_sha256: string | null;
  input_truncated: boolean | null;
  usage_id: number | null;
}

export interface ChangeDetail extends Change {
  old_snapshot_id: number | null;
  new_snapshot_id: number;
  diff_text: string;
  diff_html: string;
  analysis_runs: AnalysisRun[];
}

/** The importance rules the analyzer would apply, and which level supplies them. */
export interface EffectiveRules {
  source: "site" | "project" | "global" | "default";
  text: string;
}

/** Dry-run verdict for draft rules — never persisted to the change. */
export interface AnalysisPreview {
  significant: boolean;
  headline: string;
  summary: string;
  model: string;
  cost_usd: number | null;
}

export interface RunResult {
  site_id: number;
  status: CheckStatus;
  change_id: number | null;
  significant: boolean | null;
  notified: boolean;
  recipients: number;
  ai_error: string | null;
  capture_error: string | null;
}

export interface UsageByModel {
  model: string;
  calls: number;
  total_tokens: number;
  cost_usd: number | null;
  known_cost_usd: number;
  unknown_cost_calls: number;
}

export interface UsageBucket {
  label: string;
  calls: number;
  total_tokens: number;
  cost_usd: number | null;
  known_cost_usd: number;
  unknown_cost_calls: number;
}

export interface UsageSummary {
  total_cost_usd: number | null;
  known_cost_usd: number;
  unknown_cost_calls: number;
  total_tokens: number;
  calls: number;
  by_model: UsageByModel[];
  by_month: UsageBucket[];
  by_site: UsageBucket[];
  by_project: UsageBucket[];
}

export type Settings = Record<string, string>;

export interface VerdictSummary {
  reviewed: number;
  agreed: number;
  false_positives: number;
  false_negatives: number;
  agreement_rate: number;
}

export interface AuthCapabilities {
  registration_enabled: boolean;
  initial_setup_required: boolean;
}

/** Public branding for the landing and app shell. Empty strings mean "unset", so
 * the UI falls back to its built-in defaults. */
export interface Branding {
  brand_name: string;
  logo_url: string;
  accent_color: string;
  tagline: string;
  hero_title: string;
  hero_subtitle: string;
  hero_background_url: string;
}

export interface FactoryDefaults {
  base_prompt: string;
  importance_rules: string;
  stripped_tags: string[];
  volatile_attributes: string[];
  volatile_patterns: string[];
  response_fields: Record<string, string>;
}

export type PickerState = "starting" | "waiting" | "saved" | "cancelled" | "timed_out" | "error";

export interface PickerStatus {
  session_id: string;
  state: PickerState;
  mode: "select" | "record";
  selector_count: number;
  step_count: number;
  channel: string | null;
  detail: string | null;
}

export interface PickerResult {
  css_selector: string;
  selectors: string[];
  steps: InteractionStep[];
}

export interface PickerCapabilities {
  available: boolean;
  reason: string | null;
}
