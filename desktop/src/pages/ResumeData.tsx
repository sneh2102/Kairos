import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Config, CustomSection, ExperienceRole, GithubRepo } from "../lib/types";

type Tab = "profile" | "resume" | "projects" | "experience" | "custom-sections" | "section-order";

const BLANK_ROLE: ExperienceRole = {
  title: "",
  company: "",
  dates: "",
  domain: "",
  total_bullets: 4,
  real_bullets: 2,
  fabricated_bullets: 2,
};

export default function ResumeData() {
  const [tab, setTab] = useState<Tab>("profile");
  const [config, setConfig] = useState<Config | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [projectsText, setProjectsText] = useState("");
  const [roles, setRoles] = useState<ExperienceRole[]>([]);
  const [customSections, setCustomSections] = useState<CustomSection[]>([]);
  const [sectionOrder, setSectionOrder] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    api.getResumeData().then((d) => {
      setResumeText(d.resume_text);
      setProjectsText(d.projects_text);
      setRoles(d.experience_roles);
      setCustomSections(d.custom_sections);
      setSectionOrder(d.section_order);
    });
    api.getConfig().then(setConfig);
  }, []);

  async function save() {
    setSaving(true);
    try {
      await Promise.all([
        api.putResumeData({
          resume_text: resumeText,
          projects_text: projectsText,
          experience_roles: roles,
          custom_sections: customSections,
          section_order: sectionOrder,
        }),
        ...(config ? [api.putConfig(config)] : []),
      ]);
      setSavedAt(Date.now());
    } finally {
      setSaving(false);
    }
  }

  function updateRole(i: number, patch: Partial<ExperienceRole>) {
    setRoles((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function addRole() {
    setRoles((prev) => [...prev, { ...BLANK_ROLE }]);
  }

  function removeRole(i: number) {
    setRoles((prev) => prev.filter((_, idx) => idx !== i));
  }

  function moveRole(i: number, dir: -1 | 1) {
    setRoles((prev) => {
      const target = i + dir;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[target]] = [next[target], next[i]];
      return next;
    });
  }

  // section order always includes fixed sections + every custom section id, in some order
  const allSectionIds = ["education", "skills", "experience", "projects", ...customSections.map((c) => c.id)];
  const orderedIds = [...sectionOrder.filter((id) => allSectionIds.includes(id)), ...allSectionIds.filter((id) => !sectionOrder.includes(id))];

  function moveSection(index: number, dir: -1 | 1) {
    const next = [...orderedIds];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setSectionOrder(next);
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-fg">Resume & profile</h1>
          <p className="text-sm text-muted">Your details, and the source material the Writer Agents draw from.</p>
        </div>
        <div className="flex items-center gap-3">
          {savedAt && <span className="text-xs text-muted">Saved</span>}
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save all"}
          </button>
        </div>
      </div>

      <div className="flex border-b border-border flex-wrap">
        <TabButton active={tab === "profile"} onClick={() => setTab("profile")} label="Profile" />
        <TabButton active={tab === "resume"} onClick={() => setTab("resume")} label="Resume text" />
        <TabButton active={tab === "projects"} onClick={() => setTab("projects")} label="Projects" />
        <TabButton active={tab === "experience"} onClick={() => setTab("experience")} label="Work experience" />
        <TabButton active={tab === "custom-sections"} onClick={() => setTab("custom-sections")} label="Custom sections" />
        <TabButton active={tab === "section-order"} onClick={() => setTab("section-order")} label="Section order" />
      </div>

      {tab === "profile" && (
        config ? (
          <ProfileFields config={config} setConfig={setConfig} />
        ) : (
          <div className="text-sm text-muted">Loading…</div>
        )
      )}

      {tab === "resume" && (
        <textarea
          className="input flex-1 font-mono text-xs resize-none"
          style={{ minHeight: "60vh" }}
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
        />
      )}

      {tab === "projects" && (
        <div className="flex flex-col gap-4">
          <GithubImport onAppend={(entry) => setProjectsText((prev) => `${prev.trim()}\n\n${entry}\n`)} />
          <textarea
            className="input flex-1 font-mono text-xs resize-none"
            style={{ minHeight: "50vh" }}
            value={projectsText}
            onChange={(e) => setProjectsText(e.target.value)}
          />
        </div>
      )}

      {tab === "experience" && (
        <div className="flex flex-col gap-3 max-w-3xl">
          <p className="text-xs text-muted">
            One entry per role, in the order they should appear on the resume. "Fabricated bullets" are honest
            embellishments the Experience Writer is allowed to add on top of your real bullets — set to 0 if you
            don't want any.
          </p>
          {roles.length === 0 && (
            <div className="card p-4 text-sm text-muted">No work experience yet — add your first role below.</div>
          )}
          {roles.map((r, i) => (
            <div key={i} className="card p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-fg">
                  Role {i + 1}
                  {r.title || r.company ? ` — ${[r.title, r.company].filter(Boolean).join(" @ ")}` : ""}
                </span>
                <div className="flex items-center gap-1">
                  <button className="btn-ghost px-2 py-1" onClick={() => moveRole(i, -1)} disabled={i === 0} title="Move up">
                    ▲
                  </button>
                  <button
                    className="btn-ghost px-2 py-1"
                    onClick={() => moveRole(i, 1)}
                    disabled={i === roles.length - 1}
                    title="Move down"
                  >
                    ▼
                  </button>
                  <button className="btn-ghost px-2 py-1 text-bad hover:text-bad" onClick={() => removeRole(i)}>
                    Delete
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <LabeledInput label="Title" value={r.title} onChange={(v) => updateRole(i, { title: v })} />
                <LabeledInput label="Company" value={r.company} onChange={(v) => updateRole(i, { company: v })} />
                <LabeledInput label="Dates" value={r.dates} onChange={(v) => updateRole(i, { dates: v })} />
                <LabeledInput label="Domain" value={r.domain} onChange={(v) => updateRole(i, { domain: v })} />
                <LabeledNumber label="Total bullets" value={r.total_bullets} onChange={(v) => updateRole(i, { total_bullets: v })} />
                <LabeledNumber label="Real bullets" value={r.real_bullets} onChange={(v) => updateRole(i, { real_bullets: v })} />
                <LabeledNumber label="Fabricated bullets" value={r.fabricated_bullets} onChange={(v) => updateRole(i, { fabricated_bullets: v })} />
              </div>
            </div>
          ))}
          <button className="btn-secondary w-fit" onClick={addRole}>
            + Add role
          </button>
        </div>
      )}

      {tab === "custom-sections" && (
        <CustomSectionsEditor sections={customSections} setSections={setCustomSections} />
      )}

      {tab === "section-order" && (
        <div className="flex flex-col gap-2 max-w-md">
          <p className="text-xs text-muted mb-1">Order the resume sections appear in on the compiled resume.</p>
          {orderedIds.map((id, i) => (
            <div key={id} className="card p-3 flex items-center justify-between">
              <span className="text-sm text-fg capitalize">{id.replace(/_/g, " ")}</span>
              <div className="flex gap-1">
                <button className="btn-secondary px-2 py-1" onClick={() => moveSection(i, -1)} disabled={i === 0}>
                  ▲
                </button>
                <button
                  className="btn-secondary px-2 py-1"
                  onClick={() => moveSection(i, 1)}
                  disabled={i === orderedIds.length - 1}
                >
                  ▼
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProfileFields({ config, setConfig }: { config: Config; setConfig: (c: Config) => void }) {
  const p = config.profile;
  const set = (patch: Partial<Config["profile"]>) => setConfig({ ...config, profile: { ...p, ...patch } });
  return (
    <div className="grid grid-cols-2 gap-3 max-w-3xl">
      <LabeledInput label="Full name" value={p.full_name} onChange={(v) => set({ full_name: v })} />
      <LabeledInput label="Phone" value={p.phone} onChange={(v) => set({ phone: v })} />
      <LabeledInput label="Email" value={p.email} onChange={(v) => set({ email: v })} />
      <LabeledInput label="LinkedIn" value={p.linkedin} onChange={(v) => set({ linkedin: v })} />
      <LabeledInput label="GitHub" value={p.github} onChange={(v) => set({ github: v })} />
      <LabeledInput label="Location" value={p.location} onChange={(v) => set({ location: v })} />
      <LabeledInput label="Years of experience" value={p.experience_yrs} onChange={(v) => set({ experience_yrs: v })} />
      <label className="flex items-center gap-2 text-sm text-fg-soft mt-5">
        <input type="checkbox" checked={p.include_links} onChange={(e) => set({ include_links: e.target.checked })} />
        Show LinkedIn/GitHub links on resume
      </label>
      <div className="col-span-2">
        <LabeledTextarea label="Core stack" value={p.core_stack} onChange={(v) => set({ core_stack: v })} rows={2} />
      </div>
      <div className="col-span-2">
        <LabeledTextarea label="Target job titles" value={p.job_titles} onChange={(v) => set({ job_titles: v })} rows={2} />
      </div>
      <div className="col-span-2">
        <LabeledTextarea label="Not a fit for" value={p.not_fit_for} onChange={(v) => set({ not_fit_for: v })} rows={2} />
      </div>
    </div>
  );
}

function CustomSectionsEditor({
  sections,
  setSections,
}: {
  sections: CustomSection[];
  setSections: (s: CustomSection[]) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  function addSection() {
    const id = `section_${Date.now()}`;
    const fresh: CustomSection = {
      id,
      name: "New Section",
      system_prompt:
        "You are an expert resume writer. Output ONLY raw LaTeX — no backticks, no explanation.\n\n" +
        "OUTPUT FORMAT CONTRACT:\n\\section{New Section}\n  \\resumeSubHeadingListStart\n    \\resumeItem{content}\n  \\resumeSubHeadingListEnd\n\n" +
        "ABSOLUTE RULES:\n- NO \\documentclass, NO \\usepackage, NO \\begin{document}, NO \\end{document}.",
      user_prompt:
        "Write this section for {full_name} applying for {title} at {company}.\n\nJOB DESCRIPTION:\n{description}\n\n" +
        "CANDIDATE RESUME:\n{existing_resume}\n\nATS FEEDBACK:\n{ats_feedback}",
    };
    setSections([...sections, fresh]);
    setExpanded(id);
  }

  function update(id: string, patch: Partial<CustomSection>) {
    setSections(sections.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }

  function remove(id: string) {
    setSections(sections.filter((s) => s.id !== id));
  }

  return (
    <div className="flex flex-col gap-3 max-w-3xl">
      <p className="text-xs text-muted">
        Sections beyond Skills/Experience/Projects — e.g. Summary, Achievements. Built once per job (not part of the
        ATS fix loop). Use <code>{"{full_name}"}</code>, <code>{"{title}"}</code>, <code>{"{company}"}</code>,{" "}
        <code>{"{description}"}</code>, <code>{"{existing_resume}"}</code>, <code>{"{ats_feedback}"}</code> in the
        user prompt.
      </p>
      {sections.map((s) => (
        <div key={s.id} className="card p-4">
          <div className="flex items-center justify-between">
            <button className="text-sm font-medium text-fg" onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
              {expanded === s.id ? "▾" : "▸"} {s.name} <span className="text-muted text-xs">({s.id})</span>
            </button>
            <button className="text-xs text-no hover:underline" onClick={() => remove(s.id)}>
              Delete
            </button>
          </div>
          {expanded === s.id && (
            <div className="flex flex-col gap-3 mt-3">
              <LabeledInput label="Display name" value={s.name} onChange={(v) => update(s.id, { name: v })} />
              <div>
                <span className="label">System prompt (output format contract)</span>
                <textarea
                  className="input font-mono text-xs resize-none"
                  rows={8}
                  value={s.system_prompt}
                  onChange={(e) => update(s.id, { system_prompt: e.target.value })}
                />
              </div>
              <div>
                <span className="label">User prompt</span>
                <textarea
                  className="input font-mono text-xs resize-none"
                  rows={6}
                  value={s.user_prompt}
                  onChange={(e) => update(s.id, { user_prompt: e.target.value })}
                />
              </div>
            </div>
          )}
        </div>
      ))}
      <button className="btn-secondary w-fit" onClick={addSection}>
        + Add custom section
      </button>
    </div>
  );
}

function GithubImport({ onAppend }: { onAppend: (entry: string) => void }) {
  const [username, setUsername] = useState("");
  const [repos, setRepos] = useState<GithubRepo[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function listRepos() {
    if (!username.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.githubRepos(username.trim());
      setRepos(result.filter((r) => !r.is_fork));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function generate(repo: GithubRepo) {
    setGenerating(repo.url);
    setError(null);
    try {
      const { entry } = await api.githubGenerateEntry(repo.url);
      onAppend(entry);
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(null);
    }
  }

  return (
    <div className="card p-4">
      <div className="text-sm font-medium text-fg mb-2">Import from GitHub</div>
      <div className="flex gap-2 mb-2">
        <input
          className="input"
          placeholder="GitHub username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && listRepos()}
        />
        <button className="btn-secondary shrink-0" onClick={listRepos} disabled={loading}>
          {loading ? "Loading…" : "List repos"}
        </button>
      </div>
      {error && <div className="text-xs text-no mb-2">{error}</div>}
      {repos.length > 0 && (
        <div className="flex flex-col gap-1.5 max-h-64 overflow-y-auto">
          {repos.map((r) => (
            <div key={r.url} className="flex items-center justify-between text-sm bg-track rounded px-2.5 py-1.5">
              <div className="min-w-0">
                <div className="text-fg truncate">{r.name}</div>
                <div className="text-xs text-muted truncate">{r.description || r.language}</div>
              </div>
              <button
                className="btn-secondary shrink-0 text-xs py-1"
                onClick={() => generate(r)}
                disabled={generating === r.url}
              >
                {generating === r.url ? "Generating…" : "Generate & append"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TabButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm border-b-2 -mb-px ${
        active ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg-soft"
      }`}
    >
      {label}
    </button>
  );
}

function LabeledInput({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <span className="label">{label}</span>
      <input className="input" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function LabeledNumber({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <span className="label">{label}</span>
      <input type="number" className="input" value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function LabeledTextarea({
  label,
  value,
  onChange,
  rows = 3,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <div>
      <span className="label">{label}</span>
      <textarea className="input resize-none" rows={rows} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
