import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api } from "../lib/api";
import type { Config } from "../lib/types";

type Tab = "profile" | "model" | "prompts" | "scheduler";

export default function Settings() {
  const [config, setConfig] = useState<Config | null>(null);
  const [tab, setTab] = useState<Tab>("profile");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    api.getConfig().then(setConfig);
  }, []);

  async function save() {
    if (!config) return;
    setSaving(true);
    try {
      await api.putConfig(config);
      setSavedAt(Date.now());
    } finally {
      setSaving(false);
    }
  }

  if (!config) return <div className="text-sm text-muted">Loading…</div>;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Settings</h1>
          <p className="text-sm text-muted">Profile, model, prompts, and the daily scrape schedule. Screener rules live on their own page.</p>
        </div>
        <div className="flex items-center gap-3">
          {savedAt && <span className="text-xs text-muted">Saved</span>}
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>

      <div className="flex border-b border-border">
        {(["profile", "model", "prompts", "scheduler"] as Tab[]).map((t) => (
          <TabButton key={t} active={tab === t} onClick={() => setTab(t)} label={t} />
        ))}
      </div>

      {tab === "profile" && <ProfileTab config={config} setConfig={setConfig} />}
      {tab === "model" && <ModelTab config={config} setConfig={setConfig} />}
      {tab === "prompts" && <PromptsTab config={config} setConfig={setConfig} />}
      {tab === "scheduler" && <SchedulerTab config={config} setConfig={setConfig} />}
    </div>
  );
}

type Setter = Dispatch<SetStateAction<Config | null>>;

function ProfileTab({ config, setConfig }: { config: Config; setConfig: Setter }) {
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
      <label className="flex items-center gap-2 text-sm text-gray-300 mt-5">
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

function ModelTab({ config, setConfig }: { config: Config; setConfig: Setter }) {
  const m = config.model;
  const set = (patch: Partial<Config["model"]>) => setConfig({ ...config, model: { ...m, ...patch } });
  const github = config.github ?? { token: "" };
  return (
    <div className="grid grid-cols-2 gap-3 max-w-3xl">
      <LabeledInput label="Screening model" value={m.scraping} onChange={(v) => set({ scraping: v })} />
      <LabeledInput label="Resume/ATS model" value={m.pipeline} onChange={(v) => set({ pipeline: v })} />
      <LabeledNumber label="Temperature (x100)" value={Math.round(m.temperature * 100)} onChange={(v) => set({ temperature: v / 100 })} />
      <LabeledNumber label="Context window" value={m.num_ctx} onChange={(v) => set({ num_ctx: v })} />
      <p className="col-span-2 text-xs text-muted">
        Ollama API keys live in <code>.env</code> (OLLAMA_API_KEY_1, _2, …) — not editable here for safety.
      </p>
      <div className="col-span-2">
        <LabeledInput
          label="GitHub token (optional — raises the API rate limit for project import)"
          value={github.token}
          onChange={(v) => setConfig({ ...config, github: { token: v } })}
        />
      </div>
    </div>
  );
}

function PromptsTab({ config, setConfig }: { config: Config; setConfig: Setter }) {
  const prompt = config.prompts?.job_screener as string;
  return (
    <div className="flex flex-col gap-2 max-w-3xl">
      <p className="text-xs text-muted">
        The Screener Agent's prompt — the only one still config-driven. The three Writer Agents and ATS Checker use
        fixed prompts in the backend for consistency.
      </p>
      <textarea
        className="input font-mono text-xs resize-none"
        style={{ minHeight: "55vh" }}
        value={prompt}
        onChange={(e) => setConfig({ ...config, prompts: { ...config.prompts, job_screener: e.target.value } })}
      />
    </div>
  );
}

function SchedulerTab({ config, setConfig }: { config: Config; setConfig: Setter }) {
  const sched = config.scheduler ?? { enabled: false, time: "08:00" };
  const set = (patch: Partial<{ enabled: boolean; time: string }>) =>
    setConfig({ ...config, scheduler: { ...sched, ...patch } });
  return (
    <div className="flex flex-col gap-4 max-w-md">
      <label className="flex items-center gap-2 text-sm text-gray-300">
        <input type="checkbox" checked={sched.enabled} onChange={(e) => set({ enabled: e.target.checked })} />
        Automatically run the scraper every day
      </label>
      <LabeledInput label="Time (24h, local)" value={sched.time} onChange={(v) => set({ time: v })} />
      <p className="text-xs text-muted">Checked every 30s while the app is running.</p>
    </div>
  );
}

function TabButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm border-b-2 -mb-px capitalize ${
        active ? "border-accent text-gray-100" : "border-transparent text-muted hover:text-gray-300"
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
