import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api } from "../lib/api";
import type { Config, SpeechSettings, SpeechStatus } from "../lib/types";
import { useSpeaker } from "../lib/voice";

type Tab = "model" | "api-keys" | "prompts" | "scheduler" | "interview" | "desktop";

export default function Settings() {
  const [config, setConfig] = useState<Config | null>(null);
  const [tab, setTab] = useState<Tab>("model");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    api.getConfig().then(async (c) => {
      // launchOnStartup is OS state, not just config — read the real value
      // (e.g. the user could've removed it from Startup Apps directly) so the
      // checkbox never lies about what will actually happen on next boot.
      const actual = await window.desktop?.getLaunchOnStartup();
      if (actual !== undefined) {
        c.desktop = { runInBackground: false, ...c.desktop, launchOnStartup: actual };
      }
      setConfig(c);
    });
  }, []);

  async function save() {
    if (!config) return;
    setSaving(true);
    setSaveError(null);
    try {
      const token = config.github?.token?.trim();
      if (token) {
        const r = await api.validateGithubToken(token);
        if (!r.valid) {
          setSaveError(`GitHub token failed validation (${r.error ?? "invalid"}) — fix it on the Model tab before saving.`);
          return;
        }
      }
      // api_keys lives in this same config.json but is owned by the API Keys
      // tab's own save flow (/api/ollama-keys) — `config` here still holds
      // whatever was in it when Settings first loaded, so sending it back
      // would clobber a key just added on that tab with the stale snapshot.
      const payload = { ...config };
      delete payload.api_keys;
      await api.putConfig(payload);
      if (config.desktop) await window.desktop?.setLaunchOnStartup(config.desktop.launchOnStartup);
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

      {saveError && <div className="text-sm text-no">{saveError}</div>}

      <div className="flex border-b border-border">
        {(["model", "api-keys", "prompts", "scheduler", "interview", "desktop"] as Tab[]).map((t) => (
          <TabButton
            key={t}
            active={tab === t}
            onClick={() => setTab(t)}
            label={t === "api-keys" ? "API keys" : t}
          />
        ))}
      </div>

      {tab === "model" && <ModelTab config={config} setConfig={setConfig} />}
      {tab === "api-keys" && <ApiKeysTab />}
      {tab === "prompts" && <PromptsTab config={config} setConfig={setConfig} />}
      {tab === "scheduler" && <SchedulerTab config={config} setConfig={setConfig} />}
      {tab === "interview" && <InterviewTab config={config} setConfig={setConfig} />}
      {tab === "desktop" && <DesktopTab config={config} setConfig={setConfig} />}
    </div>
  );
}

type Setter = Dispatch<SetStateAction<Config | null>>;

const TASKS: [string, string][] = [
  ["screener", "Job screener"],
  ["projects", "Projects"],
  ["experience", "Experience"],
  ["skills", "Skills"],
  ["summary", "Summary & custom sections"],
  ["cover_letter", "Cover letter"],
  ["ats", "ATS checker, optimizer & LaTeX fixer"],
  ["interview", "Mock interviewer"],
];

