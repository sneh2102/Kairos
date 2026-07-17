import { useEffect, useMemo, useState } from "react";
import { Alert, FlatList, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { api } from "../lib/api";
import type { JobRow } from "../lib/types";
import { Badge, Btn, C, Chip, Screen, TextField, ToggleRow, scoreColor, useNav } from "../ui";

const FILTERS = ["all", "yes", "maybe", "no"] as const;
const PROVINCES: Record<string, string> = {
  AB: "Alberta", BC: "British Columbia", MB: "Manitoba", NB: "New Brunswick", NL: "Newfoundland and Labrador",
  NS: "Nova Scotia", NT: "Northwest Territories", NU: "Nunavut", ON: "Ontario", PE: "Prince Edward Island",
  QC: "Quebec", SK: "Saskatchewan", YT: "Yukon",
};
function provinceOf(location: string): string {
  const loc = (location || "").toUpperCase();
  for (const [code, name] of Object.entries(PROVINCES)) {
    if (new RegExp(`\\b${code}\\b`).test(loc) || loc.includes(name.toUpperCase())) return code;
  }
  return "";
}
function yearsOf(years: string): number {
  const m = (years || "").match(/\d+(\.\d+)?/);
  return m ? parseFloat(m[0]) : -1;
}

export default function ReviewJobs() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [site, setSite] = useState("");
  const [province, setProvince] = useState("");
  const [resumeOnly, setResumeOnly] = useState(false);
  const [sortYears, setSortYears] = useState<"" | "asc" | "desc">("");
  const [showAdd, setShowAdd] = useState(false);
  const nav = useNav();

  const load = async () => {
    setLoading(true);
    try {
      setJobs(await api.listJobs({ verdict: filter === "all" ? "" : filter, q }));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
  }, [filter]);

  const sites = useMemo(() => [...new Set(jobs.map((j) => j.site).filter(Boolean))].sort(), [jobs]);
  const provinces = useMemo(() => [...new Set(jobs.map((j) => provinceOf(j.location)).filter(Boolean))].sort(), [jobs]);
  const visible = useMemo(() => {
    const rows = jobs.filter(
      (j) => (!site || j.site === site) && (!province || provinceOf(j.location) === province) && (!resumeOnly || !!j.latex_content)
    );
    if (sortYears) {
      rows.sort((a, b) => {
        const ya = yearsOf(a.years_required), yb = yearsOf(b.years_required);
        if (ya < 0 || yb < 0) return (ya < 0 ? 1 : 0) - (yb < 0 ? 1 : 0);
        return sortYears === "asc" ? ya - yb : yb - ya;
      });
    }
    return rows;
  }, [jobs, site, province, resumeOnly, sortYears]);

  const cleanup = () => {
    const act = (fn: () => Promise<{ removed: number }>, msg: string) =>
      Alert.alert("Confirm", msg, [
        { text: "Cancel", style: "cancel" },
        { text: "Remove", style: "destructive", onPress: async () => { const r = await fn(); Alert.alert("Done", `Removed ${r.removed} job(s).`); load(); } },
      ]);
    Alert.alert("Clean up", "Remove jobs from the list", [
      { text: "Remove 'No' verdicts", onPress: () => act(api.removeNoJobs, "Remove every job rated No?") },
      { text: "Remove not applied", onPress: () => act(api.removeNotAppliedJobs, "Remove every job you haven't applied to?") },
      { text: "Remove blacklisted", onPress: () => act(api.removeBlacklistedJobs, "Remove jobs from blacklisted companies?") },
      { text: "Remove ALL", style: "destructive", onPress: () => act(api.removeAllJobs, "Remove ALL jobs? Can't be undone.") },
      { text: "Cancel", style: "cancel" },
    ]);
  };

  const header = (
    <View>
      <View style={st.searchRow}>
        <TextInput style={st.search} placeholder="Search title/company…" placeholderTextColor={C.faint} value={q} onChangeText={setQ} onSubmitEditing={load} returnKeyType="search" />
        <Btn label="Add" onPress={() => setShowAdd(true)} style={{ paddingHorizontal: 16 }} />
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={st.chipRow}>
        {FILTERS.map((f) => <Chip key={f} label={f} active={filter === f} onPress={() => setFilter(f)} />)}
      </ScrollView>
      {(sites.length > 1 || provinces.length > 0) && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={st.chipRow}>
          <Chip label="All boards" active={!site} onPress={() => setSite("")} />
          {sites.map((s) => <Chip key={s} label={s} active={site === s} onPress={() => setSite(site === s ? "" : s)} />)}
          {provinces.map((p) => <Chip key={p} label={PROVINCES[p]} active={province === p} onPress={() => setProvince(province === p ? "" : p)} />)}
        </ScrollView>
      )}
      <View style={st.filterRow}>
        <Chip label={sortYears === "asc" ? "Years ↑" : sortYears === "desc" ? "Years ↓" : "Sort: default"} active={!!sortYears} onPress={() => setSortYears(sortYears === "" ? "asc" : sortYears === "asc" ? "desc" : "")} />
        <Chip label="Resume generated" active={resumeOnly} onPress={() => setResumeOnly(!resumeOnly)} />
        <Chip label="Clean up" onPress={cleanup} />
      </View>
    </View>
  );

  return (
    <Screen title="Review jobs" scroll={false}>
      <FlatList
        data={visible}
        keyExtractor={(j) => String(j.id)}
        ListHeaderComponent={header}
        contentContainerStyle={{ padding: 16 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.accent} />}
        ListEmptyComponent={<Text style={st.empty}>{loading ? "Loading…" : "No jobs match. Run a scrape or add one."}</Text>}
        renderItem={({ item }) => {
          const match = scoreColor(item.skills_match_pct);
          return (
            <Pressable style={({ pressed }) => [st.tile, pressed && { opacity: 0.7 }]} onPress={() => nav.go({ name: "job", id: item.id, source: "jobs" })}>
              <View style={st.tileTop}>
                <Badge label={(item.ai_recommendation || "?").toUpperCase()} color={item.ai_recommendation === "yes" ? C.green : item.ai_recommendation === "maybe" ? C.amber : C.red} />
                {item.latex_content ? <Badge label={`ATS ${item.ats_score}`} color={scoreColor(item.ats_score) ?? C.muted} /> : null}
              </View>
              <Text style={st.tileTitle} numberOfLines={2}>{item.title}</Text>
              <Text style={st.tileCompany} numberOfLines={1}>{item.company}</Text>
              <Text style={st.tileMeta} numberOfLines={1}>{item.location || "Location not listed"}</Text>
              <View style={st.tileBottom}>
                <Text style={st.tileSite}>{item.site}</Text>
                {match && <Text style={[st.tileMatch, { color: match }]}>{item.skills_match_pct}% match</Text>}
              </View>
            </Pressable>
          );
        }}
      />
      {showAdd && <AddJobModal onClose={() => setShowAdd(false)} onAdded={(v) => { setShowAdd(false); Alert.alert("Screened", `Verdict: ${v.toUpperCase()}`); load(); }} />}
    </Screen>
  );
}

