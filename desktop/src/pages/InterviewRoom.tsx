import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import type { InterviewSession, InterviewTurn, Transcript } from "../lib/types";
import { readAnswerMode, useRecorder, useSpeaker } from "../lib/voice";
import { KIND_INFO, scoreTone } from "../lib/interview";
import InterviewResults from "../components/InterviewResults";
import StatusBadge from "../components/StatusBadge";
import CodeBlock from "../components/CodeBlock";
import { MicIcon, StopIcon } from "./Interview";

type Phase = "loading" | "speaking" | "ready" | "recording" | "transcribing" | "thinking" | "ended" | "error";

const PHASE_LABEL: Record<Phase, string> = {
  loading: "Loading…",
  speaking: "Interviewer is speaking",
  ready: "Your turn",
  recording: "Listening…",
  transcribing: "Transcribing your answer…",
  thinking: "Interviewer is thinking…",
  ended: "Interview complete",
  error: "Something went wrong",
};

export default function InterviewRoom() {
  const { id } = useParams();
  const sid = Number(id);
  const navigate = useNavigate();
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<InterviewTurn | null>(null);
  const [now, setNow] = useState(Date.now());
  const handsFree = readAnswerMode() === "hands-free";
  const speaker = useSpeaker();
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  const transcriptEnd = useRef<HTMLDivElement>(null);

  const turns = session?.turns ?? [];
  const lastInterviewer = [...turns].reverse().find((t) => t.speaker === "interviewer");
  const planLen = session?.context.plan?.length ?? 0;
  const qNum = Math.min((lastInterviewer?.meta.qi ?? 0) + 1, planLen);
  // the snippet for the current main question stays up through its follow-ups
  const current = lastInterviewer && !lastInterviewer.meta.closing ? session?.context.plan?.[lastInterviewer.meta.qi ?? -1] : undefined;
  const lastCandidate = [...turns].reverse().find((t) => t.speaker === "candidate");

  // ---- answering --------------------------------------------------------

  const send = useCallback(
    async (body: { text?: string; words?: Transcript["words"]; duration?: number; edit_turn_id?: number; skip?: boolean }) => {
      setPhase("thinking");
      setError(null);
      try {
        const r = await api.answerInterview(sid, body);
        const s = await api.getInterview(sid);
        setSession(s);
        speak(r.interviewer, r.done);
      } catch (e) {
        setError(String(e instanceof Error ? e.message : e));
        setSession(await api.getInterview(sid).catch(() => null));
        setPhase("error");
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sid],
  );

  const handleAudio = useCallback(
    async (blob: Blob) => {
      setPhase("transcribing");
      setError(null);
      try {
        const t = await api.transcribe(blob);
        if (!t.text.trim()) {
          setError("Didn't catch that — no speech detected. Try again, or type your answer.");
          setPhase("ready");
          return;
        }
        await send({ text: t.text, words: t.words, duration: t.duration });
      } catch (e) {
        setError(`${e instanceof Error ? e.message : e} — you can type your answer instead.`);
        setTyping(true);
        setPhase("ready");
      }
    },
    [send],
  );

  const rec = useRecorder({ handsFree, onAutoStop: handleAudio });

  const startRecording = useCallback(() => {
    if (!["ready", "speaking", "error"].includes(phaseRef.current)) return;
    speaker.stop(); // talking over the interviewer cuts it off, like a real call
    setError(null);
    setPhase("recording");
    rec.start();
  }, [rec, speaker]);

  const stopRecording = useCallback(async () => {
    if (phaseRef.current !== "recording") return;
    handleAudio(await rec.stop());
  }, [rec, handleAudio]);

  // ---- interviewer speech ----------------------------------------------

  const speak = useCallback(
    async (turn: InterviewTurn, done: boolean) => {
      setPhase("speaking");
      await speaker.play(() => api.turnSpeech(turn.id), turn.text);
      if (phaseRef.current !== "speaking") return; // the user cut in / left
      if (done) {
        setPhase("ended");
      } else if (handsFree) {
        startRecording();
      } else {
        setPhase("ready");
      }
    },
    [speaker, handsFree, startRecording],
  );

  // ---- load -------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    api
      .getInterview(sid)
      .then((s) => {
        if (cancelled) return;
        setSession(s);
        const last = s.turns[s.turns.length - 1];
        if (s.status === "ended") setPhase("ended");
        else if (!last || last.speaker === "candidate") {
          // the interviewer's turn never got generated (AI failure) — offer Retry
          setError("The interviewer didn't respond. Retry to continue.");
          setPhase("error");
        } else speak(last, false);
      })
      .catch((e) => {
        setError(String(e instanceof Error ? e.message : e));
        setPhase("error");
      });
    return () => {
      cancelled = true;
      speaker.stop();
      rec.cancel();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, phase]);

  // after the interview, answers are still being scored in the background: poll until they land
  const [scoring, setScoring] = useState(false);
  const unscored = turns.filter((t) => t.speaker === "candidate" && !t.meta.skipped && !t.eval).length;
  useEffect(() => {
    if (phase !== "ended" || !unscored) {
      setScoring(false);
      return;
    }
    setScoring(true);
    const started = Date.now();
    const t = setInterval(async () => {
      const s = await api.getInterview(sid).catch(() => null);
      if (s) setSession(s);
      if (Date.now() - started > 60000) {
        clearInterval(t);
        setScoring(false);
      }
    }, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, unscored > 0, sid]);

  async function rescore() {
    await api.scoreMissing(sid);
    const s = await api.getInterview(sid);
    // clear failed evals locally so polling restarts and the panel shows "Scoring…"
    setSession({ ...s, turns: s.turns.map((t) => (t.eval?.error ? { ...t, eval: null } : t)) });
  }

  // push-to-talk: hold Space
  useEffect(() => {
    if (handsFree) return;
    const typingTarget = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      return el.tagName === "TEXTAREA" || el.tagName === "INPUT" || el.isContentEditable;
    };
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat || typingTarget(e)) return;
      e.preventDefault();
      startRecording();
    };
    const up = (e: KeyboardEvent) => {
      if (e.code !== "Space" || typingTarget(e)) return;
      e.preventDefault();
      stopRecording();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [handsFree, startRecording, stopRecording]);

  // ---- actions ----------------------------------------------------------

  function submitTyped() {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    setTyping(false);
    const edit = editing;
    setEditing(null);
    send({ text, edit_turn_id: edit?.id });
  }

  function retry() {
    const last = turns[turns.length - 1];
    if (last?.speaker === "interviewer") {
      setError(null);
      speak(last, false);
    } else send({});
  }

  async function end() {
    speaker.stop();
    rec.cancel();
    setSession(await api.endInterview(sid));
    setPhase("ended");
  }

  if (!session) {
    return (
      <div className="text-sm text-muted">
        {phase === "error" ? <span className="text-no">{error}</span> : "Loading interview…"}
      </div>
    );
  }

  const started = new Date(session.started_at + "Z").getTime();
  const endedAt = session.ended_at ? new Date(session.ended_at + "Z").getTime() : now;
  const elapsed = Math.max(0, Math.floor((endedAt - started) / 1000));
  const busy = phase === "thinking" || phase === "transcribing" || phase === "loading";
  const micDisabled = busy || phase === "ended" || typing;
  const ended = phase === "ended";

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-3.5rem)] min-h-0">
      {/* top bar */}
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <button className="text-xs text-accent hover:underline" onClick={() => navigate("/interview")}>
            ← Interview prep
          </button>
          <h1 className="text-lg font-semibold text-fg truncate">
            {KIND_INFO[session.kind]?.label ?? "Interview"} <span className="text-muted font-normal">· {session.title}</span>
          </h1>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          {planLen > 0 && <Meta label="Question" value={`${qNum} / ${planLen}`} />}
          <Meta label={ended ? "Duration" : "Elapsed"} value={fmt(elapsed)} />
          {!ended && (
            <button className="btn-danger !py-1.5" onClick={end}>
              End interview
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-3 flex-1 min-h-0">
        {/* stage */}
        <div className="card flex flex-col min-h-0 overflow-hidden">
          <div
            className={`flex-1 min-h-0 overflow-y-auto flex flex-col items-center gap-6 px-8 py-6 text-center ${
              ended ? "justify-start" : "justify-center"
            }`}
          >
            {ended ? (
              <>
                <div className="flex flex-col gap-1">
                  <div className="text-base font-semibold text-fg">Interview complete</div>
                  <div className="text-xs text-muted">Open a question to see what worked, what to fix and a stronger answer.</div>
                </div>
                <InterviewResults session={session} scoring={scoring} onRescore={rescore} />
              </>
            ) : (
              <>
                <Avatar
                  name={session.config.interviewer_name || "Alex"}
                  speaking={phase === "speaking"}
                  thinking={phase === "thinking"}
                />
                <div className="flex flex-col items-center gap-2 max-w-xl">
                  <div className="flex items-center gap-2">
                    {lastInterviewer?.meta.topic && !lastInterviewer.meta.closing && (
                      <span className="chip !text-accent">{lastInterviewer.meta.topic}</span>
                    )}
                    {lastInterviewer?.meta.followup && <span className="chip">Follow-up</span>}
                  </div>
                  <div className="eyebrow">{PHASE_LABEL[phase]}</div>
                  <p className="text-[17px] leading-relaxed text-fg">{lastInterviewer?.text ?? "…"}</p>
                </div>
                {current?.code && <CodeBlock code={current.code} language={current.language} className="w-full max-w-2xl" />}
              </>
            )}
            {error && (
              <div className="text-sm text-no max-w-xl flex flex-col items-center gap-2">
                {error}
                {phase === "error" && (
                  <button className="btn-secondary !py-1.5" onClick={retry}>
                    Retry
                  </button>
                )}
              </div>
            )}
          </div>

          {/* controls */}
          <div className="border-t border-border px-5 py-4 shrink-0">
            {ended ? (
              <div className="flex flex-wrap items-center justify-center gap-3">
                <span className="text-sm text-muted">
                  {turns.filter((t) => t.speaker === "candidate" && !t.meta.skipped).length} answers · {fmt(elapsed)}
                </span>
                <button className="btn-primary !py-1.5" onClick={() => navigate("/interview")}>
                  New interview
                </button>
              </div>
            ) : typing ? (
              <div className="flex flex-col gap-2">
                {editing && <div className="text-xs text-warn">Editing your last answer — the interviewer will respond again.</div>}
                <textarea
                  autoFocus
                  className="input resize-none"
                  rows={3}
                  placeholder="Type your answer… (Ctrl+Enter to send)"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitTyped();
                  }}
                />
                <div className="flex justify-end gap-2">
                  <button
                    className="btn-ghost"
                    onClick={() => {
                      setTyping(false);
                      setEditing(null);
                      setDraft("");
                    }}
                  >
                    Cancel
                  </button>
                  <button className="btn-primary !py-1.5" onClick={submitTyped} disabled={!draft.trim() || busy}>
                    Send answer
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center gap-6">
                <button
                  className="btn-ghost"
                  disabled={!lastInterviewer || busy || phase === "recording"}
                  onClick={() => lastInterviewer && speak(lastInterviewer, false)}
                >
                  Repeat
                </button>
                <MicButton
                  phase={phase}
                  level={rec.level}
                  disabled={micDisabled}
                  handsFree={handsFree}
                  onPress={() => (phase === "recording" ? stopRecording() : startRecording())}
                />
                <button className="btn-ghost" disabled={busy || phase === "recording"} onClick={() => setTyping(true)}>
                  Type instead
                </button>
              </div>
            )}
            {!ended && !typing && (
              <div className="text-center text-xs text-muted mt-2">
                {phase === "recording"
                  ? handsFree
                    ? "Sends when you pause — or click to send now"
                    : "Release Space (or click) to send"
                  : handsFree
                    ? "Hands-free: the mic opens after each question"
                    : "Hold Space or click the mic to answer"}
                {!busy && phase !== "recording" && (
                  <>
                    {" · "}
                    <button className="text-accent hover:underline" onClick={() => send({ skip: true })}>
                      Skip question
                    </button>
                  </>
                )}
              </div>
            )}
            {rec.error && <div className="text-center text-xs text-no mt-2">{rec.error}</div>}
          </div>
        </div>

        {/* transcript */}
        <div className="card flex flex-col min-h-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-border text-sm font-medium text-fg shrink-0">Transcript</div>
          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 flex flex-col gap-3">
            {turns.map((t) => (
              <div key={t.id} className={`flex flex-col gap-1 ${t.speaker === "candidate" ? "items-end" : "items-start"}`}>
                {t.speaker === "interviewer" && t.meta.qi !== undefined && !t.meta.followup && !t.meta.closing && (
                  <div className="self-stretch flex items-center gap-2 text-[11px] text-muted pt-1">
                    <span className="h-px flex-1 bg-border" />
                    Question {t.meta.qi + 1}
                    {t.meta.topic ? ` · ${t.meta.topic}` : ""}
                    <span className="h-px flex-1 bg-border" />
                  </div>
                )}
                <div
                  className={`max-w-[90%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap break-words ${
                    t.speaker === "candidate" ? "bg-accent text-on-accent rounded-br-md" : "bg-subtle text-fg rounded-bl-md"
                  }`}
                >
                  {t.text}
                </div>
                <div className="text-[11px] text-muted flex gap-2">
                  {t.speaker === "candidate" ? "You" : session.config.interviewer_name || "Alex"}
                  {t.duration > 0 && <span>· {Math.round(t.duration)}s</span>}
                  {ended && t.eval && !t.eval.error && (
                    <StatusBadge label={`${t.eval.score}/10`} tone={scoreTone(t.eval.score)} dot={false} />
                  )}
                  {t.speaker === "candidate" && t.id === lastCandidate?.id && !ended && !busy && phase !== "recording" && (
                    <button
                      className="text-accent hover:underline"
                      onClick={() => {
                        speaker.stop();
                        setEditing(t);
                        setDraft(t.text);
                        setTyping(true);
                        setPhase("ready");
                      }}
                    >
                      Edit
                    </button>
                  )}
                </div>
              </div>
            ))}
            {phase === "transcribing" && <Pending side="end" />}
            {phase === "thinking" && <Pending side="start" />}
            <div ref={transcriptEnd} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MicButton({
  phase,
  level,
  disabled,
  handsFree,
  onPress,
}: {
  phase: Phase;
  level: number;
  disabled: boolean;
  handsFree: boolean;
  onPress: () => void;
}) {
  const recording = phase === "recording";
  return (
    <div className="relative h-20 w-20 flex items-center justify-center">
      {recording && (
        <span
          className="absolute inset-0 rounded-full bg-bad/25 transition-transform duration-75"
          style={{ transform: `scale(${1 + level * 0.6})` }}
        />
      )}
      <button
        onClick={onPress}
        disabled={disabled}
        aria-label={recording ? "Send answer" : "Answer"}
        title={handsFree ? "Click to start / send" : "Hold Space, or click to start / send"}
        className={`relative h-16 w-16 rounded-full flex items-center justify-center shadow-card transition-colors disabled:opacity-40 ${
          recording ? "bg-bad text-on-accent" : "bg-accent text-on-accent hover:bg-accent-hover"
        }`}
      >
        {phase === "transcribing" || phase === "thinking" ? <span className="spinner" /> : recording ? <StopIcon /> : <MicIcon />}
      </button>
    </div>
  );
}

function Avatar({ name, speaking, thinking }: { name: string; speaking: boolean; thinking: boolean }) {
  return (
    <div className="relative h-28 w-28 flex items-center justify-center">
      {speaking && <span className="absolute inset-0 rounded-full bg-accent/20 animate-ping" />}
      <span
        className={`absolute inset-0 rounded-full border-2 ${speaking ? "border-accent" : thinking ? "border-accent/50 animate-pulse" : "border-border"}`}
      />
      <div className="h-24 w-24 rounded-full bg-accent-soft flex items-center justify-center text-3xl font-semibold text-accent">
        {name.charAt(0).toUpperCase()}
      </div>
    </div>
  );
}

function Pending({ side }: { side: "start" | "end" }) {
  return (
    <div className={`flex ${side === "end" ? "justify-end" : "justify-start"}`}>
      <div className="rounded-2xl bg-subtle px-3.5 py-2.5 flex gap-1">
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-1.5 w-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: `${i * 120}ms` }} />
        ))}
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <div className="text-sm font-semibold text-fg num">{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}

function fmt(sec: number) {
  const m = Math.floor(sec / 60);
  return `${m}:${String(sec % 60).padStart(2, "0")}`;
}
