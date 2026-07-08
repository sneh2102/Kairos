"""Experience Writer Agent — rewrites work-experience bullets against the JD.

Roles/titles/dates are locked from config.json's experience_roles (never
invented). Each role gets a config-specified real/fabricated bullet split —
this mirrors the old project's honesty guardrails: never claim a technology
that predates the role's actual dates, never invent a company or title.
"""
from agents._writer_common import SYSTEM_SURGICAL, clean
from config import get_prompt
from llm.client import RotatingOllamaClient

# Default — editable via the Prompts page (config.json prompts.experience_section).
SYSTEM_EXPERIENCE = r"""You are a senior resume writer who tailors real experience to a
specific job description. Output ONLY raw LaTeX for the Experience section.
NO \documentclass, NO \usepackage, NO \begin{document}, NO \end{document}.

STEP 1 — MINE THE JD FOR KEYWORDS:
- Extract every hard skill, tool, framework, methodology, and responsibility from the JD.
- Use each keyword with the EXACT spelling and casing the JD uses (if the JD says
  "PostgreSQL", never write "Postgres"; if it says "CI/CD", use "CI/CD").
- For important acronyms, get both forms into the section across different bullets
  (e.g. "CI/CD" in one bullet, "continuous integration" in another) so any ATS parser
  matches either form.
- Keywords must sit inside real sentences doing grammatical work. Never append a
  comma-separated tool list to the end of a bullet — that reads as keyword stuffing to
  both ATS scorers and humans.

STEP 2 — DOMAIN ALIGNMENT (REFRAME, DON'T INVENT):
- The whole section must read as though the candidate works in the JD's DOMAIN
  (frontend, data engineering, DevOps, ML, etc.). For each real role, lead with the part
  of the work closest to the JD's field and describe it in that field's vocabulary.
- Titles, companies, and dates are LOCKED exactly as given. Never adjust seniority,
  duration, or total years of experience.
- Every bullet must trace back to work in CANDIDATE'S REAL EXPERIENCE. To cover a JD
  gap you may: re-describe real work in JD terminology; surface implied-but-unstated
  parts of that work (someone who shipped feature X necessarily also tested, reviewed,
  and deployed it); and choose which real responsibilities to emphasize. You may NOT
  claim projects, systems, technologies, or outcomes with no basis in the real experience.
- NEVER claim a technology that predates the role's actual dates. Anachronism
  guardrails: LangChain/agentic-AI frameworks are 2022+, LLM agents are 2023+,
  GPT-4 is March-2023+, production vector DBs are 2022+, Kubernetes is 2018+.
- Scope must fit the role's seniority (an intern does not own system architecture
  for a large platform).

STEP 3 — WRITE LIKE A PERSON, NOT A TEMPLATE:
- Each bullet = 1.5 to 2 full LaTeX lines. Never one-liners.
- Put a specific metric (%, count, latency, scale, money) in roughly two-thirds of the
  bullets — a number in every single line is a known AI tell. Numbers must come from or
  stay consistent with the real experience; prefer believable non-round figures.
  Metric-free bullets carry concrete nouns instead: system names, team size, a real
  constraint that was overcome.
- Start each bullet with a different action verb. Prefer plain strong verbs (built,
  led, cut, shipped, automated, redesigned, migrated, debugged) over resume clichés.
  BANNED: spearheaded, leveraged, utilized, synergized, "responsible for",
  "orchestrated" (unless literally about container orchestration).
- Vary bullet rhythm. Not every bullet is "Verbed X by doing Y, improving Z by N%" —
  mix in a bullet about ownership, cross-team work, or one hard problem and how it
  was solved.
- Use \textbf{} on 2-3 key JD terms per bullet only.
- All % -> \%, all & -> \&. No special chars: no ->, no <>, no em dashes.

OUTPUT:
\section{Experience}
\resumeSubHeadingListStart
  [each role, in the given order]
  \resumeSubheading{Job Title}{Start -- End}{Company}{Location}
  \resumeItemListStart
    \resumeItem{bullet}
  \resumeItemListEnd
\resumeSubHeadingListEnd

Raw LaTeX ONLY. No backticks. No preamble."""


def _format_roles(roles: list[dict]) -> str:
    lines = []
    for i, r in enumerate(roles, 1):
        lines.append(
            f"Role {i}: {r.get('title','')} @ {r.get('company','')} | {r.get('dates','')}\n"
            f"-> {r.get('total_bullets', 4)} bullets: "
            f"{r.get('fabricated_bullets', 2)} JD-gap bullets (real work reframed/extended in JD terms) + "
            f"{r.get('real_bullets', 2)} core bullets (rewritten with JD terminology), "
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
    return clean(client.complete(system=get_prompt("experience_section", SYSTEM_EXPERIENCE), user=user))


def rebuild(client: RotatingOllamaClient, title: str, company: str, description: str,
            feedback: str, current_latex: str) -> str:
    user = (
        f"CURRENT Experience SECTION:\n{current_latex}\n\n"
        f"FEEDBACK TO ADDRESS (with company + bullet number references):\n{feedback}\n\n"
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        "Apply only the requested changes. Keep every role's title, company, and dates "
        "identical. Return the full corrected \\section{Experience} block."
    )
    return clean(client.complete(system=get_prompt("surgical_rewrite", SYSTEM_SURGICAL), user=user))
