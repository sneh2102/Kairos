const STYLES: Record<string, { cls: string; dot: string }> = {
  yes: { cls: "bg-good/12 text-good border-good/30", dot: "bg-good" },
  pass: { cls: "bg-good/12 text-good border-good/30", dot: "bg-good" },
  maybe: { cls: "bg-warn/12 text-warn border-warn/30", dot: "bg-warn" },
  no: { cls: "bg-bad/12 text-bad border-bad/30", dot: "bg-bad" },
  error: { cls: "bg-bad/12 text-bad border-bad/30", dot: "bg-bad" },
  running: { cls: "bg-accent-soft text-accent border-accent/30", dot: "bg-accent animate-pulse" },
  idle: { cls: "bg-subtle text-muted border-border", dot: "bg-muted" },
};

export default function StatusBadge({
  label,
  tone,
  dot = true,
}: {
  label: string;
  tone: keyof typeof STYLES | string;
  dot?: boolean;
}) {
  const s = STYLES[tone] ?? STYLES.idle;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${s.cls}`}>
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />}
      {label}
    </span>
  );
}
