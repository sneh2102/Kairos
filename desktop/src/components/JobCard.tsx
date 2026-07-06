import StatusBadge from "./StatusBadge";

export default function JobCard({
  verdict,
  company,
  title,
  location,
  skillsMatchPct,
  matchedSkills,
  missingSkills,
}: {
  verdict: string;
  company: string;
  title: string;
  location?: string;
  skillsMatchPct: number;
  matchedSkills: string[];
  missingSkills: string[];
}) {
  const barColor = verdict === "yes" ? "bg-good" : verdict === "maybe" ? "bg-warn" : "bg-bad";
  return (
    <div className="card p-4 transition-colors hover:border-edge">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-fg text-sm truncate">{title}</div>
          <div className="text-xs text-muted truncate">
            {company}
            {location ? ` · ${location}` : ""}
          </div>
        </div>
        <StatusBadge label={verdict.toUpperCase()} tone={verdict} />
      </div>

      <div className="mt-3 flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-track overflow-hidden">
          <div
            className={`h-full ${barColor} transition-[width] duration-500`}
            style={{ width: `${Math.min(100, skillsMatchPct)}%` }}
          />
        </div>
        <span className="num text-xs text-fg-soft">{skillsMatchPct}%</span>
      </div>
      <div className="text-[11px] text-muted mt-1">skills match</div>

      {(matchedSkills.length > 0 || missingSkills.length > 0) && (
        <div className="flex flex-wrap gap-1 mt-3">
          {matchedSkills.slice(0, 6).map((s) => (
            <span key={`m-${s}`} className="text-[10px] px-1.5 py-0.5 rounded bg-good/10 text-good border border-good/25">
              {s}
            </span>
          ))}
          {missingSkills.slice(0, 4).map((s) => (
            <span key={`x-${s}`} className="text-[10px] px-1.5 py-0.5 rounded bg-bad/10 text-bad border border-bad/25">
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
