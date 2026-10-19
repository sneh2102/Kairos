import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import type { PrepGuide as Guide } from "../lib/types";

type Tab = "company" | "fit" | "qa" | "ask" | "resources";
type Sources = Guide["content"]["company_info"]["sources"];

const TABS: [Tab, string][] = [
  ["company", "Company"],
  ["fit", "Role & fit"],
  ["qa", "Practice Q&A"],
  ["ask", "Questions to ask"],
  ["resources", "Resources"],
];

export default function PrepGuide() {
  const { id } = useParams();
  const gid = Number(id);
  const navigate = useNavigate();
  const [guide, setGuide] = useState<Guide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("company");
  const [busy, setBusy] = useState<"regen" | "mock" | null>(null);

  useEffect(() => {
    setGuide(null);
    api.getPrepGuide(gid).then(setGuide).catch((e) => setError(String(e instanceof Error ? e.message : e)));
  }, [gid]);

  if (error) return <div className="text-sm text-no">{error}</div>;
  if (!guide) return <div className="text-sm text-muted">Loading prep guide…</div>;

  const c = guide.content;
  const jobRef = guide.job_id ? { job_source: guide.job_source, job_id: guide.job_id } : { role: guide.title, company: guide.company };

  async function regenerate() {
    setBusy("regen");
    setError(null);
    try {
      const fresh = await api.createPrepGuide(jobRef);
      await api.deletePrepGuide(gid);
      navigate(`/interview/prep/${fresh.id}`, { replace: true });
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(null);
    }
  }

  async function mock() {
    setBusy("mock");
    try {
      const s = await api.createInterview("behavioral", {
        ...(guide!.job_id
          ? { job_source: guide!.job_source as "jobs" | "applied", job_id: guide!.job_id }
          : { role: guide!.title, company: guide!.company }),
        length: "standard",
        persona: "neutral",
      });
      navigate(`/interview/${s.id}`);
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
      setBusy(null);
    }
  }

  async function remove() {
    await api.deletePrepGuide(gid);
    navigate("/interview");
  }

  const counts: Partial<Record<Tab, number>> = {
    qa: c.qa?.length,
    ask: c.questions_to_ask?.length,
    resources: c.resources?.length,
  };

  return (
    <div className="flex flex-col gap-4 max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <button className="text-xs text-accent hover:underline" onClick={() => navigate("/interview")}>
            ← Interview prep
          </button>
          <h1 className="text-lg font-semibold text-fg truncate">
            Prep guide <span className="text-muted font-normal">· {[guide.title, guide.company].filter(Boolean).join(" @ ")}</span>
          </h1>
          <div className="text-xs text-muted">Generated {new Date(guide.created_at + "Z").toLocaleString()}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button className="btn-primary !py-1.5" onClick={mock} disabled={!!busy}>
            {busy === "mock" ? <span className="spinner" /> : null} Mock interview for this job
          </button>
          <button className="btn-secondary !py-1.5" onClick={regenerate} disabled={!!busy} title="Re-research and rebuild (~30s)">
            {busy === "regen" ? (
              <>
                <span className="spinner" /> Rebuilding…
              </>
            ) : (
              "Regenerate"
            )}
          </button>
          <button className="btn-danger !py-1.5" onClick={remove} disabled={!!busy}>
            Delete
          </button>
        </div>
      </div>

      <div className="flex border-b border-border">
        {TABS.map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm border-b-2 -mb-px ${
              tab === t ? "border-accent text-fg font-medium" : "border-transparent text-muted hover:text-fg-soft"
            }`}
          >
            {label}
            {counts[t] ? <span className="ml-1.5 text-xs text-muted num">{counts[t]}</span> : null}
          </button>
        ))}
      </div>

      {tab === "company" && <CompanyTab info={c.company_info} company={guide.company} />}
      {tab === "fit" && <FitTab c={c} />}
      {tab === "qa" && <QaTab guideId={gid} qa={c.qa ?? []} />}
      {tab === "ask" && (
        <Card title="Questions to ask your interviewer" hint="Pick two or three. Asking specific questions signals real interest.">
          <ol className="flex flex-col gap-2">
            {(c.questions_to_ask ?? []).map((q, i) => (
              <li key={i} className="flex gap-3 text-sm text-fg-soft">
                <span className="num text-muted w-5 shrink-0">{i + 1}.</span>
                {q}
              </li>
            ))}
          </ol>
        </Card>
      )}
      {tab === "resources" && <ResourcesTab resources={c.resources ?? []} focus={c.focus_areas ?? []} />}
    </div>
  );
}

// ---- company ----------------------------------------------------------------

function CompanyTab({ info, company }: { info: Guide["content"]["company_info"]; company: string }) {
  if (!company) {
    return <Empty>No company was given for this guide, so there's no company research.</Empty>;
  }
  if (!info.web) {
    return (
      <Empty>
        Couldn't research {company} online. Web search uses your Ollama keys, and they were all out of quota or rejected. Add
        a working key under Settings › API keys, then Regenerate.
      </Empty>
    );
  }
  const s = info.sources;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-4">
      <div className="flex flex-col gap-4 min-w-0">
        <Card title={`About ${company}`}>
          {info.overview && <p className="text-sm text-fg-soft leading-relaxed">{cite(info.overview, s)}</p>}
          {!!info.facts?.length && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">
              {info.facts.map((f, i) => (
                <div key={i} className="rounded-xl bg-subtle px-3 py-2">
                  <div className="text-[11px] text-muted">{f.label}</div>
                  <div className="text-sm font-medium text-fg">{cite(f.value, s)}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
        {!!info.products?.length && <ListCard title="What they offer" items={info.products} sources={s} />}
        {!!info.recent_news?.length && (
          <Card title="Recent news" hint="Mentioning something recent shows you did your homework.">
            <ul className="flex flex-col gap-2.5">
              {info.recent_news.map((n, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <span className="text-xs text-muted w-24 shrink-0 pt-0.5">{n.date ? cite(n.date, s) : ""}</span>
                  <span className="text-fg-soft">{cite(n.headline, s)}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
        {!!info.talking_points?.length && (
          <ListCard title="“Why do you want to work here?” — talking points" items={info.talking_points} sources={s} />
        )}
      </div>
      <div className="flex flex-col gap-4 min-w-0">
        {!!info.interview_process?.length && (
          <Card title="Interview process (as reported)">
            <ol className="flex flex-col gap-2">
              {info.interview_process.map((step, i) => (
                <li key={i} className="flex gap-2.5 text-sm text-fg-soft">
                  <span className="h-5 w-5 shrink-0 rounded-full bg-accent-soft text-accent text-[11px] flex items-center justify-center num">
                    {i + 1}
                  </span>
                  <span>{cite(step, s)}</span>
                </li>
              ))}
            </ol>
          </Card>
        )}
        {!!info.values?.length && <ListCard title="Mission & values" items={info.values} sources={s} />}
        {!!info.culture?.length && <ListCard title="Culture" items={info.culture} sources={s} />}
        {!!info.tech_stack?.length && (
          <Card title="Tech they use">
            <div className="flex flex-wrap gap-1.5">
              {info.tech_stack.map((t, i) => (
                <span key={i} className="chip">
                  {t.replace(/\s*\[[\d,\s]+\]/g, "")}
                </span>
              ))}
            </div>
          </Card>
        )}
        <Card title="Sources" hint="Web search results this section was built from. Numbers in the text point here.">
          <ol className="flex flex-col gap-1.5">
            {s.map((src) => (
              <li key={src.n} className="flex gap-2 text-xs">
                <span className="num text-muted w-5 shrink-0">[{src.n}]</span>
                <a href={src.url} target="_blank" rel="noreferrer" className="text-accent hover:underline truncate" title={src.url}>
                  {src.title}
                </a>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}

/** Turns "[3]" / "[1, 4]" markers into superscript links to the numbered sources. */
function cite(text: string, sources: Sources): ReactNode {
  const parts = text.split(/(\[\d+(?:\s*,\s*\d+)*\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[([\d,\s]+)\]$/);
    if (!m) return part;
    return (
      <sup key={i} className="ml-0.5">
        {m[1].split(",").map((n, j) => {
          const src = sources.find((x) => x.n === Number(n.trim()));
          return src ? (
            <a key={j} href={src.url} target="_blank" rel="noreferrer" title={src.title} className="text-accent hover:underline mr-0.5">
              {n.trim()}
            </a>
          ) : null;
        })}
      </sup>
    );
  });
}

// ---- role & fit ---------------------------------------------------------------

function FitTab({ c }: { c: Guide["content"] }) {
  return (
    <div className="flex flex-col gap-4">
      {c.role_summary && (
        <Card title="What this role is really about">
          <p className="text-sm text-fg-soft leading-relaxed">{c.role_summary}</p>
        </Card>
      )}
      {!!c.focus_areas?.length && (
        <Card title="Focus your prep on">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {c.focus_areas.map((f, i) => (
              <div key={i} className="rounded-xl border border-border p-3">
                <div className="text-sm font-medium text-fg">{f.topic}</div>
                <div className="text-xs text-muted mt-1">{f.why}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {!!c.fit?.strengths?.length && (
          <Card title="Where you're strong">
            <ul className="flex flex-col gap-2">
              {c.fit.strengths.map((s, i) => (
                <li key={i} className="flex gap-2 text-sm text-fg-soft">
                  <span className="text-good shrink-0">✓</span>
                  {s}
                </li>
              ))}
            </ul>
          </Card>
        )}
        {!!c.fit?.gaps?.length && (
          <Card title="Gaps to prepare for">
            <ul className="flex flex-col gap-3">
              {c.fit.gaps.map((g, i) => (
                <li key={i} className="text-sm">
                  <div className="flex gap-2 text-fg">
                    <span className="text-warn shrink-0">!</span>
                    {g.gap}
                  </div>
                  <div className="text-xs text-muted mt-1 ml-4">{g.how_to_prepare}</div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}

// ---- practice Q&A -------------------------------------------------------------

function practicedKey(id: number) {
  return `prep.practiced.${id}`;
}

function QaTab({ guideId, qa }: { guideId: number; qa: NonNullable<Guide["content"]["qa"]> }) {
  const [cat, setCat] = useState("All");
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  // which questions you've practiced — a per-viewer convenience, so browser storage is fine
  const [practiced, setPracticed] = useState<Set<number>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(practicedKey(guideId)) || "[]"));
    } catch {
      return new Set();
    }
  });

  function togglePracticed(i: number) {
    const next = new Set(practiced);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    setPracticed(next);
    try {
      localStorage.setItem(practicedKey(guideId), JSON.stringify([...next]));
    } catch {
      /* not persisted — fine */
    }
  }

  const cats = ["All", ...new Set(qa.map((q) => q.category))];
  const shown = qa.map((q, i) => ({ q, i })).filter(({ q }) => cat === "All" || q.category === cat);
  const allOpen = shown.every(({ i }) => revealed.has(i));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {cats.map((c) => (
          <button
            key={c}
            onClick={() => setCat(c)}
            className={`px-3 py-1 rounded-full text-xs transition-colors ${
              cat === c ? "bg-accent text-on-accent" : "bg-subtle text-fg-soft hover:text-fg"
            }`}
          >
            {c} <span className="opacity-75 num">{c === "All" ? qa.length : qa.filter((q) => q.category === c).length}</span>
          </button>
        ))}
        <span className="ml-auto text-xs text-muted num">
          {practiced.size}/{qa.length} practiced
        </span>
        <button
          className="text-xs text-accent hover:underline"
          onClick={() => {
            const next = new Set(revealed);
            shown.forEach(({ i }) => (allOpen ? next.delete(i) : next.add(i)));
            setRevealed(next);
          }}
        >
          {allOpen ? "Hide all answers" : "Show all answers"}
        </button>
      </div>
      <p className="text-xs text-muted">Try answering out loud first, then reveal the sample answer to compare.</p>

      {shown.map(({ q, i }) => {
        const open = revealed.has(i);
        return (
          <div key={i} className={`card p-4 flex flex-col gap-2 ${practiced.has(i) ? "opacity-70" : ""}`}>
            <div className="flex items-start gap-3">
              <span className="num text-xs text-muted pt-0.5 w-6 shrink-0">Q{i + 1}</span>
              <div className="flex-1 min-w-0">
                <span className="text-[11px] font-medium text-accent">{q.category}</span>
                <div className="text-sm font-medium text-fg">{q.question}</div>
              </div>
              <label className="flex items-center gap-1.5 text-xs text-muted shrink-0 cursor-pointer">
                <input type="checkbox" checked={practiced.has(i)} onChange={() => togglePracticed(i)} />
                Practiced
              </label>
            </div>
            <div className="ml-9">
              {open ? (
                <div className="flex flex-col gap-2">
                  <p className="text-sm text-fg-soft leading-relaxed whitespace-pre-wrap">{q.answer}</p>
                  {q.tip && (
                    <div className="text-xs text-muted">
                      <span className="font-medium text-fg-soft">What they're checking:</span> {q.tip}
                    </div>
                  )}
                  <button
                    className="text-xs text-accent hover:underline w-fit"
                    onClick={() => setRevealed((r) => new Set([...r].filter((x) => x !== i)))}
                  >
                    Hide answer
                  </button>
                </div>
              ) : (
                <button className="text-xs text-accent hover:underline" onClick={() => setRevealed((r) => new Set(r).add(i))}>
                  Show sample answer
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---- resources ------------------------------------------------------------------

function ResourcesTab({
  resources,
  focus,
}: {
  resources: NonNullable<Guide["content"]["resources"]>;
  focus: NonNullable<Guide["content"]["focus_areas"]>;
}) {
  if (!resources.length) return <Empty>No resources survived the dead-link check. Try Regenerate.</Empty>;
  const groups: Record<string, typeof resources> = {};
  for (const r of resources) (groups[r.topic || "General"] ??= []).push(r);
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted">
        Every link was checked and is live. Focus areas: {focus.map((f) => f.topic).join(" · ") || "—"}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(groups).map(([topic, rs]) => (
          <Card key={topic} title={topic}>
            <ul className="flex flex-col gap-3">
              {rs.map((r, i) => (
                <li key={i}>
                  <a href={r.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-accent hover:underline">
                    {r.title} ↗
                  </a>
                  <div className="text-xs text-muted mt-0.5">{r.why}</div>
                  <div className="text-[11px] text-muted truncate">{r.url}</div>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ---- bits ---------------------------------------------------------------------------

function Card({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="card p-4 flex flex-col gap-3">
      <div>
        <div className="text-sm font-semibold text-fg">{title}</div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function ListCard({ title, items, sources }: { title: string; items: string[]; sources: Sources }) {
  return (
    <Card title={title}>
      <ul className="flex flex-col gap-1.5 list-disc pl-4">
        {items.map((it, i) => (
          <li key={i} className="text-sm text-fg-soft">
            {cite(it, sources)}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="card p-6 text-sm text-muted text-center">{children}</div>;
}
