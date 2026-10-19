import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useEventStream } from "../lib/eventStream";
import type { JobRow, Verdict } from "../lib/types";
import PdfViewer from "../components/PdfViewer";
import StatusBadge from "../components/StatusBadge";

export default function JobDetail() {
  const { id } = useParams();
  const jobId = Number(id);
  const navigate = useNavigate();
  const [job, setJob] = useState<JobRow | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"resume" | "cover">("resume");
  const { applyProgress } = useEventStream();

  function load() {
    api.getJob(jobId).then(setJob).catch((e) => setError(String(e)));
  }

  useEffect(load, [jobId]);
  useEffect(() => { api.setExtensionJob(jobId).catch(() => {}); }, [jobId]);

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

  async function build(engine: "default" | "claude" = "default") {
    setBusy("build");
    try {
      await api.buildJob(jobId, engine);
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
  const building = progress && progress.stage !== "done" && progress.stage !== "cancelled";

  const pdfUrl = tab === "resume" ? api.jobResumePdfUrl(jobId) : api.jobCoverPdfUrl(jobId);

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-3.5rem)] min-h-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <button className="text-xs text-accent hover:underline" onClick={() => navigate(-1)}>
            ← Back
          </button>
          <h1 className="text-lg font-semibold text-fg truncate">{job.title}</h1>
          <div className="text-sm text-muted truncate">
            {job.company} · {job.location} · {job.site} · posted {job.posted_date || "unknown"}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {job.link && (
            <a href={job.link} target="_blank" rel="noreferrer"
               className="btn-secondary !py-1.5 !border-accent !text-accent font-medium">
              Open original posting ↗
            </a>
          )}
          <StatusBadge label={job.ai_recommendation.toUpperCase()} tone={job.ai_recommendation} />
        </div>
      </div>

      <div className="card p-2.5 flex flex-wrap items-center gap-2">
        <button className="btn-primary !py-1.5" onClick={markApplied} disabled={busy === "apply"}>
          Mark applied
        </button>
        <button className="btn-secondary !py-1.5" onClick={() => build()} disabled={busy === "build" || !!building}>
          {building ? `Building… (${progress?.stage})` : hasResume ? "Rebuild" : "Build"}
        </button>
        <button className="btn-secondary !py-1.5" onClick={() => build("claude")} disabled={busy === "build" || !!building}
                title="Resume sections + cover letter written by Claude (uses your Claude subscription)">
          Build with Claude
        </button>
        {building && (
          <button className="btn-danger !py-1.5" onClick={() => api.cancelBuild(jobId).catch(() => {})}>
            Cancel
          </button>
        )}
        <button className="btn-secondary !py-1.5" onClick={() => navigate(`/jobs/${jobId}/editor`)} disabled={!hasResume}>
          LaTeX editor
        </button>
        {hasResume && (
          <>
            <a href={api.jobResumePdfUrl(jobId)} download className="btn-secondary !py-1.5">Resume ↓</a>
            <a href={api.jobCoverPdfUrl(jobId)} download className="btn-secondary !py-1.5">Cover ↓</a>
          </>
        )}
        <div className="flex items-center gap-1 ml-auto">
          <span className="text-xs text-muted mr-1">Verdict</span>
          {(["yes", "maybe", "no"] as Verdict[]).map((v) => (
            <button
              key={v}
              onClick={() => setVerdict(v)}
              disabled={busy === "verdict"}
              className={`btn !py-1 !px-3 ${job.ai_recommendation === v ? "btn-primary" : "btn-secondary"}`}
            >
              {v.toUpperCase()}
            </button>
          ))}
        </div>
        <button className="btn-danger !py-1.5" onClick={remove}>Delete</button>
      </div>

      {(error || (progress && typeof progress.score === "number")) && (
        <div className="text-xs flex gap-3">
          {error && <span className="text-no">{error}</span>}
          {progress && typeof progress.score === "number" && (
            <span className="text-muted">Latest ATS score: {progress.score} (iteration {progress.iteration})</span>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-3 flex-1 min-h-0">
        <div className="flex flex-col gap-3 min-h-0 min-w-0">
          <div className="card p-3 grid grid-cols-4 gap-3 shrink-0">
            <Stat label="Years req." value={job.years_required || "—"} />
            <Stat label="Level" value={job.role_level || "—"} />
            <Stat label="Skills match" value={`${job.skills_match_pct || 0}%`} />
            <Stat label="ATS" value={hasResume ? String(job.ats_score) : "not built"} />
          </div>

          <div className="card p-3 shrink-0 max-h-40 overflow-y-auto">
            <div className="text-sm font-medium text-fg mb-1">Screener reasoning</div>
            <p className="text-sm text-muted">{job.reasoning || "—"}</p>
            <div className="flex flex-wrap gap-1.5 mt-2">
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

          <div className="card p-3 flex-1 min-h-0 flex flex-col">
            <div className="text-sm font-medium text-fg mb-1 shrink-0">Job description</div>
            <p className="text-sm text-muted whitespace-pre-wrap overflow-y-auto flex-1 min-h-0">{job.description}</p>
          </div>
        </div>

        <div className="card flex flex-col min-h-0 min-w-0 overflow-hidden">
          <div className="flex border-b border-border shrink-0">
            {(["resume", "cover"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm border-b-2 -mb-px ${
                  tab === t ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg-soft"
                }`}
              >
                {t === "resume" ? "Resume" : "Cover letter"}
              </button>
            ))}
          </div>
          <div className="flex-1 min-h-0 p-2">
            {hasResume ? (
              <PdfViewer key={`${tab}-${progress?.stage}-${job.ats_score}`} url={pdfUrl} title={tab} />
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-muted">
                Build the resume and cover letter to preview the PDFs here.
              </div>
            )}
          </div>
        </div>
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
