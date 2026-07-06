import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useEventStream } from "../lib/eventStream";
import type { JobRow, Verdict } from "../lib/types";
import StatusBadge from "../components/StatusBadge";

export default function JobDetail() {
  const { id } = useParams();
  const jobId = Number(id);
  const navigate = useNavigate();
  const [job, setJob] = useState<JobRow | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { applyProgress } = useEventStream();

  function load() {
    api.getJob(jobId).then(setJob).catch((e) => setError(String(e)));
  }

  useEffect(load, [jobId]);

  const progress = job ? applyProgress[`${job.company}::${job.title}`] : undefined;
  useEffect(() => {
    if (progress?.stage === "done") load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress?.stage]);

  if (error) return <div className="text-sm text-no">{error}</div>;
  if (!job) return <div className="text-sm text-muted">Loading…</div>;

  async function setVerdict(v: Verdict) {
    setBusy("verdict");
    try {
      await api.setVerdict(jobId, v);
      load();
    } finally {
      setBusy(null);
    }
  }

  async function build() {
    setBusy("build");
    try {
      await api.buildJob(jobId);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function markApplied() {
    setBusy("apply");
    try {
      await api.applyJob(jobId);
      navigate(-1);
    } catch (e) {
      setError(String(e));
      setBusy(null);
    }
  }

  async function remove() {
    await api.deleteJob(jobId);
    navigate(-1);
  }

  const hasResume = !!job.latex_content;
  const building = progress && progress.stage !== "done";

  return (
    <div className="flex flex-col gap-4 max-w-4xl">
      <button className="text-sm text-accent hover:underline w-fit" onClick={() => navigate(-1)}>
        ← Back to Scraped Jobs
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-fg">{job.title}</h1>
          <div className="text-sm text-muted">
            {job.company} · {job.location} · {job.site} · posted {job.posted_date || "unknown"}
          </div>
          {job.link && (
            <a href={job.link} target="_blank" rel="noreferrer" className="text-xs text-accent hover:underline">
              View original posting
            </a>
          )}
        </div>
        <StatusBadge label={job.ai_recommendation.toUpperCase()} tone={job.ai_recommendation} />
      </div>

      {error && <div className="text-sm text-no">{error}</div>}

      <div className="card p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Years required" value={job.years_required || "—"} />
        <Stat label="Role level" value={job.role_level || "—"} />
        <Stat label="Skills match" value={`${job.skills_match_pct || 0}%`} />
        <Stat label="ATS score" value={hasResume ? String(job.ats_score) : "not built"} />
      </div>

      <div className="card p-4">
        <div className="text-sm font-medium text-fg mb-2">Screener reasoning</div>
        <p className="text-sm text-muted">{job.reasoning || "—"}</p>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {(job.matched_skills || "").split(",").filter(Boolean).map((s) => (
            <span key={s} className="text-[11px] px-2 py-0.5 rounded bg-yes/10 text-yes border border-yes/30">
              {s.trim()}
            </span>
          ))}
          {(job.missing_skills || "").split(",").filter(Boolean).map((s) => (
            <span key={s} className="text-[11px] px-2 py-0.5 rounded bg-no/10 text-no border border-no/30">
              {s.trim()}
            </span>
          ))}
        </div>
      </div>

      <div className="card p-4">
        <div className="text-sm font-medium text-fg mb-2">Job description</div>
        <p className="text-sm text-muted whitespace-pre-wrap max-h-64 overflow-y-auto">{job.description}</p>
      </div>

      <div className="card p-4 flex flex-col gap-3">
        <div className="text-sm font-medium text-fg">Actions</div>

        <div>
          <span className="label">Change verdict</span>
          <div className="flex gap-2">
            {(["yes", "maybe", "no"] as Verdict[]).map((v) => (
              <button
                key={v}
                onClick={() => setVerdict(v)}
                disabled={busy === "verdict"}
                className={`btn ${job.ai_recommendation === v ? "btn-primary" : "btn-secondary"}`}
              >
                {v.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
          <button className="btn-secondary" onClick={build} disabled={busy === "build" || !!building}>
            {building ? `Building… (${progress?.stage})` : hasResume ? "Rebuild resume & cover letter" : "Build resume & cover letter"}
          </button>
          <button className="btn-secondary" onClick={() => navigate(`/jobs/${jobId}/editor`)} disabled={!hasResume}>
            Open in LaTeX editor
          </button>
          <button className="btn-primary" onClick={markApplied} disabled={busy === "apply"}>
            Mark applied
          </button>
          <button className="btn-danger ml-auto" onClick={remove}>
            Delete
          </button>
        </div>
        {progress && typeof progress.score === "number" && (
          <div className="text-xs text-muted">Latest ATS score: {progress.score} (iteration {progress.iteration})</div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-base font-semibold text-fg">{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}
