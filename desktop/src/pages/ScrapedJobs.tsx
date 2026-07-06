import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import type { JobRow } from "../lib/types";
import StatusBadge from "../components/StatusBadge";

const FILTERS = ["all", "yes", "maybe", "no"] as const;

export default function ScrapedJobs() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>(
    () => (searchParams.get("verdict") as (typeof FILTERS)[number]) || "all"
  );
  const [q, setQ] = useState(() => searchParams.get("q") || "");
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const navigate = useNavigate();

  async function load() {
    setLoading(true);
    const rows = await api.listJobs({ verdict: filter === "all" ? "" : filter, q });
    setJobs(rows);
    setLoading(false);
  }

  function syncParams(nextQ: string) {
    const params: Record<string, string> = {};
    if (filter !== "all") params.verdict = filter;
    if (nextQ) params.q = nextQ;
    setSearchParams(params, { replace: true });
  }

  useEffect(() => {
    syncParams(q);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  useEffect(() => {
    syncParams(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  async function runCleanup(action: "no" | "not-applied" | "all", confirmText: string) {
    setCleanupOpen(false);
    if (!confirm(confirmText)) return;
    const fn = action === "no" ? api.removeNoJobs : action === "not-applied" ? api.removeNotAppliedJobs : api.removeAllJobs;
    const res = await fn();
    setMessage(`Removed ${res.removed} job${res.removed === 1 ? "" : "s"}.`);
    load();
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-fg tracking-tight">Review jobs</h1>
          <p className="text-sm text-muted mt-1">Every job the Screener Agent has rated — click one for details.</p>
        </div>
        <div className="flex gap-2">
          <input
            className="input w-56"
            placeholder="Search title/company…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
          <button className="btn-secondary" onClick={load}>
            Refresh
          </button>
          <CleanupMenu open={cleanupOpen} setOpen={setCleanupOpen} onPick={runCleanup} />
          <button className="btn-primary" onClick={() => setShowAdd(true)}>
            Add job
          </button>
        </div>
      </div>

      {message && (
        <div className="text-sm text-fg-soft bg-subtle border border-border rounded-xl px-3.5 py-2 flex items-center justify-between">
          {message}
          <button className="btn-ghost !px-2 !py-1" onClick={() => setMessage(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="flex gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3.5 py-1.5 rounded-full text-sm capitalize transition-colors ${
              filter === f ? "bg-accent text-on-accent" : "bg-subtle text-fg-soft hover:text-fg"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-sm text-muted">Loading…</div>
      ) : jobs.length === 0 ? (
        <div className="text-sm text-muted">No jobs match. Run a scrape, or add one yourself.</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
          {jobs.map((job) => (
            <JobTile key={job.id} job={job} onClick={() => navigate(`/jobs/${job.id}`)} />
          ))}
        </div>
      )}

      {showAdd && (
        <AddJobModal
          onClose={() => setShowAdd(false)}
          onAdded={(verdict) => {
            setShowAdd(false);
            setMessage(`Screened — verdict: ${verdict.toUpperCase()}.`);
            load();
          }}
        />
      )}
    </div>
  );
}

function JobTile({ job, onClick }: { job: JobRow; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      className="card aspect-square p-4 flex flex-col cursor-pointer hover:border-accent/50 transition-colors"
    >
      <div className="flex items-center gap-1.5 flex-wrap">
        <StatusBadge label={job.ai_recommendation.toUpperCase()} tone={job.ai_recommendation} />
        {job.latex_content && (
          <StatusBadge label={`ATS ${job.ats_score}`} tone={job.ats_score >= 85 ? "pass" : "maybe"} dot={false} />
        )}
      </div>

      <div className="mt-3 font-semibold text-fg text-[15px] leading-snug line-clamp-3">{job.title}</div>
      <div className="text-sm text-fg-soft mt-1.5 truncate">{job.company}</div>
      <div className="text-xs text-muted truncate">{job.location || "Location not listed"}</div>

      <div className="mt-auto pt-3 flex items-center justify-between">
        <span className="chip text-[11px]">{job.site}</span>
        <span className="num text-xs text-fg-soft">{job.skills_match_pct}% match</span>
      </div>
    </div>
  );
}

function CleanupMenu({
  open,
  setOpen,
  onPick,
}: {
  open: boolean;
  setOpen: (v: boolean) => void;
  onPick: (action: "no" | "not-applied" | "all", confirmText: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open, setOpen]);

  return (
    <div className="relative" ref={ref}>
      <button className="btn-secondary" onClick={() => setOpen(!open)}>
        Clean up
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+6px)] w-56 card shadow-pop p-1.5 z-20">
          <MenuItem
            label="Remove No verdicts"
            onClick={() => onPick("no", "Remove every job rated 'No'? This can't be undone.")}
          />
          <MenuItem
            label="Remove not applied"
            onClick={() => onPick("not-applied", "Remove every job you haven't applied to yet? This can't be undone.")}
          />
          <MenuItem
            danger
            label="Remove all"
            onClick={() => onPick("all", "Remove ALL jobs from this list? This can't be undone.")}
          />
        </div>
      )}
    </div>
  );
}

function MenuItem({ label, onClick, danger }: { label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left text-sm rounded-lg px-3 py-2 transition-colors ${
        danger ? "text-bad hover:bg-bad/10" : "text-fg-soft hover:bg-subtle hover:text-fg"
      }`}
    >
      {label}
    </button>
  );
}

function AddJobModal({ onClose, onAdded }: { onClose: () => void; onAdded: (verdict: string) => void }) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = title.trim() && company.trim() && description.trim();

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError("");
    try {
      const row = await api.addManualJob({
        title: title.trim(),
        company: company.trim(),
        location: location.trim(),
        job_url: jobUrl.trim(),
        description: description.trim(),
      });
      onAdded(row.ai_recommendation);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6">
      <div className="card w-full max-w-lg max-h-[85vh] flex flex-col p-5 gap-3 shadow-pop">
        <div>
          <h2 className="font-semibold text-fg">Add a job posting</h2>
          <p className="text-sm text-muted mt-1">
            Paste one you found yourself — it runs through the same Screener Agent as a scraped job.
          </p>
        </div>

        <div className="overflow-y-auto flex flex-col gap-3 pr-1">
          <div>
            <span className="label">Job title</span>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Senior Backend Engineer" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="label">Company</span>
              <input className="input" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Inc." />
            </div>
            <div>
              <span className="label">Location</span>
              <input className="input" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Remote" />
            </div>
          </div>
          <div>
            <span className="label">Job posting URL (optional)</span>
            <input className="input" value={jobUrl} onChange={(e) => setJobUrl(e.target.value)} placeholder="https://…" />
          </div>
          <div>
            <span className="label">Job description</span>
            <textarea
              className="input h-40 resize-none"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Paste the full job description here…"
            />
          </div>
        </div>

        {error && <div className="text-sm text-bad">{error}</div>}

        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={submit} disabled={!canSubmit || submitting}>
            {submitting ? "Screening…" : "Add & screen"}
          </button>
        </div>
      </div>
    </div>
  );
}
