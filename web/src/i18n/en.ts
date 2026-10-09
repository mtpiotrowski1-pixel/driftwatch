import access from "./en/access";
import audit from "./en/audit";
import billing from "./en/billing";
import addsite from "./en/addsite";
import common from "./en/common";
import dashboard from "./en/dashboard";
import landing from "./en/landing";
import login from "./en/login";
import notifications from "./en/notifications";
import operations from "./en/operations";
import organizations from "./en/organizations";
import picker from "./en/picker";
import plans from "./en/plans";
import projects from "./en/projects";
import recipients from "./en/recipients";
import rulestest from "./en/rulestest";
import settings from "./en/settings";
import sitedetail from "./en/sitedetail";
import support from "./en/support";
import twofa from "./en/twofa";

export const en: Record<string, string> = {
  ...common,
  ...landing,
  ...login,
  ...dashboard,
  ...addsite,
  ...sitedetail,
  ...recipients,
  ...projects,
  ...notifications,
  ...operations,
  ...settings,
  ...support,
  ...access,
  ...audit,
  ...billing,
  ...picker,
  ...organizations,
  ...plans,
  ...twofa,
  ...rulestest,
};
