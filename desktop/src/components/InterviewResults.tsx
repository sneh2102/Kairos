import { useState } from "react";
import type { AnswerEval, InterviewSession, InterviewTurn, PlannedQuestion } from "../lib/types";
import CodeBlock from "./CodeBlock";
import { scoreTone } from "../lib/interview";

const TONE_TEXT: Record<string, string> = { yes: "text-good", maybe: "text-warn", no: "text-bad" };
const TONE_BG: Record<string, string> = { yes: "bg-good", maybe: "bg-warn", no: "bg-bad" };
const STAR_KEYS = ["situation", "task", "action", "result"] as const;

interface Group {
  qi: number;
  topic: string;
  question: string;
  planned?: PlannedQuestion;
  answers: InterviewTurn[];
}

/** Candidate answers grouped under the main question (follow-ups included) they belong to. */
function groupAnswers(session: InterviewSession): Group[] {
  const plan = session.context.plan ?? [];
  const groups: Group[] = [];
  let current: Group | null = null;
  for (const t of session.turns) {
    if (t.speaker === "interviewer") {
      const qi = t.meta.qi;
      if (qi !== undefined && !t.meta.closing && (!current || current.qi !== qi)) {
        // the planned wording, not the spoken turn (which may open with a greeting)
        current = {
          qi,
          topic: plan[qi]?.topic || t.meta.topic || "",
          question: plan[qi]?.question || t.text,
          planned: plan[qi],
          answers: [],
        };
        groups.push(current);
      }
    } else if (current) {
      current.answers.push(t);
    }
  }
  return groups;
}

function avg(xs: number[]) {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
}

export default function InterviewResults({
  session,
  scoring,
  onRescore,
}: {
  session: InterviewSession;
  scoring: boolean;
  onRescore: () => void;
}) {
  const answers = session.turns.filter((t) => t.speaker === "candidate" && !t.meta.skipped);
  const evals = answers.map((t) => t.eval).filter((e): e is AnswerEval => !!e && !e.error && typeof e.score === "number");
  const failed = answers.some((t) => t.eval?.error);
  const pending = answers.filter((t) => !t.eval).length;
  const overall = avg(evals.map((e) => e.score));

  // criteria averages, in the order the rubric returns them
  const criteria: Record<string, number[]> = {};
  for (const e of evals) for (const [k, v] of Object.entries(e.criteria ?? {})) (criteria[k] ??= []).push(Number(v));
  const starEvals = evals.filter((e) => e.star);
  const groups = groupAnswers(session);

  // technical: average question score per topic, weakest first
  const byTopic: Record<string, number[]> = {};
  if (session.kind === "technical") {
    for (const g of groups) {
      const s = groupScore(g);
      if (s != null && g.topic) (byTopic[g.topic] ??= []).push(s);
    }
  }
  const topicScores = Object.entries(byTopic)
    .map(([t, xs]) => [t, avg(xs)!] as const)
    .sort((a, b) => a[1] - b[1]);

  if (answers.length === 0) {
    return <div className="text-sm text-muted text-center">No answers were given, so there's nothing to score.</div>;
  }

  return (
    <div className="w-full max-w-2xl flex flex-col gap-5 text-left">
      <div className="flex items-center gap-5">
        <div className="text-center shrink-0">
          <div className={`text-4xl font-semibold num ${overall != null ? TONE_TEXT[scoreTone(overall)] : "text-muted"}`}>
            {overall != null ? overall.toFixed(1) : "—"}
          </div>
          <div className="text-[11px] text-muted">avg score / 10</div>
        </div>
        <div className="flex-1 min-w-0 flex flex-col gap-1.5">
          {Object.entries(criteria).map(([k, vs]) => {
            const a = avg(vs)!;
            return (
              <div key={k} className="flex items-center gap-2 text-xs">
                <span className="w-24 text-fg-soft capitalize">{k}</span>
                <div className="flex-1 h-1.5 rounded-full bg-track overflow-hidden">
                  <div className="h-full bg-accent rounded-full" style={{ width: `${(a / 5) * 100}%` }} />
                </div>
                <span className="w-8 text-right num text-muted">{a.toFixed(1)}</span>
              </div>
            );
          })}
        </div>
      </div>

      {starEvals.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">STAR coverage</span>
          {STAR_KEYS.map((k) => {
            const pct = Math.round((starEvals.filter((e) => e.star?.[k]).length / starEvals.length) * 100);
            return (
              <span key={k} className="chip" title={`${pct}% of answers covered the ${k}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${TONE_BG[pct >= 75 ? "yes" : pct >= 40 ? "maybe" : "no"]}`} />
                <span className="capitalize">{k}</span> {pct}%
              </span>
            );
          })}
        </div>
      )}

      {topicScores.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">By topic</span>
          {topicScores.map(([t, s]) => (
            <span key={t} className="chip">
              <span className={`h-1.5 w-1.5 rounded-full ${TONE_BG[scoreTone(s)]}`} />
              {t} <span className="num font-medium">{s.toFixed(1)}</span>
            </span>
          ))}
        </div>
      )}

      {(scoring || pending > 0 || failed) && (
        <div className="text-xs text-muted flex items-center gap-2">
          {scoring ? (
            <>
              <span className="spinner" /> Scoring answers…
            </>
          ) : (
            <>
              {failed ? "Some answers couldn't be scored." : `${pending} answer(s) not scored yet.`}
              <button className="text-accent hover:underline" onClick={onRescore}>
                Score them now
              </button>
            </>
          )}
        </div>
      )}

      <div className="flex flex-col gap-2">
        {groups.map((g) => (
          <QuestionCard key={g.qi} group={g} />
        ))}
      </div>
    </div>
  );
}

