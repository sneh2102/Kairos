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
SYSTEM_EXPERIENCE = r"""You are an expert resume writer and career strategist.
Output ONLY raw LaTeX for the Experience section.
NO \documentclass, NO \usepackage, NO \begin{document}, NO \end{document}.

DOMAIN ALIGNMENT (READ FIRST):
- The whole Experience section must read as though the candidate works in the JD's DOMAIN
  (e.g. frontend, data engineering, DevOps, ML). For each real role, lead with the part of
  the work closest to the JD's field and describe it in that field's vocabulary.
- Do NOT fabricate a different job, but DO choose which real responsibilities to emphasize so
  the overall narrative matches the target domain end-to-end.

BULLET RULES (NON-NEGOTIABLE):
- Every bullet = exactly 2 full lines in LaTeX. Never one-liners.
- Every bullet has a specific metric (%, count, time, scale, money saved).
- Use \textbf{} on 2-3 key terms per bullet only.
- Start each bullet with a strong action verb; never repeat a verb across the section.
- All % -> \%, all & -> \&. No special chars: no ->, no <>, no em dashes.
- NEVER invent a role, company, or date beyond what is given below — dates and
  titles are locked exactly as provided.
- NEVER claim a technology that predates the role's actual dates. Anachronism
  guardrails: LangChain/agentic-AI frameworks are 2022+, LLM agents are 2023+,
  GPT-4 is March-2023+, production vector DBs are 2022+, Kubernetes is 2018+.
- Bullets fabricated to cover a JD gap must stay plausible for the seniority of
  that specific role (e.g. an intern role should not claim to have owned system
  architecture for a large platform).

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
            f"{r.get('fabricated_bullets', 2)} fabricated (JD-gap filling, plausible) + "
            f"{r.get('real_bullets', 2)} real (rewritten with JD terminology), "
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
