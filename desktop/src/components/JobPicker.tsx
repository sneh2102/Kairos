import { useEffect, useMemo, useRef, useState } from "react";
import type { AppliedRow, JobRow } from "../lib/types";
import StatusBadge from "./StatusBadge";

// Searchable job chooser for Interview prep — a plain <select> is unusable with hundreds of applications.

type Source = "all" | "applied" | "jobs";

interface Item {
  key: string; // "applied:4" | "jobs:12"
  title: string;
  company: string;
  location: string;
  date: string;
  source: "applied" | "jobs";
  verdict?: string;
  haystack: string;
}

const LIMIT = 100;

export default function JobPicker({
  applied,
  jobs,
  value,
  onChange,
}: {
  applied: AppliedRow[];
  jobs: JobRow[];
  value: string;
  onChange: (key: string) => void;
}) {
  const [q, setQ] = useState("");
  const [source, setSource] = useState<Source>("all");
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(!value);
  const listRef = useRef<HTMLDivElement>(null);

  const items = useMemo<Item[]>(() => {
    const mk = (i: Omit<Item, "haystack">): Item => ({
      ...i,
      haystack: `${i.title} ${i.company} ${i.location}`.toLowerCase(),
    });
    return [
      ...applied.map((j) =>
        mk({ key: `applied:${j.id}`, title: j.title, company: j.company, location: j.location, date: j.applied_date, source: "applied" }),
      ),
      ...jobs.map((j) =>
        mk({
          key: `jobs:${j.id}`,
          title: j.title,
          company: j.company,
          location: j.location,
          date: j.posted_date,
          source: "jobs",
          verdict: j.ai_recommendation,
        }),
      ),
    ];
  }, [applied, jobs]);

  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const matches = items.filter(
    (i) => (source === "all" || i.source === source) && words.every((w) => i.haystack.includes(w)),
  );
  const shown = matches.slice(0, LIMIT);
  const count = (s: Source) =>
    items.filter((i) => (s === "all" || i.source === s) && words.every((w) => i.haystack.includes(w))).length;

  useEffect(() => setActive(0), [q, source]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function pick(key: string) {
    onChange(key);
    setOpen(false);
  }

  const selected = items.find((i) => i.key === value);

  if (!open && selected) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-accent/40 bg-accent-soft px-3.5 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-fg truncate">{selected.title}</div>
          <div className="text-xs text-muted truncate">
            {selected.company}
            {selected.location && ` · ${selected.location}`}
            {selected.date && ` · ${selected.source === "applied" ? "applied" : "posted"} ${selected.date}`}
          </div>
        </div>
        <button className="btn-secondary !py-1.5 shrink-0" onClick={() => setOpen(true)}>
          Change
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <div className="p-2 border-b border-border flex flex-col gap-2">
        <input
          autoFocus
          className="input"
          placeholder="Search by title, company or location…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, shown.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter" && shown[active]) {
              e.preventDefault();
              pick(shown[active].key);
            } else if (e.key === "Escape" && selected) {
              setOpen(false);
            }
          }}
        />
        <div className="flex items-center gap-1">
          {(
            [
              ["all", "All"],
              ["applied", "Applications"],
              ["jobs", "Reviewed jobs"],
            ] as [Source, string][]
          ).map(([s, label]) => (
            <button
              key={s}
              onClick={() => setSource(s)}
              className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
                source === s ? "bg-accent text-on-accent" : "text-muted hover:text-fg hover:bg-subtle"
              }`}
            >
              {label} <span className="num opacity-75">{count(s)}</span>
            </button>
          ))}
          {selected && (
            <button className="ml-auto text-xs text-muted hover:text-fg" onClick={() => setOpen(false)}>
              Cancel
            </button>
          )}
        </div>
      </div>

      <div ref={listRef} className="max-h-72 overflow-y-auto">
        {shown.length === 0 && (
          <div className="px-4 py-6 text-sm text-muted text-center">
            {items.length === 0 ? "No saved jobs yet." : `No jobs match "${q}".`}
          </div>
        )}
        {shown.map((i, idx) => (
          <button
            key={i.key}
            data-idx={idx}
            onMouseEnter={() => setActive(idx)}
            onClick={() => pick(i.key)}
            className={`w-full text-left px-3.5 py-2.5 flex items-center gap-3 border-b border-border last:border-b-0 ${
              idx === active ? "bg-subtle" : ""
            } ${i.key === value ? "!bg-accent-soft" : ""}`}
          >
            <div className="min-w-0 flex-1">
              <div className="text-sm text-fg truncate">{i.title}</div>
              <div className="text-xs text-muted truncate">
                {i.company}
                {i.location && ` · ${i.location}`}
              </div>
            </div>
            <div className="shrink-0 flex flex-col items-end gap-1">
              {i.source === "applied" ? (
                <StatusBadge label="Applied" tone="pass" dot={false} />
              ) : (
                <StatusBadge label={(i.verdict || "job").toUpperCase()} tone={i.verdict || "idle"} dot={false} />
              )}
              {i.date && <span className="text-[11px] text-muted num">{i.date}</span>}
            </div>
          </button>
        ))}
        {matches.length > LIMIT && (
          <div className="px-4 py-2 text-xs text-muted text-center">
            Showing {LIMIT} of {matches.length} — keep typing to narrow it down.
          </div>
        )}
      </div>
    </div>
  );
}
