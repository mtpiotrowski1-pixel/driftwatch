import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

interface DisclosurePanelProps {
  open: boolean;
  id: string;
  label: string;
  className?: string;
  children: ReactNode;
}

/** Preserve field state while collapsed, but remove its controls from keyboard
 * and assistive navigation immediately, including during the closing fade. */
export function DisclosurePanel({ open, id, label, className, children }: DisclosurePanelProps) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      id={id}
      role="region"
      aria-label={label}
      aria-hidden={!open}
      inert={!open}
      initial={false}
      animate={{ height: open ? "auto" : 0 }}
      style={{ opacity: open ? 1 : 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.22, ease: [0.22, 1, 0.36, 1] }}
      className="dw-disclosure-panel overflow-hidden"
    >
      <div className={className}>{children}</div>
    </motion.div>
  );
}
