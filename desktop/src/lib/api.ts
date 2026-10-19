import type {
  AppliedRow, Config, CustomSection, ExperienceRole, GithubRepo, InterviewConfig, InterviewKind, InterviewSession,
  InterviewSessionSummary,
  InterviewTurn, JobRow, Layout, PrepGuide, PrepGuideSummary, PromptInfo, SpeechSettings, SpeechStatus, Stats, TemplateInfo, Transcript,
} from "./types";

// Electron always talks to its own local backend directly, no password needed.
// A standalone web deploy has no localhost backend to talk to, so it reads the
// tunnel URL + shared token the user entered on the Connect screen instead.
export const isElectron = typeof window !== "undefined" && !!window.desktop;

const LS_URL = "backendUrl";
const LS_TOKEN = "backendToken";

function readStored() {
  if (isElectron) return { url: "http://127.0.0.1:8756", token: "" };
  try {
    return { url: localStorage.getItem(LS_URL) ?? "", token: localStorage.getItem(LS_TOKEN) ?? "" };
  } catch {
    return { url: "", token: "" };
  }
}

const stored = readStored();
export const BACKEND_URL = stored.url;
const TOKEN = stored.token;

// True once we have a backend to talk to (Electron always does; web needs the
// Connect screen to have run first).
export const isConfigured = isElectron || !!BACKEND_URL;

// Sets the backend URL/token for a standalone web deploy and reloads, so every
// module (this one, eventStream's WS, PDF links) picks up the new value fresh.
export function setBackendConfig(url: string, token: string) {
  localStorage.setItem(LS_URL, url.replace(/\/+$/, ""));
  localStorage.setItem(LS_TOKEN, token);
  window.location.reload();
}

export function clearBackendConfig() {
  localStorage.removeItem(LS_URL);
  localStorage.removeItem(LS_TOKEN);
  window.location.reload();
}

