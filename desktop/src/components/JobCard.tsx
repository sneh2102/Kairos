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
  const barColor = verdict === "yes" ? "bg-yes" : verdict === "maybe" ? "bg-maybe" : "bg-no";
  return (
    <div className="card p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-gray-100 text-sm">{title}</div>
          <div className="text-xs text-muted">
            {company}
            {location ? ` · ${location}` : ""}
          </div>
        </div>
        <StatusBadge label={verdict.toUpperCase()} tone={verdict} />
      </div>

      <div className="mt-2 h-1.5 rounded-full bg-[#0d1117] overflow-hidden">
        <div className={`h-full ${barColor}`} style={{ width: `${Math.min(100, skillsMatchPct)}%` }} />
      </div>
      <div className="text-[11px] text-muted mt-0.5">{skillsMatchPct}% skills match</div>

      {(matchedSkills.length > 0 || missingSkills.length > 0) && (
        <div className="flex flex-wrap gap-1 mt-2">
          {matchedSkills.slice(0, 6).map((s) => (
            <span key={`m-${s}`} className="text-[10px] px-1.5 py-0.5 rounded bg-yes/10 text-yes border border-yes/30">
              {s}
            </span>
          ))}
          {missingSkills.slice(0, 4).map((s) => (
            <span key={`x-${s}`} className="text-[10px] px-1.5 py-0.5 rounded bg-no/10 text-no border border-no/30">
              {s}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
