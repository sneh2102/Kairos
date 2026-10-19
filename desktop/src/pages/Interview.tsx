import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type {
  AppliedRow, InterviewConfig, InterviewKind, InterviewSessionSummary, JobRow, PrepGuideSummary, SpeechStatus, Transcript,
} from "../lib/types";
import { KIND_INFO, SUGGESTED_TOPICS, scoreTone, topicsFromSkills } from "../lib/interview";
import { readAnswerMode, saveAnswerMode, useRecorder, useSpeaker } from "../lib/voice";
import StatusBadge from "../components/StatusBadge";
import JobPicker from "../components/JobPicker";

const LENGTHS = [
  { id: "short", label: "Short", hint: "3 main questions + follow-ups · ~10–15 min" },
  { id: "standard", label: "Standard", hint: "5 main questions + follow-ups · ~20–25 min" },
  { id: "long", label: "Long", hint: "8 main questions + follow-ups · ~40 min" },
] as const;

const PERSONAS = [
  { id: "friendly", label: "Friendly" },
  { id: "neutral", label: "Neutral" },
  { id: "tough", label: "Tough" },
] as const;

export default function Interview() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<SpeechStatus | null>(null);
  const [sessions, setSessions] = useState<InterviewSessionSummary[]>([]);
  const [guides, setGuides] = useState<PrepGuideSummary[]>([]);
  const [preparing, setPreparing] = useState(false);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [applied, setApplied] = useState<AppliedRow[]>([]);
  const [kind, setKind] = useState<InterviewKind>("behavioral");
  const [target, setTarget] = useState<"job" | "manual">("manual");
  const [jobKey, setJobKey] = useState(""); // "jobs:12" | "applied:4"
  const [topics, setTopics] = useState<string[]>([]);
  const [difficulty, setDifficulty] = useState<NonNullable<InterviewConfig["difficulty"]>>("mid");
  const [cfg, setCfg] = useState<InterviewConfig>({ role: "", company: "", length: "standard", persona: "neutral" });
  const [mode, setMode] = useState(readAnswerMode);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadStatus() {
    api.speechStatus().then(setStatus).catch(() => {});
  }

  useEffect(() => {
    loadStatus();
    api.speechWarmup().catch(() => {});
    api.listInterviews().then(setSessions).catch(() => {});
    api.listPrepGuides().then(setGuides).catch(() => {});
    api.listJobs().then(setJobs).catch(() => {});
    api.listApplied().then(setApplied).catch(() => {});
  }, []);

  // poll while a model download runs
  const downloading = status && (status.whisper.download === "downloading" || status.kokoro.download === "downloading");
  useEffect(() => {
    if (!downloading) return;
    const t = setInterval(loadStatus, 2000);
    return () => clearInterval(t);
  }, [downloading]);

  function chooseMode(m: "ptt" | "hands-free") {
    setMode(m);
    saveAnswerMode(m);
  }

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const config: InterviewConfig = { length: cfg.length, persona: cfg.persona };
      if (kind === "technical") Object.assign(config, { topics, difficulty });
      if (target === "job" && jobKey) {
        const [source, id] = jobKey.split(":");
        Object.assign(config, { job_source: source as "jobs" | "applied", job_id: Number(id) });
      } else {
        Object.assign(config, { role: cfg.role?.trim(), company: cfg.company?.trim() });
      }
      const s = await api.createInterview(kind, config);
      navigate(`/interview/${s.id}`);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setStarting(false);
    }
  }

  async function buildGuide() {
    setPreparing(true);
    setError(null);
    try {
      const [source, id] = jobKey.split(":");
      const g = await api.createPrepGuide(
        target === "job" ? { job_source: source, job_id: Number(id) } : { role: cfg.role?.trim(), company: cfg.company?.trim() },
      );
      navigate(`/interview/prep/${g.id}`);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setPreparing(false);
    }
  }

  async function removeGuide(id: number) {
    await api.deletePrepGuide(id);
    setGuides((g) => g.filter((x) => x.id !== id));
  }

  async function remove(id: number) {
    await api.deleteInterview(id);
    setSessions((s) => s.filter((x) => x.id !== id));
  }

  // picking a job pre-fills the tech topics from its skills (applications need a fetch: the list omits skills)
  async function chooseJob(key: string) {
    setJobKey(key);
    const [source, id] = key.split(":");
    if (!id) return;
    const row = source === "applied" ? await api.getApplied(Number(id)).catch(() => null) : jobs.find((j) => j.id === Number(id));
    const fromJob = topicsFromSkills(row?.matched_skills, row?.missing_skills);
    if (fromJob.length) setTopics(fromJob);
  }

  const canStart = (target === "manual" || !!jobKey) && (kind !== "technical" || topics.length > 0);
  const canPrep = target === "job" ? !!jobKey : !!(cfg.role?.trim() || cfg.company?.trim());

  return (
    <div className="flex flex-col gap-5 max-w-6xl">
      <div>
        <h1 className="text-lg font-semibold text-fg">Interview prep</h1>
        <p className="text-sm text-muted">
          A spoken mock interview grounded in your resume and the job. Answer out loud — or type.
        </p>
      </div>

      {status && <ModelBanner status={status} onDownload={(w) => api.speechDownload(w).then(loadStatus)} />}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-4">
        <div className="card p-5 flex flex-col gap-5">
          <div>
            <div className="text-sm font-semibold text-fg">New interview</div>
            <div className="text-xs text-muted">Questions are planned from your resume and the job, with follow-ups on thin answers.</div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {(Object.keys(KIND_INFO) as InterviewKind[]).map((k) => (
              <button
                key={k}
                onClick={() => setKind(k)}
                className={`text-left rounded-xl border p-3 transition-colors ${
                  kind === k ? "border-accent bg-accent-soft" : "border-border hover:border-accent/50"
                }`}
              >
                <div className={`text-sm font-medium ${kind === k ? "text-accent" : "text-fg"}`}>{KIND_INFO[k].label}</div>
                <div className="text-xs text-muted mt-1 leading-snug">{KIND_INFO[k].blurb}</div>
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-2">
            <span className="label !mb-0">Practice for</span>
            <Segmented
              value={target}
              onChange={(v) => setTarget(v as "job" | "manual")}
              options={[
                { id: "manual", label: "A role I type in" },
                { id: "job", label: "A saved job" },
              ]}
            />
            {target === "job" ? (
              <JobPicker applied={applied} jobs={jobs} value={jobKey} onChange={chooseJob} />
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <input
                  className="input"
                  placeholder="Role (optional), e.g. Backend Engineer"
                  value={cfg.role}
                  onChange={(e) => setCfg({ ...cfg, role: e.target.value })}
                />
                <input
                  className="input"
                  placeholder="Company (optional)"
                  value={cfg.company}
                  onChange={(e) => setCfg({ ...cfg, company: e.target.value })}
                />
              </div>
            )}
            {target === "job" && (
              <p className="text-xs text-muted">The interviewer reads that job's description alongside your resume.</p>
            )}
          </div>

          {kind === "technical" && (
            <div className="flex flex-col gap-4 rounded-xl border border-border p-4">
              <TopicPicker topics={topics} onChange={setTopics} />
              <div className="flex flex-col gap-2">
                <span className="label !mb-0">Level</span>
                <Segmented
                  value={difficulty}
                  onChange={(v) => setDifficulty(v as typeof difficulty)}
                  options={[
                    { id: "junior", label: "Junior" },
                    { id: "mid", label: "Mid-level" },
                    { id: "senior", label: "Senior" },
                  ]}
                />
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-2">
              <span className="label !mb-0">Length</span>
              <Segmented
                value={cfg.length!}
                onChange={(v) => setCfg({ ...cfg, length: v as InterviewConfig["length"] })}
                options={LENGTHS.map((l) => ({ id: l.id, label: l.label }))}
              />
              <span className="text-xs text-muted">{LENGTHS.find((l) => l.id === cfg.length)?.hint}</span>
            </div>
            <div className="flex flex-col gap-2">
              <span className="label !mb-0">Interviewer</span>
              <Segmented
                value={cfg.persona!}
                onChange={(v) => setCfg({ ...cfg, persona: v as InterviewConfig["persona"] })}
                options={PERSONAS.map((p) => ({ id: p.id, label: p.label }))}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <span className="label !mb-0">How you answer</span>
            <Segmented
              value={mode}
              onChange={(v) => chooseMode(v as "ptt" | "hands-free")}
              options={[
                { id: "ptt", label: "Push to talk" },
                { id: "hands-free", label: "Hands-free" },
              ]}
            />
            <span className="text-xs text-muted">
              {mode === "ptt"
                ? "Hold Space (or click the mic) while you talk; release to send."
                : "The mic opens after each question and sends when you pause for about 2 seconds."}
            </span>
          </div>

          {error && <div className="text-sm text-no">{error}</div>}
          <div className="flex items-center gap-3">
            <button className="btn-primary" onClick={start} disabled={!canStart || starting || preparing}>
              {starting ? (
                <>
                  <span className="spinner" /> Preparing interviewer…
                </>
              ) : (
                "Start interview"
              )}
            </button>
            <button
              className="btn-secondary"
              onClick={buildGuide}
              disabled={!canPrep || preparing || starting}
              title="Company research, likely questions with sample answers, and study resources — no interview"
            >
              {preparing ? (
                <>
                  <span className="spinner" /> Researching & writing… ~30s
                </>
              ) : (
                "Prep guide"
              )}
            </button>
            {!canStart && !preparing && (
              <span className="text-xs text-muted">{target === "job" && !jobKey ? "Pick a job" : "Add at least one topic"} to start.</span>
            )}
          </div>
          <p className="text-xs text-muted -mt-2">
            <strong className="text-fg-soft font-medium">Prep guide</strong> skips the interview: you get company research with
            sources, likely questions with sample answers, questions to ask them, and study links.
          </p>
        </div>

        <MicCheck />
      </div>

      {guides.length > 0 && (
        <div className="card p-5 flex flex-col gap-3">
          <div className="text-sm font-semibold text-fg">Prep guides</div>
          <div className="flex flex-col divide-y divide-border">
            {guides.map((g) => (
              <div key={g.id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <Link to={`/interview/prep/${g.id}`} className="text-sm font-medium text-fg hover:text-accent truncate block">
                    {[g.title, g.company].filter(Boolean).join(" @ ")}
                  </Link>
                  <div className="text-xs text-muted">{new Date(g.created_at + "Z").toLocaleString()}</div>
                </div>
                <Link to={`/interview/prep/${g.id}`} className="btn-secondary !py-1.5">
                  Open
                </Link>
                <button className="text-xs text-no hover:underline" onClick={() => removeGuide(g.id)}>
                  Delete
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card p-5 flex flex-col gap-3">
        <div className="text-sm font-semibold text-fg">Past interviews</div>
        {sessions.length === 0 && <div className="text-sm text-muted">No interviews yet.</div>}
        <div className="flex flex-col divide-y divide-border">
          {sessions.map((s) => (
            <div key={s.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <Link to={`/interview/${s.id}`} className="text-sm font-medium text-fg hover:text-accent truncate block">
                  {s.title}
                </Link>
                <div className="text-xs text-muted">
                  {KIND_INFO[s.kind]?.label ?? s.kind} · {new Date(s.started_at + "Z").toLocaleString()} · {s.answers} answer
                  {s.answers === 1 ? "" : "s"}
                </div>
              </div>
              {s.avg_score != null && <StatusBadge label={`${s.avg_score} / 10`} tone={scoreTone(s.avg_score)} />}
              <StatusBadge label={s.status === "active" ? "In progress" : "Completed"} tone={s.status === "active" ? "running" : "idle"} />
              <Link to={`/interview/${s.id}`} className="btn-secondary !py-1.5">
                {s.status === "active" ? "Resume" : "View"}
              </Link>
              <button className="text-xs text-no hover:underline" onClick={() => remove(s.id)}>
                Delete
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ModelBanner({ status, onDownload }: { status: SpeechStatus; onDownload: (what: string) => void }) {
  const { whisper, kokoro } = status;
  if (whisper.ready && kokoro.ready) return null;
  const item = (label: string, ready: boolean, dl: string | null, what: string, size: string) => (
    <div className="flex items-center gap-2 text-sm">
      <span className={`h-1.5 w-1.5 rounded-full ${ready ? "bg-good" : "bg-warn"}`} />
      <span className="text-fg-soft">{label}</span>
      {ready ? (
        <span className="text-xs text-muted">ready</span>
      ) : dl === "downloading" ? (
        <span className="text-xs text-muted inline-flex items-center gap-1.5">
          <span className="spinner" /> downloading…
        </span>
      ) : (
        <>
          <button className="text-xs text-accent hover:underline" onClick={() => onDownload(what)}>
            Download ({size})
          </button>
          {dl?.startsWith("error") && <span className="text-xs text-no truncate">{dl}</span>}
        </>
      )}
    </div>
  );
  return (
    <div className="card p-4 flex flex-col gap-2 border-warn/40">
      <div className="text-sm font-medium text-fg">Voice models needed for offline speech</div>
      <div className="text-xs text-muted">
        One-time download. Until then, interviews still work: speech falls back to Groq (if set in Settings › Interview) and the
        browser's voice, or you can type answers.
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 pt-1">
        {item(`Speech recognition (Whisper ${whisper.model})`, whisper.ready, whisper.download, `whisper:${whisper.model}`, "size depends on model")}
        {item("Interviewer voice (Kokoro)", kokoro.ready, kokoro.download, "kokoro", "~120 MB")}
      </div>
    </div>
  );
}

function MicCheck() {
  const rec = useRecorder();
  const speaker = useSpeaker();
  const [result, setResult] = useState<(Transcript & { ms: number }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (rec.state === "recording") {
      const blob = await rec.stop();
      setBusy(true);
      setError(null);
      const t0 = performance.now();
      try {
        const r = await api.transcribe(blob);
        setResult({ ...r, ms: Math.round(performance.now() - t0) });
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
      } finally {
        setBusy(false);
      }
    } else {
      setResult(null);
      rec.start();
    }
  }

  const sample = "Hi, I'll be your interviewer today. Tell me a little about yourself.";

  return (
    <div className="card p-5 flex flex-col gap-4">
      <div>
        <div className="text-sm font-semibold text-fg">Mic &amp; voice check</div>
        <div className="text-xs text-muted">Say a sentence, then check it was heard correctly.</div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={toggle}
          disabled={busy || rec.state === "starting"}
          className={`h-14 w-14 shrink-0 rounded-full flex items-center justify-center transition-colors ${
            rec.state === "recording" ? "bg-bad text-on-accent" : "bg-accent text-on-accent hover:bg-accent-hover"
          }`}
          aria-label={rec.state === "recording" ? "Stop recording" : "Start recording"}
        >
          {busy ? <span className="spinner" /> : rec.state === "recording" ? <StopIcon /> : <MicIcon />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="h-2 rounded-full bg-track overflow-hidden">
            <div className="h-full bg-accent transition-[width] duration-75" style={{ width: `${rec.level * 100}%` }} />
          </div>
          <div className="text-xs text-muted mt-1.5">
            {rec.state === "recording" ? "Listening… click to stop" : busy ? "Transcribing…" : "Click the mic and speak"}
          </div>
        </div>
      </div>

      {(rec.error || error) && <div className="text-xs text-no">{rec.error || error}</div>}
      {result && (
        <div className="rounded-xl bg-subtle p-3 text-sm">
          <div className="text-fg">{result.text || <span className="text-muted">(no speech detected)</span>}</div>
          <div className="text-xs text-muted mt-1">
            {result.duration}s of audio · transcribed in {(result.ms / 1000).toFixed(1)}s
          </div>
        </div>
      )}

      <div className="border-t border-border pt-4 flex items-center justify-between gap-3">
        <span className="text-xs text-muted">Interviewer voice — change it in Settings › Interview.</span>
        <button
          className="btn-secondary !py-1.5 shrink-0"
          onClick={() => (speaker.speaking ? speaker.stop() : speaker.play(() => api.speak(sample), sample))}
        >
          {speaker.speaking ? "Stop" : "Play sample"}
        </button>
      </div>
    </div>
  );
}

function TopicPicker({ topics, onChange }: { topics: string[]; onChange: (t: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const add = (raw: string) => {
    const t = raw.trim();
    if (t && topics.length < 8 && !topics.some((x) => x.toLowerCase() === t.toLowerCase())) onChange([...topics, t]);
    setDraft("");
  };
  const suggestions = SUGGESTED_TOPICS.filter((s) => !topics.some((t) => t.toLowerCase() === s.toLowerCase())).slice(0, 10);

  return (
    <div className="flex flex-col gap-2">
      <span className="label !mb-0">Topics ({topics.length}/8)</span>
      <div className="input !p-1.5 flex flex-wrap items-center gap-1.5 min-h-[44px]">
        {topics.map((t) => (
          <span key={t} className="inline-flex items-center gap-1 rounded-full bg-accent-soft text-accent text-sm pl-3 pr-1.5 py-1">
            {t}
            <button
              className="h-4 w-4 rounded-full text-xs leading-none hover:bg-accent hover:text-on-accent"
              aria-label={`Remove ${t}`}
              onClick={() => onChange(topics.filter((x) => x !== t))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          className="flex-1 min-w-[140px] bg-transparent outline-none text-sm px-2 py-1 text-fg placeholder:text-muted"
          placeholder={topics.length ? "Add another…" : "Type a technology and press Enter"}
          value={draft}
          list="topic-suggestions"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add(draft);
            } else if (e.key === "Backspace" && !draft && topics.length) {
              onChange(topics.slice(0, -1));
            }
          }}
          onBlur={() => draft && add(draft)}
        />
        <datalist id="topic-suggestions">
          {SUGGESTED_TOPICS.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {suggestions.map((s) => (
          <button key={s} className="chip hover:border-accent hover:text-accent" onClick={() => add(s)}>
            + {s}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Segmented({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { id: string; label: string }[];
}) {
  return (
    <div className="inline-flex w-fit rounded-full bg-subtle p-1 border border-border">
      {options.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          className={`px-3.5 py-1.5 text-sm rounded-full transition-colors ${
            value === o.id ? "bg-surface text-fg shadow-card font-medium" : "text-muted hover:text-fg-soft"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function MicIcon({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

export function StopIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}
