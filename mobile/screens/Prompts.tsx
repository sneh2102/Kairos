import { useEffect, useState } from "react";
import { Modal, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "../lib/api";
import type { PromptInfo } from "../lib/types";
import { Badge, Btn, C, Card, Loading, Screen, TOP } from "../ui";

export default function Prompts() {
  const [prompts, setPrompts] = useState<Record<string, PromptInfo> | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const load = () => api.getPrompts().then(setPrompts);
  useEffect(() => { load(); }, []);

  if (!prompts) return <Screen title="AI prompts"><Loading /></Screen>;

  return (
    <Screen title="AI prompts">
      <Text style={st.desc}>
        Customize each agent's instructions. The required output format (LaTeX / JSON) is enforced in code
        and always applies — editing a prompt can't break generation.
      </Text>
      {Object.entries(prompts).map(([key, info]) => (
        <Card key={key} style={{ marginTop: 12 }}>
          <View style={st.top}>
            <Text style={st.label}>{info.label}</Text>
            {info.is_default && <Badge label="default" color={C.faint} />}
          </View>
          <Text style={st.sub}>{info.description}</Text>
          <Btn label="Edit prompt" variant="secondary" onPress={() => setEditing(key)} style={{ marginTop: 10 }} />
        </Card>
      ))}
      {editing && prompts[editing] && (
        <Editor promptKey={editing} info={prompts[editing]} onClose={() => setEditing(null)} onSaved={load} />
      )}
    </Screen>
  );
}

function Editor({ promptKey, info, onClose, onSaved }: { promptKey: string; info: PromptInfo; onClose: () => void; onSaved: () => void }) {
  const [text, setText] = useState(info.text);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setSaving(true); setError("");
    try { await api.savePrompt(promptKey, text); onSaved(); onClose(); }
    catch (e) { setError(String(e)); }
    finally { setSaving(false); }
  };

  return (
    <Modal visible animationType="slide" onRequestClose={onClose}>
      <View style={[st.modal, { paddingTop: TOP + 12 }]}>
        <Text style={st.modalTitle}>Editing: {info.label}</Text>
        {info.placeholders.length > 0 && (
          <Text style={st.hint}>Placeholders: {info.placeholders.map((p) => `{${p}}`).join(", ")}</Text>
        )}
        <ScrollView style={st.editorScroll} keyboardShouldPersistTaps="handled">
          <TextInput style={st.editor} value={text} onChangeText={setText} multiline autoCapitalize="none" autoCorrect={false} />
        </ScrollView>
        {error ? <Text style={st.err}>{error}</Text> : null}
        <View style={st.row}>
          <Btn label="Reset to default" variant="secondary" onPress={() => setText(info.default)} style={{ flex: 1 }} />
          <Btn label={saving ? "Saving…" : "Save"} variant="primary" disabled={saving} onPress={save} style={{ flex: 1 }} />
        </View>
        <Btn label="Cancel" variant="secondary" onPress={onClose} style={{ marginTop: 8 }} />
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  desc: { color: C.muted, fontSize: 13, lineHeight: 19, marginTop: 4 },
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  label: { color: C.text, fontSize: 15, fontWeight: "700", flex: 1 },
  sub: { color: C.muted, fontSize: 13, marginTop: 4 },
  modal: { flex: 1, backgroundColor: C.bg, padding: 16 },
  modalTitle: { color: C.text, fontSize: 18, fontWeight: "800" },
  hint: { color: C.faint, fontSize: 12, marginTop: 8 },
  editorScroll: { flex: 1, marginTop: 10 },
  editor: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 12, color: C.text, fontSize: 12, fontFamily: "monospace", minHeight: 320, textAlignVertical: "top" },
  err: { color: C.red, marginTop: 8 },
  row: { flexDirection: "row", gap: 10, marginTop: 12 },
});
