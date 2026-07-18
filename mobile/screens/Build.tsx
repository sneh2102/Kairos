import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import { startApplyRun, useEventStream } from "../lib/eventStream";
import type { Config } from "../lib/types";
import { Badge, Btn, C, Card, Screen, SectionLabel, TextField, ToggleRow, scoreColor } from "../ui";

const STAGE_LABEL: Record<string, string> = { building: "Building sections", checking_ats: "Checking ATS", ats_score: "Scored", done: "Done" };

export default function Build() {
  const [config, setConfig] = useState<Config | null>(null);
  const [pending, setPending] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { applyProgress, applyOrder, applyRunning } = useEventStream();

  const refreshCount = () => api.listJobs({ verdict: "yes" }).then((rows) => setPending(rows.filter((r) => !r.latex_content).length));
  useEffect(() => {
    api.getConfig().then(setConfig).catch((e) => setError(String(e)));
    refreshCount();
  }, []);

  const start = async () => {
    setError(null);
    startApplyRun();
    try {
      const res = await api.startApply(["yes"]);
      setPending(res.count);
    } catch (e) {
      setError(String(e));
    }
  };

  const setPipe = (patch: Partial<Config["pipeline"]>) => config && setConfig({ ...config, pipeline: { ...config.pipeline, ...patch } });

  return (
    <Screen title="Build resumes" right={<Badge label={applyRunning ? "running" : "idle"} color={applyRunning ? C.green : C.muted} />}>
      <Text style={st.desc}>Builds every "yes" job without a resume yet. Change a verdict in Review jobs to include/exclude one.</Text>
      {error && <Text style={st.err}>{error}</Text>}

      <Card style={{ marginTop: 14 }}>
        <Text style={st.pending}>{pending ?? "…"} unbuilt "yes" job{pending === 1 ? "" : "s"} waiting</Text>
      </Card>

      {config && (
        <>
          <SectionLabel>Thresholds</SectionLabel>
          <View style={st.two}>
            <View style={{ flex: 1 }}>
              <TextField label="ATS pass threshold" value={String(config.pipeline.ats_pass_threshold)} onChangeText={(v) => setPipe({ ats_pass_threshold: Number(v) || 0 })} keyboardType="number-pad" />
            </View>
            <View style={{ flex: 1 }}>
              <TextField label="Max ATS iterations" value={String(config.pipeline.max_ats_iterations)} onChangeText={(v) => setPipe({ max_ats_iterations: Number(v) || 0 })} keyboardType="number-pad" />
            </View>
          </View>
          <ToggleRow label="Use JD location" value={config.pipeline.use_jd_location} onValueChange={(v) => setPipe({ use_jd_location: v })} />
          <TextField label="Default location" value={config.pipeline.default_location} onChangeText={(v) => setPipe({ default_location: v })} />
          <Btn label="Save" variant="secondary" onPress={() => api.putConfig(config).catch((e) => setError(String(e)))} />
        </>
      )}

      <View style={[st.two, { marginTop: 12 }]}>
        <Btn label="Start" variant="success" onPress={start} disabled={applyRunning} style={{ flex: 1 }} />
        <Btn label="Stop" variant="danger" onPress={() => api.stopApply().catch(() => {})} disabled={!applyRunning} style={{ flex: 1 }} />
      </View>

      <SectionLabel>Progress</SectionLabel>
      {applyOrder.length === 0 ? (
        <Text style={st.muted}>No activity yet — tap Start.</Text>
      ) : (
        applyOrder.map((key) => {
          const p = applyProgress[key];
          if (!p) return null;
          const passed = p.stage === "done" && (p.score ?? 0) >= (config?.pipeline.ats_pass_threshold ?? 85);
          return (
            <Card key={key} style={{ marginBottom: 10 }}>
              <View style={st.progTop}>
                <View style={{ flex: 1 }}>
                  <Text style={st.progTitle} numberOfLines={1}>{p.title}</Text>
                  <Text style={st.muted}>{p.company} · job {p.job_index + 1}/{p.total}</Text>
                </View>
                <Badge label={p.stage === "done" ? (passed ? "PASS" : "SAVED") : STAGE_LABEL[p.stage] ?? p.stage} color={p.stage === "done" ? (passed ? C.green : C.amber) : C.accent} />
              </View>
              {typeof p.score === "number" && (
                <View style={{ marginTop: 10 }}>
                  <View style={st.track}><View style={[st.fill, { width: `${Math.min(100, p.score)}%`, backgroundColor: scoreColor(p.score) ?? C.accent }]} /></View>
                  <Text style={st.scoreText}>ATS {p.score}{p.iteration ? ` · iteration ${p.iteration}` : ""}</Text>
                </View>
              )}
            </Card>
          );
        })
      )}
    </Screen>
  );
}

const st = StyleSheet.create({
  desc: { color: C.muted, fontSize: 13, lineHeight: 19, marginTop: 4 },
  err: { color: C.red, marginTop: 10 },
  pending: { color: C.text, fontSize: 15, fontWeight: "600" },
  two: { flexDirection: "row", gap: 10 },
  muted: { color: C.muted, fontSize: 13 },
  progTop: { flexDirection: "row", alignItems: "center", gap: 8 },
  progTitle: { color: C.text, fontSize: 14, fontWeight: "700" },
  track: { height: 8, backgroundColor: C.bg, borderRadius: 4, overflow: "hidden" },
  fill: { height: "100%", borderRadius: 4 },
  scoreText: { color: C.muted, fontSize: 11, marginTop: 4 },
});