/** A question's score: the mean of its answers (main + follow-ups) — each is scored on its own. */
function groupScore(g: Group) {
  return avg(g.answers.flatMap((a) => (a.eval && !a.eval.error ? [a.eval.score] : [])));
}

function QuestionCard({ group }: { group: Group }) {
  const [open, setOpen] = useState(false);
  const score = groupScore(group);
  const skipped = group.answers.length > 0 && group.answers.every((a) => a.meta.skipped);

  return (
    <div className="rounded-xl border border-border">
      <button className="w-full flex items-start gap-3 p-3 text-left" onClick={() => setOpen(!open)}>
        <span className="num text-xs text-muted pt-0.5 w-6 shrink-0">Q{group.qi + 1}</span>
        <div className="min-w-0 flex-1">
          {group.topic && <div className="text-[11px] font-medium text-accent">{group.topic}</div>}
          <div className={`text-sm text-fg ${open ? "" : "line-clamp-2"}`}>{group.question}</div>
        </div>
        <span className={`text-sm font-semibold num shrink-0 ${score != null ? TONE_TEXT[scoreTone(score)] : "text-muted"}`}>
          {skipped ? "skipped" : score != null ? `${+score.toFixed(1)}/10` : "—"}
        </span>
        <span className="text-muted text-xs pt-0.5">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="border-t border-border p-3 flex flex-col gap-3 text-sm">
          {group.planned?.code && <CodeBlock code={group.planned.code} language={group.planned.language} />}
          {group.answers.map((a, i) => (
            <div key={a.id} className="flex flex-col gap-1.5">
              <div className="text-[11px] text-muted">
                {i === 0 ? "Your answer" : "Your answer to the follow-up"}
                {a.eval && !a.eval.error && ` · ${a.eval.score}/10`}
              </div>
              <p className="text-fg-soft whitespace-pre-wrap">{a.text}</p>
              {a.eval && !a.eval.error && <Feedback ev={a.eval} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Feedback({ ev }: { ev: AnswerEval }) {
  return (
    <div className="rounded-lg bg-subtle p-3 flex flex-col gap-2 text-[13px]">
      {ev.star && (
        <div className="flex gap-1.5">
          {STAR_KEYS.map((k) => (
            <span
              key={k}
              className={`text-[11px] px-2 py-0.5 rounded-full border ${
                ev.star?.[k] ? "bg-good/12 text-good border-good/30" : "bg-bad/10 text-bad border-bad/30 line-through"
              }`}
            >
              {k[0].toUpperCase() + k.slice(1)}
            </span>
          ))}
        </div>
      )}
      {!!ev.strengths?.length && (
        <div>
          <div className="text-[11px] font-medium text-good mb-0.5">What worked</div>
          <ul className="list-disc pl-4 text-fg-soft space-y-0.5">
            {ev.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}
      {!!ev.missed_concepts?.length && (
        <div>
          <div className="text-[11px] font-medium text-bad mb-0.5">Concepts you missed</div>
          <div className="flex flex-wrap gap-1.5">
            {ev.missed_concepts.map((c, i) => (
              <span key={i} className="text-[11px] px-2 py-0.5 rounded-full bg-bad/10 text-bad border border-bad/30">
                {c}
              </span>
            ))}
          </div>
        </div>
      )}
      {!!ev.improvements?.length && (
        <div>
          <div className="text-[11px] font-medium text-warn mb-0.5">Improve</div>
          <ul className="list-disc pl-4 text-fg-soft space-y-0.5">
            {ev.improvements.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}
      {ev.better_answer && (
        <div>
          <div className="text-[11px] font-medium text-accent mb-0.5">A stronger answer</div>
          <p className="text-fg-soft italic">{ev.better_answer}</p>
        </div>
      )}
    </div>
  );
}
