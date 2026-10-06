"""Skills Writer Agent — tailors the Technical Skills section to the JD.

The model returns JSON; tools.section_render turns it into LaTeX."""
from agents._writer_common import SYSTEM_SURGICAL, ask_json
from config import get_prompt
from llm.client import RotatingOllamaClient
from tools.section_render import render_skills

# Default — editable via the Prompts page (config.json prompts.skills_section).
SYSTEM_SKILLS = r"""You are an expert resume writer specializing in ATS optimization.
Output ONLY raw LaTeX for the Technical Skills section.
NO \documentclass, NO \usepackage, NO \begin{{document}}, NO \end{{document}}.
Output ONLY the \section{{Technical Skills}} block — nothing else.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JOB TITLE:   {title}
COMPANY:     {company}
JOB DESCRIPTION:
{description}

CANDIDATE'S EXISTING SKILLS (from resume):
{existing_resume}

ATS FEEDBACK FROM PREVIOUS ATTEMPT (MUST address every point):
{ats_feedback}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Read the JD carefully. Extract EVERY distinct technical skill, tool, framework, platform, methodology mentioned.
2. Map each JD keyword to the candidate's existing skills.
3. Create 5-6 categories that match JD domain terminology exactly.
4. FRONT-LOAD: Put the most JD-relevant keywords FIRST in each category.
5. Include JD-specific tools even if candidate used equivalents (show both if possible).
6. Category names should mirror JD language (e.g. if JD says "Cloud Infrastructure" use that, not "Cloud").

CATEGORY EXAMPLES BY DOMAIN:
- Languages: Python, Java, TypeScript, JavaScript, Go, SQL, Bash
- Frontend: React, Next.js, TypeScript, HTML5, CSS3, Tailwind CSS
- Backend: Node.js, FastAPI, Spring Boot, REST APIs, GraphQL, Microservices
- Cloud & DevOps: AWS (EC2, S3, Lambda, RDS), Docker, Kubernetes, Terraform, CI/CD, GitHub Actions
- Data & AI: PostgreSQL, MongoDB, Redis, Apache Kafka, Spark, LangChain, pandas, scikit-learn
- Tools: Git, JIRA, Linux, VS Code, Postman, Jupyter

RULES:
- All % → \%, all & → \&
- No special chars: no ->, no <>, no em dashes
- Use exact JD terminology where possible
- 8-12 items per category maximum

OUTPUT FORMAT:
\section{{Technical Skills}}
 \begin{{itemize}}[leftmargin=0.15in, label={{}}]
    \small{{\item{{
     \textbf{{[Category 1]}}{{: tool1, tool2, tool3, tool4}} \\
     \textbf{{[Category 2]}}{{: tool1, tool2, tool3, tool4}} \\
     \textbf{{[Category 3]}}{{: tool1, tool2, tool3, tool4}} \\
     \textbf{{[Category 4]}}{{: tool1, tool2, tool3, tool4}} \\
     \textbf{{[Category 5]}}{{: tool1, tool2, tool3, tool4}} \\
     \textbf{{[Category 6]}}{{: tool1, tool2, tool3, tool4}}
    }}}
 \end{{itemize}}"""

# Fixed by the code (not editable) — the renderer depends on this exact shape.
JSON_SPEC = """

RESPONSE FORMAT — overrides any output-format instructions above. Reply with ONLY this JSON
object, no prose, no code fences, no LaTeX:
{"categories": [{"name": "Category name", "items": ["skill", "skill", "skill"]}]}"""


def write(client: RotatingOllamaClient, title: str, company: str, description: str,
          existing_resume: str, ats_feedback: str = "") -> str:
    user = (
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        f"CANDIDATE'S EXISTING SKILLS (from resume):\n{existing_resume}\n\n"
        f"ATS FEEDBACK FROM PREVIOUS ATTEMPT (must address every point):\n"
        f"{ats_feedback or 'None — first attempt.'}"
    )
    return ask_json(client, get_prompt("skills_section", SYSTEM_SKILLS) + JSON_SPEC, user, render_skills)


def rebuild(client: RotatingOllamaClient, title: str, company: str, description: str,
            feedback: str, current_latex: str) -> str:
    user = (
        f"CURRENT Technical Skills SECTION (for reference):\n{current_latex}\n\n"
        f"FEEDBACK TO ADDRESS:\n{feedback}\n\n"
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        "Apply only the requested changes and return the full corrected section as JSON."
    )
    return ask_json(client, get_prompt("surgical_rewrite", SYSTEM_SURGICAL) + JSON_SPEC, user, render_skills)
