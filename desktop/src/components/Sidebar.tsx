import { NavLink } from "react-router-dom";
import { useEventStream } from "../lib/eventStream";
import ThemeToggle from "./ThemeToggle";

// The four workflow steps are a real sequence — numbering encodes the order you
// actually use them in. Setup and System are supporting areas, no numbers.
const WORKFLOW = [
  { to: "/scraper", label: "Find jobs" },
  { to: "/scraped-jobs", label: "Review jobs" },
  { to: "/build", label: "Build resumes" },
  { to: "/applied", label: "Applications" },
];

const SETUP = [
  { to: "/resume-data", label: "Resume & profile" },
  { to: "/templates", label: "Formats" },
  { to: "/screener-config", label: "Screening rules" },
  { to: "/prompts", label: "AI prompts" },
];

const SYSTEM = [
  { to: "/logs", label: "Activity log" },
  { to: "/settings", label: "Settings" },
  { to: "/setup", label: "Setup wizard" },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center rounded-full px-3.5 py-2 text-sm transition-colors duration-150 ${
    isActive ? "bg-accent-soft text-accent font-medium" : "text-fg-soft hover:bg-subtle hover:text-fg"
  }`;

export default function Sidebar() {
  const { connected } = useEventStream();

  return (
    <nav className="w-60 shrink-0 border-r border-border bg-surface flex flex-col">
      <div className="px-5 pt-6 pb-5">
        <div className="text-[17px] font-semibold text-fg tracking-tight">Job Scraper</div>
        <div className="text-[12px] text-muted mt-0.5">Your applicant pipeline</div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-3 flex flex-col gap-6">
        <NavLink to="/" end className={linkClass}>
          Overview
        </NavLink>

        <Group label="Workflow">
          {WORKFLOW.map((item, i) => (
            <NavLink key={item.to} to={item.to} className={linkClass}>
              {({ isActive }) => (
                <>
                  <span
                    className={`num mr-2.5 flex h-5 w-5 items-center justify-center rounded-full text-[11px] shrink-0 ${
                      isActive ? "bg-accent text-on-accent" : "bg-subtle text-muted"
                    }`}
                  >
                    {i + 1}
                  </span>
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </Group>

        <Group label="Setup">
          {SETUP.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClass}>
              {item.label}
            </NavLink>
          ))}
        </Group>

        <Group label="System">
          {SYSTEM.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClass}>
              {item.label}
            </NavLink>
          ))}
        </Group>
      </div>

      <div className="border-t border-border px-4 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2" title={connected ? "Backend connected" : "Backend not reachable"}>
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-good" : "bg-bad"}`} />
          <span className="text-[12px] text-muted">{connected ? "Connected" : "Offline"}</span>
        </div>
        <ThemeToggle />
      </div>
    </nav>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="eyebrow px-3.5 mb-2">{label}</div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}
