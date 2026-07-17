import { useEffect, useRef, useState } from "react";
import { RefreshControl, StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import { startApplyRun, startScrapeRun, useEventStream } from "../lib/eventStream";
import type { Stats } from "../lib/types";
import { Btn, C, Card, Empty, Loading, Screen, SectionLabel, scoreColor, useNav } from "../ui";

export default function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [chaining, setChaining] = useState(false);
  const { scrapeRunning, applyRunning } = useEventStream();
  const wasScraping = useRef(scrapeRunning);
  const nav = useNav();

  const load = () => {
    setLoading(true);
    api.getStats().then(setStats).catch((e) => setError(String(e))).finally(() => setLoading(false));
  };
  useEffect(load, []);

  // chained run: when the scrape we started finishes, kick off the build
  useEffect(() => {
    if (chaining && wasScraping.current && !scrapeRunning) {
      setChaining(false);
      startApplyRun();
      api.startApply(["yes"]).catch(() => {});
    }
    wasScraping.current = scrapeRunning;
  }, [scrapeRunning, chaining]);

  const runPipeline = async () => {
    setChaining(true);
    startScrapeRun();
    try {
      await api.startScrape();
    } catch {
      setChaining(false);
    }
  };

  const busy = chaining || scrapeRunning || applyRunning;
  const label = scrapeRunning ? "Scraping jobs…" : applyRunning ? "Building resumes…" : "▶ Run scraper + build resumes";

  const avg =
    stats && stats.ats_scores.length
      ? Math.round(stats.ats_scores.reduce((a, b) => a + b, 0) / stats.ats_scores.length)
      : null;

  return (
    <Screen title="Overview" scroll refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.accent} />}>
      <Btn label={label} onPress={runPipeline} disabled={busy} variant="success" />
      {error && <Text style={st.err}>{error}</Text>}
      {!stats ? (
        <Loading />
      ) : (
        <>
          <View style={st.grid}>
            <Tile label="Applications sent" value={stats.applied_count} color={C.accent} />
            <Tile label="Jobs to review" value={stats.pending_jobs} />
            <Tile label="Worth applying" value={stats.verdict_counts.yes ?? 0} color={C.green} />
            <Tile label="Resumes created" value={stats.resumes_created} />
            <Tile label="Jobs extracted" value={stats.total_extracted} />
            <Tile label="Avg ATS" value={avg ?? "—"} color={avg != null ? scoreColor(avg) ?? undefined : undefined} />
          </View>

          <SectionLabel>Screener verdicts</SectionLabel>
          <Card>
            {(["yes", "maybe", "no"] as const).map((v) => (
              <Bar key={v} label={v} value={stats.verdict_counts[v] ?? 0} max={Math.max(1, ...["yes", "maybe", "no"].map((k) => stats.verdict_counts[k] ?? 0))} color={v === "yes" ? C.green : v === "maybe" ? C.amber : C.red} />
            ))}
          </Card>

          {stats.top_missing_skills.length > 0 && (
            <>
              <SectionLabel>Skills costing you matches</SectionLabel>
              <Card>
                {stats.top_missing_skills.slice(0, 8).map((sk) => (
                  <Bar key={sk.skill} label={sk.skill} value={sk.count} max={stats.top_missing_skills[0].count} color={C.accent} />
                ))}
              </Card>
            </>
          )}

          <SectionLabel>Recent applications</SectionLabel>
          {stats.recent_applied.length === 0 ? (
            <Empty text="Mark a job applied to see it here." />
          ) : (
            <Card style={{ padding: 0 }}>
              {stats.recent_applied.map((r, i) => (
                <View key={r.id} style={[st.recent, i > 0 && st.recentBorder]}>
                  <View style={{ flex: 1 }}>
                    <Text style={st.recentTitle} numberOfLines={1}>{r.title}</Text>
                    <Text style={st.recentSub} numberOfLines={1}>{r.company} · {r.applied_date}</Text>
                  </View>
                  <Text style={[st.ats, { color: scoreColor(r.ats_score) ?? C.muted }]}>ATS {r.ats_score}</Text>
                </View>
              ))}
              <View style={{ padding: 12 }}>
                <Btn label="View all applications" variant="secondary" onPress={() => nav.go({ name: "applied" })} />
              </View>
            </Card>
          )}
        </>
      )}
    </Screen>
  );
}

function Tile({ label, value, color }: { label: string; value: number | string; color?: string }) {
  return (
    <View style={st.tile}>
      <Text style={[st.tileValue, color && { color }]}>{value}</Text>
      <Text style={st.tileLabel}>{label}</Text>
    </View>
  );
}

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <View style={st.barRow}>
      <Text style={st.barLabel} numberOfLines={1}>{label}</Text>
      <View style={st.barTrack}>
        <View style={[st.barFill, { width: `${Math.max(3, (value / max) * 100)}%`, backgroundColor: color }]} />
      </View>
      <Text style={st.barValue}>{value}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  err: { color: C.red, marginTop: 12 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 16 },
  tile: { width: "47.5%", backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 14, flexGrow: 1 },
  tileValue: { color: C.text, fontSize: 26, fontWeight: "800" },
  tileLabel: { color: C.muted, fontSize: 12, marginTop: 2 },
  barRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 6 },
  barLabel: { color: C.muted, fontSize: 13, width: 90, textTransform: "capitalize" },
  barTrack: { flex: 1, height: 8, backgroundColor: C.bg, borderRadius: 4, overflow: "hidden" },
  barFill: { height: "100%", borderRadius: 4 },
  barValue: { color: C.text, fontSize: 13, fontWeight: "700", width: 34, textAlign: "right" },
  recent: { flexDirection: "row", alignItems: "center", padding: 14 },
  recentBorder: { borderTopWidth: 1, borderTopColor: C.border },
  recentTitle: { color: C.text, fontSize: 14, fontWeight: "600" },
  recentSub: { color: C.muted, fontSize: 12, marginTop: 2 },
  ats: { fontSize: 12, fontWeight: "700", marginLeft: 8 },
});
