import { useReducedMotion } from "motion/react";
import { forwardRef, useCallback } from "react";
import {
  Link as RouterLink,
  NavLink as RouterNavLink,
  useNavigate as useRouterNavigate,
  type LinkProps,
  type NavigateFunction,
  type NavigateOptions,
  type NavLinkProps,
  type To,
} from "react-router-dom";

/** Let the router capture outgoing/incoming views after its blockers allow a
 * navigation. Unsupported browsers keep ordinary navigation; no stale route is
 * retained or re-mounted just to animate it. Callers can explicitly opt out. */
export const Link = forwardRef<HTMLAnchorElement, LinkProps>(function Link(
  { viewTransition, ...props },
  ref,
) {
  const reduceMotion = useReducedMotion();
  return <RouterLink ref={ref} viewTransition={!reduceMotion && (viewTransition ?? true)} {...props} />;
});

export const NavLink = forwardRef<HTMLAnchorElement, NavLinkProps>(function NavLink(
  { viewTransition, ...props },
  ref,
) {
  const reduceMotion = useReducedMotion();
  return <RouterNavLink ref={ref} viewTransition={!reduceMotion && (viewTransition ?? true)} {...props} />;
});

export function useNavigate(): NavigateFunction {
  const navigate = useRouterNavigate();
  const reduceMotion = useReducedMotion();
  return useCallback(
    ((to: To | number, options?: NavigateOptions) => {
      if (typeof to === "number") return navigate(to);
      return navigate(to, {
        ...options,
        viewTransition: !reduceMotion && (options?.viewTransition ?? true),
      });
    }) as NavigateFunction,
    [navigate, reduceMotion],
  );
}
