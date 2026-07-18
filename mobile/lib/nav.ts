// Simple route model — a lightweight state-based navigator (no nav dependency,
// so it always works in Expo Go). App.tsx keeps a stack of these.
export type Route =
  | { name: "overview" }
  | { name: "find" }
  | { name: "review" }
  | { name: "job"; id: number; source: "jobs" | "applied" }
  | { name: "latex"; id: number; source: "jobs" | "applied" }
  | { name: "build" }
  | { name: "applied" }
  | { name: "resume" }
  | { name: "templates" }
  | { name: "screener" }
  | { name: "prompts" }
  | { name: "logs" }
  | { name: "settings" }
  | { name: "setup" };

export interface Nav {
  go: (r: Route) => void;
  back: () => void;
}
