import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Theme = "indigo" | "emerald" | "violet" | "sunset" | "rose";

export interface ThemeOption {
  value: Theme;
  labelKey: string;
  /** Three brand/accent stops mirrored from index.css, used for the swatch preview. */
  swatch: [string, string, string];
}

// The legacy "indigo" storage value now names Driftwatch's default Signal
// palette. Keeping the value avoids invalidating existing user preferences.
export const THEMES: ThemeOption[] = [
  { value: "indigo", labelKey: "theme.indigo", swatch: ["#b4e653", "#ff6b4a", "#36b8ad"] },
  { value: "emerald", labelKey: "theme.emerald", swatch: ["#34d399", "#10b981", "#a3e635"] },
  { value: "violet", labelKey: "theme.violet", swatch: ["#a78bfa", "#8b5cf6", "#e879f9"] },
  { value: "sunset", labelKey: "theme.sunset", swatch: ["#fb923c", "#f97316", "#fbbf24"] },
  { value: "rose", labelKey: "theme.rose", swatch: ["#f472b6", "#ec4899", "#c084fc"] },
];

const STORAGE_KEY = "driftwatch_theme";
const THEME_VALUES = new Set<string>(THEMES.map((option) => option.value));

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function initialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored && THEME_VALUES.has(stored) ? (stored as Theme) : "indigo";
}

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "indigo") {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = theme;
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used within a ThemeProvider");
  return value;
}