function AddJobModal({ onClose, onAdded }: { onClose: () => void; onAdded: (verdict: string) => void }) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const canSubmit = title.trim() && company.trim() && description.trim();

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const row = await api.addManualJob({ title: title.trim(), company: company.trim(), location: location.trim(), job_url: jobUrl.trim(), description: description.trim() });
      onAdded(row.ai_recommendation);
    } catch (e) {
      Alert.alert("Failed", String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal animationType="slide" transparent onRequestClose={onClose}>
      <View style={st.modalWrap}>
        <View style={st.modal}>
          <Text style={st.modalTitle}>Add a job posting</Text>
          <Text style={st.modalSub}>Runs through the same Screener Agent as a scraped job.</Text>
          <ScrollView>
            <TextField label="Job title" value={title} onChangeText={setTitle} placeholder="Senior Backend Engineer" />
            <TextField label="Company" value={company} onChangeText={setCompany} placeholder="Acme Inc." />
            <TextField label="Location" value={location} onChangeText={setLocation} placeholder="Remote" />
            <TextField label="Posting URL (optional)" value={jobUrl} onChangeText={setJobUrl} placeholder="https://…" autoCapitalize="none" />
            <TextField label="Job description" value={description} onChangeText={setDescription} placeholder="Paste the full description…" multiline />
          </ScrollView>
          <View style={{ flexDirection: "row", gap: 10, marginTop: 8 }}>
            <Btn label="Cancel" variant="secondary" onPress={onClose} style={{ flex: 1 }} />
            <Btn label={submitting ? "Screening…" : "Add & screen"} onPress={submit} disabled={!canSubmit || submitting} style={{ flex: 1 }} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  searchRow: { flexDirection: "row", gap: 10, alignItems: "center" },
  search: { flex: 1, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 11, color: C.text, fontSize: 15 },
  chipRow: { gap: 8, paddingVertical: 10 },
  filterRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, paddingBottom: 6 },
  empty: { color: C.faint, textAlign: "center", marginTop: 40, fontSize: 15 },
  tile: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 16, marginBottom: 12 },
  tileTop: { flexDirection: "row", gap: 8, flexWrap: "wrap", marginBottom: 10 },
  tileTitle: { color: C.text, fontSize: 16, fontWeight: "700", lineHeight: 21 },
  tileCompany: { color: C.sub, fontSize: 14, marginTop: 4, fontWeight: "600" },
  tileMeta: { color: C.faint, fontSize: 13, marginTop: 2 },
  tileBottom: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 12 },
  tileSite: { color: C.muted, fontSize: 12, backgroundColor: C.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, overflow: "hidden" },
  tileMatch: { fontSize: 12, fontWeight: "700" },
  modalWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  modal: { backgroundColor: C.bg, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, paddingTop: 16, maxHeight: "90%", borderWidth: 1, borderColor: C.border },
  modalTitle: { color: C.text, fontSize: 18, fontWeight: "800" },
  modalSub: { color: C.muted, fontSize: 13, marginTop: 4, marginBottom: 12 },
});
