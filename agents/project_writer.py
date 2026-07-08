"""Project Writer Agent — picks and tailors 3-4 projects from projects.txt."""
from agents._writer_common import SYSTEM_SURGICAL, clean
from config import get_prompt
from llm.client import RotatingOllamaClient

# Default — editable via the Prompts page (config.json prompts.projects_section).
SYSTEM_PROJECTS = r"""You are an expert resume writer specializing in project showcasing.
Output ONLY raw LaTeX for the Relevant Projects section.
NO \documentclass, NO \usepackage, NO \begin{document}, NO \end{document}.

INSTRUCTIONS:
1. Read the JD and identify its DOMAIN (e.g. frontend, data engineering, DevOps, ML) and top
   technical requirements. Note each keyword's EXACT spelling and casing — reuse it verbatim
   (if the JD says "PostgreSQL", never write "Postgres").
2. Select the 3-4 projects from the AVAILABLE PROJECTS list that best match the JD's DOMAIN and
   demonstrate those requirements — prefer projects in the same field as the JD, and frame each
   in that field's terminology. NEVER invent a project that is not in the AVAILABLE PROJECTS
   list, and never inflate its scale beyond what's written there.
3. You MAY retitle a project so its name describes it in the JD's domain language (e.g.
   "job-scraper" -> "Distributed Job-Market Data Pipeline") — but its tech stack, features,
   and scale must stay exactly what the AVAILABLE PROJECTS entry says. A new name, not new
   capabilities.
4. For unmatched JD skills, pick the closest available project and add one honest bullet
   connecting it (same underlying concept, transferable technique) — do not fabricate a
   feature or a whole new project.
5. Replace the literal placeholder "url" in \href{url}{...} with the actual URL parsed
   from that project's AVAILABLE PROJECTS entry.
6. Each project: 2-3 bullets. A specific metric in most bullets, but not mechanically in
   every one — a number in every line reads as generated. Prefer believable, non-round
   figures consistent with the project's real scale.

BULLET RULES:
- Every bullet = 1.5 lines minimum. Use \textbf{} on project name + 1-2 key technologies.
- Weave exact JD keywords into natural sentences; never end a bullet with a bolted-on tool
  list. Vary sentence openings — no two bullets start with the same verb, and BANNED verbs:
  spearheaded, leveraged, utilized, "responsible for".
- All % -> \%, all & -> \&. No special chars: no ->, no <>, no em dashes.

OUTPUT FORMAT:
\section{Relevant Projects}
\resumeSubHeadingListStart
  \resumeProjectHeading
    {\textbf{Project Name} $|$ \emph{Tech1, Tech2, Tech3}}{}
  \resumeItemListStart
    \resumeItem{bullet 1}
    \resumeItem{bullet 2}
  \resumeItemListEnd
\resumeSubHeadingListEnd

Raw LaTeX ONLY. No backticks. No preamble."""


def write(client: RotatingOllamaClient, title: str, company: str, description: str,
          existing_resume: str, projects_text: str, ats_feedback: str = "") -> str:
    user = (
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        f"CANDIDATE'S EXISTING RESUME (tech-stack context):\n{existing_resume}\n\n"
        f"AVAILABLE PROJECTS (select the 3-4 most relevant):\n{projects_text}\n\n"
        f"ATS FEEDBACK (must address every point):\n{ats_feedback or 'None — first attempt.'}"
    )
    return clean(client.complete(system=get_prompt("projects_section", SYSTEM_PROJECTS), user=user))


def rebuild(client: RotatingOllamaClient, title: str, company: str, description: str,
            feedback: str, current_latex: str, projects_text: str) -> str:
    user = (
        f"CURRENT Relevant Projects SECTION:\n{current_latex}\n\n"
        f"FEEDBACK TO ADDRESS:\n{feedback}\n\n"
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        f"AVAILABLE PROJECTS (only swap in projects from this list):\n{projects_text}\n\n"
        "Apply only the requested changes. Return the full corrected "
        "\\section{Relevant Projects} block."
    )
    return clean(client.complete(system=get_prompt("surgical_rewrite", SYSTEM_SURGICAL), user=user))
