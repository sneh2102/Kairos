import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import { startScrapeRun, useEventStream } from "../lib/eventStream";
import type { Config } from "../lib/types";
import { Badge, Btn, C, Card, Chip, Field, TextField, ToggleRow, Screen, SectionLabel } from "../ui";

const SITES = [
  { value: "indeed", label: "Indeed" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "glassdoor", label: "Glassdoor" },
  { value: "zip_recruiter", label: "ZipRecruiter" },
  { value: "google", label: "Google Jobs" },
  { value: "bayt", label: "Bayt" },
  { value: "naukri", label: "Naukri" },
  { value: "bdjobs", label: "BDJobs" },
  { value: "jobright", label: "JobRight" },
  { value: "wellfound", label: "Wellfound" },
];

export default function FindJobs() {
  const [config, setConfig] = useState<Config | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { scrapeJobs, scrapeRunning, connected, logs } = useEventStream();

  useEffect(() => {
    api.getConfig().then(setConfig).catch((e) => setError(String(e)));
  }, []);

  if (error) return <Screen title="Find jobs"><Text style={st.err}>{error}</Text></Screen>;
  if (!config) return <Screen title="Find jobs"><Text style={st.muted}>Loading…</Text></Screen>;

  const sc = config.scraper;
  const setSc = (patch: Partial<Config["scraper"]>) => setConfig({ ...config, scraper: { ...sc, ...patch } });
  const selectedSites = sc.sites.split(",").map((s) => s.trim()).filter(Boolean);
  const toggleSite = (v: string) =>
    setSc({ sites: (selectedSites.includes(v) ? selectedSites.filter((s) => s !== v) : [...selectedSites, v]).join(",") });

  const save = async () => {
    setSaving(true);
    try {
      await api.putConfig(config);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };
  const start = async () => {
    startScrapeRun();
    try {
      await api.startScrape();
    } catch (e) {
      setError(String(e));
    }
  };

  const yes = scrapeJobs.filter((j) => j.verdict === "yes").length;
  const maybe = scrapeJobs.filter((j) => j.verdict === "maybe").length;
  const no = scrapeJobs.filter((j) => j.verdict === "no").length;

  return (
    <Screen
      title="Find jobs"
      right={<Badge label={scrapeRunning ? "running" : connected ? "idle" : "offline"} color={scrapeRunning ? C.green : connected ? C.muted : C.red} />}
    >
      <SectionLabel>Job boards</SectionLabel>
      <View style={st.chips}>
        {SITES.map((si) => (
          <Chip key={si.value} label={si.label} active={selectedSites.includes(si.value)} onPress={() => toggleSite(si.value)} />
        ))}
      </View>

      <View style={{ marginTop: 20 }}>
        <TextField label="Search terms (one per line)" value={sc.search_terms} onChangeText={(v) => setSc({ search_terms: v })} multiline />
        <TextField label="Location" value={sc.location} onChangeText={(v) => setSc({ location: v })} />
        <TextField label="Country (for Indeed — e.g. canada, usa, uk)" value={sc.country_indeed} onChangeText={(v) => setSc({ country_indeed: v })} autoCapitalize="none" />
        <View style={st.two}>
          <View style={{ flex: 1 }}>
            <TextField label="Hours old" value={String(sc.hours_old)} onChangeText={(v) => setSc({ hours_old: Number(v) || 0 })} keyboardType="number-pad" />
          </View>
          <View style={{ flex: 1 }}>
            <TextField label="Results wanted" value={String(sc.results_wanted)} onChangeText={(v) => setSc({ results_wanted: Number(v) || 0 })} keyboardType="number-pad" />
          </View>
        </View>
        <ToggleRow label="Remote only" value={sc.is_remote} onValueChange={(v) => setSc({ is_remote: v })} />
      </View>

      <View style={{ gap: 10, marginTop: 12 }}>
        <Btn label={saving ? "Saving…" : "Save config"} variant="secondary" onPress={save} disabled={saving} />
        <View style={st.two}>
          <Btn label="Start" variant="success" onPress={start} disabled={scrapeRunning} style={{ flex: 1 }} />
          <Btn label="Stop" variant="danger" onPress={() => api.stopScrape().catch(() => {})} disabled={!scrapeRunning} style={{ flex: 1 }} />
        </View>
      </View>

      <SectionLabel>Live results</SectionLabel>
      <View style={st.counts}>
        <Text style={st.muted}>{scrapeJobs.length} processed</Text>
        <Text style={{ color: C.green, fontWeight: "700" }}>{yes} yes</Text>
        <Text style={{ color: C.amber, fontWeight: "700" }}>{maybe} maybe</Text>
        <Text style={{ color: C.red, fontWeight: "700" }}>{no} no</Text>
      </View>
      <Card style={{ marginTop: 10 }}>
        {logs.length === 0 ? (
          <Text style={st.muted}>No activity yet — tap Start.</Text>
        ) : (
          logs.slice(-40).map((l, i) => (
            <Text key={i} style={[st.log, l.level === "ERROR" ? { color: C.red } : l.level === "WARNING" ? { color: C.amber } : { color: C.muted }]}>
              {l.message}
            </Text>
          ))
        )}
      </Card>
    </Screen>
  );
}

const st = StyleSheet.create({
  err: { color: C.red, marginTop: 16 },
  muted: { color: C.muted, marginTop: 8 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 6 },
  two: { flexDirection: "row", gap: 10 },
  counts: { flexDirection: "row", gap: 14, alignItems: "center", flexWrap: "wrap" },
  log: { fontSize: 11, fontFamily: "monospace" as any, marginBottom: 2 },
});
