import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import type { Config, CustomSection, ExperienceRole, GithubRepo } from "../lib/types";
import { Btn, C, Card, Loading, NumField, Screen, SectionLabel, Tabs, TextField, ToggleRow } from "../ui";

const TABS = [
  { key: "profile", label: "Profile" },
  { key: "resume", label: "Résumé text" },
  { key: "projects", label: "Projects" },
  { key: "experience", label: "Experience" },
  { key: "custom", label: "Custom sections" },
  { key: "order", label: "Section order" },
];

const BLANK_ROLE: ExperienceRole = { title: "", company: "", dates: "", domain: "", total_bullets: 4, real_bullets: 2, fabricated_bullets: 2 };
const FIXED_SECTIONS = ["education", "skills", "experience", "projects"];

export default function ResumeProfile() {
  const [tab, setTab] = useState("profile");
  const [config, setConfig] = useState<Config | null>(null);
  const [resumeText, setResumeText] = useState("");
  const [projectsText, setProjectsText] = useState("");
  const [roles, setRoles] = useState<ExperienceRole[]>([]);
  const [customSections, setCustomSections] = useState<CustomSection[]>([]);
  const [sectionOrder, setSectionOrder] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getResumeData().then((d) => {
      setResumeText(d.resume_text); setProjectsText(d.projects_text);
      setRoles(d.experience_roles); setCustomSections(d.custom_sections); setSectionOrder(d.section_order);
    });
    api.getConfig().then(setConfig);
  }, []);

  const save = async () => {
    setSaving(true); setSaved(false);
    try {
      await Promise.all([
        api.putResumeData({ resume_text: resumeText, projects_text: projectsText, experience_roles: roles, custom_sections: customSections, section_order: sectionOrder }),
        ...(config ? [api.putConfig(config)] : []),
      ]);
      setSaved(true);
    } finally { setSaving(false); }
  };

  const allIds = [...FIXED_SECTIONS, ...customSections.map((c) => c.id)];
  const orderedIds = [...sectionOrder.filter((id) => allIds.includes(id)), ...allIds.filter((id) => !sectionOrder.includes(id))];
  const moveSection = (i: number, dir: -1 | 1) => {
    const next = [...orderedIds], t = i + dir;
    if (t < 0 || t >= next.length) return;
    [next[i], next[t]] = [next[t], next[i]];
    setSectionOrder(next);
  };

  return (
    <Screen title="Résumé & profile" right={saved ? <Text style={st.saved}>Saved</Text> : undefined}>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "profile" && (config ? <ProfileFields config={config} setConfig={setConfig} /> : <Loading />)}

      {tab === "resume" && (
        <View style={{ marginTop: 12 }}>
          <Text style={st.hint}>The source résumé the Writer Agents draw from.</Text>
          <TextField label="" value={resumeText} multiline onChangeText={setResumeText} autoCapitalize="none" />
        </View>
      )}

      {tab === "projects" && (
        <View style={{ marginTop: 12 }}>
          <GithubImport onAppend={(entry) => setProjectsText((p) => `${p.trim()}\n\n${entry}\n`)} />
          <TextField label="" value={projectsText} multiline onChangeText={setProjectsText} autoCapitalize="none" />
        </View>
      )}

      {tab === "experience" && (
        <View style={{ marginTop: 12 }}>
          <Text style={st.hint}>One entry per role. "Fabricated bullets" are honest embellishments the Writer may add on top of your real ones — set 0 for none.</Text>
          {roles.map((r, i) => (
            <Card key={i} style={{ marginTop: 10 }}>
              <View style={st.roleTop}>
                <Text style={st.roleTitle}>Role {i + 1}{r.title || r.company ? ` — ${[r.title, r.company].filter(Boolean).join(" @ ")}` : ""}</Text>
                <Btn label="✕" variant="danger" onPress={() => setRoles((p) => p.filter((_, x) => x !== i))} style={st.tiny} />
              </View>
              <TextField label="Title" value={r.title} onChangeText={(v) => setRoles((p) => p.map((x, idx) => idx === i ? { ...x, title: v } : x))} />
              <TextField label="Company" value={r.company} onChangeText={(v) => setRoles((p) => p.map((x, idx) => idx === i ? { ...x, company: v } : x))} />
              <TextField label="Dates" value={r.dates} onChangeText={(v) => setRoles((p) => p.map((x, idx) => idx === i ? { ...x, dates: v } : x))} />
              <TextField label="Domain" value={r.domain} onChangeText={(v) => setRoles((p) => p.map((x, idx) => idx === i ? { ...x, domain: v } : x))} />
              <View style={st.row}>
                <View style={{ flex: 1 }}><NumField label="Total" value={r.total_bullets} onChangeNumber={(v) => setRoles((p) => p.map((x, idx) => idx === i ? { ...x, total_bullets: v } : x))} /></View>
                <View style={{ flex: 1 }}><NumField label="Real" value={r.real_bullets} onChangeNumber={(v) => setRoles((p) => p.map((x, idx) => idx === i ? { ...x, real_bullets: v } : x))} /></View>
                <View style={{ flex: 1 }}><NumField label="Fabricated" value={r.fabricated_bullets} onChangeNumber={(v) => setRoles((p) => p.map((x, idx) => idx === i ? { ...x, fabricated_bullets: v } : x))} /></View>
              </View>
            </Card>
          ))}
          <Btn label="+ Add role" variant="secondary" onPress={() => setRoles((p) => [...p, { ...BLANK_ROLE }])} style={{ marginTop: 10 }} />
        </View>
      )}

      {tab === "custom" && <CustomSections sections={customSections} setSections={setCustomSections} />}

      {tab === "order" && (
        <View style={{ marginTop: 12 }}>
          <Text style={st.hint}>Order the sections appear in on the compiled résumé.</Text>
          {orderedIds.map((id, i) => (
            <Card key={id} style={[st.orderRow, { marginTop: 8 }]}>
              <Text style={st.orderName}>{id.replace(/_/g, " ")}</Text>
              <View style={st.row}>
                <Btn label="▲" variant="secondary" disabled={i === 0} onPress={() => moveSection(i, -1)} style={st.tiny} />
                <Btn label="▼" variant="secondary" disabled={i === orderedIds.length - 1} onPress={() => moveSection(i, 1)} style={st.tiny} />
              </View>
            </Card>
          ))}
        </View>
      )}

      <Btn label={saving ? "Saving…" : "Save all"} variant="primary" disabled={saving} onPress={save} style={{ marginTop: 18 }} />
    </Screen>
  );
}

