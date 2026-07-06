import { useEffect, useRef } from "react";
import { useEventStream } from "../lib/eventStream";

const COLOR: Record<string, string> = {
  ERROR: "text-no",
  WARNING: "text-maybe",
  INFO: "text-fg-soft",
  DEBUG: "text-muted",
};

export default function Logs() {
  const { logs, connected } = useEventStream();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [logs.length]);

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-fg">Logs</h1>
          <p className="text-sm text-muted">Live output from the backend — {connected ? "connected" : "disconnected"}.</p>
        </div>
      </div>
      <div className="card p-3 flex-1 overflow-y-auto font-mono text-xs" style={{ minHeight: "70vh" }}>
        {logs.length === 0 && <div className="text-muted">Nothing logged yet.</div>}
        {logs.map((l, i) => (
          <div key={i} className={COLOR[l.level] ?? "text-fg-soft"}>
            <span className="text-muted">{new Date(l.ts).toLocaleTimeString()}</span> [{l.level}] {l.message}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
