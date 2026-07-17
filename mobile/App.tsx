import { useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useEventStream } from "./lib/eventStream";
import type { Nav, Route } from "./lib/nav";
import { C, MenuProvider, NavProvider, TOP } from "./ui";
import Applications from "./screens/Applications";
import Build from "./screens/Build";
import FindJobs from "./screens/FindJobs";
import JobDetail from "./screens/JobDetail";
import LatexEditor from "./screens/LatexEditor";
import Logs from "./screens/Logs";
import Overview from "./screens/Overview";
import Prompts from "./screens/Prompts";
import ResumeProfile from "./screens/ResumeProfile";
import ReviewJobs from "./screens/ReviewJobs";
import Screener from "./screens/Screener";
import Settings from "./screens/Settings";
import Setup from "./screens/Setup";
import Templates from "./screens/Templates";

type Item = { route: Route; label: string };
const MENU: { group: string; items: Item[] }[] = [
  { group: "", items: [{ route: { name: "overview" }, label: "Overview" }] },
  {
    group: "Workflow",
    items: [
      { route: { name: "find" }, label: "Find jobs" },
      { route: { name: "review" }, label: "Review jobs" },
      { route: { name: "build" }, label: "Build resumes" },
      { route: { name: "applied" }, label: "Applications" },
    ],
  },
  {
    group: "Setup",
    items: [
      { route: { name: "resume" }, label: "Résumé & profile" },
      { route: { name: "templates" }, label: "Formats" },
      { route: { name: "screener" }, label: "Screening rules" },
      { route: { name: "prompts" }, label: "AI prompts" },
    ],
  },
  {
    group: "System",
    items: [
      { route: { name: "logs" }, label: "Activity log" },
      { route: { name: "settings" }, label: "Settings" },
      { route: { name: "setup" }, label: "Setup wizard" },
    ],
  },
];

export default function App() {
  const [stack, setStack] = useState<Route[]>([{ name: "overview" }]);
  const [menuOpen, setMenuOpen] = useState(false);
  const current = stack[stack.length - 1];

  const nav: Nav = {
    go: (r) => setStack((s) => [...s, r]),
    back: () => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s)),
  };
  const goRoot = (r: Route) => {
    setStack([r]);
    setMenuOpen(false);
  };

  return (
    <NavProvider value={nav}>
      <MenuProvider value={() => setMenuOpen(true)}>
        <View style={{ flex: 1, backgroundColor: C.bg }}>
          {renderScreen(current)}
          <MenuDrawer open={menuOpen} onClose={() => setMenuOpen(false)} current={current.name} onPick={goRoot} />
        </View>
      </MenuProvider>
    </NavProvider>
  );
}

function renderScreen(r: Route) {
  switch (r.name) {
    case "overview":
      return <Overview />;
    case "find":
      return <FindJobs />;
    case "review":
      return <ReviewJobs />;
    case "build":
      return <Build />;
    case "applied":
      return <Applications />;
    case "job":
      return <JobDetail id={r.id} source={r.source} />;
    case "latex":
      return <LatexEditor id={r.id} source={r.source} />;
    case "resume":
      return <ResumeProfile />;
    case "templates":
      return <Templates />;
    case "screener":
      return <Screener />;
    case "prompts":
      return <Prompts />;
    case "logs":
      return <Logs />;
    case "settings":
      return <Settings />;
    case "setup":
      return <Setup />;
  }
}

function MenuDrawer({ open, onClose, current, onPick }: { open: boolean; onClose: () => void; current: string; onPick: (r: Route) => void }) {
  const { connected } = useEventStream();
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={st.scrim} onPress={onClose}>
        <Pressable style={[st.drawer, { paddingTop: TOP + 8 }]} onPress={() => {}}>
          <Text style={st.brand}>Kairos</Text>
          <Text style={st.tagline}>Your applicant pipeline</Text>
          <View style={[st.status, { marginBottom: 8 }]}>
            <View style={[st.statusDot, { backgroundColor: connected ? C.green : C.red }]} />
            <Text style={st.statusText}>{connected ? "Connected" : "Offline"}</Text>
          </View>
          <ScrollView showsVerticalScrollIndicator={false}>
            {MENU.map((section) => (
              <View key={section.group} style={{ marginBottom: 18 }}>
                {section.group ? <Text style={st.groupLabel}>{section.group}</Text> : null}
                {section.items.map((item) => {
                  const active = item.route.name === current;
                  return (
                    <Pressable key={item.route.name} onPress={() => onPick(item.route)} style={[st.item, active && st.itemActive]}>
                      <Text style={[st.itemText, active && st.itemTextActive]}>{item.label}</Text>
                    </Pressable>
                  );
                })}
              </View>
            ))}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const st = StyleSheet.create({
  scrim: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", flexDirection: "row" },
  drawer: { width: 264, backgroundColor: C.surface, borderRightWidth: 1, borderRightColor: C.border, paddingHorizontal: 14, paddingBottom: 20 },
  brand: { color: C.text, fontSize: 20, fontWeight: "800", paddingHorizontal: 8 },
  tagline: { color: C.faint, fontSize: 12, paddingHorizontal: 8, marginTop: 2, marginBottom: 12 },
  status: { flexDirection: "row", alignItems: "center", gap: 7, paddingHorizontal: 8 },
  statusDot: { width: 7, height: 7, borderRadius: 4 },
  statusText: { color: C.muted, fontSize: 12 },
  groupLabel: { color: C.faint, fontSize: 11, fontWeight: "800", letterSpacing: 1, textTransform: "uppercase", paddingHorizontal: 8, marginBottom: 6 },
  item: { paddingVertical: 11, paddingHorizontal: 12, borderRadius: 10, marginBottom: 2 },
  itemActive: { backgroundColor: C.accentBg },
  itemText: { color: C.muted, fontSize: 15, fontWeight: "600" },
  itemTextActive: { color: "#fff" },
});
