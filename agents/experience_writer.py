"""Experience Writer Agent — rewrites work-experience bullets against the JD.

Roles/titles/dates are locked from config.json's experience_roles (never
invented). Each role gets a config-specified real/fabricated bullet split —
this mirrors the old project's honesty guardrails: never claim a technology
that predates the role's actual dates, never invent a company or title.
"""
from functools import partial

from agents._writer_common import BOLD_RULE, SYSTEM_SURGICAL, ask_json
from config import CONFIG, get_prompt
from llm.client import RotatingOllamaClient
from tools.section_render import render_experience

# Default — editable via the Prompts page (config.json prompts.experience_section).
SYSTEM_EXPERIENCE = r"""You are a senior resume writer. The candidate is a hands-on full-stack /
DevOps engineer who has genuinely worked with every mainstream language and framework (everything
except Rust) and with the standard DevOps toolchain (Docker, Kubernetes, Helm, Terraform, Jenkins,
GitHub Actions, CI/CD, cloud, monitoring, unit/integration/e2e testing frameworks). Anything they
likely touched in some form across their roles is fair game. Write the Experience section as
structured data that reads as a strong, believable match for the JD.

Each role is given a split like "N JD-gap bullets + M core bullets". Treat them differently:

CORE bullets (the REAL ones) - keep these mostly the same:
- Start from the candidate's real bullets in the resume. Keep the same core work and outcome.
- Light edit only: sharpen the wording, work in JD vocabulary, tighten or adjust the metric.
- If the JD uses a different tech stack for the same kind of task (a different language,
  framework, database, cloud, CI tool, test framework), swap the stack but keep the work.
  Example: a real Python/Flask API bullet becomes Node.js/Express or Java/Spring Boot when the
  JD wants that, and a Jenkins pipeline becomes GitHub Actions or GitLab CI.
- Do not rewrite all core bullets - leave roughly half of them very close to the original.

JD-GAP bullets (the NEW ones) - these are where you change and invent:
- Write fresh, believable bullets that cover JD requirements the real bullets do not. Invent a
  plausible task, system, or result that fits the role's domain and the candidate's skill set,
  built around a JD technology or responsibility (Kubernetes/Helm rollouts, Terraform modules,
  Jenkins or other CI/CD pipelines, test automation, observability, event streaming, API
  design, performance tuning, security hardening, and so on).
- The bullet must sit naturally inside that role's domain and scope: a believable project
  for that employer, not a random buzzword drop.
- Do not repeat a theme already covered by a core bullet in the same role.
- Across the whole section, vary which JD themes the new bullets hit, so each role adds
  something different.

JD KEYWORDS:
- Extract the hard skills, tools, frameworks, methodologies and responsibilities from the JD.
- Use the JD's exact spelling and casing ("PostgreSQL" not "Postgres", "CI/CD" as written).
- Get important acronyms in both forms across different bullets ("CI/CD" in one,
  "continuous integration" in another).
- Skip anything involving Rust. Skip a JD item only if the candidate truly could not plausibly
  have done it (for example a niche tool in a stack they have never used and is unrelated).
- Keywords must sit inside real sentences. Never append a comma-separated tool list to a
  bullet.

HARD GUARDRAILS (never break):
- Titles, companies, and dates are LOCKED exactly as given. Never change seniority,
  duration, or total years of experience.
- Match tech to the era of the role's dates: LangChain/agentic AI is 2022+, LLM agents 2023+,
  GPT-4 is March 2023+, production vector DBs 2022+, Kubernetes 2018+.
- Scope must fit seniority and tenure. An intern or a 6-month role does not own platform
  architecture, run a large team, or ship a multi-year migration. A short role gets
  smaller, believable scope.
- Metrics must be believable for that scope.

STYLE - WRITE LIKE A PERSON, NOT A TEMPLATE:
- Each bullet = 1.5 to 2 full lines (about 200-260 characters). Never one-liners.
- Put a specific metric (%, count, latency, scale, time saved, money) in roughly two-thirds
  of the bullets, with believable non-round figures (37%, 11 services, 2.4s to 0.9s,
  team of 4). Metric-free bullets carry concrete nouns: system names, team size, a real
  constraint overcome.
- Start each bullet with a different action verb. Prefer plain strong verbs (built, led,
  cut, shipped, automated, redesigned, migrated, debugged). BANNED: spearheaded, leveraged,
  utilized, synergized, "responsible for", "orchestrated" (unless literally container
  orchestration).
- Simple, spoken English. Vary the rhythm: not every bullet is "Verbed X by doing Y,
  improving Z by N%". Mix in ownership, cross-team work, or one hard problem and how it
  was solved.
- Never mention which bullets are new or which are original.
- Bold only 2-3 key JD terms per bullet. No arrows, no em dashes."""

# Fixed by the code (not editable) — the renderer depends on this exact shape.
JSON_SPEC = """

RESPONSE FORMAT — overrides any output-format instructions above. Reply with ONLY this JSON
object, no prose, no code fences, no LaTeX. One entry per role, in the given order:
{"roles": [{"title": "Job Title", "company": "Company", "dates": "Start - End",
            "location": "City, Province", "bullets": ["bullet one", "bullet two"]}]}
""" + BOLD_RULE


def _format_roles(roles: list[dict]) -> str:
    lines = []
    for i, r in enumerate(roles, 1):
        lines.append(
            f"Role {i}: {r.get('title','')} @ {r.get('company','')} | {r.get('dates','')}\n"
            f"-> {r.get('total_bullets', 4)} bullets: "
            f"{r.get('fabricated_bullets', 2)} JD-gap bullets (NEW, invented to fit the role and cover JD gaps) + "
            f"{r.get('real_bullets', 2)} core bullets (REAL, lightly edited, tech stack swapped to the JD if needed), "
            f"domain: {r.get('domain','')}"
        )
    return "\n".join(lines)


def write(client: RotatingOllamaClient, title: str, company: str, description: str,
          existing_resume: str, experience_roles: list[dict], ats_feedback: str = "") -> str:
    user = (
        f"JOB TITLE: {title}\nCOMPANY: {company}\n"
        f"JOB DESCRIPTION (extract every required skill and responsibility):\n{description}\n\n"
        f"CANDIDATE'S REAL EXPERIENCE (source of truth for real bullets):\n{existing_resume}\n\n"
        f"ROLES -- KEEP TITLES/COMPANY/DATES EXACTLY AS SHOWN:\n{_format_roles(experience_roles)}\n\n"
        f"ATS FEEDBACK (must address every point):\n{ats_feedback or 'None — first attempt.'}"
    )
    return ask_json(client, get_prompt("experience_section", SYSTEM_EXPERIENCE) + JSON_SPEC, user,
                    partial(render_experience, locked_roles=experience_roles))


def rebuild(client: RotatingOllamaClient, title: str, company: str, description: str,
            feedback: str, current_latex: str) -> str:
    user = (
        f"CURRENT Experience SECTION:\n{current_latex}\n\n"
        f"FEEDBACK TO ADDRESS (with company + bullet number references):\n{feedback}\n\n"
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        "Apply only the requested changes. Keep every role's title, company, and dates "
        "identical. Return the full corrected section as JSON."
    )
    return ask_json(client, get_prompt("surgical_rewrite", SYSTEM_SURGICAL) + JSON_SPEC, user,
                    partial(render_experience, locked_roles=CONFIG.get("experience_roles")))
