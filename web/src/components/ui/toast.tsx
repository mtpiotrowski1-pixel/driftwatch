import { CheckCircle2, XCircle } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

type Tone = "success" | "error";

interface Toast {
  id: number;
  message: string;
  tone: Tone;
}

interface ToastApi {
  notify: (message: string, tone?: Tone) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const TONES: Record<Tone, string> = {
  success: "border-emerald-400/30 text-emerald-400",
  error: "border-rose-400/30 text-rose-400",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const reduceMotion = useReducedMotion();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);
  const mounted = useRef(true);
  const expiryTimers = useRef(new Set<number>());

  useEffect(() => {
    mounted.current = true;
    const timers = expiryTimers.current;
    return () => {
      mounted.current = false;
      for (const timer of timers) window.clearTimeout(timer);
      timers.clear();
    };
  }, []);

  const notify = useCallback((message: string, tone: Tone = "success") => {
    if (!mounted.current) return;
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message, tone }]);
    const timer = window.setTimeout(() => {
      expiryTimers.current.delete(timer);
      if (!mounted.current) return;
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 4000);
    expiryTimers.current.add(timer);
  }, []);

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-[min(92vw,22rem)] flex-col gap-2"
      >
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              layout
              initial={{ opacity: 0, y: reduceMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: reduceMotion ? 0 : 4 }}
              transition={{ duration: reduceMotion ? 0 : 0.18, ease: "easeOut" }}
              className={cn(
                "glass pointer-events-auto flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-sm",
                TONES[toast.tone],
              )}
            >
              {toast.tone === "success" ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <span className="text-mist-200">{toast.message}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used within a ToastProvider");
  return api;
}
