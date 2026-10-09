import access from "./pl/access";
import audit from "./pl/audit";
import billing from "./pl/billing";
import addsite from "./pl/addsite";
import common from "./pl/common";
import dashboard from "./pl/dashboard";
import landing from "./pl/landing";
import login from "./pl/login";
import notifications from "./pl/notifications";
import operations from "./pl/operations";
import organizations from "./pl/organizations";
import picker from "./pl/picker";
import plans from "./pl/plans";
import projects from "./pl/projects";
import recipients from "./pl/recipients";
import rulestest from "./pl/rulestest";
import settings from "./pl/settings";
import sitedetail from "./pl/sitedetail";
import support from "./pl/support";
import twofa from "./pl/twofa";

export const pl: Record<string, string> = {
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
