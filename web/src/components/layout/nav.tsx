import {
  Activity,
  Bell,
  Building2,
  CreditCard,
  FolderTree,
  LayoutDashboard,
  Plus,
  ScrollText,
  Settings,
  ShieldCheck,
  Tags,
  Users,
} from "lucide-react";
import { type ReactNode } from "react";

export interface NavItem {
  to: string;
  labelKey: string;
  icon: ReactNode;
  adminOnly?: boolean;
  superadminOnly?: boolean;
  organizationOnly?: boolean;
  // Items in the "operator" group are the instance-running surfaces (customers,
  // plans, pricing) shown under their own heading, apart from the product nav.
  group?: "operator";
  availableInActingOrganization?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  {
    to: "/dashboard",
    labelKey: "nav.dashboard",
    icon: <LayoutDashboard className="h-4 w-4" />,
    organizationOnly: true,
  },
  {
    to: "/sites/new",
    labelKey: "nav.addSite",
    icon: <Plus className="h-4 w-4" />,
    organizationOnly: true,
  },
  {
    to: "/projects",
    labelKey: "nav.projects",
    icon: <FolderTree className="h-4 w-4" />,
    organizationOnly: true,
  },
  {
    to: "/recipients",
    labelKey: "nav.recipients",
    icon: <Users className="h-4 w-4" />,
    organizationOnly: true,
  },
  {
    to: "/notifications",
    labelKey: "nav.notifications",
    icon: <Bell className="h-4 w-4" />,
    organizationOnly: true,
  },
  { to: "/users", labelKey: "nav.access", icon: <ShieldCheck className="h-4 w-4" />, adminOnly: true },
  {
    to: "/audit",
    labelKey: "nav.audit",
    icon: <ScrollText className="h-4 w-4" />,
    adminOnly: true,
  },
  {
    to: "/billing",
    labelKey: "nav.billing",
    icon: <CreditCard className="h-4 w-4" />,
    adminOnly: true,
    organizationOnly: true,
  },
  { to: "/settings", labelKey: "nav.settings", icon: <Settings className="h-4 w-4" /> },
  {
    to: "/operations",
    labelKey: "nav.operations",
    icon: <Activity className="h-4 w-4" />,
    superadminOnly: true,
    group: "operator",
    availableInActingOrganization: true,
  },
  {
    to: "/organizations",
    labelKey: "nav.organizations",
    icon: <Building2 className="h-4 w-4" />,
    superadminOnly: true,
    group: "operator",
  },
  {
    to: "/plans",
    labelKey: "nav.plans",
    icon: <Tags className="h-4 w-4" />,
    superadminOnly: true,
    group: "operator",
  },
];

interface NavViewer {
  is_admin?: boolean;
  is_superadmin?: boolean;
  organization_id?: number | null;
}

export function visibleNavItems(
  user: NavViewer | null | undefined,
  actingOrganization = false,
): NavItem[] {
  return NAV_ITEMS.filter((item) => {
    if (
      actingOrganization
      && item.group === "operator"
      && !item.availableInActingOrganization
    ) return false;
    if (item.organizationOnly) {
      const inOrganization = user?.is_superadmin
        ? actingOrganization
        : user?.organization_id != null;
      if (!inOrganization) return false;
    }
    if (item.superadminOnly) return user?.is_superadmin ?? false;
    if (item.adminOnly) return Boolean(user?.is_admin || user?.is_superadmin);
    return true;
  });
}

export function isOperatorNavPath(pathname: string): boolean {
  return NAV_ITEMS.some((item) => item.group === "operator" && item.to === pathname);
}

export function isInstanceOnlyOperatorNavPath(pathname: string): boolean {
  return NAV_ITEMS.some(
    (item) =>
      item.group === "operator"
      && !item.availableInActingOrganization
      && item.to === pathname,
  );
}
