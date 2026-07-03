import { HashRouter, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import { EventStreamProvider } from "./lib/eventStream";
import Dashboard from "./pages/Dashboard";
import ScreenerConfig from "./pages/ScreenerConfig";
import Scraper from "./pages/Scraper";
import Build from "./pages/Build";
import ScrapedJobs from "./pages/ScrapedJobs";
import JobDetail from "./pages/JobDetail";
import LatexEditor from "./pages/LatexEditor";
import Applied from "./pages/Applied";
import ResumeData from "./pages/ResumeData";
import Prompts from "./pages/Prompts";
import Settings from "./pages/Settings";
import Logs from "./pages/Logs";

export default function App() {
  return (
    <EventStreamProvider>
      <HashRouter>
        <div className="flex h-screen w-screen overflow-hidden bg-bg">
          <Sidebar />
          <main className="flex-1 overflow-y-auto p-6">
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
              <Route path="/prompts" element={<Prompts />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/logs" element={<Logs />} />
            </Routes>
          </main>
        </div>
      </HashRouter>
    </EventStreamProvider>
  );
}
