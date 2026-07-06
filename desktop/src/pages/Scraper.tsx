import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import { useEventStream } from "../lib/eventStream";
import type { Config } from "../lib/types";
import JobCard from "../components/JobCard";
import StatusBadge from "../components/StatusBadge";

// value = what jobspy's Site enum expects (see jobspy/model.py)
const SITES = [
  { value: "indeed", label: "Indeed" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "glassdoor", label: "Glassdoor" },
  { value: "zip_recruiter", label: "ZipRecruiter" },
  { value: "google", label: "Google Jobs" },
  { value: "bayt", label: "Bayt" },
  { value: "naukri", label: "Naukri" },
  { value: "bdjobs", label: "BDJobs" },
  { value: "jobright", label: "JobRight" },
  { value: "wellfound", label: "Wellfound" },
];

export default function Scraper() {
  const [config, setConfig] = useState<Config | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { scrapeJobs, scrapeRunning, startScrapeRun, logs, connected } = useEventStream();

  useEffect(() => {
    api.getConfig().then(setConfig).catch((e) => setError(String(e)));
  }, []);

  const yes = scrapeJobs.filter((j) => j.verdict === "yes").length;
  const maybe = scrapeJobs.filter((j) => j.verdict === "maybe").length;
  const no = scrapeJobs.filter((j) => j.verdict === "no").length;

  async function save() {
    if (!config) return;
    setSaving(true);
    try {
      await api.putConfig(config);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function start() {
    setError(null);
    startScrapeRun();
    try {
      await api.startScrape();
    } catch (e) {
      setError(String(e));
    }
  }

  async function stop() {
    await api.stopScrape().catch(() => {});
  }

  return (
    <div className="flex flex-col gap-6 h-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-fg">Scraper</h1>
          <p className="text-sm text-muted">Job Scraper Agent + Screener Agent — finds and rates new postings.</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge label={connected ? "connected" : "disconnected"} tone={connected ? "pass" : "error"} />
          <StatusBadge label={scrapeRunning ? "running" : "idle"} tone={scrapeRunning ? "running" : "idle"} />
        </div>
      </div>

      {error && <div className="text-sm text-no">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-6 flex-1 min-h-0">
        <div className="card p-4 flex flex-col gap-3 h-fit">
          {config && (
            <>
              <Field label="Sites">
                <SiteSelect
                  value={config.scraper.sites}
                  onChange={(sites) => setConfig({ ...config, scraper: { ...config.scraper, sites } })}
                />
              </Field>
              <Field label="Search terms (one per line)">
                <textarea
                  className="input h-24 resize-none"
                  value={config.scraper.search_terms}
                  onChange={(e) =>
                    setConfig({ ...config, scraper: { ...config.scraper, search_terms: e.target.value } })
                  }
                />
              </Field>
              <Field label="Location">
                <input
                  className="input"
                  value={config.scraper.location}
                  onChange={(e) => setConfig({ ...config, scraper: { ...config.scraper, location: e.target.value } })}
                />
              </Field>
              <Field label="Country (for Indeed — e.g. canada, usa, uk)">
                <input
                  className="input"
                  value={config.scraper.country_indeed}
                  onChange={(e) =>
                    setConfig({ ...config, scraper: { ...config.scraper, country_indeed: e.target.value } })
                  }
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Hours old">
                  <input
                    type="number"
                    className="input"
                    value={config.scraper.hours_old}
                    onChange={(e) =>
                      setConfig({ ...config, scraper: { ...config.scraper, hours_old: Number(e.target.value) } })
                    }
                  />
                </Field>
                <Field label="Results wanted">
                  <input
                    type="number"
                    className="input"
                    value={config.scraper.results_wanted}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        scraper: { ...config.scraper, results_wanted: Number(e.target.value) },
                      })
                    }
                  />
                </Field>
              </div>
              <label className="flex items-center gap-2 text-sm text-fg-soft">
                <input
                  type="checkbox"
                  checked={config.scraper.is_remote}
                  onChange={(e) =>
                    setConfig({ ...config, scraper: { ...config.scraper, is_remote: e.target.checked } })
                  }
                />
                Remote only
              </label>

              <div className="flex gap-2 pt-2">
                <button className="btn-secondary flex-1" onClick={save} disabled={saving}>
                  {saving ? "Saving…" : "Save config"}
                </button>
              </div>
              <div className="flex gap-2">
                <button className="btn-primary flex-1" onClick={start} disabled={scrapeRunning}>
                  Start
                </button>
                <button className="btn-danger flex-1" onClick={stop} disabled={!scrapeRunning}>
                  Stop
                </button>
              </div>
            </>
          )}
        </div>

        <div className="flex flex-col gap-3 min-h-0">
          <div className="flex items-center gap-4 text-sm">
            <span className="text-muted"><span className="num text-fg">{scrapeJobs.length}</span> processed</span>
            <Count color="bg-good" label="yes" n={yes} />
            <Count color="bg-warn" label="maybe" n={maybe} />
            <Count color="bg-bad" label="no" n={no} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 overflow-y-auto pr-1" style={{ maxHeight: "55vh" }}>
            {scrapeJobs.map((j, i) => (
              <JobCard
                key={i}
                verdict={j.verdict}
                company={j.company}
                title={j.title}
                location={j.location}
                skillsMatchPct={j.skills_match_pct}
                matchedSkills={j.matched_skills}
                missingSkills={j.missing_skills}
              />
            ))}
            {scrapeJobs.length === 0 && (
              <div className="text-sm text-muted col-span-2">No jobs yet — click Start.</div>
            )}
          </div>

          <div className="card p-3 flex-1 min-h-[160px] overflow-y-auto font-mono text-xs">
            {logs.slice(-100).map((l, i) => (
              <div key={i} className={l.level === "ERROR" ? "text-no" : l.level === "WARNING" ? "text-maybe" : "text-muted"}>
                {l.message}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function SiteSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const selected = value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  function toggle(site: string) {
    const next = selected.includes(site) ? selected.filter((s) => s !== site) : [...selected, site];
    onChange(next.join(","));
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {SITES.map((s) => {
        const on = selected.includes(s.value);
        return (
          <button
            key={s.value}
            type="button"
            aria-pressed={on}
            onClick={() => toggle(s.value)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-150 ${
              on
                ? "bg-accent border-accent text-on-accent"
                : "bg-surface border-edge text-fg-soft hover:border-accent hover:text-fg"
            }`}
          >
            {on && (
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 6L9 17l-5-5" />
              </svg>
            )}
            {s.label}
          </button>
        );
      })}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <span className="label">{label}</span>
      {children}
    </div>
  );
}

function Count({ color, label, n }: { color: string; label: string; n: number }) {
  return (
    <span className="flex items-center gap-1.5 text-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      <span className="num text-fg">{n}</span> {label}
    </span>
  );
}
