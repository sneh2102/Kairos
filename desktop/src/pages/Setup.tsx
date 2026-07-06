import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { Config } from "../lib/types";
import { ProfileFields } from "./ResumeData";
import { SiteSelect } from "./Scraper";

const STEPS = ["Welcome", "Profile", "Resume material", "Model & API key", "Scraper defaults", "Save location"] as const;

export default function Setup() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [config, setConfig] = useState<Config | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [projectsText, setProjectsText] = useState("");
  const [ollamaKey, setOllamaKeyInput] = useState("");
  const [keyAlreadySet, setKeyAlreadySet] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getConfig().then(setConfig);
    api.getResumeData().then((d) => {
      setResumeText(d.resume_text);
      setProjectsText(d.projects_text);
    });
    api.getOllamaKeyStatus().then((s) => setKeyAlreadySet(s.is_set));
  }, []);

  async function persist(markOnboarded: boolean) {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      await Promise.all([
        api.putConfig({ ...config, onboarded: markOnboarded }),
        api.putResumeData({ resume_text: resumeText, projects_text: projectsText }),
        ...(ollamaKey.trim() ? [api.setOllamaKey(ollamaKey.trim())] : []),
      ]);
      navigate("/");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (!config) return <div className="text-sm text-muted">Loading…</div>;

  const last = step === STEPS.length - 1;

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      <div>
        <h1 className="text-xl font-semibold text-fg">Set up Job Scraper</h1>
        <p className="text-sm text-muted mt-1">
          A few things it needs before it can find jobs and build resumes for you. You can change any of this later
          from the sidebar.
        </p>
      </div>

      <div className="flex gap-1.5">
        {STEPS.map((label, i) => (
          <div
            key={label}
            className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-accent" : "bg-subtle"}`}
            title={label}
          />
        ))}
      </div>

      {error && <div className="text-sm text-no">{error}</div>}

      <div className="card p-5">
        {step === 0 && (
          <div className="flex flex-col gap-2">
            <h2 className="font-semibold text-fg">Welcome</h2>
            <p className="text-sm text-muted">
              This wizard sets your profile, resume material, model/API key, scraper defaults, and where resumes get
              saved. Takes a couple minutes — or hit "Skip for now" and configure it later.
            </p>
          </div>
        )}

        {step === 1 && (
          <div className="flex flex-col gap-3">
            <h2 className="font-semibold text-fg">Your profile</h2>
            <ProfileFields config={config} setConfig={setConfig} />
          </div>
        )}

        {step === 2 && (
          <div className="flex flex-col gap-3">
            <h2 className="font-semibold text-fg">Resume material</h2>
            <p className="text-xs text-muted">
              The Writer Agents draw from this. Paste your resume text and project list — full formatting/reordering
              lives on the Resume & profile page later.
            </p>
            <div>
              <span className="label">Resume text</span>
              <textarea
                className="input font-mono text-xs resize-none"
                rows={10}
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
                placeholder="Name, contact info, education, skills, experience bullets…"
              />
            </div>
            <div>
              <span className="label">Projects</span>
              <textarea
                className="input font-mono text-xs resize-none"
                rows={8}
                value={projectsText}
                onChange={(e) => setProjectsText(e.target.value)}
                placeholder={"Project Name | tech, stack | https://github.com/...\n- bullet\n- bullet"}
              />
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="flex flex-col gap-3 max-w-md">
            <h2 className="font-semibold text-fg">Model & API key</h2>
            <Field label="Screening model">
              <input
                className="input"
                value={config.model.scraping}
                onChange={(e) => setConfig({ ...config, model: { ...config.model, scraping: e.target.value } })}
              />
            </Field>
            <Field label="Resume/ATS model">
              <input
                className="input"
                value={config.model.pipeline}
                onChange={(e) => setConfig({ ...config, model: { ...config.model, pipeline: e.target.value } })}
              />
            </Field>
            <Field label={`Ollama API key${keyAlreadySet ? " (already set — leave blank to keep it)" : ""}`}>
              <input
                type="password"
                className="input"
                value={ollamaKey}
                onChange={(e) => setOllamaKeyInput(e.target.value)}
                placeholder={keyAlreadySet ? "••••••••" : "sk-…"}
              />
            </Field>
          </div>
        )}

        {step === 4 && (
          <div className="flex flex-col gap-3 max-w-md">
            <h2 className="font-semibold text-fg">Scraper defaults</h2>
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
                onChange={(e) => setConfig({ ...config, scraper: { ...config.scraper, search_terms: e.target.value } })}
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
          </div>
        )}

        {step === 5 && (
          <div className="flex flex-col gap-3 max-w-md">
            <h2 className="font-semibold text-fg">Where resumes get saved</h2>
            <Field label="Save resumes to">
              <div className="flex gap-2">
                <input
                  className="input flex-1"
                  readOnly
                  placeholder="Documents/Job-Hunter/Resumes (default)"
                  value={config.pipeline.output_dir}
                  title={config.pipeline.output_dir || undefined}
                />
                <button
                  className="btn-secondary shrink-0"
                  onClick={async () => {
                    const dir = await window.desktop?.pickFolder();
                    if (dir) setConfig({ ...config, pipeline: { ...config.pipeline, output_dir: dir } });
                  }}
                >
                  Browse…
                </button>
                {config.pipeline.output_dir && (
                  <button
                    className="btn-secondary shrink-0"
                    onClick={() => setConfig({ ...config, pipeline: { ...config.pipeline, output_dir: "" } })}
                  >
                    Reset
                  </button>
                )}
              </div>
            </Field>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between">
        <button className="btn-ghost" onClick={() => persist(true)} disabled={saving}>
          Skip for now
        </button>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
            Back
          </button>
          {last ? (
            <button className="btn-primary" onClick={() => persist(true)} disabled={saving}>
              {saving ? "Saving…" : "Finish setup"}
            </button>
          ) : (
            <button className="btn-primary" onClick={() => setStep((s) => s + 1)}>
              Next
            </button>
          )}
        </div>
      </div>
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
