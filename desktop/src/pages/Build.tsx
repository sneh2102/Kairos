import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import { useEventStream } from "../lib/eventStream";
import type { Config } from "../lib/types";
import StatusBadge from "../components/StatusBadge";

const STAGE_LABEL: Record<string, string> = {
  building: "Building sections",
  checking_ats: "Checking ATS",
  ats_score: "Scored",
  done: "Done",
};

export default function Build() {
  const [config, setConfig] = useState<Config | null>(null);
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { applyProgress, applyOrder, applyRunning, startApplyRun } = useEventStream();

  function refreshCount() {
    api.listJobs({ verdict: "yes" }).then((rows) => setPendingCount(rows.filter((r) => !r.latex_content).length));
  }

  useEffect(() => {
    api.getConfig().then(setConfig);
    refreshCount();
  }, []);

  async function start() {
    setError(null);
    startApplyRun();
    try {
      const res = await api.startApply(["yes"]);
      setPendingCount(res.count);
    } catch (e) {
      setError(String(e));
    }
  }

  async function stop() {
    await api.stopApply().catch(() => {});
  }

  async function saveThresholds() {
    if (!config) return;
    await api.putConfig(config);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Build</h1>
          <p className="text-sm text-muted">
            Skills / Experience / Project Writers → ATS Checker, looping until it passes. Builds every
            "yes" job that doesn't have a resume yet — change a verdict in Scraped Jobs to include/exclude one.
          </p>
        </div>
        <StatusBadge label={applyRunning ? "running" : "idle"} tone={applyRunning ? "running" : "idle"} />
      </div>

      {error && <div className="text-sm text-no">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
        <div className="card p-4 flex flex-col gap-3 h-fit">
          <div className="text-sm text-gray-300">
            {pendingCount ?? "…"} unbuilt "yes" job{pendingCount === 1 ? "" : "s"} waiting
          </div>
          {config && (
            <>
              <Field label="ATS pass threshold">
                <input
                  type="number"
                  className="input"
                  value={config.pipeline.ats_pass_threshold}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      pipeline: { ...config.pipeline, ats_pass_threshold: Number(e.target.value) },
                    })
                  }
                />
              </Field>
              <Field label="Max ATS iterations">
                <input
                  type="number"
                  className="input"
                  value={config.pipeline.max_ats_iterations}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      pipeline: { ...config.pipeline, max_ats_iterations: Number(e.target.value) },
                    })
                  }
                />
              </Field>
              <button className="btn-secondary" onClick={saveThresholds}>
                Save
              </button>
            </>
          )}
          <div className="flex gap-2 pt-2">
            <button className="btn-primary flex-1" onClick={start} disabled={applyRunning}>
              Start
            </button>
            <button className="btn-danger flex-1" onClick={stop} disabled={!applyRunning}>
              Stop
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          {applyOrder.length === 0 && <div className="text-sm text-muted">No activity yet — click Start.</div>}
          {applyOrder.map((key) => {
            const p = applyProgress[key];
            if (!p) return null;
            const passed = p.stage === "done" && (p.score ?? 0) >= (config?.pipeline.ats_pass_threshold ?? 85);
            return (
              <div key={key} className="card p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-gray-100 text-sm">{p.title}</div>
                    <div className="text-xs text-muted">
                      {p.company} · job {p.job_index + 1}/{p.total}
                    </div>
                  </div>
                  <StatusBadge
                    label={p.stage === "done" ? (passed ? "PASS" : "SAVED") : STAGE_LABEL[p.stage] ?? p.stage}
                    tone={p.stage === "done" ? (passed ? "pass" : "maybe") : "running"}
                  />
                </div>
                {typeof p.score === "number" && (
                  <div className="mt-2">
                    <div className="h-1.5 rounded-full bg-[#0d1117] overflow-hidden">
                      <div
                        className={`h-full ${passed ? "bg-pass" : "bg-maybe"}`}
                        style={{ width: `${Math.min(100, p.score)}%` }}
                      />
                    </div>
                    <div className="text-[11px] text-muted mt-0.5">
                      ATS score {p.score}
                      {p.iteration ? ` · iteration ${p.iteration}` : ""}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
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
