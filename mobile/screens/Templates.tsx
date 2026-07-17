import { useEffect, useState } from "react";
import { Alert, Modal, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { api, downloadPdf } from "../lib/api";
import type { TemplateInfo } from "../lib/types";
import { Badge, Btn, C, Card, Loading, Screen, TOP } from "../ui";

export default function Templates() {
  const [templates, setTemplates] = useState<TemplateInfo[] | null>(null);
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState<{ id: string | null } | null>(null);

  const load = () => api.listTemplates().then(setTemplates);
  useEffect(() => { load(); }, []);

  if (!templates) return <Screen title="Formats"><Loading /></Screen>;

  const activate = async (id: string) => { setBusy(id); try { await api.activateTemplate(id); await load(); } finally { setBusy(""); } };
  const remove = (id: string) =>
    Alert.alert("Delete format?", `"${id}" can't be undone.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => { await api.deleteTemplate(id); load(); } },
    ]);
  const preview = (id: string) =>
    downloadPdf(`/api/templates/${id}/preview.pdf`, `format_${id}`).catch((e) => Alert.alert("Preview failed", String(e)));

  return (
    <Screen title="Formats">
      <Text style={st.desc}>The LaTeX format every generated resume uses. Paste your own — missing macros are added automatically so generated sections always compile.</Text>
      <Btn label="+ Add format" variant="primary" onPress={() => setEditing({ id: null })} style={{ marginTop: 12 }} />

      {templates.map((t) => (
        <Card key={t.id} style={{ marginTop: 12 }}>
          <View style={st.top}>
            <Text style={st.name}>{t.name}</Text>
            {t.active && <Badge label="ACTIVE" color={C.green} />}
          </View>
          <View style={st.actions}>
            {!t.active && <Btn label={busy === t.id ? "…" : "Use this"} variant="secondary" disabled={busy === t.id} onPress={() => activate(t.id)} style={{ flex: 1 }} />}
            <Btn label="Preview" variant="secondary" onPress={() => preview(t.id)} style={{ flex: 1 }} />
            {!t.builtin && <Btn label="Edit" variant="secondary" onPress={() => setEditing({ id: t.id })} style={{ flex: 1 }} />}
            {!t.builtin && <Btn label="Delete" variant="danger" onPress={() => remove(t.id)} style={{ flex: 1 }} />}
          </View>
        </Card>
      ))}
      <Text style={st.hint}>Preview opens the sample resume PDF via the share sheet.</Text>

      {editing && (
        <Editor templateId={editing.id} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
      )}
    </Screen>
  );
}

function Editor({ templateId, onClose, onSaved }: { templateId: string | null; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(templateId ?? "");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { if (templateId) api.getTemplate(templateId).then((t) => setContent(t.content)); }, [templateId]);

  const save = async () => {
    setSaving(true); setError("");
    try {
      if (templateId) await api.updateTemplate(templateId, content);
      else await api.addTemplate(name, content);
      onSaved();
    } catch (e) { setError(String(e)); } finally { setSaving(false); }
  };

  return (
    <Modal visible animationType="slide" onRequestClose={onClose}>
      <View style={[st.modal, { paddingTop: TOP + 12 }]}>
        <Text style={st.modalTitle}>{templateId ? `Edit format: ${templateId}` : "Add resume format"}</Text>
        {!templateId && (
          <TextInput style={st.nameInput} value={name} onChangeText={setName} placeholder="Format name (e.g. Modern Two-Column)" placeholderTextColor={C.faint} />
        )}
        <Text style={st.hint}>Paste a full .tex resume or its preamble — everything before \begin{"{"}document{"}"} is used. Needed macros are added automatically.</Text>
        <ScrollView style={{ flex: 1, marginTop: 10 }} keyboardShouldPersistTaps="handled">
          <TextInput style={st.editor} value={content} onChangeText={setContent} multiline autoCapitalize="none" autoCorrect={false} placeholder={"\\documentclass[letterpaper,11pt]{article}\n..."} placeholderTextColor={C.faint} />
        </ScrollView>
        {error ? <Text style={st.err}>{error}</Text> : null}
        <View style={st.row}>
          <Btn label="Cancel" variant="secondary" onPress={onClose} style={{ flex: 1 }} />
          <Btn label={saving ? "Saving…" : "Save"} variant="primary" disabled={saving || (!templateId && !name.trim())} onPress={save} style={{ flex: 1 }} />
        </View>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  desc: { color: C.muted, fontSize: 13, lineHeight: 19, marginTop: 4 },
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  name: { color: C.text, fontSize: 15, fontWeight: "700", flex: 1 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 },
  hint: { color: C.faint, fontSize: 12, marginTop: 12 },
  modal: { flex: 1, backgroundColor: C.bg, padding: 16 },
  modalTitle: { color: C.text, fontSize: 18, fontWeight: "800" },
  nameInput: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, color: C.text, fontSize: 15, marginTop: 12 },
  editor: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 12, color: C.text, fontSize: 12, fontFamily: "monospace", minHeight: 320, textAlignVertical: "top" },
  err: { color: C.red, marginTop: 8 },
  row: { flexDirection: "row", gap: 10, marginTop: 12 },
});
