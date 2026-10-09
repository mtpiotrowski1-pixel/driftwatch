import { beforeEach, describe, expect, it } from "vitest";

import {
  checkoutStorageKey,
  clearCheckoutKey,
  clearOrganizationCheckoutKeys,
  getOrCreateCheckoutKey,
  trustedHostedBillingUrl,
  type CheckoutKeyScope,
} from "./billing";

const SCOPE: CheckoutKeyScope = {
  organizationId: 7,
  billingPriceId: 3,
  termsSha256: "a".repeat(64),
  privacySha256: "b".repeat(64),
};

beforeEach(() => sessionStorage.clear());

describe("trustedHostedBillingUrl", () => {
  it.each([
    "http://checkout.stripe.com/c/pay/session",
    "https://checkout.stripe.com.evil.test/c/pay/session",
    "https://billing.stripe.com:444/p/session/test",
    "https://user@billing.stripe.com/p/session/test",
    "not a URL",
  ])("rejects an untrusted provider destination: %s", (value) => {
    expect(trustedHostedBillingUrl(value)).toBeNull();
  });

  it.each([
    "https://checkout.stripe.com/c/pay/session",
    "https://billing.stripe.com/p/session/test",
  ])("accepts a pinned Stripe hosted surface: %s", (value) => {
    expect(trustedHostedBillingUrl(value)).toBe(new URL(value).toString());
  });
});

describe("checkout retry key", () => {
  it("survives a component reload within the same tab and legal contract", () => {
    const first = getOrCreateCheckoutKey(SCOPE);
    const afterReload = getOrCreateCheckoutKey({ ...SCOPE });

    expect(first).toMatch(/^checkout-/);
    expect(afterReload).toBe(first);
  });

  it("does not reuse a key across an organization, price, or legal fingerprint", () => {
    const first = getOrCreateCheckoutKey(SCOPE);
    const otherOrganization = getOrCreateCheckoutKey({ ...SCOPE, organizationId: 8 });
    const otherPrice = getOrCreateCheckoutKey({ ...SCOPE, billingPriceId: 4 });
    const otherTerms = getOrCreateCheckoutKey({ ...SCOPE, termsSha256: "c".repeat(64) });

    expect(new Set([first, otherOrganization, otherPrice, otherTerms]).size).toBe(4);
  });

  it("clears one terminal attempt or all successful attempts for an organization", () => {
    const first = getOrCreateCheckoutKey(SCOPE);
    const secondScope = { ...SCOPE, billingPriceId: 4 };
    getOrCreateCheckoutKey(secondScope);
    getOrCreateCheckoutKey({ ...SCOPE, organizationId: 8 });

    clearCheckoutKey(SCOPE);
    expect(sessionStorage.getItem(checkoutStorageKey(SCOPE))).toBeNull();
    expect(sessionStorage.getItem(checkoutStorageKey(secondScope))).not.toBeNull();

    sessionStorage.setItem(checkoutStorageKey(SCOPE), first);
    clearOrganizationCheckoutKeys(7);
    expect(sessionStorage.getItem(checkoutStorageKey(SCOPE))).toBeNull();
    expect(sessionStorage.getItem(checkoutStorageKey(secondScope))).toBeNull();
    expect(sessionStorage.length).toBe(1);
  });
});
