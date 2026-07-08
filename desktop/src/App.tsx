import { useEffect, useState } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import { api } from "./lib/api";
import { EventStreamProvider } from "./lib/eventStream";
import { ThemeProvider } from "./lib/theme";
import Dashboard from "./pages/Dashboard";
import ScreenerConfig from "./pages/ScreenerConfig";
import Scraper from "./pages/Scraper";
import Build from "./pages/Build";
import ScrapedJobs from "./pages/ScrapedJobs";
import JobDetail from "./pages/JobDetail";
import LatexEditor from "./pages/LatexEditor";
import Applied from "./pages/Applied";
import ResumeData from "./pages/ResumeData";
import Templates from "./pages/Templates";
import Prompts from "./pages/Prompts";
import Settings from "./pages/Settings";
import Setup from "./pages/Setup";
import Logs from "./pages/Logs";

export default function App() {
  return (
    <ThemeProvider>
      <EventStreamProvider>
        <HashRouter>
          <AppShell />
        </HashRouter>
      </EventStreamProvider>
    </ThemeProvider>
  );
}

function AppShell() {
  const [onboarded, setOnboarded] = useState<boolean | null>(null);
  const location = useLocation();

  useEffect(() => {
    api.getConfig().then((c) => setOnboarded(!!c.onboarded)).catch(() => setOnboarded(true));
  }, []);

  const needsSetup = onboarded === false && location.pathname !== "/setup";

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg">
      <Sidebar />
      <main className="flex-1 overflow-y-auto px-8 py-7">
        {onboarded === null ? null : needsSetup ? (
          <Navigate to="/setup" replace />
        ) : (
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/screener-config" element={<ScreenerConfig />} />
            <Route path="/scraper" element={<Scraper />} />
            <Route path="/build" element={<Build />} />
            <Route path="/scraped-jobs" element={<ScrapedJobs />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
            <Route path="/jobs/:id/editor" element={<LatexEditor kind="job" />} />
            <Route path="/applied/:id/editor" element={<LatexEditor kind="applied" />} />
            <Route path="/applied" element={<Applied />} />
            <Route path="/resume-data" element={<ResumeData />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/prompts" element={<Prompts />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/setup" element={<Setup onDone={() => setOnboarded(true)} />} />
            <Route path="/logs" element={<Logs />} />
          </Routes>
        )}
      </main>
    </div>
  );
}
