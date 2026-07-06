import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Choice = "light" | "dark" | "system";
type Resolved = "light" | "dark";

interface ThemeCtx {
  choice: Choice;
  resolved: Resolved;
  setChoice: (c: Choice) => void;
}

const Ctx = createContext<ThemeCtx | null>(null);
const KEY = "jobscraper-theme";

function systemResolved(): Resolved {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function apply(choice: Choice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<Choice>(() => (localStorage.getItem(KEY) as Choice) || "system");
  const [resolved, setResolved] = useState<Resolved>(() =>
    choice === "system" ? systemResolved() : choice,
  );

  useEffect(() => {
    apply(choice);
    setResolved(choice === "system" ? systemResolved() : choice);
    if (choice !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setResolved(systemResolved());
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [choice]);

  function setChoice(c: Choice) {
    localStorage.setItem(KEY, c);
    setChoiceState(c);
  }

  return <Ctx.Provider value={{ choice, resolved, setChoice }}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

// Concrete colors for canvas/SVG charts (recharts can't read CSS vars).
export const CHART = {
  light: { grid: "#e2e5ea", axis: "#6b7280", accent: "#4f6bed", good: "#1f9d57", warn: "#b8801a", bad: "#d24b45", surface: "#ffffff", border: "#e2e5ea" },
  dark: { grid: "#262b33", axis: "#7f8794", accent: "#6b84ff", good: "#3fb07a", warn: "#e0a93b", bad: "#f0655e", surface: "#171a20", border: "#262b33" },
} as const;