function ModelTab({ config, setConfig }: { config: Config; setConfig: Setter }) {
  const m = config.model;
  const set = (patch: Partial<Config["model"]>) => setConfig({ ...config, model: { ...m, ...patch } });
  const github = config.github ?? { token: "" };
  const [check, setCheck] = useState<KeyCheck>({ state: "idle" });
  const [geminiCheck, setGeminiCheck] = useState<KeyCheck>({ state: "idle" });
  const provider = m.provider ?? "ollama";
  const used = TASKS.map(([id]) => (m.task_providers?.[id] ?? "default") === "default" ? provider : m.task_providers![id]);
  const usesGemini = used.includes("gemini");
  const usesOllama = used.includes("ollama");

  async function verifyGeminiKey() {
    setGeminiCheck({ state: "checking" });
    try {
      const keys = (m.gemini_api_keys ?? []).filter(Boolean);
      const rs = await Promise.all(keys.map((k) => api.validateGeminiKey(k)));
      const bad = rs.findIndex((r) => !r.valid);
      setGeminiCheck(bad < 0 ? { state: "valid" } : { state: "invalid", error: `key ${bad + 1}: ${rs[bad].error ?? "invalid"}` });
    } catch (e) {
      setGeminiCheck({ state: "invalid", error: String(e) });
    }
  }

  async function verifyGithubToken() {
    const value = github.token.trim();
    if (!value) return;
    setCheck({ state: "checking" });
    try {
      const r = await api.validateGithubToken(value);
      setCheck({ state: r.valid ? "valid" : "invalid", error: r.error ?? undefined });
    } catch (e) {
      setCheck({ state: "invalid", error: String(e) });
    }
  }

  return (
    <div className="grid grid-cols-2 gap-3 max-w-3xl">
      <div className="col-span-2">
        <span className="label">AI provider</span>
        <select className="input" value={provider} onChange={(e) => set({ provider: e.target.value as "ollama" | "gemini" })}>
          <option value="ollama">Ollama (cloud)</option>
          <option value="gemini">Google Gemini (AI Studio)</option>
        </select>
      </div>
      {usesGemini && (
        <>
          <div className="col-span-2">
            <span className="label">Gemini model (used for screening, resume and ATS). Clear the box to see all options.</span>
            <input
              className="input"
              list="gemini-models"
              value={m.gemini_model ?? "gemini-3.1-flash-lite"}
              onChange={(e) => set({ gemini_model: e.target.value })}
            />
            <datalist id="gemini-models">
              <option value="gemini-3.8-flash" />
              <option value="gemini-3.7-flash" />
              <option value="gemini-3.6-flash" />
              <option value="gemini-3.5-flash" />
              <option value="gemini-3.5-flash-lite" />
              <option value="gemini-3-flash-preview" />
              <option value="gemini-3.1-flash-lite" />
              <option value="gemini-flash-latest" />
              <option value="gemini-flash-lite-latest" />
              <option value="gemma-4-26b-a4b-it" />
              <option value="gemma-4-31b-it" />
            </datalist>
          </div>
          <div className="col-span-2 flex flex-col gap-1">
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <span className="label">Gemini API keys, one per line (rotated on rate limits)</span>
                <textarea
                  className="input font-mono text-xs resize-none"
                  rows={3}
                  value={(m.gemini_api_keys ?? []).join("\n")}
                  onChange={(e) => {
                    set({ gemini_api_keys: e.target.value.split("\n").map((k) => k.trim()) });
                    setGeminiCheck({ state: "idle" });
                  }}
                />
              </div>
              <button
                className="btn-secondary shrink-0"
                onClick={verifyGeminiKey}
                disabled={geminiCheck.state === "checking" || !(m.gemini_api_keys ?? []).some(Boolean)}
              >
                {geminiCheck.state === "checking" ? "Checking…" : "Verify"}
              </button>
            </div>
            {geminiCheck.state === "valid" && <span className="text-xs text-yes">✓ Valid</span>}
            {geminiCheck.state === "invalid" && <span className="text-xs text-no">✗ {geminiCheck.error ?? "Invalid key"}</span>}
          </div>
        </>
      )}
      {usesOllama && (
        <>
          <LabeledInput label="Screening model" value={m.scraping} onChange={(v) => set({ scraping: v })} />
          <LabeledInput label="Resume/ATS model" value={m.pipeline} onChange={(v) => set({ pipeline: v })} />
          <LabeledNumber label="Context window" value={m.num_ctx} onChange={(v) => set({ num_ctx: v })} />
        </>
      )}
      <div className="col-span-2">
        <span className="label">Provider per task (Default = the provider selected above)</span>
        <div className="grid grid-cols-2 gap-x-3 gap-y-2">
          {TASKS.map(([id, label]) => (
            <label key={id} className="flex items-center justify-between gap-2 text-sm text-fg-soft">
              {label}
              <select
                className="input w-40"
                value={m.task_providers?.[id] ?? "default"}
                onChange={(e) =>
                  set({ task_providers: { ...m.task_providers, [id]: e.target.value as "default" | "ollama" | "gemini" } })
                }
              >
                <option value="default">Default</option>
                <option value="ollama">Ollama</option>
                <option value="gemini">Gemini</option>
              </select>
            </label>
          ))}
        </div>
      </div>
      <LabeledNumber label="Temperature (x100)" value={Math.round(m.temperature * 100)} onChange={(v) => set({ temperature: v / 100 })} />
      {usesOllama && (
        <p className="col-span-2 text-xs text-muted">
          Ollama API keys live on the <strong className="text-fg-soft">API keys</strong> tab.
        </p>
      )}
      <div className="col-span-2 flex flex-col gap-1">
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <LabeledInput
              label="GitHub token (optional — raises the API rate limit for project import)"
              value={github.token}
              onChange={(v) => {
                setConfig({ ...config, github: { token: v } });
                setCheck({ state: "idle" });
              }}
            />
          </div>
          <button
            className="btn-secondary shrink-0"
            onClick={verifyGithubToken}
            disabled={check.state === "checking" || !github.token.trim()}
          >
            {check.state === "checking" ? "Checking…" : "Verify"}
          </button>
        </div>
        {check.state === "valid" && <span className="text-xs text-yes">✓ Valid</span>}
        {check.state === "invalid" && <span className="text-xs text-no">✗ {check.error ?? "Invalid token"}</span>}
      </div>
    </div>
  );
}

