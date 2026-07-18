import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Linking, Platform, StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import { savePdfToPhone } from "../lib/deviceStore";
import { useEventStream } from "../lib/eventStream";
import type { AppliedRow, JobRow, Verdict } from "../lib/types";
import { Badge, Btn, C, Card, Screen, SectionLabel, scoreColor, useNav } from "../ui";

export default function JobDetail({ id, source }: { id: number; source: "jobs" | "applied" }) {
  const isJob = source === "jobs";
  const [job, setJob] = useState<JobRow | AppliedRow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNav();
  const { applyProgress } = useEventStream();

  const load = () => {
    (isJob ? api.getJob(id) : api.getApplied(id)).then(setJob).catch((e) => setError(String(e)));
  };
  useEffect(load, [id]);

  const progress = job ? applyProgress[`${job.company}::${job.title}`] : undefined;
  useEffect(() => {
    if (progress?.stage === "done") load();
  }, [progress?.stage]);

  const run = async (fn: () => Promise<unknown>, ok?: string, then?: () => void) => {
    setBusy(true);
    try {
      await fn();
      if (ok) Alert.alert("Done", ok);
      then?.();
    } catch (e: any) {
      Alert.alert("Failed", e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  const savePdf = (kind: "resume" | "cover") => {
    if (!job) return;
    const path = kind === "resume" ? job.resume_path : job.cover_path;
    if (!path) return Alert.alert("Not built yet", `No ${kind} generated for this job yet.`);
    const base = isJob ? `/api/jobs/${id}` : `/api/outputs/${id}`;
    run(async () => {
      const cfg = await api.getConfig();
      const rel = await savePdfToPhone(`${base}/${kind}.pdf`, {
        company: job.company,
        title: job.title,
        filename: kind === "resume" ? cfg.pipeline.resume_filename : cfg.pipeline.cover_letter_filename,
      });
      const where = Platform.OS === "android" ? "your chosen folder" : "Files → On My iPhone → Kairos";
      Alert.alert("Saved to phone", `${rel}\n\nin ${where}.`);
    });
  };

  if (error) return <Screen title="Job" onBack={nav.back}><Text style={st.err}>{error}</Text></Screen>;
  if (!job) return <Screen title="Job" onBack={nav.back}><ActivityIndicator style={{ marginTop: 40 }} color={C.accent} /></Screen>;

  const j = job as JobRow;
  const hasResume = isJob ? !!j.latex_content : !!job.resume_path;
  const building = progress && progress.stage !== "done";
  const rec = job.ai_recommendation || "";

  return (
    <Screen
      title={source === "applied" ? "Application" : "Job"}
      onBack={nav.back}
      right={rec ? <Badge label={rec.toUpperCase()} color={rec === "yes" ? C.green : rec === "maybe" ? C.amber : C.red} /> : undefined}
    >
      <Text style={st.title}>{job.title}</Text>
      <Text style={st.company}>{job.company}</Text>
      <Text style={st.meta}>{[job.location, job.site, isJob ? j.posted_date : (job as AppliedRow).applied_date].filter(Boolean).join(" · ")}</Text>
      {(() => {
        const url = isJob ? j.link : (job as AppliedRow).job_url;
        return url ? (
          <Text style={st.link} onPress={() => Linking.openURL(url).catch(() => Alert.alert("Couldn't open link", url))}>
            🔗 View original posting
          </Text>
        ) : null;
      })()}

      <View style={st.statGrid}>
        <Stat label="Years req." value={job.years_required || "—"} />
        <Stat label="Role level" value={job.role_level || "—"} />
        <Stat label="Skills match" value={`${job.skills_match_pct || 0}%`} />
        <Stat label="ATS score" value={hasResume ? String(job.ats_score) : "—"} color={hasResume ? scoreColor(job.ats_score) ?? undefined : undefined} />
      </View>

      {!!job.reasoning && (
        <>
          <SectionLabel>Screener reasoning</SectionLabel>
          <Card>
            <Text style={st.body}>{job.reasoning}</Text>
            <View style={st.skills}>
              {(job.matched_skills || "").split(",").filter(Boolean).map((s) => <Tag key={s} label={s.trim()} color={C.green} />)}
              {(job.missing_skills || "").split(",").filter(Boolean).map((s) => <Tag key={s} label={s.trim()} color={C.red} />)}
            </View>
          </Card>
        </>
      )}

      {!!job.description && (
        <>
          <SectionLabel>Job description</SectionLabel>
          <Card><Text style={st.body}>{job.description}</Text></Card>
        </>
      )}

      {isJob && (
        <>
          <SectionLabel>Verdict</SectionLabel>
          <View style={st.verdictRow}>
            {(["yes", "maybe", "no"] as Verdict[]).map((v) => (
              <Btn key={v} label={v.toUpperCase()} variant={rec === v ? "primary" : "secondary"} disabled={busy} onPress={() => run(() => api.setVerdict(id, v), undefined, load)} style={{ flex: 1 }} />
            ))}
          </View>
          <SectionLabel>Pipeline</SectionLabel>
          <View style={{ gap: 10 }}>
            <Btn label={building ? `Building… (${progress?.stage})` : hasResume ? "⚙️ Rebuild resume & cover" : "⚙️ Generate resume & cover"} variant="primary" disabled={busy || !!building} onPress={() => run(() => api.buildJob(id), "Building on your PC — pull to refresh soon.")} />
            <Btn label="✅ Mark applied" variant="teal" disabled={busy} onPress={() => run(() => api.applyJob(id), "Marked as applied.", nav.back)} />
            <Btn label="🗑 Delete job" variant="danger" disabled={busy} onPress={() => Alert.alert("Delete job?", "This can't be undone.", [{ text: "Cancel", style: "cancel" }, { text: "Delete", style: "destructive", onPress: () => run(() => api.deleteJob(id), undefined, nav.back) }])} />
          </View>
        </>
      )}

      {source === "applied" && (
        <>
          <SectionLabel>Application</SectionLabel>
          <View style={{ gap: 10 }}>
            <Btn label="↩ Unapply" variant="secondary" disabled={busy} onPress={() => run(() => api.unapply(id), "Moved back to jobs.", nav.back)} />
            <Btn label="🗑 Delete application" variant="danger" disabled={busy} onPress={() => Alert.alert("Delete?", "This can't be undone.", [{ text: "Cancel", style: "cancel" }, { text: "Delete", style: "destructive", onPress: () => run(() => api.deleteApplied(id), undefined, nav.back) }])} />
          </View>
        </>
      )}

      <SectionLabel>Documents</SectionLabel>
      <View style={{ gap: 10 }}>
        {hasResume && <Btn label="✏️ Edit LaTeX résumé" variant="primary" disabled={busy} onPress={() => nav.go({ name: "latex", id, source })} />}
        <Btn label="📄 Save Resume PDF" variant="secondary" disabled={busy} onPress={() => savePdf("resume")} />
        <Btn label="✉️ Save Cover Letter PDF" variant="secondary" disabled={busy} onPress={() => savePdf("cover")} />
      </View>
      <Text style={st.hint}>
        Saved into <Text style={{ color: C.sub }}>Company/Title/</Text> — the same folder tree as the desktop app.
        {Platform.OS === "android" ? " First save asks you to pick a base folder." : ""}
      </Text>

      {busy && <View style={st.overlay}><ActivityIndicator size="large" color="#fff" /></View>}
    </Screen>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={st.stat}>
      <Text style={[st.statValue, color && { color }]}>{value}</Text>
      <Text style={st.statLabel}>{label}</Text>
    </View>
  );
}
function Tag({ label, color }: { label: string; color: string }) {
  return <Text style={[st.tag, { color, borderColor: color }]}>{label}</Text>;
}

const st = StyleSheet.create({
  err: { color: C.red, marginTop: 16 },
  title: { color: C.text, fontSize: 22, fontWeight: "800", lineHeight: 28 },
  company: { color: C.sub, fontSize: 17, marginTop: 6, fontWeight: "600" },
  meta: { color: C.muted, fontSize: 13, marginTop: 4 },
  link: { color: C.accent, fontSize: 14, fontWeight: "600", marginTop: 8 },
  statGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 16 },
  stat: { width: "47.5%", flexGrow: 1, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 12 },
  statValue: { color: C.text, fontSize: 17, fontWeight: "800" },
  statLabel: { color: C.muted, fontSize: 12, marginTop: 2 },
  body: { color: C.muted, fontSize: 14, lineHeight: 20 },
  skills: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 12 },
  tag: { fontSize: 11, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, borderWidth: 1, overflow: "hidden" },
  verdictRow: { flexDirection: "row", gap: 10 },
  hint: { color: C.faint, fontSize: 12, marginTop: 10 },
  overlay: { position: "absolute", top: 0, bottom: 0, left: 0, right: 0, backgroundColor: "rgba(5,7,12,0.55)", justifyContent: "center", alignItems: "center" },
});
