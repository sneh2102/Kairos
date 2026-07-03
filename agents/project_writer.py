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
   technical requirements.
2. Select the 3-4 projects from the AVAILABLE PROJECTS list that best match the JD's DOMAIN and
   demonstrate those requirements — prefer projects in the same field as the JD, and frame each
   in that field's terminology. NEVER invent a project that is not in the AVAILABLE PROJECTS
   list, and never inflate its scale beyond what's written there.
3. For unmatched JD skills, pick the closest available project and add one honest bullet
   connecting it — do not fabricate a whole new project.
4. Replace the literal placeholder "url" in \href{url}{...} with the actual URL parsed
   from that project's AVAILABLE PROJECTS entry.
5. Each project: 2-3 bullets, each with a specific metric.

BULLET RULES:
- Every bullet = 1.5 lines minimum. Use \textbf{} on project name + 1-2 key technologies.
- Use exact JD keywords naturally. All % -> \%, all & -> \&.

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