function ProfileFields({ config, setConfig }: { config: Config; setConfig: (c: Config) => void }) {
  const p = config.profile;
  const set = (patch: Partial<Config["profile"]>) => setConfig({ ...config, profile: { ...p, ...patch } });
  return (
    <View style={{ marginTop: 12 }}>
      <TextField label="Full name" value={p.full_name} onChangeText={(v) => set({ full_name: v })} />
      <TextField label="Phone" value={p.phone} onChangeText={(v) => set({ phone: v })} keyboardType="phone-pad" />
      <TextField label="Email" value={p.email} onChangeText={(v) => set({ email: v })} autoCapitalize="none" keyboardType="email-address" />
      <TextField label="LinkedIn" value={p.linkedin} onChangeText={(v) => set({ linkedin: v })} autoCapitalize="none" />
      <TextField label="GitHub" value={p.github} onChangeText={(v) => set({ github: v })} autoCapitalize="none" />
      <TextField label="Location" value={p.location} onChangeText={(v) => set({ location: v })} />
      <TextField label="Years of experience" value={p.experience_yrs} onChangeText={(v) => set({ experience_yrs: v })} />
      <ToggleRow label="Show LinkedIn/GitHub links on résumé" value={p.include_links} onValueChange={(v) => set({ include_links: v })} />
      <TextField label="Core stack" value={p.core_stack} multiline onChangeText={(v) => set({ core_stack: v })} />
      <TextField label="Target job titles" value={p.job_titles} multiline onChangeText={(v) => set({ job_titles: v })} />
      <TextField label="Not a fit for" value={p.not_fit_for} multiline onChangeText={(v) => set({ not_fit_for: v })} />
    </View>
  );
}

