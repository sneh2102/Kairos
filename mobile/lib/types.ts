// Mirror of the desktop app's types (desktop/src/lib/types.ts).
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

export interface CustomSection {
  id: string;
  name: string;
  system_prompt: string;
  user_prompt: string;
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
  };
  model: {
    scraping: string;
    pipeline: string;
    num_predict: number;
    num_ctx: number;
    temperature: number;
  };
  pipeline: {
    max_ats_iterations: number;
    ats_pass_threshold: number;
    max_no_improve: number;
    output_dir: string;
    resume_path: string;
    projects_path: string;
    resume_filename: string;
    cover_letter_filename: string;
    use_jd_location: boolean;
    default_location: string;
  };
  section_order: string[];
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
      stage: "building" | "checking_ats" | "ats_score" | "done";
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
