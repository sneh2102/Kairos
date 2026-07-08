"""Skills Writer Agent — tailors the Technical Skills section to the JD."""
from agents._writer_common import SYSTEM_SURGICAL, clean
from config import get_prompt
from llm.client import RotatingOllamaClient

# Default — editable via the Prompts page (config.json prompts.skills_section).
SYSTEM_SKILLS = r"""You are an expert resume writer specializing in ATS optimization.
Output ONLY raw LaTeX for the Technical Skills section.
NO \documentclass, NO \usepackage, NO \begin{document}, NO \end{document}.
Output ONLY the \section{Technical Skills} block — nothing else.

INSTRUCTIONS
1. Read the JD carefully. Extract every distinct technical skill, tool, framework, platform, methodology mentioned.
2. Map each JD keyword to the candidate's existing skills. Use the JD's EXACT spelling and
   casing (JD says "PostgreSQL" -> write "PostgreSQL", not "Postgres"). For key acronyms,
   include both forms once across the section, e.g. "CI/CD (Continuous Integration/Continuous
   Deployment)", so any ATS parser matches either.
3. Create 5-6 categories that match JD domain terminology exactly.
4. Front-load the most JD-relevant keywords first in each category.
5. Include JD-specific tools even if the candidate used equivalents (show both if possible).
6. Category names should mirror JD language.
7. Never add a technology not present anywhere in the candidate's existing resume — one
   optional trailing "Familiar With:" category is allowed for adjacent-but-unused tools.

RULES:
- All % -> \%, all & -> \&. No special chars: no ->, no <>, no em dashes.
- Use exact JD terminology where possible. 8-12 items per category maximum.

OUTPUT FORMAT:
\section{Technical Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
     \textbf{Category 1}{: tool1, tool2, tool3, tool4} \\
     \textbf{Category 2}{: tool1, tool2, tool3, tool4} \\
     \textbf{Category 3}{: tool1, tool2, tool3, tool4} \\
     \textbf{Category 4}{: tool1, tool2, tool3, tool4} \\
     \textbf{Category 5}{: tool1, tool2, tool3, tool4}
    }}
 \end{itemize}"""


def write(client: RotatingOllamaClient, title: str, company: str, description: str,
          existing_resume: str, ats_feedback: str = "") -> str:
    user = (
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        f"CANDIDATE'S EXISTING SKILLS (from resume):\n{existing_resume}\n\n"
        f"ATS FEEDBACK FROM PREVIOUS ATTEMPT (must address every point):\n"
        f"{ats_feedback or 'None — first attempt.'}"
    )
    return clean(client.complete(system=get_prompt("skills_section", SYSTEM_SKILLS), user=user))


def rebuild(client: RotatingOllamaClient, title: str, company: str, description: str,
            feedback: str, current_latex: str) -> str:
    user = (
        f"CURRENT Technical Skills SECTION:\n{current_latex}\n\n"
        f"FEEDBACK TO ADDRESS:\n{feedback}\n\n"
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        "Apply only the requested changes and return the full corrected "
        "\\section{Technical Skills} block."
    )
    return clean(client.complete(system=get_prompt("surgical_rewrite", SYSTEM_SURGICAL), user=user))
