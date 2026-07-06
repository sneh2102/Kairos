import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Config } from "../lib/types";

export default function ScreenerConfig() {
  const [config, setConfig] = useState<Config | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [newCompany, setNewCompany] = useState("");

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
  const s = config.screener;
  const set = (patch: Partial<Config["screener"]>) => setConfig({ ...config, screener: { ...s, ...patch } });

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-fg">Screener Configuration</h1>
          <p className="text-sm text-muted">
            Rules the Screener Agent uses to rate every scraped job yes / maybe / no.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {savedAt && <span className="text-xs text-muted">Saved</span>}
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <LabeledNumber label="Max years exp" value={s.max_years_exp} onChange={(v) => set({ max_years_exp: v })} />
        <LabeledNumber label="Yes match %" value={s.yes_match_pct} onChange={(v) => set({ yes_match_pct: v })} />
        <LabeledNumber label="Maybe match %" value={s.maybe_match_pct} onChange={(v) => set({ maybe_match_pct: v })} />
      </div>

      <div>
        <span className="label">Accepted role levels</span>
        <div className="flex gap-4">
          {["junior", "mid", "senior"].map((level) => (
            <label key={level} className="flex items-center gap-2 text-sm text-fg-soft">
              <input
                type="checkbox"
                checked={s.accept_role_levels.includes(level)}
                onChange={(e) =>
                  set({
                    accept_role_levels: e.target.checked
                      ? [...s.accept_role_levels, level]
                      : s.accept_role_levels.filter((l) => l !== level),
                  })
                }
              />
              {level}
            </label>
          ))}
        </div>
      </div>

      <LabeledTextarea label="Required skills" value={s.required_skills} onChange={(v) => set({ required_skills: v })} rows={2} />
      <LabeledTextarea label="Preferred skills" value={s.preferred_skills} onChange={(v) => set({ preferred_skills: v })} rows={2} />
      <LabeledTextarea label="Reject keywords" value={s.reject_keywords} onChange={(v) => set({ reject_keywords: v })} rows={2} />
      <LabeledTextarea label="Accept keywords" value={s.accept_keywords} onChange={(v) => set({ accept_keywords: v })} rows={2} />

      <div className="flex gap-6">
        <label className="flex items-center gap-2 text-sm text-fg-soft">
          <input type="checkbox" checked={s.skip_applied} onChange={(e) => set({ skip_applied: e.target.checked })} />
          Skip jobs already applied to
        </label>
        <label className="flex items-center gap-2 text-sm text-fg-soft">
          <input type="checkbox" checked={s.fuzzy_dedup} onChange={(e) => set({ fuzzy_dedup: e.target.checked })} />
          Fuzzy dedup across sites
        </label>
      </div>

      <div>
        <span className="label">Blacklisted companies</span>
        <div className="flex flex-wrap gap-1.5 mb-2">
          {s.blacklisted_companies.map((c) => (
            <span key={c} className="text-xs px-2 py-1 rounded-full bg-subtle border border-border flex items-center gap-1.5">
              {c}
              <button
                className="text-no"
                onClick={() => set({ blacklisted_companies: s.blacklisted_companies.filter((x) => x !== c) })}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input className="input" value={newCompany} onChange={(e) => setNewCompany(e.target.value)} placeholder="Company name" />
          <button
            className="btn-secondary"
            onClick={() => {
              if (newCompany.trim()) {
                set({ blacklisted_companies: [...s.blacklisted_companies, newCompany.trim()] });
                setNewCompany("");
              }
            }}
          >
            Add
          </button>
        </div>
      </div>
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
