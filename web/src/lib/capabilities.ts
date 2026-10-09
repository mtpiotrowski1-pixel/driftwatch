import type { Project, Site, User } from "./types";

export function canEditProject(user: User | null | undefined, projectId: number): boolean {
  return !!user && (
    user.is_admin || user.is_superadmin || (user.project_ids ?? []).includes(projectId)
  );
}

export function canEditSite(user: User | null | undefined, site: Pick<Site, "id" | "project_id">): boolean {
  return !!user && (
    user.is_admin || user.is_superadmin || (user.site_ids ?? []).includes(site.id) ||
    (site.project_id !== null && canEditProject(user, site.project_id))
  );
}

export function canCreateSite(user: User | null | undefined): boolean {
  return !!user && (
    user.is_admin || user.is_superadmin || (user.project_ids ?? []).length > 0
  );
}

export function canManageRecipient(
  user: User | null | undefined,
  recipientId: number,
  sites: readonly Pick<Site, "id" | "project_id" | "recipient_ids">[],
  projects: readonly Pick<Project, "id" | "recipient_ids">[],
): boolean {
  if (!user) return false;
  if (user.is_admin || user.is_superadmin) return true;
  // A site's inherited project destination belongs to the project; a direct
  // site grant cannot authorize redirecting that project's shared recipient.
  return sites.some((site) => site.recipient_ids.includes(recipientId) && canEditSite(user, site)) ||
    projects.some((project) => project.recipient_ids.includes(recipientId) && canEditProject(user, project.id));
}
