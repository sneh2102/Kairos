const STYLES: Record<string, string> = {
  yes: "bg-yes/15 text-yes border-yes/40",
  pass: "bg-pass/15 text-yes border-pass/40",
  maybe: "bg-maybe/15 text-maybe border-maybe/40",
  no: "bg-no/15 text-no border-no/40",
  error: "bg-reject/15 text-no border-reject/40",
  running: "bg-accent/15 text-accent border-accent/40",
  idle: "bg-muted/15 text-muted border-muted/40",
};

export default function StatusBadge({ label, tone }: { label: string; tone: keyof typeof STYLES | string }) {
  const cls = STYLES[tone] ?? STYLES.idle;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${cls}`}>
      {label}
    </span>
  );
}
