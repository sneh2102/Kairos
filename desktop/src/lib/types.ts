export type Verdict = "yes" | "maybe" | "no";

export interface JobRow {
  id: number;
  ai_recommendation: string;
  company: string;
  title: string;
  link: string;
  location: string;
  site: string;
  years_required: string;
  role_level: string;
  skills_match_pct: string;
  matched_skills: string;
  missing_skills: string;
  reasoning: string;
  description: string;
  posted_date: string;
  application_status: string;
  created_at: string;
  latex_content: string;
  cover_letter_content: string;
  ats_score: number;
  resume_path: string;
  cover_path: string;
}

export interface AppliedRow {
  id: number;
  company: string;
  title: string;
  job_url: string;
  location: string;
  applied_date: string;
  ats_score: number;
  status: string;
  resume_path: string;
  cover_path: string;
  role_level?: string;
  skills_match_pct?: string;
  // full fields below only present on the single-row GET (not the list)
  years_required?: string;
  matched_skills?: string;
  missing_skills?: string;
  reasoning?: string;
  description?: string;
  posted_date?: string;
  site?: string;
  ai_recommendation?: string;
  tex_content?: string;
  cover_letter_content?: string;
}

export interface Stats {
  pending_jobs: number;
  applied_count: number;
  total_extracted: number;
  resumes_created: number;
  verdict_counts: Record<string, number>;
  applied_by_date: { date: string; count: number }[];
  ats_scores: number[];
  top_missing_skills: { skill: string; count: number }[];
  site_counts: { site: string; total: number; yes: number }[];
  recent_applied: { id: number; company: string; title: string; applied_date: string; ats_score: number }[];
}

export interface EducationEntry {
  degree: string;
  dates: string;
  institution: string;
  location: string;
}

export interface ExperienceRole {
  title: string;
  company: string;
  dates: string;
  domain: string;
  total_bullets: number;
  real_bullets: number;
  fabricated_bullets: number;
}

export interface StaticEntry {
  title: string;
  subtitle: string;
  date: string;
  location: string;
  link: string;
  bullets: string[];
}

// kind "static" = written by you in the Resume Designer (no AI); otherwise the AI writes it per job.
export interface CustomSection {
  id: string;
  name: string;
  system_prompt?: string;
  user_prompt?: string;
  kind?: "ai" | "static";
  layout?: "bullets" | "text" | "entries";
  bullets?: string[];
  entries?: StaticEntry[];
}

export interface LayoutStyle {
  font: "computer-modern" | "helvetica" | "times" | "palatino";
  font_size: 10 | 11 | 12;
  margin: "narrow" | "normal" | "wide";
  density: "compact" | "normal" | "relaxed";
  accent: string;
  heading_style: "rule" | "thick" | "none";
  heading_case: "smallcaps" | "caps" | "normal";
  header_align: "center" | "left";
  bullet: "bullet" | "dash" | "circle" | "triangle";
}

export interface Layout {
  style: LayoutStyle;
  section_order: string[];
  hidden_sections: string[];
  custom_sections: CustomSection[];
}

export interface TemplateInfo {
  id: string;
  name: string;
  builtin: boolean;
  active: boolean;
}

export interface PromptInfo {
  label: string;
  description: string;
  text: string;
  default: string;
  placeholders: string[];
  is_default: boolean;
}

export interface GithubRepo {
  name: string;
  full_name: string;
  url: string;
  description: string;
  stars: number;
  language: string;
  is_fork: boolean;
}

export interface Config {
  onboarded?: boolean;
  scraper: {
    sites: string;
    location: string;
    country_indeed: string;
    hours_old: number;
    results_wanted: number;
    is_remote: boolean;
    search_terms: string;
    greenhouse_cookie: string;
  };
  model: {
    scraping: string;
    pipeline: string;
    num_predict: number;
    num_ctx: number;
    temperature: number;
    provider?: "ollama" | "gemini";
    gemini_model?: string;
    gemini_api_keys?: string[];
    task_providers?: Record<string, "default" | "ollama" | "gemini">;
  };
  pipeline: {
    max_ats_iterations: number;
    ats_pass_threshold: number;
    max_no_improve: number;
    build_workers: number;
    output_dir: string;
    resume_path: string;
    projects_path: string;
    resume_filename: string;
    cover_letter_filename: string;
    use_jd_location: boolean;
    default_location: string;
    project_bullets: number;
    project_count?: number;
  };
  section_order: string[];
  google: { client_id: string; client_secret: string };
  profile: {
    full_name: string;
    phone: string;
    email: string;
    linkedin: string;
    github: string;
    location: string;
    experience_yrs: string;
    core_stack: string;
    job_titles: string;
    not_fit_for: string;
    education: EducationEntry[];
    include_links: boolean;
  };
  experience_roles: ExperienceRole[];
  custom_sections: CustomSection[];
  github: { token: string };
  prompts: { job_screener: string; [key: string]: string };
  screener: {
    max_years_exp: number;
    yes_match_pct: number;
    maybe_match_pct: number;
    accept_role_levels: string[];
    required_skills: string;
    preferred_skills: string;
    reject_keywords: string;
    accept_keywords: string;
    blacklisted_companies: string[];
    skip_applied: boolean;
    fuzzy_dedup: boolean;
  };
  scheduler?: { enabled: boolean; time: string; autopilot?: boolean };
  desktop?: { runInBackground: boolean; launchOnStartup: boolean };
  interview?: Partial<SpeechSettings>;
  [key: string]: unknown;
}

