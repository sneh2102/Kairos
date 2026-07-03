import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { JobRow } from "../lib/types";
import StatusBadge from "../components/StatusBadge";

const FILTERS = ["all", "yes", "maybe", "no"] as const;

export default function ScrapedJobs() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  async function load() {
    setLoading(true);
    const rows = await api.listJobs({ verdict: filter === "all" ? "" : filter, q });
    setJobs(rows);
    setLoading(false);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">Scraped Jobs</h1>
          <p className="text-sm text-muted">Every job the Screener Agent has rated — click one for details.</p>
        </div>
        <div className="flex gap-2">
          <input
            className="input w-56"
            placeholder="Search title/company…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
          />
          <button className="btn-secondary" onClick={load}>
            Refresh
          </button>
        </div>
      </div>

      <div className="flex gap-1">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-md text-sm capitalize ${
              filter === f ? "bg-primary text-white" : "bg-[#21262d] text-gray-300 hover:text-gray-100"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-sm text-muted">Loading…</div>
      ) : jobs.length === 0 ? (
        <div className="text-sm text-muted">No jobs match. Run a scrape first.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {jobs.map((job) => (
            <div
              key={job.id}
              onClick={() => navigate(`/jobs/${job.id}`)}
              className="card p-4 flex items-center justify-between gap-4 cursor-pointer hover:border-accent/50"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <div className="font-semibold text-gray-100 truncate">{job.title}</div>
                  <StatusBadge label={job.ai_recommendation.toUpperCase()} tone={job.ai_recommendation} />
                  {job.latex_content && <StatusBadge label={`ATS ${job.ats_score}`} tone={job.ats_score >= 85 ? "pass" : "maybe"} />}
                </div>
                <div className="text-sm text-muted truncate">
                  {job.company} · {job.location} · {job.site} · {job.skills_match_pct}% match
                </div>
              </div>
              <div className="text-muted text-lg">›</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
