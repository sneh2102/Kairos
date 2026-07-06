import { useTheme } from "../lib/theme";

const SunIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
);

const MoonIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
);

const AutoIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none" />
  </svg>
);

const OPTIONS = [
  { value: "light", label: "Light theme", icon: <SunIcon /> },
  { value: "dark", label: "Dark theme", icon: <MoonIcon /> },
  { value: "system", label: "Match system theme", icon: <AutoIcon /> },
] as const;

export default function ThemeToggle() {
  const { choice, setChoice } = useTheme();
  return (
    <div className="inline-flex items-center gap-0.5 rounded-lg border border-border p-0.5 bg-bg">
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          aria-label={o.label}
          title={o.label}
          aria-pressed={choice === o.value}
          onClick={() => setChoice(o.value)}
          className={`flex items-center justify-center h-6 w-6 rounded-md transition-colors ${
            choice === o.value ? "bg-surface text-accent shadow-card" : "text-muted hover:text-fg"
          }`}
        >
          {o.icon}
        </button>
      ))}
    </div>
  );
}
