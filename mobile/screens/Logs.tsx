import { StyleSheet, Text, View } from "react-native";
import { clearLogs, useEventStream } from "../lib/eventStream";
import { Badge, Btn, C, Empty, Screen } from "../ui";

const LEVEL_COLOR: Record<string, string> = { ERROR: C.red, WARNING: C.amber, INFO: C.muted, DEBUG: C.faint };

export default function Logs() {
  const { logs, connected } = useEventStream();
  return (
    <Screen
      title="Activity log"
      right={<Badge label={connected ? "live" : "offline"} color={connected ? C.green : C.red} />}
    >
      <Btn label="Clear" variant="secondary" onPress={clearLogs} style={{ marginBottom: 12 }} />
      {logs.length === 0 ? (
        <Empty text={"No activity yet.\nStart a scrape or a build to see live logs."} />
      ) : (
        [...logs].reverse().map((l, i) => (
          <View key={logs.length - i} style={st.row}>
            <Text style={[st.level, { color: LEVEL_COLOR[l.level] ?? C.muted }]}>{l.level}</Text>
            <Text style={st.msg}>{l.message}</Text>
          </View>
        ))
      )}
    </Screen>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: "row", gap: 8, paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: C.border },
  level: { fontSize: 10, fontWeight: "800", width: 58 },
  msg: { color: C.text, fontSize: 12, flex: 1, fontFamily: "monospace" },
});