function CustomSections({ sections, setSections }: { sections: CustomSection[]; setSections: (s: CustomSection[]) => void }) {
  const [open, setOpen] = useState<string | null>(null);
  const update = (id: string, patch: Partial<CustomSection>) => setSections(sections.map((s) => s.id === id ? { ...s, ...patch } : s));
  const add = () => {
    const id = `section_${Date.now()}`;
    setSections([...sections, {
      id, name: "New Section",
      system_prompt: "You are an expert resume writer. Output ONLY raw LaTeX — no backticks, no explanation.\n\nABSOLUTE RULES:\n- NO \\documentclass, NO \\usepackage, NO \\begin{document}, NO \\end{document}.",
      user_prompt: "Write this section for {full_name} applying for {title} at {company}.\n\nJOB DESCRIPTION:\n{description}\n\nCANDIDATE RESUME:\n{existing_resume}",
    }]);
    setOpen(id);
  };
  return (
    <View style={{ marginTop: 12 }}>
      <Text style={st.hint}>Sections beyond Skills/Experience/Projects. Use {"{full_name} {title} {company} {description} {existing_resume} {ats_feedback}"} in the user prompt.</Text>
      {sections.map((s) => (
        <Card key={s.id} style={{ marginTop: 10 }}>
          <View style={st.roleTop}>
            <Text style={st.roleTitle} onPress={() => setOpen(open === s.id ? null : s.id)}>{open === s.id ? "▾" : "▸"} {s.name}</Text>
            <Btn label="✕" variant="danger" onPress={() => setSections(sections.filter((x) => x.id !== s.id))} style={st.tiny} />
          </View>
          {open === s.id && (
            <View style={{ marginTop: 8 }}>
              <TextField label="Display name" value={s.name} onChangeText={(v) => update(s.id, { name: v })} />
              <TextField label="System prompt" value={s.system_prompt} multiline onChangeText={(v) => update(s.id, { system_prompt: v })} autoCapitalize="none" />
              <TextField label="User prompt" value={s.user_prompt} multiline onChangeText={(v) => update(s.id, { user_prompt: v })} autoCapitalize="none" />
            </View>
          )}
        </Card>
      ))}
      <Btn label="+ Add custom section" variant="secondary" onPress={add} style={{ marginTop: 10 }} />
    </View>
  );
}

function GithubImport({ onAppend }: { onAppend: (entry: string) => void }) {
  const [username, setUsername] = useState("");
  const [repos, setRepos] = useState<GithubRepo[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState("");

  const list = async () => {
    if (!username.trim()) return;
    setLoading(true); setError("");
    try { setRepos((await api.githubRepos(username.trim())).filter((r) => !r.is_fork)); }
    catch (e) { setError(String(e)); } finally { setLoading(false); }
  };
  const gen = async (r: GithubRepo) => {
    setGenerating(r.url); setError("");
    try { onAppend((await api.githubGenerateEntry(r.url)).entry); }
    catch (e) { setError(String(e)); } finally { setGenerating(null); }
  };

  return (
    <Card style={{ marginBottom: 12 }}>
      <SectionLabel>Import from GitHub</SectionLabel>
      <View style={st.row}>
        <View style={{ flex: 1 }}><TextField label="" value={username} placeholder="GitHub username" autoCapitalize="none" onChangeText={setUsername} /></View>
        <Btn label={loading ? "…" : "List"} variant="secondary" disabled={loading} onPress={list} style={{ height: 46, marginTop: 6 }} />
      </View>
      {error ? <Text style={st.err}>{error}</Text> : null}
      {repos.map((r) => (
        <View key={r.url} style={st.repoRow}>
          <View style={{ flex: 1 }}>
            <Text style={st.repoName} numberOfLines={1}>{r.name}</Text>
            <Text style={st.repoDesc} numberOfLines={1}>{r.description || r.language}</Text>
          </View>
          <Btn label={generating === r.url ? "…" : "Append"} variant="secondary" disabled={generating === r.url} onPress={() => gen(r)} style={st.tiny} />
        </View>
      ))}
    </Card>
  );
}

const st = StyleSheet.create({
  saved: { color: C.green, fontSize: 12, fontWeight: "700" },
  hint: { color: C.muted, fontSize: 13, lineHeight: 19, marginBottom: 10 },
  row: { flexDirection: "row", gap: 8, alignItems: "flex-start" },
  roleTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 6 },
  roleTitle: { color: C.text, fontSize: 14, fontWeight: "700", flex: 1 },
  tiny: { paddingVertical: 8, paddingHorizontal: 12 },
  orderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  orderName: { color: C.text, fontSize: 15, textTransform: "capitalize" },
  err: { color: C.red, fontSize: 13, marginTop: 6 },
  repoRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 8 },
  repoName: { color: C.text, fontSize: 14, fontWeight: "600" },
  repoDesc: { color: C.muted, fontSize: 12 },
});
