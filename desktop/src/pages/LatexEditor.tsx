import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import type { CustomSection } from "../lib/types";
import PdfViewer from "../components/PdfViewer";

export default function LatexEditor({ kind }: { kind: "job" | "applied" }) {
  const { id } = useParams();
  const recordId = Number(id);
  const navigate = useNavigate();
  const [latexCode, setLatexCode] = useState("");
  const [title, setTitle] = useState("");
  const [compiling, setCompiling] = useState(false);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [previewVersion, setPreviewVersion] = useState(0);
  const [customSections, setCustomSections] = useState<CustomSection[]>([]);
  const [rebuildId, setRebuildId] = useState("");
  const [rebuildMsg, setRebuildMsg] = useState("");
  const [rebuilding, setRebuilding] = useState(false);

  useEffect(() => {
    if (kind === "job") {
      api.getJob(recordId).then((job) => {
        setLatexCode(job.latex_content || "");
        setTitle(`${job.title} @ ${job.company}`);
      });
      api.getResumeData().then((d) => {
        setCustomSections(d.custom_sections);
        setRebuildId(d.custom_sections[0]?.id || "");
      });
    } else {
      api.getApplied(recordId).then((row) => {
        setLatexCode(row.tex_content || "");
        setTitle(`${row.title} @ ${row.company}`);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, recordId]);

  async function rebuildSection() {
    setRebuilding(true);
    setMessage(null);
    try {
      const res = await api.rebuildSection(recordId, rebuildId, rebuildMsg.trim(), latexCode);
      setLatexCode(res.latex);
      setMessage({ text: "Section rebuilt — review, then Compile & Save.", ok: true });
    } catch (e) {
      setMessage({ text: String(e), ok: false });
    } finally {
      setRebuilding(false);
    }
  }

  async function compileAndSave() {
    setCompiling(true);
    setMessage(null);
    try {
      const res =
        kind === "job" ? await api.compileJob(recordId, latexCode) : await api.compileApplied(recordId, latexCode);
      setMessage({ text: res.compiled ? "Compiled and saved." : "Saved — pdflatex unavailable, .tex written instead.", ok: true });
      setPreviewVersion((v) => v + 1);
    } catch (e) {
      setMessage({ text: String(e), ok: false });
    } finally {
      setCompiling(false);
    }
  }

  const previewUrl =
    (kind === "job" ? api.jobResumePdfUrl(recordId) : api.resumePdfUrl(recordId)) + `?v=${previewVersion}`;

  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="flex items-center justify-between">
        <div>
          <button className="text-sm text-accent hover:underline" onClick={() => navigate(-1)}>
            ← Back
          </button>
          <h1 className="text-lg font-semibold text-fg mt-1">LaTeX editor — {title}</h1>
        </div>
        <div className="flex items-center gap-3">
          {message && <span className={`text-xs ${message.ok ? "text-yes" : "text-no"}`}>{message.text}</span>}
          <button className="btn-primary" onClick={compileAndSave} disabled={compiling}>
            {compiling ? "Compiling…" : "Compile & Save"}
          </button>
        </div>
      </div>

      {kind === "job" && customSections.length > 0 && (
        <div className="card flex flex-wrap items-center gap-2 p-2">
          <span className="text-xs text-muted">Rebuild custom section:</span>
          <select
            className="input text-xs py-1 w-auto"
            value={rebuildId}
            onChange={(e) => setRebuildId(e.target.value)}
          >
            {customSections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <input
            className="input text-xs py-1 flex-1 min-w-[12rem]"
            placeholder="Optional instruction (e.g. 'make it more concise') — leave blank to just rebuild"
            value={rebuildMsg}
            onChange={(e) => setRebuildMsg(e.target.value)}
          />
          <button className="btn-secondary text-xs" onClick={rebuildSection} disabled={rebuilding || !rebuildId}>
            {rebuilding ? "Rebuilding…" : "Rebuild"}
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 flex-1 min-h-[75vh]">
        <textarea
          className="input font-mono text-xs resize-none h-full"
          value={latexCode}
          onChange={(e) => setLatexCode(e.target.value)}
          spellCheck={false}
        />
        <div className="h-full">
          {previewVersion > 0 || latexCode ? (
            <PdfViewer url={previewUrl} title="Resume preview" />
          ) : (
            <div className="h-full flex items-center justify-center text-sm text-muted card">
              Compile to see a preview.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
