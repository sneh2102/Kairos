import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import type { Config } from "../lib/types";
import { Btn, C, Loading, NumField, Screen, SectionLabel, Tabs, TextField, ToggleRow } from "../ui";

const TABS = [
  { key: "model", label: "Model" },
  { key: "keys", label: "API keys" },
  { key: "prompt", label: "Screener prompt" },
  { key: "scheduler", label: "Scheduler" },
];

export default function Settings() {
  const [config, setConfig] = useState<Config | null>(null);
  const [tab, setTab] = useState("model");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.getConfig().then(setConfig); }, []);
  if (!config) return <Screen title="Settings"><Loading /></Screen>;

  const save = async () => {
    setSaving(true); setSaved(false);
    try { await api.putConfig(config); setSaved(true); } finally { setSaving(false); }
  };

  return (
    <Screen title="Settings" right={saved ? <Text style={st.saved}>Saved</Text> : undefined}>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "model" && <ModelTab config={config} setConfig={setConfig} />}
      {tab === "keys" && <KeysTab />}
      {tab === "prompt" && <PromptTab config={config} setConfig={setConfig} />}
      {tab === "scheduler" && <SchedulerTab config={config} setConfig={setConfig} />}
      {tab !== "keys" && <Btn label={saving ? "Saving…" : "Save changes"} variant="primary" disabled={saving} onPress={save} style={{ marginTop: 18 }} />}
    </Screen>
  );
}

function ModelTab({ config, setConfig }: { config: Config; setConfig: (c: Config) => void }) {
  const m = config.model;
  const set = (patch: Partial<Config["model"]>) => setConfig({ ...config, model: { ...m, ...patch } });
  return (
    <View style={{ marginTop: 12 }}>
      <TextField label="Screening model" value={m.scraping} onChangeText={(v) => set({ scraping: v })} autoCapitalize="none" />
      <TextField label="Resume / ATS model" value={m.pipeline} onChangeText={(v) => set({ pipeline: v })} autoCapitalize="none" />
      <NumField label="Temperature (×100)" value={Math.round(m.temperature * 100)} onChangeNumber={(v) => set({ temperature: v / 100 })} />
      <NumField label="Context window" value={m.num_ctx} onChangeNumber={(v) => set({ num_ctx: v })} />
      <TextField label="GitHub token (optional)" value={config.github?.token ?? ""} onChangeText={(v) => setConfig({ ...config, github: { token: v } })} autoCapitalize="none" />
    </View>
  );
}

function KeysTab() {
  const [keys, setKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.getOllamaKeys().then((r) => setKeys(r.keys)).finally(() => setLoading(false)); }, []);
  if (loading) return <Loading />;

  const save = async () => {
    setSaving(true); setSaved(false);
    const cleaned = keys.map((k) => k.trim()).filter(Boolean);
    try { await api.putOllamaKeys(cleaned); setKeys(cleaned); setSaved(true); } finally { setSaving(false); }
  };

  return (
    <View style={{ marginTop: 12 }}>
      <Text style={st.hint}>Ollama API keys, tried in order — when one hits its rate limit the pipeline rotates to the next.</Text>
      {keys.map((k, i) => (
        <View key={i} style={st.keyRow}>
          <View style={{ flex: 1 }}>
            <TextField label="" value={k} placeholder={`Key ${i + 1}`} autoCapitalize="none" autoCorrect={false}
              onChangeText={(v) => setKeys((prev) => prev.map((x, idx) => (idx === i ? v : x)))} />
          </View>
          <Btn label="✕" variant="danger" onPress={() => setKeys((prev) => prev.filter((_, idx) => idx !== i))} style={{ height: 46, marginTop: 6, paddingHorizontal: 16 }} />
        </View>
      ))}
      <View style={st.keyRow}>
        <Btn label="+ Add key" variant="secondary" onPress={() => setKeys((prev) => [...prev, ""])} style={{ flex: 1 }} />
        <Btn label={saving ? "Saving…" : "Save keys"} variant="primary" disabled={saving} onPress={save} style={{ flex: 1 }} />
      </View>
      {saved && <Text style={st.saved}>Saved</Text>}
    </View>
  );
}

function PromptTab({ config, setConfig }: { config: Config; setConfig: (c: Config) => void }) {
  return (
    <View style={{ marginTop: 12 }}>
      <Text style={st.hint}>The Screener Agent's prompt — the only config-driven one. Writer agents use fixed backend prompts.</Text>
      <TextField label="" value={config.prompts?.job_screener ?? ""} multiline autoCapitalize="none"
        onChangeText={(v) => setConfig({ ...config, prompts: { ...config.prompts, job_screener: v } })} />
    </View>
  );
}

function SchedulerTab({ config, setConfig }: { config: Config; setConfig: (c: Config) => void }) {
  const sched = config.scheduler ?? { enabled: false, time: "08:00" };
  const set = (patch: Partial<{ enabled: boolean; time: string }>) => setConfig({ ...config, scheduler: { ...sched, ...patch } });
  return (
    <View style={{ marginTop: 12 }}>
      <SectionLabel>Daily scrape</SectionLabel>
      <ToggleRow label="Run the scraper automatically every day" value={sched.enabled} onValueChange={(v) => set({ enabled: v })} />
      <TextField label="Time (24h, local)" value={sched.time} onChangeText={(v) => set({ time: v })} placeholder="08:00" />
    </View>
  );
}

const st = StyleSheet.create({
  saved: { color: C.green, fontSize: 12, fontWeight: "700" },
  hint: { color: C.muted, fontSize: 13, lineHeight: 19, marginBottom: 12 },
  keyRow: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
});
