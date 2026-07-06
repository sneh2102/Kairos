import { useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
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
  const appliedData = stats.applied_by_date.map((d) => ({ date: d.date.slice(5), count: d.count }));
  const scoreData = stats.ats_scores.map((score, i) => ({ index: i + 1, score }));
  const avgScore = scoreData.length
    ? Math.round(scoreData.reduce((s, d) => s + d.score, 0) / scoreData.length)
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
        <StatCard label="Jobs to review" value={stats.pending_jobs} />
        <StatCard label="Applications sent" value={stats.applied_count} accent="accent" />
        <StatCard label="Worth applying" value={stats.verdict_counts.yes ?? 0} accent="good" />
        <StatCard label="Avg ATS score" value={avgScore ?? "—"} accent={avgScore != null && avgScore >= 85 ? "good" : "warn"} />
      </div>

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

        <ChartCard title="Applications over time" subtitle="When you sent them">
          {appliedData.length === 0 ? (
            <EmptyChart hint="Mark a job applied to start the trend." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={appliedData} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={c.grid} vertical={false} />
                <XAxis dataKey="date" stroke={c.axis} fontSize={12} tickLine={false} axisLine={{ stroke: c.grid }} />
                <YAxis stroke={c.axis} fontSize={12} allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line type="monotone" dataKey="count" stroke={c.accent} strokeWidth={2.5} dot={{ r: 3, fill: c.accent }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="ATS scores" subtitle="Each built resume · 85 is the pass line" className="lg:col-span-2">
          {scoreData.length === 0 ? (
            <EmptyChart hint="Build a resume to see its score." />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={scoreData} margin={{ top: 6, right: 10, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={c.grid} vertical={false} />
                <XAxis dataKey="index" stroke={c.axis} fontSize={12} tickLine={false} axisLine={{ stroke: c.grid }} />
                <YAxis stroke={c.axis} fontSize={12} domain={[0, 100]} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <ReferenceLine y={85} stroke={c.good} strokeDasharray="5 4" strokeWidth={1.5} />
                <Line type="monotone" dataKey="score" stroke={c.accent} strokeWidth={2.5} dot={{ r: 3, fill: c.accent }} activeDot={{ r: 5 }} />
              </LineChart>
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
