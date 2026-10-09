import { useReducedMotion } from "motion/react";
import { useEffect, useRef, type HTMLAttributes } from "react";

/** Content is visible by default. Only a viewport entry starts a brief reveal,
 * so delayed/unsupported observers and reduced motion can never hide content. */
export function Reveal({ children, ...props }: HTMLAttributes<HTMLDivElement>) {
  const ref = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const element = ref.current;
    if (reduceMotion || !element?.animate || typeof IntersectionObserver === "undefined") return;
    let animation: Animation | undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        observer.disconnect();
        animation = element.animate(
          [
            { opacity: 0.65, transform: "translateY(8px)" },
            { opacity: 1, transform: "translateY(0)" },
          ],
          { duration: 320, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
        );
      },
      { threshold: 0.08, rootMargin: "0px 0px -24px 0px" },
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
      animation?.cancel();
    };
  }, [reduceMotion]);

  return <div ref={ref} {...props}>{children}</div>;
}
