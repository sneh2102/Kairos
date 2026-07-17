import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "../lib/api";
import { savePdfToPhone } from "../lib/deviceStore";
import { Btn, C, Screen, useNav } from "../ui";

// Edit the résumé .tex, compile it on the PC (same endpoint the desktop editor
// uses), then save the resulting PDF to the phone. No inline PDF preview: Expo
// Go can't render PDFs without a native lib, so we mirror it to the device and
// let the system viewer open it instead.
export default function LatexEditor({ id, source }: { id: number; source: "jobs" | "applied" }) {
  const isJob = source === "jobs";
  const nav = useNav();
  const [code, setCode] = useState("");
  const [meta, setMeta] = useState<{ company: string; title: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    (isJob ? api.getJob(id) : api.getApplied(id))
      .then((r: any) => {
        setCode((isJob ? r.latex_content : r.tex_content) || "");
        setMeta({ company: r.company, title: r.title });
      })
      .catch((e) => setMsg({ text: String(e), ok: false }))
      .finally(() => setLoading(false));
  }, [id, source]);

  const compile = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = isJob ? await api.compileJob(id, code) : await api.compileApplied(id, code);
      setMsg({ text: res.compiled ? "Compiled and saved on your PC." : "Saved — pdflatex unavailable, .tex written instead.", ok: true });
    } catch (e) {
      setMsg({ text: String(e), ok: false });
    } finally {
      setBusy(false);
    }
  };

  const savePdf = async () => {
    if (!meta) return;
    setBusy(true);
    try {
      const cfg = await api.getConfig();
      const rel = await savePdfToPhone(`/api/${isJob ? "jobs" : "outputs"}/${id}/resume.pdf`, {
        company: meta.company,
        title: meta.title,
        filename: cfg.pipeline.resume_filename,
      });
      const where = Platform.OS === "android" ? "your chosen folder" : "Files → On My iPhone → Kairos";
      Alert.alert("Saved to phone", `${rel}\n\nin ${where}.`);
    } catch (e: any) {
      Alert.alert("Failed", e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Screen title="LaTeX editor" onBack={nav.back}><ActivityIndicator style={{ marginTop: 40 }} color={C.accent} /></Screen>;

  return (
    <Screen title="LaTeX editor" onBack={nav.back} scroll={false}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={st.wrap}>
          {meta && <Text style={st.sub} numberOfLines={1}>{meta.title} @ {meta.company}</Text>}
          <TextInput
            style={st.editor}
            value={code}
            onChangeText={setCode}
            multiline
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            placeholder="% LaTeX résumé source"
            placeholderTextColor={C.faint}
          />
          {msg && <Text style={[st.msg, { color: msg.ok ? C.green : C.red }]}>{msg.text}</Text>}
          <View style={st.row}>
            <Btn label={busy ? "Compiling…" : "Compile & Save"} variant="primary" disabled={busy} onPress={compile} style={{ flex: 1 }} />
            <Btn label="📄 Save PDF" variant="secondary" disabled={busy} onPress={savePdf} style={{ flex: 1 }} />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const st = StyleSheet.create({
  wrap: { flex: 1, padding: 16, gap: 10 },
  sub: { color: C.sub, fontSize: 14, fontWeight: "600" },
  editor: {
    flex: 1,
    backgroundColor: C.surface,
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 12,
    padding: 12,
    color: C.text,
    fontSize: 12,
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    textAlignVertical: "top",
  },
  msg: { fontSize: 13 },
  row: { flexDirection: "row", gap: 10 },
});
