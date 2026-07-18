import { createContext, useContext, type ReactNode } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";
import type { Nav } from "./lib/nav";

export const C = {
  bg: "#0b0d12",
  surface: "#141824",
  surface2: "#181d29",
  border: "#1e2330",
  text: "#f3f4f6",
  sub: "#c7d2fe",
  muted: "#9ca3af",
  faint: "#6b7280",
  accent: "#818cf8",
  accentBg: "#4f46e5",
  green: "#22c55e",
  amber: "#eab308",
  red: "#ef4444",
  teal: "#0d9488",
};

export const TOP = Platform.OS === "android" ? (StatusBar.currentHeight ?? 24) : 52;

// contexts so screens can navigate / open the menu without prop drilling
const NavCtx = createContext<Nav>({ go: () => {}, back: () => {} });
const MenuCtx = createContext<() => void>(() => {});
export const NavProvider = NavCtx.Provider;
export const MenuProvider = MenuCtx.Provider;
export const useNav = () => useContext(NavCtx);
export const useMenu = () => useContext(MenuCtx);

export function scoreColor(raw: string | number | undefined): string | null {
  const n = typeof raw === "number" ? raw : parseInt(String(raw ?? ""), 10);
  if (Number.isNaN(n)) return null;
  return n >= 70 ? C.green : n >= 40 ? C.amber : C.red;
}

export function Screen({
  title,
  right,
  onBack,
  children,
  scroll = true,
  refreshControl,
}: {
  title: string;
  right?: ReactNode;
  onBack?: () => void;
  children: ReactNode;
  scroll?: boolean;
  refreshControl?: React.ReactElement;
}) {
  const openMenu = useMenu();
  return (
    <View style={s.screen}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <View style={[s.topbar, { paddingTop: TOP }]}>
        <Pressable onPress={onBack ?? openMenu} hitSlop={12} style={s.topIconBtn}>
          <Text style={s.topIcon}>{onBack ? "‹" : "☰"}</Text>
        </Pressable>
        <Text style={s.topTitle} numberOfLines={1}>
          {title}
        </Text>
        <View style={s.topRight}>{right}</View>
      </View>
      {scroll ? (
        <ScrollView contentContainerStyle={s.body} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
          {children}
        </ScrollView>
      ) : (
        <View style={s.bodyFlex}>{children}</View>
      )}
    </View>
  );
}

export function Btn({
  label,
  onPress,
  variant = "primary",
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger" | "success" | "teal";
  disabled?: boolean;
  style?: object;
}) {
  const bg = {
    primary: C.accentBg,
    secondary: C.surface2,
    danger: C.red,
    success: C.green,
    teal: C.teal,
  }[variant];
  return (
    <Pressable
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        s.btn,
        { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.8 : 1 },
        variant === "secondary" && { borderWidth: 1, borderColor: C.border },
        style,
      ]}
    >
      <Text style={[s.btnText, variant === "success" && { color: "#04120a" }]}>{label}</Text>
    </Pressable>
  );
}

export function Card({ children, style, onPress }: { children: ReactNode; style?: object; onPress?: () => void }) {
  if (onPress) {
    return (
      <Pressable onPress={onPress} style={({ pressed }) => [s.card, pressed && { opacity: 0.7 }, style]}>
        {children}
      </Pressable>
    );
  }
  return <View style={[s.card, style]}>{children}</View>;
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <Text style={s.sectionLabel}>{children}</Text>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={s.fieldLabel}>{label}</Text>
      {children}
    </View>
  );
}

export function TextField({ label, ...props }: { label: string } & TextInputProps) {
  return (
    <Field label={label}>
      <TextInput
        placeholderTextColor={C.faint}
        style={[s.input, props.multiline && { height: 100, textAlignVertical: "top" }]}
        {...props}
      />
    </Field>
  );
}

export function NumField({ label, value, onChangeNumber }: { label: string; value: number; onChangeNumber: (v: number) => void }) {
  return (
    <TextField
      label={label}
      value={String(value)}
      keyboardType="number-pad"
      onChangeText={(t) => onChangeNumber(Number(t.replace(/[^0-9.]/g, "")) || 0)}
    />
  );
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
      {tabs.map((t) => (
        <Chip key={t.key} label={t.label} active={t.key === active} onPress={() => onChange(t.key)} />
      ))}
    </ScrollView>
  );
}

export function ToggleRow({ label, value, onValueChange }: { label: string; value: boolean; onValueChange: (v: boolean) => void }) {
  return (
    <View style={s.toggleRow}>
      <Text style={s.toggleLabel}>{label}</Text>
      <Switch value={value} onValueChange={onValueChange} trackColor={{ true: C.accentBg, false: "#333" }} thumbColor="#fff" />
    </View>
  );
}

export function Badge({ label, color }: { label: string; color: string }) {
  return (
    <View style={[s.badge, { borderColor: color }]}>
      <View style={[s.dot, { backgroundColor: color }]} />
      <Text style={[s.badgeText, { color }]}>{label}</Text>
    </View>
  );
}

export function Chip({ label, active, onPress }: { label: string; active?: boolean; onPress?: () => void }) {
  return (
    <Pressable onPress={onPress} style={[s.chip, active && { backgroundColor: C.accentBg, borderColor: C.accentBg }]}>
      <Text style={[s.chipText, active && { color: "#fff" }]}>{label}</Text>
    </Pressable>
  );
}

export function Loading() {
  return <ActivityIndicator style={{ marginTop: 50 }} color={C.accent} />;
}

export function Empty({ text }: { text: string }) {
  return <Text style={s.empty}>{text}</Text>;
}

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  topbar: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: C.border, gap: 4 },
  topIconBtn: { width: 36, height: 36, justifyContent: "center", alignItems: "center" },
  topIcon: { color: C.text, fontSize: 24, fontWeight: "400" },
  topTitle: { color: C.text, fontSize: 19, fontWeight: "800", flex: 1, letterSpacing: -0.3 },
  topRight: { flexDirection: "row", alignItems: "center", gap: 8 },
  body: { padding: 16, paddingBottom: 48 },
  bodyFlex: { flex: 1 },

  btn: { borderRadius: 12, paddingVertical: 14, alignItems: "center", justifyContent: "center" },
  btnText: { color: "#fff", fontSize: 15, fontWeight: "700" },

  card: { backgroundColor: C.surface, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border },

  sectionLabel: { color: C.faint, fontSize: 12, fontWeight: "800", letterSpacing: 1, textTransform: "uppercase", marginTop: 22, marginBottom: 10 },
  fieldLabel: { color: C.muted, fontSize: 13, fontWeight: "600", marginBottom: 6 },
  input: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, color: C.text, fontSize: 15 },

  toggleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 8 },
  toggleLabel: { color: C.text, fontSize: 15, flex: 1, paddingRight: 12 },

  badge: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderRadius: 20, paddingVertical: 4, paddingHorizontal: 10 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  badgeText: { fontSize: 12, fontWeight: "700" },

  chip: { borderWidth: 1, borderColor: C.border, borderRadius: 20, paddingVertical: 7, paddingHorizontal: 14, backgroundColor: C.surface },
  chipText: { color: C.muted, fontWeight: "700", fontSize: 13 },

  empty: { color: C.faint, textAlign: "center", marginTop: 60, fontSize: 15, lineHeight: 24 },
});
