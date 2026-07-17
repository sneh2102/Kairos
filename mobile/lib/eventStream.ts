import { useEffect, useState } from "react";
import { API_BASE } from "../config";
import type { WsEvent } from "./types";

// Backend broadcasts scrape/apply progress over /ws/events (ungated — no token).
const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws/events";

type Log = { level: string; message: string };
export type ScrapeJob = {
  verdict: string;
  company: string;
  title: string;
  location: string;
  skills_match_pct: number;
  matched_skills: string[];
  missing_skills: string[];
};
export type ApplyProgress = {
  company: string;
  title: string;
  stage: string;
  job_index: number;
  total: number;
  iteration?: number;
  score?: number;
  status?: string;
  job_id?: number;
};
type State = {
  connected: boolean;
  logs: Log[];
  scrapeRunning: boolean;
  applyRunning: boolean;
  scrapeJobs: ScrapeJob[];
  applyProgress: Record<string, ApplyProgress>;
  applyOrder: string[];
};

let ws: WebSocket | null = null;
let state: State = {
  connected: false,
  logs: [],
  scrapeRunning: false,
  applyRunning: false,
  scrapeJobs: [],
  applyProgress: {},
  applyOrder: [],
};
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}
function set(patch: Partial<State>) {
  state = { ...state, ...patch };
  emit();
}

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  ws = new WebSocket(WS_URL);
  ws.onopen = () => set({ connected: true });
  ws.onclose = () => {
    set({ connected: false });
    setTimeout(connect, 3000); // auto-reconnect
  };
  ws.onerror = () => {};
  ws.onmessage = (e) => {
    let ev: WsEvent;
    try {
      ev = JSON.parse(e.data as string);
    } catch {
      return;
    }
    if (ev.type === "log") {
      set({ logs: [...state.logs.slice(-200), { level: ev.level, message: ev.message }] });
    } else if (ev.type === "status") {
      if (ev.stage === "scrape") set({ scrapeRunning: ev.state === "running" });
      else set({ applyRunning: ev.state === "running" });
    } else if (ev.type === "scrape_job") {
      set({
        scrapeJobs: [
          ...state.scrapeJobs,
          {
            verdict: ev.verdict,
            company: ev.company,
            title: ev.title,
            location: ev.location,
            skills_match_pct: ev.skills_match_pct,
            matched_skills: ev.matched_skills,
            missing_skills: ev.missing_skills,
          },
        ],
      });
    } else if (ev.type === "apply_progress") {
      const key = `${ev.company}::${ev.title}`;
      const order = state.applyOrder.includes(key) ? state.applyOrder : [...state.applyOrder, key];
      set({ applyProgress: { ...state.applyProgress, [key]: ev }, applyOrder: order });
    } else if (ev.type === "done") {
      if (ev.stage === "scrape") set({ scrapeRunning: false });
      else set({ applyRunning: false });
    }
  };
}

export function clearLogs() {
  set({ logs: [] });
}
// Called right when the user taps Start, so the UI flips to "running" and clears
// last run's results before the first server event arrives.
export function startScrapeRun() {
  set({ scrapeRunning: true, scrapeJobs: [], logs: [] });
}
export function startApplyRun() {
  set({ applyRunning: true, applyProgress: {}, applyOrder: [] });
}

export function useEventStream(): State {
  const [, force] = useState(0);
  useEffect(() => {
    const l = () => force((n) => n + 1);
    listeners.add(l);
    connect();
    return () => {
      listeners.delete(l);
    };
  }, []);
  return state;
}
