import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { PromptInfo } from "../lib/types";

export default function Prompts() {
  const [prompts, setPrompts] = useState<Record<string, PromptInfo> | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);

  function load() {
    api.getPrompts().then(setPrompts);
  }

  useEffect(load, []);

  if (!prompts) return <div className="text-sm text-muted">Loading…</div>;

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <div>
        <h1 className="text-lg font-semibold text-gray-100">Prompts</h1>
        <p className="text-sm text-muted">
          Customize the instructions each AI agent uses. The required output format (LaTeX section
          rules / JSON schema) is enforced in code separately and always applies, regardless of what
          you write here — editing a prompt can't break generation.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        {Object.entries(prompts).map(([key, info]) => (
          <div key={key} className="card p-4 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-gray-100">{info.label}</span>
                {info.is_default && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[#21262d] border border-border text-muted">
                    default
                  </span>
                )}
              </div>
              <div className="text-sm text-muted truncate">{info.description}</div>
            </div>
            <button className="btn-secondary shrink-0" onClick={() => setEditingKey(key)}>
              Edit Prompt
            </button>
          </div>
        ))}
      </div>

      {editingKey && prompts[editingKey] && (
        <PromptEditor
          promptKey={editingKey}
          info={prompts[editingKey]}
          onClose={() => setEditingKey(null)}
          onSaved={load}
        />
      )}
    </div>
  );
}

function PromptEditor({
  promptKey,
  info,
  onClose,
  onSaved,
}: {
  promptKey: string;
  info: PromptInfo;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [text, setText] = useState(info.text);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setError("");
    try {
      await api.savePrompt(promptKey, text);
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function resetToDefault() {
    setText(info.default);
    setError("");
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6">
      <div className="card w-full max-w-3xl h-[85vh] flex flex-col p-5 gap-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-100">Editing: {info.label}</h2>
          <button className="text-muted hover:text-gray-100 text-lg leading-none" onClick={onClose}>
            ×
          </button>
        </div>

        {info.placeholders.length > 0 && (
          <div className="text-xs text-muted">
            Available placeholders: {info.placeholders.map((p) => `{${p}}`).join(", ")}
          </div>
        )}

        <div className="text-xs text-[#d29922] bg-[#21262d] border border-border rounded-md px-3 py-2">
          🔒 The required output format is enforced in code and always applies, no matter what you
          write here.
        </div>

        <textarea
          className="input flex-1 resize-none font-mono text-xs leading-relaxed"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />

        {error && <div className="text-sm text-no">⚠ {error}</div>}

        <div className="flex items-center justify-between">
          <button className="btn-secondary" onClick={resetToDefault}>
            Reset to Default
          </button>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button className="btn-primary" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