export type WsEvent =
  | { type: "log"; level: "INFO" | "WARNING" | "ERROR" | "DEBUG"; message: string }
  | { type: "status"; stage: "scrape" | "apply"; state: string }
  | {
      type: "scrape_job";
      verdict: Verdict;
      company: string;
      title: string;
      location: string;
      skills_match_pct: number;
      matched_skills: string[];
      missing_skills: string[];
    }
  | {
      type: "apply_progress";
      company: string;
      title: string;
      stage: "queued" | "cancelled" | "building" | "checking_ats" | "ats_score" | "done";
      job_index: number;
      total: number;
      iteration?: number;
      score?: number;
      status?: string;
      resume_path?: string;
      cover_path?: string;
      job_id?: number;
    }
  | { type: "done"; stage: "scrape" | "apply" };

// ---- interview prep ----------------------------------------------------------

export interface SpeechSettings {
  stt_engine: "local" | "groq";
  whisper_model: string;
  whisper_device: "auto" | "cuda" | "cpu";
  groq_api_key: string;
  tts_engine: "kokoro" | "edge" | "browser";
  kokoro_voice: string;
  edge_voice: string;
  tts_speed: number;
}

export interface SpeechStatus {
  whisper: { model: string; ready: boolean; download: string | null; device: string | null };
  kokoro: { ready: boolean; download: string | null };
}

export interface Transcript {
  text: string;
  words: { w: string; s: number; e: number }[];
  duration: number;
}

export type InterviewKind = "general" | "behavioral" | "resume" | "technical";

export interface AnswerEval {
  score: number;
  star?: { situation?: boolean; task?: boolean; action?: boolean; result?: boolean };
  criteria?: Record<string, number>;
  strengths?: string[];
  improvements?: string[];
  better_answer?: string;
  missed_concepts?: string[];
  error?: string; // scoring failed; POST /score retries it
}

export interface InterviewTurn {
  id: number;
  session_id: number;
  speaker: "interviewer" | "candidate";
  text: string;
  words: Transcript["words"];
  duration: number;
  created_at: string;
  // interviewer: which planned question; candidate: {skipped}
  meta: { qi?: number; followups?: number; topic?: string; followup?: boolean; closing?: boolean; skipped?: boolean };
  eval: AnswerEval | null;
}

export interface InterviewConfig {
  role?: string;
  company?: string;
  job_id?: number;
  job_source?: "jobs" | "applied";
  length?: "short" | "standard" | "long";
  persona?: "friendly" | "neutral" | "tough";
  interviewer_name?: string;
  topics?: string[];
  difficulty?: "junior" | "mid" | "senior";
}

export interface PlannedQuestion {
  topic: string;
  question: string;
  code?: string; // technical: snippet shown on screen
  language?: string;
}

export interface InterviewSessionSummary {
  id: number;
  kind: InterviewKind;
  title: string;
  status: "active" | "ended";
  score: number | null;
  started_at: string;
  ended_at: string | null;
  answers: number;
  avg_score: number | null;
}

export interface InterviewSession extends Omit<InterviewSessionSummary, "answers" | "avg_score"> {
  config: InterviewConfig;
  context: { company?: string; title?: string; description?: string; plan?: PlannedQuestion[] };
  turns: InterviewTurn[];
}

// ---- interview prep guides -------------------------------------------------------

export interface PrepGuideSummary {
  id: number;
  title: string;
  company: string;
  job_source: string;
  job_id: number | null;
  created_at: string;
}

export interface PrepGuide extends PrepGuideSummary {
  content: {
    company_info: {
      web: boolean; // false = no live research; company facts left out
      sources: { n: number; title: string; url: string }[];
      overview?: string;
      facts?: { label: string; value: string }[];
      products?: string[];
      values?: string[];
      recent_news?: { headline: string; date?: string }[];
      tech_stack?: string[];
      interview_process?: string[];
      culture?: string[];
      talking_points?: string[];
    };
    role_summary?: string;
    focus_areas?: { topic: string; why: string }[];
    fit?: { strengths?: string[]; gaps?: { gap: string; how_to_prepare: string }[] };
    qa?: { category: string; question: string; answer: string; tip?: string }[];
    questions_to_ask?: string[];
    resources?: { topic: string; title: string; url: string; why: string }[];
  };
}
