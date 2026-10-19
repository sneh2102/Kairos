import type { InterviewKind } from "./types";

export const KIND_INFO: Record<InterviewKind, { label: string; blurb: string }> = {
  behavioral: {
    label: "Behavioral",
    blurb: "“Tell me about a time…” questions picked for the role. Probed for STAR: situation, task, your action, result.",
  },
  resume: {
    label: "Resume deep-dive",
    blurb: "A senior engineer grills you on your own projects: design choices, trade-offs, failures, scale.",
  },
  technical: {
    label: "Tech stack",
    blurb: "Pick technologies (React, SQL, AWS…). Under-the-hood, debugging and code-on-screen questions.",
  },
  general: {
    label: "General screen",
    blurb: "A first-round mix: background, motivation, experience and technical questions.",
  },
};

export const SUGGESTED_TOPICS = [
  "React", "JavaScript", "TypeScript", "Node.js", "Python", "Java", "Spring Boot", "Go", "C#", ".NET",
  "SQL", "PostgreSQL", "MongoDB", "Redis", "Docker", "Kubernetes", "AWS", "Azure", "GCP", "GraphQL",
  "REST APIs", "System design", "Angular", "Vue", "Next.js", "Kafka", "CI/CD", "Linux", "Git",
];

/** Topic chips from a job's comma-separated skill lists: matched skills first, then missing ones. */
export function topicsFromSkills(matched?: string, missing?: string, max = 5): string[] {
  const all = [matched, missing].flatMap((s) => (s || "").split(",")).map((s) => s.trim()).filter(Boolean);
  return [...new Set(all)].slice(0, max);
}

export function scoreTone(score: number) {
  return score >= 8 ? "yes" : score >= 5 ? "maybe" : "no";
}
