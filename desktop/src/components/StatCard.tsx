export default function StatCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string | number;
  hint?: string;
  accent?: "good" | "warn" | "bad" | "accent";
}) {
  const valueColor = accent ? `text-${accent}` : "text-fg";
  return (
    <div className="card p-4 flex-1 min-w-[150px]">
      <div className="text-[11px] font-medium uppercase tracking-[0.05em] text-muted">{label}</div>
      <div className={`num text-[28px] leading-none font-semibold mt-2 ${valueColor}`}>{value}</div>
      {hint && <div className="text-[11px] text-muted mt-1.5">{hint}</div>}
    </div>
  );
}
