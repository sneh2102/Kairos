import { fetch as expoFetch } from "expo/fetch";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { API_BASE, API_TOKEN } from "../config";
import type {
  AppliedRow,
  Config,
  CustomSection,
  ExperienceRole,
  GithubRepo,
  JobRow,
  PromptInfo,
  Stats,
  TemplateInfo,
  Verdict,
} from "./types";

const authHeaders = { "x-api-token": API_TOKEN };

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status} ${await res.text().catch(() => "")}`);
  return res.json();
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { ...authHeaders, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${await res.text().catch(() => "")}`);
  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface ResumeData {
  resume_text: string;
  projects_text: string;
  experience_roles: ExperienceRole[];
  custom_sections: CustomSection[];
  section_order: string[];
}

export const api = {
  health: () => get<{ ok: boolean }>("/api/health"),

  getConfig: () => get<Config>("/api/config"),
  putConfig: (cfg: Config) => send("PUT", "/api/config", cfg),

  getOllamaKeyStatus: () => get<{ is_set: boolean }>("/api/ollama-key"),
  setOllamaKey: (apiKey: string) => send<{ saved: boolean }>("PUT", "/api/ollama-key", { api_key: apiKey }),
  getOllamaKeys: () => get<{ keys: string[] }>("/api/ollama-keys"),
  putOllamaKeys: (keys: string[]) => send<{ saved: boolean }>("PUT", "/api/ollama-keys", { keys }),

  getResumeData: () => get<ResumeData>("/api/resume-data"),
  putResumeData: (payload: Record<string, unknown>) => send("PUT", "/api/resume-data", payload),

  githubRepos: (username: string) => get<GithubRepo[]>(`/api/github/repos?username=${encodeURIComponent(username)}`),
  githubGenerateEntry: (repoUrl: string) => send<{ entry: string }>("POST", "/api/github/generate-entry", { repo_url: repoUrl }),

  listJobs: (params: { verdict?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
    return get<JobRow[]>(`/api/jobs?${qs.toString()}`);
  },
  getJob: (id: number) => get<JobRow>(`/api/jobs/${id}`),
  addManualJob: (payload: { title: string; company: string; location: string; job_url: string; description: string }) =>
    send<JobRow>("POST", "/api/jobs/manual", payload),
  setVerdict: (id: number, verdict: Verdict) => send("PUT", `/api/jobs/${id}/verdict`, { verdict }),
  deleteJob: (id: number) => send("DELETE", `/api/jobs/${id}`),
  removeNoJobs: () => send<{ removed: number }>("POST", "/api/jobs/remove-no"),
  removeNotAppliedJobs: () => send<{ removed: number }>("POST", "/api/jobs/remove-not-applied"),
  removeAllJobs: () => send<{ removed: number }>("POST", "/api/jobs/remove-all"),
  removeBlacklistedJobs: () => send<{ removed: number }>("POST", "/api/jobs/remove-blacklisted"),
  applyJob: (id: number) => send<AppliedRow>("POST", `/api/jobs/${id}/apply`),
  buildJob: (id: number) => send<{ started: boolean }>("POST", `/api/jobs/${id}/build`),
  compileJob: (id: number, latexCode: string) =>
    send<{ compiled: boolean; resume_path: string }>("POST", `/api/jobs/${id}/compile`, { latex: latexCode }),

  listApplied: () => get<AppliedRow[]>("/api/applied"),
  getApplied: (id: number) => get<AppliedRow>(`/api/applied/${id}`),
  deleteApplied: (id: number) => send("DELETE", `/api/applied/${id}`),
  unapply: (id: number) => send<JobRow>("POST", `/api/applied/${id}/unapply`),
  compileApplied: (id: number, latexCode: string) =>
    send<{ compiled: boolean; resume_path: string }>("POST", `/api/applied/${id}/compile`, { latex: latexCode }),

  listTemplates: () => get<TemplateInfo[]>("/api/templates"),
  getTemplate: (id: string) => get<{ id: string; content: string }>(`/api/templates/${id}`),
  addTemplate: (name: string, content: string) => send<{ id: string }>("POST", "/api/templates", { name, content }),
  updateTemplate: (id: string, content: string) => send("PUT", `/api/templates/${id}`, { content }),
  deleteTemplate: (id: string) => send("DELETE", `/api/templates/${id}`),
  activateTemplate: (id: string) => send("POST", `/api/templates/${id}/activate`),

  getPrompts: () => get<Record<string, PromptInfo>>("/api/prompts"),
  savePrompt: (key: string, text: string) => send<{ saved: boolean }>("PUT", `/api/prompts/${key}`, { text }),
  resetPrompt: (key: string) => send<{ text: string }>("POST", `/api/prompts/${key}/reset`),

  getStats: () => get<Stats>("/api/stats"),

  startScrape: () => send<{ started: boolean }>("POST", "/api/scrape/start"),
  stopScrape: () => send("POST", "/api/scrape/stop"),
  startApply: (verdicts: string[] = ["yes"]) => send<{ started: boolean; count: number }>("POST", "/api/apply/start", { verdicts }),
  stopApply: () => send("POST", "/api/apply/stop"),

  getScheduler: () => get<{ enabled: boolean; time: string }>("/api/scheduler"),
  putScheduler: (payload: { enabled: boolean; time: string }) => send("PUT", "/api/scheduler", payload),
};

function safeName(s: string) {
  return s.replace(/[^a-z0-9]+/gi, "_").slice(0, 60);
}

// Fetch a PDF built on your PC as raw bytes (expo/fetch carries the auth header).
export async function fetchPdfBytes(apiPath: string): Promise<Uint8Array> {
  const res = await expoFetch(`${API_BASE}${apiPath}`, { headers: authHeaders });
  if (!res.ok) {
    throw new Error(res.status === 404 ? "No PDF built for this job yet." : `Download failed (${res.status}).`);
  }
  return new Uint8Array(await res.arrayBuffer());
}

// Download a PDF and open the share sheet ("Save to Files" keeps it on-device).
export async function downloadPdf(apiPath: string, filename: string): Promise<string> {
  const bytes = await fetchPdfBytes(apiPath);
  const file = new File(Paths.document, safeName(filename) + ".pdf");
  if (file.exists) file.delete();
  file.create();
  file.write(bytes);
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(file.uri, { mimeType: "application/pdf", UTI: "com.adobe.pdf" });
  }
  return file.uri;
}
