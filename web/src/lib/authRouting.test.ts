import { describe, expect, it } from "vitest";

import { authenticatedDestination, requiredAuthenticatedRoute } from "./authRouting";

const tenantUser = {
  acting_organization_id: null,
  is_superadmin: false,
  mfa_enrollment_required: false,
  organization_suspended: false,
};

describe("requiredAuthenticatedRoute", () => {
  it("routes a suspended tenant away from locked product APIs", () => {
    const user = { ...tenantUser, organization_suspended: true };
    expect(requiredAuthenticatedRoute(user, "/dashboard")).toBe("/billing");
    expect(requiredAuthenticatedRoute(user, "/billing")).toBeNull();
  });

  it("keeps mandatory administrator MFA enrollment as the first restriction", () => {
    const user = { ...tenantUser, mfa_enrollment_required: true, organization_suspended: true };
    expect(requiredAuthenticatedRoute(user, "/dashboard")).toBe("/settings");
  });

  it("does not redirect an unrestricted account", () => {
    expect(requiredAuthenticatedRoute(tenantUser, "/dashboard")).toBeNull();
  });

  it("keeps an instance operator out of tenant routes until an organization is selected", () => {
    const operator = { ...tenantUser, is_superadmin: true };

    expect(requiredAuthenticatedRoute(operator, "/dashboard")).toBe("/operations");
    expect(requiredAuthenticatedRoute(operator, "/notifications")).toBe("/operations");
    expect(requiredAuthenticatedRoute(operator, "/operations")).toBeNull();
    expect(requiredAuthenticatedRoute(operator, "/users")).toBeNull();
    expect(authenticatedDestination(operator, "/sites/7?change=8")).toBe("/operations");
  });

  it("allows the operator to enter tenant routes only in an acting organization", () => {
    const operator = { ...tenantUser, is_superadmin: true, acting_organization_id: 12 };

    expect(requiredAuthenticatedRoute(operator, "/dashboard")).toBeNull();
    expect(authenticatedDestination(operator)).toBe("/dashboard");
  });
});
