import { useEffect, useState } from "react";
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
import StatCard from "../components/StatCard";

const VERDICT_COLOR: Record<string, string> = { yes: "#3fb950", maybe: "#d29922", no: "#f85149" };

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getStats()
      .then(setStats)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <div className="text-no text-sm">Failed to load dashboard: {error}</div>;
  }
  if (!stats) {
    return <div className="text-muted text-sm">Loading…</div>;
  }

  const verdictData = ["yes", "maybe", "no"].map((v) => ({
    verdict: v,
    count: stats.verdict_counts[v] ?? 0,
  }));
  const appliedData = stats.applied_by_date.map((d) => ({ date: d.date.slice(5), count: d.count }));
  const scoreData = stats.ats_scores.map((score, i) => ({ index: i + 1, score }));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Dashboard</h1>
        <p className="text-sm text-muted">Snapshot of your job search pipeline.</p>
      </div>

      <div className="flex gap-4 flex-wrap">
        <StatCard label="Pending / Screened jobs" value={stats.pending_jobs} />
        <StatCard label="Applications sent" value={stats.applied_count} />
        <StatCard label="Yes verdicts" value={stats.verdict_counts.yes ?? 0} />
        <StatCard label="Maybe verdicts" value={stats.verdict_counts.maybe ?? 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-4">
          <div className="text-sm font-medium text-gray-200 mb-3">Screener verdict breakdown</div>
          {verdictData.every((d) => d.count === 0) ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={verdictData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
                <XAxis dataKey="verdict" stroke="#8b949e" fontSize={12} tickFormatter={(v) => v.toUpperCase()} />
                <YAxis stroke="#8b949e" fontSize={12} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {verdictData.map((d) => (
                    <Cell key={d.verdict} fill={VERDICT_COLOR[d.verdict]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card p-4">
          <div className="text-sm font-medium text-gray-200 mb-3">Applications over time</div>
          {appliedData.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={appliedData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
                <XAxis dataKey="date" stroke="#8b949e" fontSize={12} />
                <YAxis stroke="#8b949e" fontSize={12} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Line type="monotone" dataKey="count" stroke="#58a6ff" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card p-4 lg:col-span-2">
          <div className="text-sm font-medium text-gray-200 mb-3">ATS score trend (85 = pass threshold)</div>
          {scoreData.length === 0 ? (
            <EmptyChart />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={scoreData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
                <XAxis dataKey="index" stroke="#8b949e" fontSize={12} />
                <YAxis stroke="#8b949e" fontSize={12} domain={[0, 100]} />
                <Tooltip contentStyle={tooltipStyle} />
                <ReferenceLine y={85} stroke="#3fb950" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="score" stroke="#58a6ff" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}

const tooltipStyle = { background: "#161b22", border: "1px solid #30363d", borderRadius: 8, fontSize: 12 };

function EmptyChart() {
  return <div className="h-[220px] flex items-center justify-center text-sm text-muted">No data yet</div>;
}

export { VERDICT_COLOR };
