import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { TemplateInfo } from "../lib/types";
import PdfViewer from "../components/PdfViewer";

export default function Templates() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [selected, setSelected] = useState<string>("classic");
  const [previewVersion, setPreviewVersion] = useState(0);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string | null } | null>(null);
  const [busy, setBusy] = useState("");

  async function load() {
    const rows = await api.listTemplates();
    setTemplates(rows);
    if (!rows.some((t) => t.id === selected)) setSelected(rows[0]?.id ?? "classic");
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // probe the preview endpoint so a failed compile shows the REAL error, not a broken embed
  useEffect(() => {
    let cancelled = false;
    setPreviewError(null);
    fetch(api.templatePreviewUrl(selected))
      .then(async (r) => {
        if (cancelled) return;
        if (!r.ok) {
          const detail = await r.json().then((b) => b.detail).catch(() => "");
          setPreviewError(detail || "Preview could not be compiled.");
        }
      })
      .catch(() => !cancelled && setPreviewError("Could not reach the backend to build a preview."));
    return () => { cancelled = true; };
  }, [selected, previewVersion]);

  async function activate(id: string) {
    setBusy(id);
    try {
      await api.activateTemplate(id);
      await load();
    } finally {
      setBusy("");
    }
  }

  async function remove(id: string) {
    if (!confirm(`Delete template "${id}"?`)) return;
    await api.deleteTemplate(id);
    await load();
  }

  return (
    <div className="flex gap-4 h-full">
      <div className="w-80 shrink-0 flex flex-col gap-3">
        <div>
          <h1 className="text-lg font-semibold text-fg">Resume Formats</h1>
          <p className="text-sm text-muted">
            Pick the LaTeX format every generated resume uses. Paste your own — missing macros are
            added automatically so generated sections always compile.
          </p>
        </div>

        <button className="btn-primary" onClick={() => setEditing({ id: null })}>
          + Add Format
        </button>

        <div className="flex flex-col gap-2 overflow-y-auto">
          {templates.map((t) => (
            <div
              key={t.id}
              onClick={() => setSelected(t.id)}
              className={`card p-3 cursor-pointer ${selected === t.id ? "border-accent" : "hover:border-accent/50"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-fg truncate">{t.name}</div>
                {t.active && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary text-white shrink-0">ACTIVE</span>
                )}
              </div>
              <div className="flex gap-2 mt-2">
                {!t.active && (
                  <button
                    className="btn-secondary text-xs px-2 py-1"
                    disabled={busy === t.id}
                    onClick={(e) => { e.stopPropagation(); activate(t.id); }}
                  >
                    {busy === t.id ? "…" : "Use this format"}
                  </button>
                )}
                {!t.builtin && (
                  <>
                    <button className="btn-secondary text-xs px-2 py-1"
                            onClick={(e) => { e.stopPropagation(); setEditing({ id: t.id }); }}>
                      Edit
                    </button>
                    <button className="btn-danger text-xs px-2 py-1"
                            onClick={(e) => { e.stopPropagation(); remove(t.id); }}>
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="text-sm text-muted mb-2">
          Preview — sample resume rendered in "{templates.find((t) => t.id === selected)?.name ?? selected}"
        </div>
        {previewError ? (
          <div className="card flex-1 flex flex-col items-center justify-center gap-3 p-8 text-center">
            <div className="text-sm text-fg font-medium">Preview could not be compiled</div>
            <div className="text-xs text-no font-mono max-w-xl break-words whitespace-pre-wrap">{previewError}</div>
            <div className="text-xs text-muted max-w-md">
              Fix the LaTeX in this format, or install the missing LaTeX package/font via your TeX
              distribution's package manager, then reopen this tab.
            </div>
          </div>
        ) : (
          <PdfViewer url={`${api.templatePreviewUrl(selected)}?v=${previewVersion}`} title="Format preview" />
        )}
      </div>

      {editing && (
        <TemplateEditor
          templateId={editing.id}
          onClose={() => setEditing(null)}
          onSaved={async (id) => {
            setEditing(null);
            await load();
            setSelected(id);
            setPreviewVersion((v) => v + 1);
          }}
        />
      )}
    </div>
  );
}

function TemplateEditor({
  templateId,
  onClose,
  onSaved,
}: {
  templateId: string | null;
  onClose: () => void;
  onSaved: (id: string) => void;
}) {
  const [name, setName] = useState(templateId ?? "");
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (templateId) api.getTemplate(templateId).then((t) => setContent(t.content));
  }, [templateId]);

  async function save() {
    setSaving(true);
    setError("");
    try {
      if (templateId) {
        await api.updateTemplate(templateId, content);
        onSaved(templateId);
      } else {
        const res = await api.addTemplate(name, content);
        onSaved(res.id);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6">
      <div className="card w-full max-w-3xl h-[85vh] flex flex-col p-5 gap-3">
        <h2 className="font-semibold text-fg">
          {templateId ? `Edit format: ${templateId}` : "Add resume format"}
        </h2>

        {!templateId && (
          <input className="input" placeholder="Format name (e.g. Modern Two-Column)"
                 value={name} onChange={(e) => setName(e.target.value)} />
        )}

        <div className="text-xs text-muted">
          Paste a full .tex resume (e.g. from Overleaf) or just its preamble — everything before
          \begin{"{"}document{"}"} is used. Macros the generator needs (\resumeItem, \resumeSubheading, …)
          are added automatically if your format doesn't define them.
        </div>

        <textarea
          className="input flex-1 resize-none font-mono text-xs leading-relaxed"
          placeholder={"\\documentclass[letterpaper,11pt]{article}\n\\usepackage{...}\n..."}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />

        {error && <div className="text-sm text-bad">{error}</div>}

        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={save} disabled={saving || (!templateId && !name.trim())}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
