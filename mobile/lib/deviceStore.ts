// Mirrors built PDFs onto the phone in the SAME folder tree the desktop app
// uses on disk: <Company>/<Title>/<Filename>.pdf.
//
// Android: Storage Access Framework — the user picks a base folder ONCE, we get
//   a persistable tree URI, and every later save writes silently into it.
// iOS: apps can't write to arbitrary user folders (Apple sandbox), so we mirror
//   the same subfolder tree inside the app's own Documents dir, which app.json
//   exposes in the Files app under "On My iPhone → <app>".
import { Platform } from "react-native";
import { Directory, File, Paths } from "expo-file-system";
import { StorageAccessFramework as SAF } from "expo-file-system/legacy";
import { fetchPdfBytes } from "./api";

// Mirror of tools/latex.py sanitize_folder_name — keep in sync so phone folder
// names match the PC exactly. Uses ASCII \w (not Unicode \p{L}) on purpose:
// Hermes fails to compile Unicode property-escape regexes and bricks the bundle.
// ASCII names match Python exactly; a heavily accented name may differ by a char.
export function sanitizeFolder(name: string): string {
  const stripped = (name || "unknown").replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "_");
  return stripped.slice(0, 60) || "unknown";
}

export interface MirrorTarget {
  company: string;
  title: string;
  filename: string; // desktop's resume_filename / cover_letter_filename, no extension
}

// Thrown when Android has no picked base folder yet — caller prompts pickMirrorRoot().
export class NeedFolderError extends Error {
  constructor() {
    super("no-folder");
    this.name = "NeedFolderError";
  }
}

// Persisted Android SAF tree URI lives in one tiny file in app documents.
const rootFile = () => new File(Paths.document, "mirror-root.txt");

export function getMirrorRoot(): string | null {
  if (Platform.OS !== "android") return null;
  const f = rootFile();
  return f.exists ? f.textSync().trim() || null : null;
}

export async function pickMirrorRoot(): Promise<string> {
  const res = await SAF.requestDirectoryPermissionsAsync();
  if (!res.granted) throw new Error("Folder access was not granted.");
  const f = rootFile();
  if (f.exists) f.delete();
  f.create();
  f.write(res.directoryUri);
  return res.directoryUri;
}

export function clearMirrorRoot() {
  const f = rootFile();
  if (f.exists) f.delete();
}

// SAF child URIs encode the path; the display name is the last decoded segment.
const nameOf = (uri: string) => decodeURIComponent(uri).split("/").pop() ?? "";

// SAF makeDirectoryAsync is NOT idempotent (creates "Company (1)" if it exists),
// so look for an existing child first.
async function safChildDir(parentUri: string, name: string): Promise<string> {
  const kids = await SAF.readDirectoryAsync(parentUri);
  return kids.find((u) => nameOf(u) === name) ?? (await SAF.makeDirectoryAsync(parentUri, name));
}

// Bytes → base64 without pulling a dependency: round-trip through a temp file.
function toBase64(bytes: Uint8Array): string {
  const tmp = new File(Paths.cache, "mirror-tmp");
  if (tmp.exists) tmp.delete();
  tmp.create();
  tmp.write(bytes);
  const b64 = tmp.base64Sync();
  tmp.delete();
  return b64;
}

// Writes the PDF into <Company>/<Title>/<Filename>.pdf and returns the relative
// path for a confirmation message.
export async function mirrorToDevice(bytes: Uint8Array, t: MirrorTarget): Promise<string> {
  const company = sanitizeFolder(t.company);
  const title = sanitizeFolder(t.title);
  const rel = `${company}/${title}/${t.filename}.pdf`;

  if (Platform.OS === "android") {
    const root = getMirrorRoot();
    if (!root) throw new NeedFolderError();
    const titleUri = await safChildDir(await safChildDir(root, company), title);
    const kids = await SAF.readDirectoryAsync(titleUri);
    const existing = kids.find((u) => nameOf(u) === `${t.filename}.pdf`);
    const fileUri = existing ?? (await SAF.createFileAsync(titleUri, t.filename, "application/pdf"));
    await SAF.writeAsStringAsync(fileUri, toBase64(bytes), { encoding: "base64" });
    return rel;
  }

  // iOS / other: app Documents, exposed via app.json ios.infoPlist file sharing.
  const dir = new Directory(Paths.document, "Resumes", company, title);
  dir.create({ intermediates: true, idempotent: true });
  const file = new File(dir, `${t.filename}.pdf`);
  if (file.exists) file.delete();
  file.create();
  file.write(bytes);
  return `Resumes/${rel}`;
}

// Fetch a built PDF from the PC and mirror it, prompting once for the Android
// base folder if none is set yet. Returns the relative path saved.
export async function savePdfToPhone(apiPath: string, target: MirrorTarget): Promise<string> {
  const bytes = await fetchPdfBytes(apiPath);
  try {
    return await mirrorToDevice(bytes, target);
  } catch (e) {
    if (!(e instanceof NeedFolderError)) throw e;
    await pickMirrorRoot();
    return mirrorToDevice(bytes, target);
  }
}