// Appends the shared token as a query param, for plain <embed>/<a> links (PDF
// previews) that can't set the x-api-token header.
function withToken(url: string): string {
  if (!TOKEN) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(TOKEN)}`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(TOKEN ? { "x-api-token": TOKEN } : {}),
    },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    const detail = (() => {
      try {
        return JSON.parse(body).detail;
      } catch {
        return undefined;
      }
    })();
    throw new Error(detail ?? `${options?.method ?? "GET"} ${path} -> ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  health: () => request<{ ok: boolean }>("/api/health"),

  getConfig: () => request<Config>("/api/config"),
  putConfig: (cfg: Config) => request("/api/config", { method: "PUT", body: JSON.stringify(cfg) }),

  getOllamaKeyStatus: () => request<{ is_set: boolean }>("/api/ollama-key"),
  setOllamaKey: (apiKey: string) =>
    request<{ saved: boolean }>("/api/ollama-key", { method: "PUT", body: JSON.stringify({ api_key: apiKey }) }),

  getOllamaKeys: () => request<{ keys: string[] }>("/api/ollama-keys"),
  putOllamaKeys: (keys: string[]) =>
    request<{ saved: boolean }>("/api/ollama-keys", { method: "PUT", body: JSON.stringify({ keys }) }),

  getLayout: () => request<Layout>("/api/layout"),
  saveLayout: (layout: Layout) => request<Layout>("/api/layout", { method: "PUT", body: JSON.stringify(layout) }),
  // compiles an unsaved draft; resolves to a blob: URL for the PDF embed
  previewLayout: async (layout: Layout, signal?: AbortSignal): Promise<string> => {
    const res = await fetch(`${BACKEND_URL}/api/layout/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(TOKEN ? { "x-api-token": TOKEN } : {}) },
      body: JSON.stringify(layout),
      signal,
    });
    if (!res.ok) {
      const detail = await res.json().then((b) => b.detail).catch(() => "");
      throw new Error(detail || "Preview could not be compiled");
    }
    return URL.createObjectURL(await res.blob());
  },
  validateOllamaKey: (apiKey: string) =>
    request<{ valid: boolean; error: string | null }>("/api/validate/ollama-key", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    }),
  validateGeminiKey: (apiKey: string) =>
    request<{ valid: boolean; error: string | null }>("/api/validate/gemini-key", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    }),
  validateGithubToken: (token: string) =>
    request<{ valid: boolean; error: string | null }>("/api/validate/github-token", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  getResumeData: () =>
    request<{
      resume_text: string;
      projects_text: string;
      experience_roles: ExperienceRole[];
      custom_sections: CustomSection[];
      section_order: string[];
    }>("/api/resume-data"),
  putResumeData: (payload: Record<string, unknown>) =>
    request("/api/resume-data", { method: "PUT", body: JSON.stringify(payload) }),

  githubRepos: (username: string) => request<GithubRepo[]>(`/api/github/repos?username=${encodeURIComponent(username)}`),
  githubGenerateEntry: (repoUrl: string) =>
    request<{ entry: string }>("/api/github/generate-entry", {
      method: "POST",
      body: JSON.stringify({ repo_url: repoUrl }),
    }),

  listJobs: (params: { verdict?: string; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
    return request<JobRow[]>(`/api/jobs?${qs.toString()}`);
  },
  setExtensionJob: (id: number) => request(`/api/extension/current/${id}`, { method: "POST" }),
  getJob: (id: number) => request<JobRow>(`/api/jobs/${id}`),
  addManualJob: (payload: { title: string; company: string; location: string; job_url: string; description: string }) =>
    request<JobRow>("/api/jobs/manual", { method: "POST", body: JSON.stringify(payload) }),
  setVerdict: (id: number, verdict: string) =>
    request(`/api/jobs/${id}/verdict`, { method: "PUT", body: JSON.stringify({ verdict }) }),
  deleteJob: (id: number) => request(`/api/jobs/${id}`, { method: "DELETE" }),
  removeNoJobs: () => request<{ removed: number }>("/api/jobs/remove-no", { method: "POST" }),
  removeNotAppliedJobs: () => request<{ removed: number }>("/api/jobs/remove-not-applied", { method: "POST" }),
  removeAllJobs: () => request<{ removed: number }>("/api/jobs/remove-all", { method: "POST" }),
  removeBlacklistedJobs: () => request<{ removed: number }>("/api/jobs/remove-blacklisted", { method: "POST" }),
  applyJob: (id: number) => request<AppliedRow>(`/api/jobs/${id}/apply`, { method: "POST" }),
  buildJob: (id: number, engine: "default" | "claude" = "default") =>
    request<{ started: boolean }>(`/api/jobs/${id}/build`, { method: "POST", body: JSON.stringify({ engine }) }),
  compileJob: (id: number, latexCode: string) =>
    request<{ compiled: boolean; resume_path: string }>(`/api/jobs/${id}/compile`, {
      method: "POST",
      body: JSON.stringify({ latex: latexCode }),
    }),
  rebuildableSections: () => request<{ id: string; name: string }[]>("/api/rebuildable-sections"),
  rebuildSection: (id: number, sectionId: string, message: string, latex: string) =>
    request<{ section_id: string; latex: string; block: string }>(`/api/jobs/${id}/rebuild-section`, {
      method: "POST",
      body: JSON.stringify({ section_id: sectionId, message, latex }),
    }),
  jobResumePdfUrl: (id: number) => withToken(`${BACKEND_URL}/api/jobs/${id}/resume.pdf`),
  jobCoverPdfUrl: (id: number) => withToken(`${BACKEND_URL}/api/jobs/${id}/cover.pdf`),

  listApplied: () => request<AppliedRow[]>("/api/applied"),
  getApplied: (id: number) => request<AppliedRow>(`/api/applied/${id}`),
  deleteApplied: (id: number) => request(`/api/applied/${id}`, { method: "DELETE" }),
  unapply: (id: number) => request<JobRow>(`/api/applied/${id}/unapply`, { method: "POST" }),
  compileApplied: (id: number, latexCode: string) =>
    request<{ compiled: boolean; resume_path: string }>(`/api/applied/${id}/compile`, {
      method: "POST",
      body: JSON.stringify({ latex: latexCode }),
    }),
  resumePdfUrl: (id: number) => withToken(`${BACKEND_URL}/api/outputs/${id}/resume.pdf`),
  coverPdfUrl: (id: number) => withToken(`${BACKEND_URL}/api/outputs/${id}/cover.pdf`),

  listTemplates: () => request<TemplateInfo[]>("/api/templates"),
  getTemplate: (id: string) => request<{ id: string; content: string }>(`/api/templates/${id}`),
  addTemplate: (name: string, content: string) =>
    request<{ id: string }>("/api/templates", { method: "POST", body: JSON.stringify({ name, content }) }),
  updateTemplate: (id: string, content: string) =>
    request(`/api/templates/${id}`, { method: "PUT", body: JSON.stringify({ content }) }),
  deleteTemplate: (id: string) => request(`/api/templates/${id}`, { method: "DELETE" }),
  activateTemplate: (id: string) => request(`/api/templates/${id}/activate`, { method: "POST" }),
  templatePreviewUrl: (id: string) => withToken(`${BACKEND_URL}/api/templates/${id}/preview.pdf`),

  getPrompts: () => request<Record<string, PromptInfo>>("/api/prompts"),
  savePrompt: (key: string, text: string) =>
    request<{ saved: boolean }>(`/api/prompts/${key}`, { method: "PUT", body: JSON.stringify({ text }) }),
  resetPrompt: (key: string) => request<{ text: string }>(`/api/prompts/${key}/reset`, { method: "POST" }),

  getStats: () => request<Stats>("/api/stats"),

  startScrape: () => request<{ started: boolean }>("/api/scrape/start", { method: "POST" }),
  stopScrape: () => request("/api/scrape/stop", { method: "POST" }),
  startApply: (verdicts: string[] = ["yes"]) =>
    request<{ started: boolean; count: number }>("/api/apply/start", {
      method: "POST",
      body: JSON.stringify({ verdicts }),
    }),
  stopApply: () => request("/api/apply/stop", { method: "POST" }),
  cancelBuild: (id: number) => request(`/api/jobs/${id}/build/cancel`, { method: "POST" }),
  applyQueue: () => request<{ running: boolean; job_ids: number[]; total: number; done: number }>("/api/apply/queue"),

  getScheduler: () => request<{ enabled: boolean; time: string }>("/api/scheduler"),
  putScheduler: (payload: { enabled: boolean; time: string }) =>
    request("/api/scheduler", { method: "PUT", body: JSON.stringify(payload) }),

  greenhouseStatus: () => request<{ connected: boolean }>("/api/greenhouse/status"),
  greenhouseConnect: () => request<{ connected: boolean }>("/api/greenhouse/connect", { method: "POST" }),
  greenhouseDisconnect: () => request<{ disconnected: boolean }>("/api/greenhouse/disconnect", { method: "POST" }),
  jobrightStatus: () => request<{ connected: boolean }>("/api/jobright/status"),
  jobrightConnect: () => request<{ connected: boolean }>("/api/jobright/connect", { method: "POST" }),
  jobrightDisconnect: () => request<{ disconnected: boolean }>("/api/jobright/disconnect", { method: "POST" }),

  // ---- interview prep ----
  speechStatus: () => request<SpeechStatus>("/api/speech/status"),
  speechDownload: (what: string) =>
    request<{ started: boolean }>("/api/speech/download", { method: "POST", body: JSON.stringify({ what }) }),
  speechWarmup: () => request("/api/speech/warmup", { method: "POST" }),
  speechVoices: () => request<{ kokoro: string[] }>("/api/speech/voices"),
  // raw audio body, not multipart
  transcribe: async (audio: Blob): Promise<Transcript> => {
    const res = await fetch(`${BACKEND_URL}/api/speech/transcribe`, {
      method: "POST",
      headers: { "Content-Type": audio.type || "audio/webm", ...(TOKEN ? { "x-api-token": TOKEN } : {}) },
      body: audio,
    });
    if (!res.ok) throw new Error(await res.json().then((b) => b.detail).catch(() => `Transcription failed (${res.status})`));
    return res.json();
  },
  // null = 204: the server has no voice for this, speak it in the browser
  speak: (text: string, settings?: Partial<SpeechSettings>) =>
    fetchAudio("/api/speech/tts", { method: "POST", body: JSON.stringify({ text, settings }) }),
  turnSpeech: (turnId: number) => fetchAudio(`/api/interview/turns/${turnId}/speech`),

  listInterviews: () => request<InterviewSessionSummary[]>("/api/interview/sessions"),
  getInterview: (id: number) => request<InterviewSession>(`/api/interview/sessions/${id}`),
  createInterview: (kind: InterviewKind, config: InterviewConfig) =>
    request<InterviewSession>("/api/interview/sessions", { method: "POST", body: JSON.stringify({ kind, config }) }),
  answerInterview: (
    id: number,
    body: { text?: string; words?: Transcript["words"]; duration?: number; edit_turn_id?: number; skip?: boolean },
  ) =>
    request<{ candidate: InterviewTurn | null; interviewer: InterviewTurn; done: boolean }>(
      `/api/interview/sessions/${id}/answer`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  scoreMissing: (id: number) => request<{ scoring: number }>(`/api/interview/sessions/${id}/score`, { method: "POST" }),
  endInterview: (id: number) => request<InterviewSession>(`/api/interview/sessions/${id}/end`, { method: "POST" }),
  deleteInterview: (id: number) => request(`/api/interview/sessions/${id}`, { method: "DELETE" }),

  // body: {job_source, job_id} or {role, company}; takes ~20-60s (web research + generation)
  createPrepGuide: (body: { job_source?: string; job_id?: number; role?: string; company?: string }) =>
    request<PrepGuide>("/api/prep", { method: "POST", body: JSON.stringify(body) }),
  listPrepGuides: () => request<PrepGuideSummary[]>("/api/prep"),
  getPrepGuide: (id: number) => request<PrepGuide>(`/api/prep/${id}`),
  deletePrepGuide: (id: number) => request(`/api/prep/${id}`, { method: "DELETE" }),
};

async function fetchAudio(path: string, options?: RequestInit): Promise<Blob | null> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(TOKEN ? { "x-api-token": TOKEN } : {}) },
  });
  if (res.status === 204) return null;
  if (!res.ok) throw new Error(`Speech failed (${res.status})`);
  return res.blob();
}
