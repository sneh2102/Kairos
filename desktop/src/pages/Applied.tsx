import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { AppliedRow } from "../lib/types";
import PdfViewer from "../components/PdfViewer";
import StatusBadge from "../components/StatusBadge";

export default function Applied() {
  const [rows, setRows] = useState<AppliedRow[]>([]);
  const [selected, setSelected] = useState<AppliedRow | null>(null);
  const [tab, setTab] = useState<"resume" | "cover" | "details">("resume");
  const [q, setQ] = useState("");
  const [driveMsg, setDriveMsg] = useState<string | null>(null);
  const navigate = useNavigate();

  const filteredRows = rows.filter((row) => {
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    return (
      row.company.toLowerCase().includes(needle) ||
      row.title.toLowerCase().includes(needle) ||
      row.applied_date.toLowerCase().includes(needle)
    );
  });

  function load() {
    api.listApplied().then(setRows);
  }

  useEffect(load, []);

  async function remove(id: number) {
    await api.deleteApplied(id);
    if (selected?.id === id) setSelected(null);
    load();
  }

  async function unapply(id: number) {
    await api.unapply(id);
    if (selected?.id === id) setSelected(null);
    load();
  }

  async function uploadToDrive(id: number) {
    setDriveMsg(null);
    try {
      await api.uploadAppliedToDrive(id);
      setDriveMsg("Uploaded to Google Drive.");
    } catch (e) {
      setDriveMsg(String(e));
    }
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-fg">Applied</h1>
          <p className="text-sm text-muted">{rows.length} applications on file.</p>
        </div>
        <button className="btn-secondary" onClick={load}>
          Refresh
        </button>
      </div>

      <input
        className="input"
        placeholder="Search by company, position, or date..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.1fr] gap-4 flex-1 min-h-0">
        <div className="flex flex-col gap-2 overflow-y-auto pr-1">
          {rows.length === 0 && <div className="text-sm text-muted">No applications yet.</div>}
          {rows.length > 0 && filteredRows.length === 0 && (
            <div className="text-sm text-muted">No applications match "{q}".</div>
          )}
          {filteredRows.map((row) => (
            <div
              key={row.id}
              onClick={() => {
                setSelected(row);
                setTab("resume");
                api.getApplied(row.id).then(setSelected);
              }}
              className={`card p-3 cursor-pointer transition-colors ${
                selected?.id === row.id ? "border-accent" : "hover:border-accent/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-fg text-sm">{row.title}</div>
                  <div className="text-xs text-muted">
                    {row.company} · {row.location} · {row.applied_date}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge label={`ATS ${row.ats_score}`} tone={row.ats_score >= 85 ? "pass" : "maybe"} />
                  <button
                    className="text-xs text-no hover:underline"
                    onClick={(e) => {
                      e.stopPropagation();
                      remove(row.id);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="card flex flex-col min-h-[70vh]">
          {selected ? (
            <>
              <div className="flex items-center justify-between border-b border-border">
                <div className="flex">
                  <TabButton active={tab === "resume"} onClick={() => setTab("resume")} label="Resume" />
                  <TabButton active={tab === "cover"} onClick={() => setTab("cover")} label="Cover letter" />
                  <TabButton active={tab === "details"} onClick={() => setTab("details")} label="Details" />
                </div>
                <div className="flex gap-2 pr-2">
                  {tab !== "details" && (
                    <a
                      href={tab === "resume" ? api.resumePdfUrl(selected.id) : api.coverPdfUrl(selected.id)}
                      download
                      className="text-xs text-accent hover:underline"
                    >
                      Download
                    </a>
                  )}
                  <button className="text-xs text-accent hover:underline" onClick={() => navigate(`/applied/${selected.id}/editor`)}>
                    Edit LaTeX
                  </button>
                  <button className="text-xs text-accent hover:underline" onClick={() => uploadToDrive(selected.id)}>
                    Upload to Drive
                  </button>
                  <button className="text-xs text-maybe hover:underline" onClick={() => unapply(selected.id)}>
                    Unapply
                  </button>
                </div>
              </div>
              {driveMsg && <div className="text-xs text-yes px-3 pt-2">{driveMsg}</div>}
              <div className="flex-1 p-2">
                {tab === "details" ? (
                  <div className="p-3 text-sm text-fg-soft space-y-2 overflow-y-auto h-full">
                    <div><span className="text-muted">Years required:</span> {selected.years_required || "—"}</div>
                    <div><span className="text-muted">Role level:</span> {selected.role_level || "—"}</div>
                    <div><span className="text-muted">Skills match:</span> {selected.skills_match_pct || "—"}%</div>
                    <div><span className="text-muted">Site:</span> {selected.site || "—"}</div>
                    {selected.job_url && (
                      <div>
                        <a href={selected.job_url} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                          Original posting
                        </a>
                      </div>
                    )}
                    <div className="pt-2">
                      <div className="text-muted mb-1">Job description</div>
                      <p className="whitespace-pre-wrap text-muted">{selected.description || "—"}</p>
                    </div>
                  </div>
                ) : (
                  <PdfViewer
                    url={tab === "resume" ? api.resumePdfUrl(selected.id) : api.coverPdfUrl(selected.id)}
                    title={tab === "resume" ? "Resume" : "Cover letter"}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-sm text-muted">
              Select an application to preview its PDFs.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm border-b-2 -mb-px ${
        active ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg-soft"
      }`}
    >
      {label}
    </button>
  );
}
