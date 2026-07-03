export default function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="card p-4 flex-1 min-w-[140px]">
      <div className="text-2xl font-semibold text-gray-100">{value}</div>
      <div className="text-xs text-muted mt-1">{label}</div>
      {hint && <div className="text-[11px] text-muted mt-0.5">{hint}</div>}
    </div>
  );
}
