import { NavLink } from "react-router-dom";

const ITEMS = [
  { to: "/", label: "Dashboard", icon: "🏠", end: true },
  { to: "/screener-config", label: "Screener Config", icon: "🎯" },
  { to: "/scraper", label: "Scraper", icon: "🔍" },
  { to: "/build", label: "Build", icon: "🛠️" },
  { to: "/scraped-jobs", label: "Scraped Jobs", icon: "📋" },
  { to: "/applied", label: "Applied", icon: "✅" },
  { to: "/resume-data", label: "Resume Data", icon: "📄" },
  { to: "/prompts", label: "Prompts", icon: "✏️" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
  { to: "/logs", label: "Logs", icon: "🪵" },
];

export default function Sidebar() {
  return (
    <nav className="w-56 shrink-0 border-r border-border bg-panel flex flex-col py-4">
      <div className="px-4 pb-4 mb-2 border-b border-border">
        <div className="text-sm font-bold text-gray-100">Job Scraper</div>
        <div className="text-[11px] text-muted">LangGraph pipeline</div>
      </div>
      <div className="flex flex-col gap-0.5 px-2">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive ? "bg-primary text-white" : "text-gray-300 hover:bg-[#21262d]"
              }`
            }
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