type KeyCheck = { state: "idle" | "checking" | "valid" | "invalid"; error?: string };

function ApiKeysTab() {
  const [keys, setKeys] = useState<string[]>([]);
  const [checks, setChecks] = useState<Record<number, KeyCheck>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getOllamaKeys().then((r) => setKeys(r.keys)).finally(() => setLoading(false));
  }, []);

  function update(i: number, value: string) {
    setKeys((prev) => prev.map((k, idx) => (idx === i ? value : k)));
    setChecks((prev) => ({ ...prev, [i]: { state: "idle" } }));
  }

  function remove(i: number) {
    setKeys((prev) => prev.filter((_, idx) => idx !== i));
    setChecks((prev) => {
      const next: Record<number, KeyCheck> = {};
      Object.entries(prev).forEach(([idx, v]) => {
        const n = Number(idx);
        if (n < i) next[n] = v;
        else if (n > i) next[n - 1] = v;
      });
      return next;
    });
  }

  async function verify(i: number): Promise<boolean> {
    const value = keys[i].trim();
    if (!value) return true;
    setChecks((prev) => ({ ...prev, [i]: { state: "checking" } }));
    try {
      const r = await api.validateOllamaKey(value);
      setChecks((prev) => ({ ...prev, [i]: { state: r.valid ? "valid" : "invalid", error: r.error ?? undefined } }));
      return r.valid;
    } catch (e) {
      setChecks((prev) => ({ ...prev, [i]: { state: "invalid", error: String(e) } }));
      return false;
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const results = await Promise.all(keys.map((_, i) => verify(i)));
      if (results.some((ok) => !ok)) {
        setError("One or more keys failed validation — fix or remove them before saving.");
        return;
      }
      const cleaned = keys.map((k) => k.trim()).filter(Boolean);
      await api.putOllamaKeys(cleaned);
      setKeys(cleaned);
      setChecks({});
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
        Ollama API keys, tried in order — when one hits its rate limit the pipeline rotates to the next. Verified
        against Ollama before saving. Saved to <code>config.json</code> as <code>api_keys</code>.
      </p>
      {keys.length === 0 && (
        <div className="text-sm text-muted">No keys yet — add at least one to run the scraper or build resumes.</div>
      )}
      {keys.map((k, i) => {
        const check = checks[i] ?? { state: "idle" };
        return (
          <div key={i} className="flex flex-col gap-1">
            <div className="flex gap-2">
              <input className="input flex-1" value={k} onChange={(e) => update(i, e.target.value)} placeholder={`Key ${i + 1}`} />
              <button className="btn-secondary shrink-0" onClick={() => verify(i)} disabled={check.state === "checking" || !k.trim()}>
                {check.state === "checking" ? "Checking…" : "Verify"}
              </button>
              <button className="btn-ghost px-2 py-1 text-bad hover:text-bad" onClick={() => remove(i)}>
                Remove
              </button>
            </div>
            {check.state === "valid" && <span className="text-xs text-yes">✓ Valid</span>}
            {check.state === "invalid" && <span className="text-xs text-no">✗ {check.error ?? "Invalid key"}</span>}
          </div>
        );
      })}
      <div className="flex items-center gap-3">
        <button className="btn-secondary w-fit" onClick={() => setKeys((prev) => [...prev, ""])}>
          + Add key
        </button>
        <button className="btn-primary w-fit" onClick={save} disabled={saving}>
          {saving ? "Verifying & saving…" : "Save keys"}
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

const SPEECH_DEFAULTS: SpeechSettings = {
  stt_engine: "local",
  whisper_model: "small.en",
  whisper_device: "auto",
  groq_api_key: "",
  tts_engine: "kokoro",
  kokoro_voice: "af_heart",
  edge_voice: "en-US-AndrewNeural",
  tts_speed: 1,
};

const WHISPER_MODELS: [string, string][] = [
  ["tiny.en", "tiny.en — ~75 MB, fastest, least accurate"],
  ["base.en", "base.en — ~145 MB"],
  ["small.en", "small.en — ~480 MB, recommended"],
  ["distil-large-v3", "distil-large-v3 — ~1.5 GB, best accuracy for speed (GPU)"],
  ["large-v3-turbo", "large-v3-turbo — ~1.6 GB, most accurate (GPU)"],
];

const EDGE_VOICES = ["en-US-AndrewNeural", "en-US-AvaNeural", "en-US-BrianNeural", "en-US-EmmaNeural", "en-GB-RyanNeural", "en-GB-SoniaNeural", "en-IN-PrabhatNeural", "en-IN-NeerjaNeural"];

function InterviewTab({ config, setConfig }: { config: Config; setConfig: Setter }) {
  const s: SpeechSettings = { ...SPEECH_DEFAULTS, ...config.interview };
  const set = (patch: Partial<SpeechSettings>) => setConfig({ ...config, interview: { ...s, ...patch } });
  const [status, setStatus] = useState<SpeechStatus | null>(null);
  const [voices, setVoices] = useState<string[]>([]);
  const speaker = useSpeaker();

  function refresh() {
    api.speechStatus().then(setStatus).catch(() => {});
    api.speechVoices().then((v) => setVoices(v.kokoro)).catch(() => {});
  }
  useEffect(refresh, []);
  const downloading = status && (status.whisper.download === "downloading" || status.kokoro.download === "downloading");
  useEffect(() => {
    if (!downloading) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [downloading]);

  // status reflects the SAVED model; a just-picked, unsaved size has no status yet
  const whisperStatus = status?.whisper.model === s.whisper_model ? status.whisper : null;
  const sample = "Thanks for joining. Let's start with a quick overview of your background.";

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      <section className="flex flex-col gap-3">
        <div className="text-sm font-semibold text-fg">Speech recognition (your answers)</div>
        <div className="grid grid-cols-2 gap-3">
          <label>
            <span className="label">Engine</span>
            <select className="input" value={s.stt_engine} onChange={(e) => set({ stt_engine: e.target.value as SpeechSettings["stt_engine"] })}>
              <option value="local">Whisper on this PC (offline)</option>
              <option value="groq">Groq Whisper (free online API)</option>
            </select>
          </label>
          <label>
            <span className="label">Run on</span>
            <select
              className="input"
              value={s.whisper_device}
              onChange={(e) => set({ whisper_device: e.target.value as SpeechSettings["whisper_device"] })}
            >
              <option value="auto">Auto (GPU if available)</option>
              <option value="cuda">GPU (CUDA)</option>
              <option value="cpu">CPU</option>
            </select>
          </label>
          <label className="col-span-2">
            <span className="label">Whisper model</span>
            <select className="input" value={s.whisper_model} onChange={(e) => set({ whisper_model: e.target.value })}>
              {WHISPER_MODELS.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="text-xs text-muted flex items-center gap-3">
          {!whisperStatus ? (
            <span>Save to check this model.</span>
          ) : whisperStatus.ready ? (
            <span className="text-yes">
              ✓ Downloaded{whisperStatus.device ? ` · running on ${whisperStatus.device.toUpperCase()}` : ""}
            </span>
          ) : whisperStatus.download === "downloading" ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="spinner" /> Downloading…
            </span>
          ) : (
            <>
              <span>Not downloaded.</span>
              <button className="text-accent hover:underline" onClick={() => api.speechDownload(`whisper:${s.whisper_model}`).then(refresh)}>
                Download now
              </button>
              {whisperStatus.download?.startsWith("error") && <span className="text-no">{whisperStatus.download}</span>}
            </>
          )}
        </div>
        <label>
          <span className="label">Groq API key (optional; also used as a backup when local Whisper fails)</span>
          <input
            className="input font-mono text-xs"
            type="password"
            placeholder="gsk_… — free at console.groq.com"
            value={s.groq_api_key}
            onChange={(e) => set({ groq_api_key: e.target.value.trim() })}
          />
        </label>
      </section>

      <section className="flex flex-col gap-3 border-t border-border pt-5">
        <div className="text-sm font-semibold text-fg">Interviewer voice</div>
        <div className="grid grid-cols-2 gap-3">
          <label>
            <span className="label">Engine</span>
            <select className="input" value={s.tts_engine} onChange={(e) => set({ tts_engine: e.target.value as SpeechSettings["tts_engine"] })}>
              <option value="kokoro">Kokoro on this PC (offline, natural)</option>
              <option value="edge">Microsoft Edge voices (free, online)</option>
              <option value="browser">Built-in system voice</option>
            </select>
          </label>
          {s.tts_engine === "kokoro" && (
            <label>
              <span className="label">Voice</span>
              {voices.length ? (
                <select className="input" value={s.kokoro_voice} onChange={(e) => set({ kokoro_voice: e.target.value })}>
                  {voices.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              ) : status?.kokoro.download === "downloading" ? (
                <div className="input text-muted inline-flex items-center gap-2">
                  <span className="spinner" /> Downloading voice model…
                </div>
              ) : (
                <button className="btn-secondary w-full" onClick={() => api.speechDownload("kokoro").then(refresh)}>
                  Download voice model (~120 MB)
                </button>
              )}
            </label>
          )}
          {s.tts_engine === "edge" && (
            <label>
              <span className="label">Voice</span>
              <select className="input" value={s.edge_voice} onChange={(e) => set({ edge_voice: e.target.value })}>
                {EDGE_VOICES.map((v) => (
                  <option key={v} value={v}>
                    {v.replace("Neural", "")}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="col-span-2">
            <span className="label">Speaking speed: {s.tts_speed.toFixed(2)}×</span>
            <input
              type="range"
              min={0.7}
              max={1.4}
              step={0.05}
              value={s.tts_speed}
              onChange={(e) => set({ tts_speed: Number(e.target.value) })}
              className="w-full accent-[color:var(--accent)]"
            />
          </label>
        </div>
        <div className="flex items-center gap-3">
          <button
            className="btn-secondary !py-1.5"
            onClick={() => (speaker.speaking ? speaker.stop() : speaker.play(() => api.speak(sample, s), sample))}
          >
            {speaker.speaking ? "Stop" : "Preview voice"}
          </button>
          <span className="text-xs text-muted">Previews the settings above, even before you save.</span>
        </div>
      </section>

      <p className="text-xs text-muted border-t border-border pt-4">
        The interviewer's AI follows <strong className="text-fg-soft">Model › Provider per task › Mock interviewer</strong>. Gemini Flash
        gives the fastest replies. Edit its prompt on the AI prompts page.
      </p>
    </div>
  );
}

function DesktopTab({ config, setConfig }: { config: Config; setConfig: Setter }) {
  const d = config.desktop ?? { runInBackground: false, launchOnStartup: false };
  const set = (patch: Partial<{ runInBackground: boolean; launchOnStartup: boolean }>) =>
    setConfig({ ...config, desktop: { ...d, ...patch } });
  return (
    <div className="flex flex-col gap-4 max-w-md">
      <label className="flex items-center gap-2 text-sm text-fg-soft">
        <input
          type="checkbox"
          checked={d.runInBackground}
          onChange={(e) => set({ runInBackground: e.target.checked })}
        />
        Keep running in the background when the window is closed
      </label>
      <p className="text-xs text-muted -mt-2">
        Closing the window minimizes to the system tray instead of quitting, so scraping and other scheduled jobs
        keep running. Use the tray icon's Quit to fully exit.
      </p>
      <label className="flex items-center gap-2 text-sm text-fg-soft">
        <input
          type="checkbox"
          checked={d.launchOnStartup}
          onChange={(e) => set({ launchOnStartup: e.target.checked })}
        />
        Launch Kairos automatically when you log in
      </label>
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

