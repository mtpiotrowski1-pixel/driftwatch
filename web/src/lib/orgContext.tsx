import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  ACTING_ORG_STORAGE_KEY,
  RequestContextChangedError,
  api,
  bindRequestSession,
  instanceRequestContext,
  organizationRequestContext,
} from "./api";
import {
  ACTING_ORG_CLEARED_EVENT,
  keys,
  resetOrganizationQueryCache,
  useCurrentUser,
} from "./queries";
import type { User } from "./types";
import { BEFORE_ORGANIZATION_CHANGE } from "./useUnsavedChanges";

export interface ActingOrg {
  id: number;
  name: string;
}

function readStored(): ActingOrg | null {
  try {
    const raw = localStorage.getItem(ACTING_ORG_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ActingOrg;
    return Number.isSafeInteger(parsed?.id) && parsed.id > 0 && typeof parsed.name === "string"
      ? parsed
      : null;
  } catch {
    return null;
  }
}

interface OrgContextValue {
  /** The organization the operator has entered, or null for the instance view. */
  actingOrg: ActingOrg | null;
  enterOrg: (org: ActingOrg) => Promise<User>;
  exitOrg: (expectedOrganizationId?: number) => Promise<void>;
}

export class OrganizationTransitionCancelledError extends Error {
  constructor() {
    super("Organization change cancelled");
    this.name = "OrganizationTransitionCancelledError";
  }
}

const OrgContext = createContext<OrgContextValue | null>(null);

export function OrgProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const { data: user } = useCurrentUser();
  // localStorage is only the requested header context. Nothing is displayed as
  // active until /auth/me confirms the same organization on the server.
  const [actingOrg, setActingOrg] = useState<ActingOrg | null>(null);
  const transition = useRef(0);

  useEffect(() => {
    if (!user?.is_superadmin || user.acting_organization_id == null) {
      setActingOrg(null);
      return;
    }
    setActingOrg({
      id: user.acting_organization_id,
      name: user.acting_organization_name ?? readStored()?.name ?? String(user.acting_organization_id),
    });
  }, [user]);

  useEffect(() => {
    const handleSessionChange = () => setActingOrg(null);
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key !== ACTING_ORG_STORAGE_KEY) return;
      const requested = readStored();
      const call = ++transition.current;
      setActingOrg(null);
      resetOrganizationQueryCache(client);
      void api
        .get<User>("/api/auth/me", undefined, {
          context: requested
            ? organizationRequestContext(requested.id)
            : instanceRequestContext,
        })
        .then((confirmed) => {
          if (call !== transition.current) return;
          if (
            requested &&
            (confirmed.acting_organization_id !== requested.id || !confirmed.is_superadmin)
          ) {
            throw new RequestContextChangedError();
          }
          bindRequestSession(confirmed);
          client.setQueryData(keys.me, confirmed);
          setActingOrg(
            requested
              ? {
                  id: requested.id,
                  name: confirmed.acting_organization_name ?? requested.name,
                }
              : null,
          );
        })
        .catch(() => {
          if (call !== transition.current) return;
          if (event.oldValue === null) localStorage.removeItem(ACTING_ORG_STORAGE_KEY);
          else localStorage.setItem(ACTING_ORG_STORAGE_KEY, event.oldValue);
          setActingOrg(null);
          void client.invalidateQueries({ queryKey: keys.me });
        });
    };

    window.addEventListener(ACTING_ORG_CLEARED_EVENT, handleSessionChange);
    window.addEventListener("storage", handleStorageChange);
    return () => {
      window.removeEventListener(ACTING_ORG_CLEARED_EVENT, handleSessionChange);
      window.removeEventListener("storage", handleStorageChange);
    };
  }, [client]);

  // Write the header source before resetting active queries; their refetches
  // must start in the new organization, never under the previous one.
  const enterOrg = useCallback(
    async (org: ActingOrg) => {
      if (!window.dispatchEvent(new Event(BEFORE_ORGANIZATION_CHANGE, { cancelable: true }))) throw new OrganizationTransitionCancelledError();
      const previous = localStorage.getItem(ACTING_ORG_STORAGE_KEY);
      const call = ++transition.current;
      try {
        const confirmed = await api.get<User>("/api/auth/me", undefined, {
          context: organizationRequestContext(org.id),
          allowContextTransition: true,
        });
        if (call !== transition.current) throw new RequestContextChangedError();
        if (
          !confirmed.is_superadmin ||
          confirmed.acting_organization_id !== org.id ||
          !confirmed.acting_organization_name
        ) {
          throw new RequestContextChangedError();
        }
        const next = { id: org.id, name: confirmed.acting_organization_name };
        localStorage.setItem(ACTING_ORG_STORAGE_KEY, JSON.stringify(next));
        bindRequestSession(confirmed);
        resetOrganizationQueryCache(client);
        client.setQueryData(keys.me, confirmed);
        setActingOrg(next);
        return confirmed;
      } catch (error) {
        if (call === transition.current) {
          if (previous === null) localStorage.removeItem(ACTING_ORG_STORAGE_KEY);
          else localStorage.setItem(ACTING_ORG_STORAGE_KEY, previous);
        }
        throw error;
      }
    },
    [client],
  );

  const exitOrg = useCallback(async (expectedOrganizationId?: number) => {
    if (!window.dispatchEvent(new Event(BEFORE_ORGANIZATION_CHANGE, { cancelable: true }))) throw new OrganizationTransitionCancelledError();
    const previous = localStorage.getItem(ACTING_ORG_STORAGE_KEY);
    const stored = readStored();
    if (expectedOrganizationId !== undefined && stored?.id !== expectedOrganizationId) {
      throw new RequestContextChangedError();
    }
    const call = ++transition.current;
    try {
      const confirmed = await api.get<User>("/api/auth/me", undefined, {
        context: instanceRequestContext,
        allowContextTransition: true,
      });
      if (call !== transition.current) throw new RequestContextChangedError();
      if (!confirmed.is_superadmin || confirmed.acting_organization_id !== null) {
        throw new RequestContextChangedError();
      }
      localStorage.removeItem(ACTING_ORG_STORAGE_KEY);
      bindRequestSession(confirmed);
      resetOrganizationQueryCache(client);
      client.setQueryData(keys.me, confirmed);
      setActingOrg(null);
    } catch (error) {
      if (call === transition.current && previous !== null) {
        localStorage.setItem(ACTING_ORG_STORAGE_KEY, previous);
      }
      throw error;
    }
  }, [client]);

  const value = useMemo(
    () => ({ actingOrg, enterOrg, exitOrg }),
    [actingOrg, enterOrg, exitOrg],
  );
  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useOrg(): OrgContextValue {
  const value = useContext(OrgContext);
  if (!value) throw new Error("useOrg must be used within an OrgProvider");
  return value;
}

/** Whether the caller is currently inside an organization, i.e. creating things
 * is meaningful. Org members and admins always are; the operator must enter one
 * first (otherwise they're in the cross-org instance view). */
export function useInOrgContext(): boolean {
  const { actingOrg } = useOrg();
  const { data: user } = useCurrentUser();
  return !user?.is_superadmin || actingOrg !== null;
}
