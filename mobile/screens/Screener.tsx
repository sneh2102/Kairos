import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import type { Config } from "../lib/types";
import { Btn, C, Chip, Loading, NumField, Screen, SectionLabel, TextField, ToggleRow } from "../ui";

export default function Screener() {
  const [config, setConfig] = useState<Config | null>(null);
  const [saving, setSaving] = useState(false);
  const [newCompany, setNewCompany] = useState("");

  useEffect(() => { api.getConfig().then(setConfig); }, []);
  if (!config) return <Screen title="Screening rules"><Loading /></Screen>;

  const s = config.screener;
  const set = (patch: Partial<Config["screener"]>) => setConfig({ ...config, screener: { ...s, ...patch } });
  const save = async () => { setSaving(true); try { await api.putConfig(config); } finally { setSaving(false); } };

  return (
    <Screen title="Screening rules">
      <Text style={st.desc}>Rules the Screener Agent uses to rate every scraped job yes / maybe / no.</Text>

      <SectionLabel>Thresholds</SectionLabel>
      <View style={st.row}>
        <View style={{ flex: 1 }}><NumField label="Max years" value={s.max_years_exp} onChangeNumber={(v) => set({ max_years_exp: v })} /></View>
        <View style={{ flex: 1 }}><NumField label="Yes %" value={s.yes_match_pct} onChangeNumber={(v) => set({ yes_match_pct: v })} /></View>
        <View style={{ flex: 1 }}><NumField label="Maybe %" value={s.maybe_match_pct} onChangeNumber={(v) => set({ maybe_match_pct: v })} /></View>
      </View>

      <SectionLabel>Accepted role levels</SectionLabel>
      <View style={st.chips}>
        {["junior", "mid", "senior"].map((level) => (
          <Chip
            key={level}
            label={level}
            active={s.accept_role_levels.includes(level)}
            onPress={() => set({
              accept_role_levels: s.accept_role_levels.includes(level)
                ? s.accept_role_levels.filter((l) => l !== level)
                : [...s.accept_role_levels, level],
            })}
          />
        ))}
      </View>

      <SectionLabel>Skills & keywords</SectionLabel>
      <TextField label="Required skills" value={s.required_skills} multiline onChangeText={(v) => set({ required_skills: v })} />
      <TextField label="Preferred skills" value={s.preferred_skills} multiline onChangeText={(v) => set({ preferred_skills: v })} />
      <TextField label="Reject keywords" value={s.reject_keywords} multiline onChangeText={(v) => set({ reject_keywords: v })} />
      <TextField label="Accept keywords" value={s.accept_keywords} multiline onChangeText={(v) => set({ accept_keywords: v })} />

      <ToggleRow label="Skip jobs already applied to" value={s.skip_applied} onValueChange={(v) => set({ skip_applied: v })} />
      <ToggleRow label="Fuzzy dedup across sites" value={s.fuzzy_dedup} onValueChange={(v) => set({ fuzzy_dedup: v })} />

      <SectionLabel>Blacklisted companies</SectionLabel>
      <View style={st.chips}>
        {s.blacklisted_companies.map((c) => (
          <Pressable key={c} onPress={() => set({ blacklisted_companies: s.blacklisted_companies.filter((x) => x !== c) })} style={st.tag}>
            <Text style={st.tagText}>{c}  ×</Text>
          </Pressable>
        ))}
      </View>
      <View style={st.row}>
        <View style={{ flex: 1 }}>
          <TextField label="" value={newCompany} placeholder="Company name" onChangeText={setNewCompany} />
        </View>
        <Btn label="Add" variant="secondary" onPress={() => {
          if (newCompany.trim()) { set({ blacklisted_companies: [...s.blacklisted_companies, newCompany.trim()] }); setNewCompany(""); }
        }} style={{ height: 46, marginTop: 6 }} />
      </View>

      <Btn label={saving ? "Saving…" : "Save"} variant="primary" disabled={saving} onPress={save} style={{ marginTop: 16 }} />
    </Screen>
  );
}

const st = StyleSheet.create({
  desc: { color: C.muted, fontSize: 13, lineHeight: 19, marginTop: 4 },
  row: { flexDirection: "row", gap: 10, alignItems: "flex-start" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  tag: { backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, borderRadius: 20, paddingVertical: 7, paddingHorizontal: 12 },
  tagText: { color: C.text, fontSize: 13, fontWeight: "600" },
});
