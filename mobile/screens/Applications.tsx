import { useEffect, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { api } from "../lib/api";
import type { AppliedRow } from "../lib/types";
import { Badge, C, Screen, scoreColor, useNav } from "../ui";

export default function Applications() {
  const [rows, setRows] = useState<AppliedRow[]>([]);
  const [loading, setLoading] = useState(false);
  const nav = useNav();

  const load = () => {
    setLoading(true);
    api.listApplied().then(setRows).finally(() => setLoading(false));
  };
  useEffect(load, []);

  return (
    <Screen title="Applications" scroll={false}>
      <FlatList
        data={rows}
        keyExtractor={(r) => String(r.id)}
        contentContainerStyle={{ padding: 16 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.accent} />}
        ListHeaderComponent={<Text style={st.count}>{rows.length} application{rows.length === 1 ? "" : "s"} on file</Text>}
        ListEmptyComponent={<Text style={st.empty}>{loading ? "Loading…" : "No applications yet."}</Text>}
        renderItem={({ item }) => (
          <Pressable style={({ pressed }) => [st.card, pressed && { opacity: 0.7 }]} onPress={() => nav.go({ name: "job", id: item.id, source: "applied" })}>
            <View style={{ flex: 1 }}>
              <Text style={st.title} numberOfLines={1}>{item.title}</Text>
              <Text style={st.sub} numberOfLines={1}>{item.company} · {item.location}</Text>
              <Text style={st.date}>{item.applied_date}</Text>
            </View>
            <Badge label={`ATS ${item.ats_score}`} color={scoreColor(item.ats_score) ?? C.muted} />
          </Pressable>
        )}
      />
    </Screen>
  );
}

const st = StyleSheet.create({
  count: { color: C.muted, fontSize: 13, marginBottom: 12 },
  empty: { color: C.faint, textAlign: "center", marginTop: 40, fontSize: 15 },
  card: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 14, padding: 14, marginBottom: 10 },
  title: { color: C.text, fontSize: 15, fontWeight: "700" },
  sub: { color: C.sub, fontSize: 13, marginTop: 3 },
  date: { color: C.faint, fontSize: 12, marginTop: 2 },
});
