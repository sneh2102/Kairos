import type { AppliedRow, Config, CustomSection, ExperienceRole, GithubRepo, JobRow, PromptInfo, Stats } from "./types";

export const BACKEND_URL = "http://127.0.0.1:8756";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
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
  getJob: (id: number) => request<JobRow>(`/api/jobs/${id}`),
  setVerdict: (id: number, verdict: string) =>
    request(`/api/jobs/${id}/verdict`, { method: "PUT", body: JSON.stringify({ verdict }) }),
  deleteJob: (id: number) => request(`/api/jobs/${id}`, { method: "DELETE" }),
  applyJob: (id: number) => request<AppliedRow>(`/api/jobs/${id}/apply`, { method: "POST" }),
  buildJob: (id: number) => request<{ started: boolean }>(`/api/jobs/${id}/build`, { method: "POST" }),
  compileJob: (id: number, latexCode: string) =>
    request<{ compiled: boolean; resume_path: string }>(`/api/jobs/${id}/compile`, {
      method: "POST",
      body: JSON.stringify({ latex: latexCode }),
    }),
  jobResumePdfUrl: (id: number) => `${BACKEND_URL}/api/jobs/${id}/resume.pdf`,
  jobCoverPdfUrl: (id: number) => `${BACKEND_URL}/api/jobs/${id}/cover.pdf`,

  listApplied: () => request<AppliedRow[]>("/api/applied"),
  getApplied: (id: number) => request<AppliedRow>(`/api/applied/${id}`),
  deleteApplied: (id: number) => request(`/api/applied/${id}`, { method: "DELETE" }),
  unapply: (id: number) => request<JobRow>(`/api/applied/${id}/unapply`, { method: "POST" }),
  compileApplied: (id: number, latexCode: string) =>
    request<{ compiled: boolean; resume_path: string }>(`/api/applied/${id}/compile`, {
      method: "POST",
      body: JSON.stringify({ latex: latexCode }),
    }),
  resumePdfUrl: (id: number) => `${BACKEND_URL}/api/outputs/${id}/resume.pdf`,
  coverPdfUrl: (id: number) => `${BACKEND_URL}/api/outputs/${id}/cover.pdf`,

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

  getScheduler: () => request<{ enabled: boolean; time: string }>("/api/scheduler"),
  putScheduler: (payload: { enabled: boolean; time: string }) =>
    request("/api/scheduler", { method: "PUT", body: JSON.stringify(payload) }),
};
