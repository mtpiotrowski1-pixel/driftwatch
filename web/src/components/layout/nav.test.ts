import { describe, expect, it } from "vitest";

import {
  isInstanceOnlyOperatorNavPath,
  isOperatorNavPath,
  visibleNavItems,
} from "./nav";

const labelsFor = (
  user:
    | { is_admin?: boolean; is_superadmin?: boolean; organization_id?: number | null }
    | undefined,
) =>
  visibleNavItems(user).map((item) => item.labelKey);

describe("visibleNavItems", () => {
  it("hides admin and operator entries from a regular member", () => {
    const labels = labelsFor({
      is_admin: false,
      is_superadmin: false,
      organization_id: 1,
    });
    expect(labels).toContain("nav.dashboard");
    expect(labels).not.toContain("nav.access");
    expect(labels).not.toContain("nav.audit");
    expect(labels).not.toContain("nav.organizations");
    expect(labels).not.toContain("nav.plans");
  });

  it("shows Access to an admin, but not Organizations or Plans", () => {
    const labels = labelsFor({ is_admin: true, is_superadmin: false, organization_id: 1 });
    expect(labels).toContain("nav.access");
    expect(labels).toContain("nav.audit");
    expect(labels).not.toContain("nav.organizations");
    expect(labels).not.toContain("nav.plans");
  });

  it("shows Organizations and Plans to the operator", () => {
    const labels = labelsFor({ is_admin: true, is_superadmin: true });
    expect(labels).toContain("nav.operations");
    expect(labels).toContain("nav.organizations");
    expect(labels).toContain("nav.plans");
    expect(labels).toContain("nav.access");
    expect(labels).toContain("nav.audit");
    expect(labels).not.toContain("nav.dashboard");
    expect(labels).not.toContain("nav.notifications");
  });

  it("treats the operator role as administrative without a duplicated admin flag", () => {
    const labels = labelsFor({ is_admin: false, is_superadmin: true });
    expect(labels).toContain("nav.access");
    expect(labels).toContain("nav.audit");
    expect(labels).toContain("nav.operations");
    expect(labels).not.toContain("nav.dashboard");
  });

  it("requires an explicit organization before showing tenant billing to an operator", () => {
    const instanceLabels = visibleNavItems({
      is_admin: true,
      is_superadmin: true,
      organization_id: 7,
    }).map((item) => item.labelKey);
    const tenantLabels = visibleNavItems(
      { is_admin: true, is_superadmin: true, organization_id: 7 },
      true,
    ).map((item) => item.labelKey);

    expect(instanceLabels).not.toContain("nav.billing");
    expect(instanceLabels).not.toContain("nav.dashboard");
    expect(tenantLabels).toContain("nav.billing");
    expect(tenantLabels).toContain("nav.dashboard");
  });

  it("shows tenant billing to an organization administrator", () => {
    const labels = labelsFor({
      is_admin: true,
      is_superadmin: false,
      organization_id: 7,
    });

    expect(labels).toContain("nav.billing");
  });

  it("treats an unknown viewer as a member", () => {
    const labels = labelsFor(undefined);
    expect(labels).not.toContain("nav.access");
    expect(labels).not.toContain("nav.organizations");
  });

  it("groups Organizations and Plans under the operator section", () => {
    const operator = visibleNavItems({ is_admin: true, is_superadmin: true }).filter(
      (item) => item.group === "operator",
    );
    expect(operator.map((item) => item.labelKey)).toEqual([
      "nav.operations",
      "nav.organizations",
      "nav.plans",
    ]);
  });

  it("keeps recovery operations but hides other instance navigation inside an organization", () => {
    const labels = visibleNavItems({ is_admin: true, is_superadmin: true }, true).map(
      (item) => item.labelKey,
    );

    expect(labels).toContain("nav.dashboard");
    expect(labels).toContain("nav.access");
    expect(labels).toContain("nav.operations");
    expect(labels).not.toContain("nav.organizations");
    expect(labels).not.toContain("nav.plans");
  });

  it("identifies routes that could switch the active organization", () => {
    expect(isOperatorNavPath("/operations")).toBe(true);
    expect(isOperatorNavPath("/organizations")).toBe(true);
    expect(isOperatorNavPath("/plans")).toBe(true);
    expect(isOperatorNavPath("/dashboard")).toBe(false);
    expect(isInstanceOnlyOperatorNavPath("/operations")).toBe(false);
    expect(isInstanceOnlyOperatorNavPath("/organizations")).toBe(true);
    expect(isInstanceOnlyOperatorNavPath("/plans")).toBe(true);
  });
});
