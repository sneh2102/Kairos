import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api } from "../lib/api";
import type { Config } from "../lib/types";

type Tab = "model" | "api-keys" | "prompts" | "scheduler" | "google-drive";

export default function Settings() {
  const [config, setConfig] = useState<Config | null>(null);
  const [tab, setTab] = useState<Tab>("model");
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
          <h1 className="text-lg font-semibold text-fg">Settings</h1>
          <p className="text-sm text-muted">
            Model, prompts, and the daily scrape schedule. Profile lives on the Resume & profile page; screener
            rules live on their own page.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {savedAt && <span className="text-xs text-muted">Saved</span>}
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>

      <div className="flex border-b border-border">
        {(["model", "api-keys", "prompts", "scheduler", "google-drive"] as Tab[]).map((t) => (
          <TabButton
            key={t}
            active={tab === t}
            onClick={() => setTab(t)}
            label={t === "api-keys" ? "API keys" : t === "google-drive" ? "Google Drive" : t}
          />
        ))}
      </div>

      {tab === "model" && <ModelTab config={config} setConfig={setConfig} />}
      {tab === "api-keys" && <ApiKeysTab />}
      {tab === "prompts" && <PromptsTab config={config} setConfig={setConfig} />}
      {tab === "scheduler" && <SchedulerTab config={config} setConfig={setConfig} />}
      {tab === "google-drive" && <GoogleDriveTab config={config} setConfig={setConfig} save={save} saving={saving} />}
    </div>
  );
}

type Setter = Dispatch<SetStateAction<Config | null>>;

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
        Ollama API keys live on the <strong className="text-fg-soft">API keys</strong> tab.
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

function GoogleDriveTab({
  config,
  setConfig,
  save,
  saving,
}: {
  config: Config;
  setConfig: Setter;
  save: () => void;
  saving: boolean;
}) {
  const g = config.google ?? { client_id: "", client_secret: "" };
  const [status, setStatus] = useState<{ configured: boolean; connected: boolean; email: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function refreshStatus() {
    api.googleStatus().then(setStatus);
  }
  useEffect(refreshStatus, []);

  async function connect() {
    setBusy(true);
    setMessage(null);
    try {
      await api.googleConnect();
      setMessage("A browser window opened to finish signing in — once approved, click \"Refresh status\" below.");
    } catch (e) {
      setMessage(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      await api.googleDisconnect();
      refreshStatus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 max-w-2xl">
      <p className="text-xs text-muted">
        Connects your own Google account so "Upload to Drive" (on a job or applied record) can save the built
        resume/cover-letter PDFs into a "Job Tracker Resumes" folder in your Drive. This is a one-time setup done
        from the desktop app — the connection then works for uploads triggered from mobile too, since both talk to
        this same backend.
      </p>

      <div className="card p-3 text-xs text-muted space-y-1">
        <div className="text-fg-soft font-medium">One-time Google Cloud setup (only if you haven't already):</div>
        <ol className="list-decimal list-inside space-y-0.5">
          <li>Create a project at console.cloud.google.com and enable the "Google Drive API".</li>
          <li>Configure the OAuth consent screen (External, testing mode is fine — add your own email as a test user).</li>
          <li>
            Create an OAuth client ID of type <strong className="text-fg-soft">Desktop app</strong>.
          </li>
          <li>Copy its Client ID and Client secret into the fields below and save.</li>
        </ol>
      </div>

      <LabeledInput label="Client ID" value={g.client_id} onChange={(v) => setConfig({ ...config, google: { ...g, client_id: v } })} />
      <LabeledInput
        label="Client secret"
        value={g.client_secret}
        onChange={(v) => setConfig({ ...config, google: { ...g, client_secret: v } })}
      />
      <button className="btn-secondary w-fit" onClick={save} disabled={saving}>
        {saving ? "Saving…" : "Save credentials"}
      </button>

      <div className="pt-2 border-t border-border flex items-center gap-3">
        {status?.connected ? (
          <>
            <span className="text-sm text-yes">Connected as {status.email}</span>
            <button className="btn-secondary" onClick={disconnect} disabled={busy}>
              Disconnect
            </button>
          </>
        ) : (
          <button className="btn-primary" onClick={connect} disabled={busy || !status?.configured}>
            {busy ? "Opening browser…" : "Connect Google Drive"}
          </button>
        )}
        <button className="btn-ghost text-xs" onClick={refreshStatus}>
          Refresh status
        </button>
      </div>
      {!status?.configured && <p className="text-xs text-muted">Save a Client ID/secret above before connecting.</p>}
      {message && <p className="text-xs text-fg-soft">{message}</p>}
    </div>
  );
}

function ApiKeysTab() {
  const [keys, setKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getOllamaKeys().then((r) => setKeys(r.keys)).finally(() => setLoading(false));
  }, []);

  function update(i: number, value: string) {
    setKeys((prev) => prev.map((k, idx) => (idx === i ? value : k)));
  }

  function remove(i: number) {
    setKeys((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const cleaned = keys.map((k) => k.trim()).filter(Boolean);
      await api.putOllamaKeys(cleaned);
      setKeys(cleaned);
      setSavedAt(Date.now());
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-sm text-muted">Loading…</div>;

  return (
    <div className="flex flex-col gap-3 max-w-2xl">
      <p className="text-xs text-muted">
        Ollama API keys, tried in order — when one hits its rate limit the pipeline rotates to the next. Saved
        to <code>config.json</code> as <code>api_keys</code>.
      </p>
      {keys.length === 0 && (
        <div className="text-sm text-muted">No keys yet — add at least one to run the scraper or build resumes.</div>
      )}
      {keys.map((k, i) => (
        <div key={i} className="flex gap-2">
          <input className="input flex-1" value={k} onChange={(e) => update(i, e.target.value)} placeholder={`Key ${i + 1}`} />
          <button className="btn-ghost px-2 py-1 text-bad hover:text-bad" onClick={() => remove(i)}>
            Remove
          </button>
        </div>
      ))}
      <div className="flex items-center gap-3">
        <button className="btn-secondary w-fit" onClick={() => setKeys((prev) => [...prev, ""])}>
          + Add key
        </button>
        <button className="btn-primary w-fit" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save keys"}
        </button>
        {savedAt && <span className="text-xs text-muted">Saved</span>}
      </div>
      {error && <div className="text-sm text-no">{error}</div>}
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
      <label className="flex items-center gap-2 text-sm text-fg-soft">
        <input type="checkbox" checked={sched.enabled} onChange={(e) => set({ enabled: e.target.checked })} />
        Automatically run the scraper every day
      </label>
      <LabeledInput label="Time (24h, local)" value={sched.time} onChange={(v) => set({ time: v })} />
    </div>
  );
}

function TabButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm border-b-2 -mb-px capitalize ${
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

