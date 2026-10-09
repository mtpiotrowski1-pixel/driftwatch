const TRUSTED_BILLING_HOSTS = new Set(["checkout.stripe.com", "billing.stripe.com"]);
const CHECKOUT_STORAGE_PREFIX = "driftwatch:billing:checkout";
const IDEMPOTENCY_KEY = /^[A-Za-z0-9._:-]{8,100}$/;

export interface CheckoutKeyScope {
  organizationId: number;
  billingPriceId: number;
  termsSha256: string;
  privacySha256: string;
}

export function trustedHostedBillingUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (
      url.protocol !== "https:" ||
      url.username !== "" ||
      url.password !== "" ||
      url.port !== "" ||
      !TRUSTED_BILLING_HOSTS.has(url.hostname)
    ) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

export function createBillingIdempotencyKey(prefix: "checkout" | "portal"): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

export function checkoutStorageKey(scope: CheckoutKeyScope): string {
  return [
    CHECKOUT_STORAGE_PREFIX,
    scope.organizationId,
    scope.billingPriceId,
    scope.termsSha256,
    scope.privacySha256,
  ].join(":");
}

/** Keep a checkout retry stable across reloads without persisting it across tabs. */
export function getOrCreateCheckoutKey(
  scope: CheckoutKeyScope,
  storage: Storage = sessionStorage,
): string {
  const storageKey = checkoutStorageKey(scope);
  try {
    const existing = storage.getItem(storageKey);
    if (existing && IDEMPOTENCY_KEY.test(existing)) return existing;
    const created = createBillingIdempotencyKey("checkout");
    storage.setItem(storageKey, created);
    return created;
  } catch {
    return createBillingIdempotencyKey("checkout");
  }
}

export function clearCheckoutKey(
  scope: CheckoutKeyScope,
  storage: Storage = sessionStorage,
): void {
  try {
    storage.removeItem(checkoutStorageKey(scope));
  } catch {
    // Storage can be disabled; server-side stale-attempt recovery remains authoritative.
  }
}

export function clearOrganizationCheckoutKeys(
  organizationId: number,
  storage: Storage = sessionStorage,
): void {
  const prefix = `${CHECKOUT_STORAGE_PREFIX}:${organizationId}:`;
  try {
    const matches: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key?.startsWith(prefix)) matches.push(key);
    }
    for (const key of matches) storage.removeItem(key);
  } catch {
    // A blocked Storage API is equivalent to an already-cleared client hint.
  }
}
