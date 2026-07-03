import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from "react";
import type { ReactNode } from "react";
import { BACKEND_URL } from "./api";
import type { WsEvent } from "./types";

interface LogLine {
  level: string;
  message: string;
  ts: number;
}

interface ScrapeJobEvent {
  verdict: string;
  company: string;
  title: string;
  location: string;
  skills_match_pct: number;
  matched_skills: string[];
  missing_skills: string[];
  ts: number;
}

interface ApplyProgressEvent {
  company: string;
  title: string;
  stage: string;
  job_index: number;
  total: number;
  iteration?: number;
  score?: number;
  status?: string;
  ts: number;
}

interface State {
  connected: boolean;
  logs: LogLine[];
  scrapeJobs: ScrapeJobEvent[];
  scrapeRunning: boolean;
  applyProgress: Record<string, ApplyProgressEvent>;
  applyOrder: string[];
  applyRunning: boolean;
}

type Action =
  | { type: "connected"; value: boolean }
  | { type: "event"; event: WsEvent }
  | { type: "clear_scrape" }
  | { type: "clear_apply" }
  | { type: "mark_scrape_running"; running: boolean }
  | { type: "mark_apply_running"; running: boolean };

const initialState: State = {
  connected: false,
  logs: [],
  scrapeJobs: [],
  scrapeRunning: false,
  applyProgress: {},
  applyOrder: [],
  applyRunning: false,
};

function keyFor(company: string, title: string) {
  return `${company}::${title}`;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "connected":
      return { ...state, connected: action.value };
    case "clear_scrape":
      return { ...state, scrapeJobs: [] };
    case "clear_apply":
      return { ...state, applyProgress: {}, applyOrder: [] };
    case "mark_scrape_running":
      return { ...state, scrapeRunning: action.running };
    case "mark_apply_running":
      return { ...state, applyRunning: action.running };
    case "event": {
      const e = action.event;
      const logs = state.logs.length > 500 ? state.logs.slice(-400) : state.logs;
      if (e.type === "log") {
        return { ...state, logs: [...logs, { level: e.level, message: e.message, ts: Date.now() }] };
      }
      if (e.type === "scrape_job") {
        return { ...state, scrapeJobs: [{ ...e, ts: Date.now() }, ...state.scrapeJobs] };
      }
      if (e.type === "apply_progress") {
        const key = keyFor(e.company, e.title);
        const order = state.applyOrder.includes(key) ? state.applyOrder : [key, ...state.applyOrder];
        return {
          ...state,
          applyProgress: { ...state.applyProgress, [key]: { ...e, ts: Date.now() } },
          applyOrder: order,
        };
      }
      if (e.type === "status") {
        return state;
      }
      if (e.type === "done") {
        return e.stage === "scrape" ? { ...state, scrapeRunning: false } : { ...state, applyRunning: false };
      }
      return state;
    }
    default:
      return state;
  }
}

interface Ctx extends State {
  startScrapeRun: () => void;
  startApplyRun: () => void;
}

const EventStreamContext = createContext<Ctx | null>(null);

export function EventStreamProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    function connect() {
      if (cancelled) return;
      const ws = new WebSocket(`${BACKEND_URL.replace("http", "ws")}/ws/events`);
      wsRef.current = ws;
      ws.onopen = () => dispatch({ type: "connected", value: true });
      ws.onclose = () => {
        dispatch({ type: "connected", value: false });
        if (!cancelled) retryTimer = window.setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (msg) => {
        try {
          const event: WsEvent = JSON.parse(msg.data);
          dispatch({ type: "event", event });
          notifyOnDone(event);
        } catch {
          // ignore malformed frames
        }
      };
    }
    connect();

    return () => {
      cancelled = true;
      window.clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, []);

  const startScrapeRun = useCallback(() => {
    dispatch({ type: "clear_scrape" });
    dispatch({ type: "mark_scrape_running", running: true });
  }, []);

  const startApplyRun = useCallback(() => {
    dispatch({ type: "clear_apply" });
    dispatch({ type: "mark_apply_running", running: true });
  }, []);

  const value = useMemo(() => ({ ...state, startScrapeRun, startApplyRun }), [state, startScrapeRun, startApplyRun]);

  return <EventStreamContext.Provider value={value}>{children}</EventStreamContext.Provider>;
}

function notifyOnDone(event: WsEvent) {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  if (event.type === "done") {
    new Notification(event.stage === "scrape" ? "Scrape finished" : "Apply run finished", {
      body: event.stage === "scrape" ? "Job scraping and screening is done." : "Resume generation is done.",
    });
  }
  if (event.type === "apply_progress" && event.stage === "done" && (event.score ?? 0) >= 85) {
    new Notification("Resume passed ATS", {
      body: `${event.title} @ ${event.company} — score ${event.score}`,
    });
  }
}

export function useEventStream() {
  const ctx = useContext(EventStreamContext);
  if (!ctx) throw new Error("useEventStream must be used within EventStreamProvider");
  return ctx;
}
