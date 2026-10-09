import type { User } from "./types";

type AuthRoutingUser = Pick<
  User,
  | "acting_organization_id"
  | "is_superadmin"
  | "mfa_enrollment_required"
  | "organization_suspended"
>;

const INSTANCE_OPERATOR_ROUTES = [
  "/audit",
  "/operations",
  "/organizations",
  "/plans",
  "/settings",
  "/users",
] as const;

/** Return the only protected route the current account state may enter. */
export function requiredAuthenticatedRoute(
  user: AuthRoutingUser,
  pathname: string,
): string | null {
  if (user.mfa_enrollment_required && pathname !== "/settings") return "/settings";
  if (user.organization_suspended && pathname !== "/billing") return "/billing";
  if (
    user.is_superadmin &&
    user.acting_organization_id === null &&
    !INSTANCE_OPERATOR_ROUTES.some(
      (route) => pathname === route || pathname.startsWith(`${route}/`),
    )
  ) {
    return "/operations";
  }
  return null;
}

/** Resolve a requested in-app destination without crossing an account boundary. */
export function authenticatedDestination(
  user: AuthRoutingUser,
  requested = "/dashboard",
): string {
  const pathname = requested.split(/[?#]/, 1)[0] || "/";
  return requiredAuthenticatedRoute(user, pathname) ?? requested;
}
