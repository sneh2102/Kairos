import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../lib/api";
import type { Stats } from "../lib/types";
import { CHART, useTheme } from "../lib/theme";
import { useEventStream } from "../lib/eventStream";
import StatCard from "../components/StatCard";

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [chaining, setChaining] = useState(false);
  const { resolved } = useTheme();
  const c = CHART[resolved];
  const { scrapeRunning, applyRunning, startScrapeRun, startApplyRun } = useEventStream();
  const wasScraping = useRef(scrapeRunning);

  useEffect(() => {
    api.getStats().then(setStats).catch((e) => setError(String(e)));
  }, []);

  // chained run: once the scrape this button kicked off finishes, start the build
  useEffect(() => {
    if (chaining && wasScraping.current && !scrapeRunning) {
      setChaining(false);
      startApplyRun();
      api.startApply(["yes"]).catch((e) => setPipelineError(String(e)));
    }
    wasScraping.current = scrapeRunning;
  }, [scrapeRunning, chaining, startApplyRun]);

  async function runFullPipeline() {
    setPipelineError(null);
    setChaining(true);
    startScrapeRun();
    try {
      await api.startScrape();
    } catch (e) {
      setChaining(false);
      setPipelineError(String(e));
    }
  }

  const pipelineBusy = chaining || scrapeRunning || applyRunning;
  const pipelineLabel = scrapeRunning ? "Scraping jobs…" : applyRunning ? "Building resumes…" : "Run scraper + build resumes";

  if (error) return <div className="text-bad text-sm">Failed to load dashboard: {error}</div>;
  if (!stats) return <div className="text-muted text-sm">Loading…</div>;

  const VERDICT_COLOR: Record<string, string> = { yes: c.good, maybe: c.warn, no: c.bad };
  const verdictData = ["yes", "maybe", "no"].map((v) => ({ verdict: v, count: stats.verdict_counts[v] ?? 0 }));
  const appliedData = fillLastDays(stats.applied_by_date, 30);
  const avgScore = stats.ats_scores.length
    ? Math.round(stats.ats_scores.reduce((s, v) => s + v, 0) / stats.ats_scores.length)
    : null;
  const tooltipStyle = { background: c.surface, border: `1px solid ${c.border}`, borderRadius: 10, fontSize: 12, color: "var(--fg)" };

  return (
    <div className="flex flex-col gap-7 max-w-6xl">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-fg tracking-tight">Overview</h1>
          <p className="text-sm text-muted mt-1">Where every job stands, from first scrape to sent application.</p>
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <button className="btn-primary" onClick={runFullPipeline} disabled={pipelineBusy}>
            {pipelineLabel}
          </button>
          {pipelineError && <span className="text-xs text-bad">{pipelineError}</span>}
        </div>
      </header>

      <div className="flex gap-4 flex-wrap">
        <StatCard label="Applications sent" value={stats.applied_count} accent="accent" />
        <StatCard label="Jobs extracted" value={stats.total_extracted} />
        <StatCard label="Resumes created" value={stats.resumes_created} />
        <StatCard label="Jobs to review" value={stats.pending_jobs} />
        <StatCard label="Worth applying" value={stats.verdict_counts.yes ?? 0} accent="good" />
        <StatCard label="Avg ATS score" value={avgScore ?? "—"} accent={avgScore != null && avgScore >= 85 ? "good" : "warn"} />
      </div>

      <Funnel
        stages={[
          { label: "Jobs extracted", value: stats.total_extracted },
          { label: "Resumes created", value: stats.resumes_created },
          { label: "Applications sent", value: stats.applied_count },
        ]}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Screener verdicts" subtitle="How your rules rated scraped jobs">
          {verdictData.every((d) => d.count === 0) ? (
            <EmptyChart hint="Run a scrape to see verdicts." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={verdictData} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={c.grid} vertical={false} />
                <XAxis dataKey="verdict" stroke={c.axis} fontSize={12} tickLine={false} axisLine={{ stroke: c.grid }} tickFormatter={(v) => v[0].toUpperCase() + v.slice(1)} />
                <YAxis stroke={c.axis} fontSize={12} allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: c.grid, opacity: 0.35 }} />
                <Bar dataKey="count" radius={[5, 5, 0, 0]} maxBarSize={64}>
                  {verdictData.map((d) => (
                    <Cell key={d.verdict} fill={VERDICT_COLOR[d.verdict]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Applications per day" subtitle="Last 30 days, including the quiet ones">
          {stats.applied_by_date.length === 0 ? (
            <EmptyChart hint="Mark a job applied to start the trend." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={appliedData} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={c.grid} vertical={false} />
                <XAxis dataKey="date" stroke={c.axis} fontSize={12} tickLine={false} axisLine={{ stroke: c.grid }} minTickGap={24} />
                <YAxis stroke={c.axis} fontSize={12} allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: c.grid, opacity: 0.35 }} />
                <Bar dataKey="count" fill={c.accent} radius={[4, 4, 0, 0]} maxBarSize={18} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Jobs by board" subtitle="Where jobs come from, and which boards are worth your scraper's time">
          {stats.site_counts.length === 0 ? (
            <EmptyChart hint="Run a scrape to compare job boards." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={stats.site_counts} margin={{ top: 6, right: 6, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={c.grid} vertical={false} />
                <XAxis dataKey="site" stroke={c.axis} fontSize={12} tickLine={false} axisLine={{ stroke: c.grid }} />
                <YAxis stroke={c.axis} fontSize={12} allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: c.grid, opacity: 0.35 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="total" name="Scraped" fill={c.accent} radius={[4, 4, 0, 0]} maxBarSize={28} />
                <Bar dataKey="yes" name="Worth applying" fill={c.good} radius={[4, 4, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Recent applications" subtitle="The last five you sent">
          {stats.recent_applied.length === 0 ? (
            <EmptyChart hint="Mark a job applied to see it here." />
          ) : (
            <div className="flex flex-col divide-y divide-border">
              {stats.recent_applied.map((r) => (
                <Link key={r.id} to="/applied" className="flex items-center gap-3 py-2.5 group">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-fg truncate group-hover:text-accent transition-colors">{r.title}</div>
                    <div className="text-xs text-muted truncate">{r.company}</div>
                  </div>
                  <span className="text-xs text-muted shrink-0 num">{r.applied_date}</span>
                  <span className={`chip text-[11px] shrink-0 ${r.ats_score >= 85 ? "text-good" : "text-warn"}`}>
                    ATS {r.ats_score}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </ChartCard>

        <ChartCard
          title="Skills costing you matches"
          subtitle="What screened JDs keep asking for that your resume doesn't show — learn or add these first"
          className="lg:col-span-2"
        >
          {stats.top_missing_skills.length === 0 ? (
            <EmptyChart hint="Run a scrape — missing skills show up once jobs are screened." />
          ) : (
            <ResponsiveContainer width="100%" height={Math.max(220, stats.top_missing_skills.length * 30)}>
              <BarChart data={stats.top_missing_skills} layout="vertical" margin={{ top: 6, right: 24, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={c.grid} horizontal={false} />
                <XAxis type="number" stroke={c.axis} fontSize={12} allowDecimals={false} tickLine={false} axisLine={{ stroke: c.grid }} />
                <YAxis type="category" dataKey="skill" width={140} stroke={c.axis} fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: c.grid, opacity: 0.35 }} formatter={(v) => [`${v} jobs`, "Missing in"]} />
                <Bar dataKey="count" fill={c.accent} radius={[0, 4, 4, 0]} maxBarSize={18} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>
    </div>
  );
}

function ChartCard({
  title,
  subtitle,
  className = "",
  children,
}: {
  title: string;
  subtitle?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`card p-5 ${className}`}>
      <div className="mb-4">
        <div className="text-sm font-semibold text-fg">{title}</div>
        {subtitle && <div className="text-xs text-muted mt-0.5">{subtitle}</div>}
      </div>
      {children}
    </div>
  );
}

function EmptyChart({ hint }: { hint: string }) {
  return <div className="h-[220px] flex items-center justify-center text-sm text-muted">{hint}</div>;
}

function Funnel({ stages }: { stages: { label: string; value: number }[] }) {
  return (
    <div className="card px-5 py-4 flex items-center gap-2 flex-wrap">
      {stages.map((s, i) => {
        const prev = i > 0 ? stages[i - 1].value : 0;
        const pct = i > 0 && prev > 0 ? Math.round((s.value / prev) * 100) : null;
        return (
          <div key={s.label} className="flex items-center gap-2">
            {i > 0 && <span className="text-muted text-lg px-1" aria-hidden>›</span>}
            <div>
              <div className="num text-lg font-semibold text-fg leading-tight">
                {s.value.toLocaleString()}
                {pct != null && <span className="text-xs font-normal text-muted ml-1.5">{pct}% of previous</span>}
              </div>
              <div className="text-xs text-muted">{s.label}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Zero-fills the last N local days so no-application days show as gaps in the
// bars instead of being silently skipped by the axis.
function fillLastDays(rows: { date: string; count: number }[], days: number) {
  const byDate = new Map(rows.map((r) => [r.date, r.count]));
  const out: { date: string; count: number }[] = [];
  const d = new Date();
  d.setDate(d.getDate() - (days - 1));
  for (let i = 0; i < days; i++) {
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    out.push({ date: iso.slice(5), count: byDate.get(iso) ?? 0 });
    d.setDate(d.getDate() + 1);
  }
  return out;
}
