import { describe, expect, it } from "vitest";
import { canCreateSite, canEditProject, canEditSite, canManageRecipient } from "./capabilities";
import type { User } from "./types";

const MEMBER = { is_admin: false, is_superadmin: false, project_ids: [10], site_ids: [20] } as User;

describe("resource editing affordances", () => {
  it("reflects direct and inherited grants without granting another project", () => {
    expect(canEditProject(MEMBER, 10)).toBe(true);
    expect(canEditProject(MEMBER, 11)).toBe(false);
    expect(canEditSite(MEMBER, { id: 20, project_id: null })).toBe(true);
    expect(canEditSite(MEMBER, { id: 21, project_id: 10 })).toBe(true);
    expect(canEditSite(MEMBER, { id: 22, project_id: 11 })).toBe(false);
    expect(canCreateSite({ ...MEMBER, project_ids: [] })).toBe(false);
  });

  it("keeps management of a shared project recipient separate from a direct site grant", () => {
    const siteEditor = { ...MEMBER, project_ids: [] };
    const projects = [{ id: 10, recipient_ids: [1] }];
    const sites = [{ id: 20, project_id: 10, recipient_ids: [] }];
    expect(canManageRecipient(siteEditor, 1, sites, projects)).toBe(false);
    expect(canManageRecipient(siteEditor, 1, [{ ...sites[0], recipient_ids: [1] }], projects)).toBe(true);
    expect(canManageRecipient(MEMBER, 1, [], projects)).toBe(true);
    expect(canManageRecipient(siteEditor, 1, [{ id: 21, project_id: 11, recipient_ids: [1] }], [])).toBe(false);
    expect(canManageRecipient({ ...siteEditor, is_admin: true }, 1, [], [])).toBe(true);
    expect(canManageRecipient(null, 1, sites, projects)).toBe(false);
  });
});
