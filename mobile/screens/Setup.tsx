import { StyleSheet, Text, View } from "react-native";
import type { Route } from "../lib/nav";
import { C, Card, Screen, useNav } from "../ui";

// The desktop Setup wizard bundles fields that, on mobile, each live on their own
// screen. Rather than re-implement the stepper, this is a hub that points at them.
const STEPS: { route: Route; title: string; body: string }[] = [
  { route: { name: "resume" }, title: "1 · Résumé & profile", body: "Your name, contact details, résumé text, work experience, and projects." },
  { route: { name: "settings" }, title: "2 · Models & API keys", body: "Add at least one Ollama API key and pick the models (Settings → API keys / Model)." },
  { route: { name: "screener" }, title: "3 · Screening rules", body: "Thresholds, required skills, and blacklists the Screener Agent rates jobs against." },
  { route: { name: "templates" }, title: "4 · Résumé format", body: "Pick or paste the LaTeX format every generated résumé uses." },
  { route: { name: "find" }, title: "5 · Find jobs", body: "Set search terms and run your first scrape." },
];

export default function Setup() {
  const nav = useNav();
  return (
    <Screen title="Setup wizard">
      <Text style={st.desc}>
        Work through these once to get running. First-time setup is easiest on the desktop app (where the
        backend and LaTeX engine live), but every setting is editable here too.
      </Text>
      {STEPS.map((s) => (
        <Card key={s.title} style={{ marginTop: 12 }} onPress={() => nav.go(s.route)}>
          <Text style={st.title}>{s.title}</Text>
          <Text style={st.body}>{s.body}</Text>
          <Text style={st.go}>Open ›</Text>
        </Card>
      ))}
    </Screen>
  );
}

const st = StyleSheet.create({
  desc: { color: C.muted, fontSize: 13, lineHeight: 19, marginTop: 4 },
  title: { color: C.text, fontSize: 15, fontWeight: "700" },
  body: { color: C.muted, fontSize: 13, lineHeight: 19, marginTop: 4 },
  go: { color: C.accent, fontSize: 13, fontWeight: "700", marginTop: 8 },
});
