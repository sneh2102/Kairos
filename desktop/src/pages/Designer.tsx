import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import type { CustomSection, Layout, LayoutStyle, StaticEntry } from "../lib/types";

const CORE_NAMES: Record<string, string> = {
  skills: "Technical Skills",
  experience: "Experience",
  projects: "Relevant Projects",
  education: "Education",
};

// Ready-made section types for "+ Add section".
const PRESETS: { name: string; layout: "bullets" | "text" | "entries" }[] = [
  { name: "Achievements", layout: "bullets" },
  { name: "Volunteering", layout: "entries" },
  { name: "Certifications", layout: "entries" },
  { name: "Awards", layout: "bullets" },
  { name: "Publications", layout: "entries" },
  { name: "Languages", layout: "text" },
  { name: "Interests", layout: "text" },
  { name: "Custom section", layout: "bullets" },
];

const emptyEntry = (): StaticEntry => ({ title: "", subtitle: "", date: "", location: "", link: "", bullets: [""] });

export default function Designer() {
  const [layout, setLayout] = useState<Layout | null>(null);
  const [saved, setSaved] = useState("");
  const [tab, setTab] = useState<"sections" | "style">("sections");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [compiling, setCompiling] = useState(false);

  useEffect(() => {
    api.getLayout().then((l) => {
      setLayout(l);
      setSaved(JSON.stringify(l));
    }).catch((e) => setError(String(e)));
  }, []);

  // live preview: recompile (debounced) whenever the draft changes
  useEffect(() => {
    if (!layout) return;
    const ctrl = new AbortController();
    setCompiling(true);
    const t = setTimeout(() => {
      api.previewLayout(layout, ctrl.signal)
        .then((url) => {
          setPreviewUrl((old) => {
            if (old) URL.revokeObjectURL(old);
            return url;
          });
          setPreviewError("");
        })
        .catch((e) => !ctrl.signal.aborted && setPreviewError(String(e.message ?? e)))
        .finally(() => !ctrl.signal.aborted && setCompiling(false));
    }, 700);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [layout]);

  const dirty = useMemo(() => !!layout && JSON.stringify(layout) !== saved, [layout, saved]);

  if (!layout) return <div className="text-sm text-muted">{error || "Loading…"}</div>;

  const customById = Object.fromEntries(layout.custom_sections.map((s) => [s.id, s]));
  const patch = (p: Partial<Layout>) => setLayout({ ...layout, ...p });
  const hidden = new Set(layout.hidden_sections);

  function toggle(id: string) {
    const next = new Set(hidden);
    if (next.has(id)) next.delete(id); else next.add(id);
    patch({ hidden_sections: [...next] });
  }

  function move(id: string, dir: -1 | 1) {
    const order = [...layout!.section_order];
    const i = order.indexOf(id);
    const j = i + dir;
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    patch({ section_order: order });
  }

  function updateSection(id: string, p: Partial<CustomSection>) {
    patch({ custom_sections: layout!.custom_sections.map((s) => (s.id === id ? { ...s, ...p } : s)) });
  }

  function addSection(preset: (typeof PRESETS)[number]) {
    const id = `custom_${Date.now().toString(36)}`;
    const fresh: CustomSection = {
      id, name: preset.name, kind: "static", layout: preset.layout,
      bullets: preset.layout === "entries" ? [] : ["", "", ""],
      entries: preset.layout === "entries" ? [emptyEntry()] : [],
    };
    patch({ custom_sections: [...layout!.custom_sections, fresh], section_order: [...layout!.section_order, id] });
    setExpanded(id);
  }

  function removeSection(id: string) {
    if (!confirm(`Delete the "${customById[id]?.name}" section?`)) return;
    patch({
      custom_sections: layout!.custom_sections.filter((s) => s.id !== id),
      section_order: layout!.section_order.filter((x) => x !== id),
      hidden_sections: layout!.hidden_sections.filter((x) => x !== id),
    });
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const out = await api.saveLayout(layout!);
      setLayout(out);
      setSaved(JSON.stringify(out));
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex gap-5 h-full">
      <div className="w-[27rem] shrink-0 flex flex-col gap-3 min-h-0">
        <div>
          <h1 className="text-lg font-semibold text-fg">Resume designer</h1>
          <p className="text-sm text-muted">
            Design the look, choose which sections appear, and write your own. Saving makes this the base
            template for every new resume.
          </p>
        </div>

        <div className="flex gap-2">
          <button className={tab === "sections" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("sections")}>Sections</button>
          <button className={tab === "style" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("style")}>Style</button>
          <div className="flex-1" />
          <button className="btn-primary" onClick={save} disabled={saving || !dirty}>
            {saving ? "Saving…" : dirty ? "Save & use" : "Saved"}
          </button>
        </div>
        {error && <div className="text-sm text-no break-words">{error}</div>}

        <div className="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-2">
          {tab === "style" ? (
            <StyleTab style={layout.style} onChange={(s) => patch({ style: s })} />
          ) : (
            <>
              <p className="text-xs text-muted">
                Tick a section to include it. Experience, Skills and Projects are written by the AI for each job;
                sections you add here are your own text, used as-is.
              </p>
              {layout.section_order.map((id, i) => {
                const custom = customById[id];
                const isStatic = custom?.kind === "static";
                const name = custom?.name ?? CORE_NAMES[id] ?? id;
                return (
                  <div key={id} className={`card p-3 ${hidden.has(id) ? "opacity-60" : ""}`}>
                    <div className="flex items-center gap-2">
                      <input type="checkbox" checked={!hidden.has(id)} onChange={() => toggle(id)} title="Show in resume" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-fg truncate">{name}</div>
                        <div className="text-[11px] text-muted">{isStatic ? "Your text" : custom ? "AI-written" : "AI-written (core)"}</div>
                      </div>
                      <button className="btn-ghost px-2" disabled={i === 0} onClick={() => move(id, -1)} title="Move up">↑</button>
                      <button className="btn-ghost px-2" disabled={i === layout.section_order.length - 1} onClick={() => move(id, 1)} title="Move down">↓</button>
                      {isStatic && (
                        <button className="btn-secondary text-xs px-2 py-1" onClick={() => setExpanded(expanded === id ? null : id)}>
                          {expanded === id ? "Close" : "Edit"}
                        </button>
                      )}
                    </div>
                    {isStatic && expanded === id && (
                      <StaticEditor section={custom} onChange={(p) => updateSection(id, p)} onDelete={() => removeSection(id)} />
                    )}
                  </div>
                );
              })}
              <AddSectionMenu onPick={addSection} />
            </>
          )}
        </div>
      </div>

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="text-sm text-muted mb-2 flex items-center gap-2">
          Live preview {compiling && <span className="text-xs">· updating…</span>}
          <span className="text-xs">(Experience, Skills and Projects show sample text; the AI fills them per job)</span>
        </div>
        {previewError ? (
          <div className="card flex-1 flex flex-col items-center justify-center gap-2 p-8 text-center">
            <div className="text-sm text-fg font-medium">Preview could not be compiled</div>
            <div className="text-xs text-no font-mono max-w-xl break-words whitespace-pre-wrap">{previewError}</div>
          </div>
        ) : previewUrl ? (
          <embed src={previewUrl} type="application/pdf" className="w-full h-full rounded-md border border-border bg-white" />
        ) : (
          <div className="card flex-1 flex items-center justify-center text-sm text-muted">Building preview…</div>
        )}
      </div>
    </div>
  );
}

function AddSectionMenu({ onPick }: { onPick: (p: (typeof PRESETS)[number]) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      <button className="btn-secondary w-fit" onClick={() => setOpen(!open)}>+ Add section</button>
      {open && (
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button key={p.name} className="btn-ghost border border-border text-xs px-2.5 py-1"
                    onClick={() => { onPick(p); setOpen(false); }}>
              {p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---- editing a section you wrote -------------------------------------------

function StaticEditor({
  section, onChange, onDelete,
}: {
  section: CustomSection;
  onChange: (p: Partial<CustomSection>) => void;
  onDelete: () => void;
}) {
  const layout = section.layout ?? "bullets";
  const bullets = section.bullets ?? [];
  const entries = section.entries ?? [];

  const setEntry = (i: number, p: Partial<StaticEntry>) =>
    onChange({ entries: entries.map((e, k) => (k === i ? { ...e, ...p } : e)) });

  return (
    <div className="flex flex-col gap-3 mt-3 pt-3 border-t border-border">
      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="label">Section title</span>
          <input className="input" value={section.name} onChange={(e) => onChange({ name: e.target.value })} />
        </label>
        <label className="block">
          <span className="label">Layout</span>
          <select className="input" value={layout} onChange={(e) => onChange({ layout: e.target.value as CustomSection["layout"] })}>
            <option value="bullets">Bullet points</option>
            <option value="text">Plain lines (no bullets)</option>
            <option value="entries">Entries (title, org, date, place)</option>
          </select>
        </label>
      </div>
      <p className="text-[11px] text-muted">
        In any text box: <b>B</b> bolds the selection, <i>I</i> italicises it, <b>Link</b> turns it into a link
        (replace <code>https://</code> with your URL).
      </p>

      {layout === "entries" ? (
        <>
          {entries.map((en, i) => (
            <div key={i} className="rounded-md border border-border p-2.5 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted">Entry {i + 1}</span>
                <button className="text-xs text-no hover:underline" onClick={() => onChange({ entries: entries.filter((_, k) => k !== i) })}>Remove</button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <LabeledText label="Title" value={en.title} onChange={(v) => setEntry(i, { title: v })} />
                <LabeledText label="Organization / subtitle" value={en.subtitle} onChange={(v) => setEntry(i, { subtitle: v })} />
                <LabeledText label="Date" value={en.date} onChange={(v) => setEntry(i, { date: v })} placeholder="2023 -- 2024" />
                <LabeledText label="Location" value={en.location} onChange={(v) => setEntry(i, { location: v })} />
              </div>
              <LabeledText label="Link on the title (optional)" value={en.link} onChange={(v) => setEntry(i, { link: v })} placeholder="https://" />
              <PointList label="Points" items={en.bullets} onChange={(b) => setEntry(i, { bullets: b })} />
            </div>
          ))}
          <button className="btn-secondary w-fit text-xs" onClick={() => onChange({ entries: [...entries, emptyEntry()] })}>+ Add entry</button>
        </>
      ) : (
        <PointList label={layout === "text" ? "Lines" : "Points"} items={bullets} onChange={(b) => onChange({ bullets: b })} />
      )}

      <button className="text-xs text-no hover:underline w-fit" onClick={onDelete}>Delete this section</button>
    </div>
  );
}

function LabeledText({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input className="input" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function PointList({ label, items, onChange }: { label: string; items: string[]; onChange: (items: string[]) => void }) {
  const count = items.length;
  function setCount(n: number) {
    n = Math.max(0, Math.min(15, n));
    onChange(n >= count ? [...items, ...Array(n - count).fill("")] : items.slice(0, n));
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="label mb-0">{label}</span>
        <button className="btn-ghost border border-border px-2 text-xs" onClick={() => setCount(count - 1)} disabled={count === 0}>−</button>
        <span className="text-xs text-fg w-4 text-center">{count}</span>
        <button className="btn-ghost border border-border px-2 text-xs" onClick={() => setCount(count + 1)}>+</button>
      </div>
      {items.map((b, i) => (
        <RichInput key={i} value={b} onChange={(v) => onChange(items.map((x, k) => (k === i ? v : x)))}
                   onRemove={() => onChange(items.filter((_, k) => k !== i))} />
      ))}
    </div>
  );
}

// A text box with Bold / Italic / Link buttons that wrap the selection in the markers the
// renderer understands: **bold**, *italic*, [text](url).
function RichInput({ value, onChange, onRemove }: { value: string; onChange: (v: string) => void; onRemove: () => void }) {
  const ref = useRef<HTMLTextAreaElement>(null);

  function wrap(before: string, after: string, selectAfter?: string) {
    const el = ref.current;
    if (!el) return;
    const { selectionStart: a, selectionEnd: b } = el;
    const picked = value.slice(a, b) || "text";
    onChange(value.slice(0, a) + before + picked + after + value.slice(b));
    requestAnimationFrame(() => {
      el.focus();
      if (selectAfter) {
        const start = a + before.length + picked.length + after.indexOf(selectAfter);
        el.setSelectionRange(start, start + selectAfter.length);
      } else {
        el.setSelectionRange(a + before.length, a + before.length + picked.length);
      }
    });
  }

  return (
    <div className="flex gap-1.5 items-start">
      <textarea ref={ref} className="input flex-1 resize-none text-sm" rows={2} value={value} onChange={(e) => onChange(e.target.value)} />
      <div className="flex flex-col gap-1">
        <div className="flex gap-1">
          <button className="btn-ghost border border-border px-2 text-xs font-bold" title="Bold" onClick={() => wrap("**", "**")}>B</button>
          <button className="btn-ghost border border-border px-2 text-xs italic" title="Italic" onClick={() => wrap("*", "*")}>I</button>
          <button className="btn-ghost border border-border px-2 text-xs" title="Link" onClick={() => wrap("[", "](https://)", "https://")}>Link</button>
        </div>
        <button className="text-[11px] text-no hover:underline self-end" onClick={onRemove}>remove</button>
      </div>
    </div>
  );
}

// ---- style controls --------------------------------------------------------

function StyleTab({ style, onChange }: { style: LayoutStyle; onChange: (s: LayoutStyle) => void }) {
  const set = <K extends keyof LayoutStyle>(k: K, v: LayoutStyle[K]) => onChange({ ...style, [k]: v });
  return (
    <div className="flex flex-col gap-4">
      <Choice label="Font" value={style.font} onChange={(v) => set("font", v)}
              options={[["computer-modern", "Classic serif"], ["helvetica", "Sans (Helvetica)"], ["times", "Times"], ["palatino", "Palatino"]]} />
      <Choice label="Text size" value={String(style.font_size)} onChange={(v) => set("font_size", Number(v) as LayoutStyle["font_size"])}
              options={[["10", "10 pt"], ["11", "11 pt"], ["12", "12 pt"]]} />
      <Choice label="Page margins" value={style.margin} onChange={(v) => set("margin", v)}
              options={[["narrow", "Narrow"], ["normal", "Normal"], ["wide", "Wide"]]} />
      <Choice label="Spacing" value={style.density} onChange={(v) => set("density", v)}
              options={[["compact", "Compact"], ["normal", "Normal"], ["relaxed", "Relaxed"]]} />
      <Choice label="Section headings" value={style.heading_case} onChange={(v) => set("heading_case", v)}
              options={[["smallcaps", "Small caps"], ["caps", "ALL CAPS"], ["normal", "Bold"]]} />
      <Choice label="Heading line" value={style.heading_style} onChange={(v) => set("heading_style", v)}
              options={[["rule", "Thin line"], ["thick", "Thick line"], ["none", "No line"]]} />
      <label className="block">
        <span className="label">Accent color (headings and lines)</span>
        <div className="flex items-center gap-2">
          <input type="color" value={style.accent} onChange={(e) => set("accent", e.target.value)}
                 className="h-9 w-12 rounded border border-border bg-transparent cursor-pointer" />
          <input className="input w-28 font-mono text-xs" value={style.accent}
                 onChange={(e) => /^#[0-9a-fA-F]{0,6}$/.test(e.target.value) && set("accent", e.target.value)} />
          {["#000000", "#1f4e79", "#2f6f4f", "#8b1e2d", "#5b3a8c"].map((c) => (
            <button key={c} className="h-6 w-6 rounded-full border border-border" style={{ background: c }} onClick={() => set("accent", c)} title={c} />
          ))}
        </div>
      </label>
      <Choice label="Name and contact" value={style.header_align} onChange={(v) => set("header_align", v)}
              options={[["center", "Centered"], ["left", "Left"]]} />
      <Choice label="Bullet symbol" value={style.bullet} onChange={(v) => set("bullet", v)}
              options={[["bullet", "•"], ["dash", "–"], ["circle", "○"], ["triangle", "▷"]]} />
    </div>
  );
}

function Choice<T extends string>({ label, value, options, onChange }: {
  label: string; value: string; options: [T, string][]; onChange: (v: T) => void;
}) {
  return (
    <div>
      <span className="label">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([v, text]) => (
          <button key={v} onClick={() => onChange(v)}
                  className={`rounded-full px-3 py-1 text-sm border transition-colors ${
                    value === v ? "bg-accent-soft text-accent border-accent font-medium" : "border-border text-fg-soft hover:bg-subtle"}`}>
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
