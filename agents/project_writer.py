"""Project Writer Agent — picks and tailors 3-4 projects from projects.txt.

The model returns JSON; tools.section_render turns it into LaTeX. GitHub links
are looked up from projects.txt in code, never typed by the model."""
import re
from functools import partial

from agents._writer_common import BOLD_RULE, SYSTEM_SURGICAL, ask_json
from config import CONFIG, get_prompt
from llm.client import RotatingOllamaClient
from tools.section_render import render_projects


def _pinned() -> str:
    """Projects the user wants on every resume (config.json `pinned_projects`)."""
    names = [n for n in CONFIG.get("pinned_projects", []) if n]
    return (f"MUST INCLUDE these projects (they count toward the 3-4 total): {', '.join(names)}\n\n"
            if names else "")

# Default — editable via the Prompts page (config.json prompts.projects_section).
SYSTEM_PROJECTS = r"""You are an expert resume writer specializing in project showcasing.
Output ONLY raw LaTeX for the Relevant Projects section.
NO \documentclass, NO \usepackage, NO \begin{document}, NO \end{document}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Read JD carefully. Identify the top 5 technical requirements.
2. Select 3 projects from the AVAILABLE PROJECTS list that best demonstrate those requirements.
   NEVER invent a project that is not in the AVAILABLE PROJECTS list, and never inflate its
   scale beyond what's written there.
3. For each project, write 2-3 bullets following this structure:
   Bullet 1: The problem + technology used + scale (what you built and with what)
   Bullet 2: The technical implementation detail + specific tool from JD
4. For a critical JD skill with no matching project, pick the closest available project and add
   one honest bullet connecting it (same underlying concept, transferable technique) instead of
   fabricating a new project.

BULLET RULES:
- Every bullet = 1 full lines minimum
- Every bullet has a specific number/metric
- Use \textbf{} on project name and 1-2 key technologies
- Use exact JD keywords naturally
- All % -> \%, all & -> \&

OUTPUT FORMAT:
\section{Relevant Projects}
\resumeSubHeadingListStart
  \resumeProjectHeading
    {\textbf{Project Name} | \emph{Tech1, Tech2, Tech3}}{}
  \resumeItemListStart
    \resumeItem{bullet 1}
    \resumeItem{bullet 2}
  \resumeItemListEnd
\resumeSubHeadingListEnd

Raw LaTeX ONLY. No backticks. No preamble."""

# Fixed by the code (not editable) — the renderer depends on this exact shape.
JSON_SPEC = """

RESPONSE FORMAT — overrides any output-format instructions above. Reply with ONLY this JSON
object, no prose, no code fences, no LaTeX. Do not include links; they are added automatically:
{"projects": [{"name": "Project Name", "tech": ["Tech1", "Tech2"], "bullets": ["bullet one", "bullet two"]}]}
""" + BOLD_RULE


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", text.lower()))


def find_url(name: str, techs: list[str], projects_text: str) -> str:
    """GitHub URL for a project from projects.txt ('Name | techs | url' lines).
    The model may retitle a project, so match by name first, then by tech overlap;
    below 50% overlap there is no link rather than a wrong one."""
    name, want = name.lower().strip(), _tokens(" ".join(techs))
    best, best_score = "", 0.0
    for line in projects_text.splitlines():
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 3 or not parts[-1].startswith("http"):
            continue
        ename = parts[0].lower()
        if name and (ename in name or name in ename):
            return parts[-1]
        have = _tokens(parts[1])
        score = len(want & have) / max(len(want | have), 1)
        if score > best_score:
            best, best_score = parts[-1], score
    return best if best_score >= 0.5 else ""


def write(client: RotatingOllamaClient, title: str, company: str, description: str,
          existing_resume: str, projects_text: str, ats_feedback: str = "", bullets: int = 3) -> str:
    user = (
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        f"CANDIDATE'S EXISTING RESUME (tech-stack context):\n{existing_resume}\n\n"
        f"{_pinned()}AVAILABLE PROJECTS (select the 3-4 most relevant):\n{projects_text}\n\n"
        f"BULLETS PER PROJECT: exactly {bullets} bullets for each selected project.\n\n"
        f"ATS FEEDBACK (must address every point):\n{ats_feedback or 'None — first attempt.'}"
    )
    return ask_json(client, get_prompt("projects_section", SYSTEM_PROJECTS) + JSON_SPEC, user,
                    partial(render_projects, url_for=lambda n, t: find_url(n, t, projects_text)))


def rebuild(client: RotatingOllamaClient, title: str, company: str, description: str,
            feedback: str, current_latex: str, projects_text: str) -> str:
    user = (
        f"CURRENT Relevant Projects SECTION (for reference):\n{current_latex}\n\n"
        f"FEEDBACK TO ADDRESS:\n{feedback}\n\n"
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        f"{_pinned().replace('MUST INCLUDE', 'KEEP (never remove)')}"
        f"AVAILABLE PROJECTS (only swap in projects from this list):\n{projects_text}\n\n"
        "Apply only the requested changes. Return the full corrected section as JSON."
    )
    return ask_json(client, get_prompt("surgical_rewrite", SYSTEM_SURGICAL) + JSON_SPEC, user,
                    partial(render_projects, url_for=lambda n, t: find_url(n, t, projects_text)))


if __name__ == "__main__":
    pt = ("RagGpt | Python, Langchain, Ollama, ChromaDB | https://github.com/a/RagGpt\n"
          "Loan Monitoring | Python, LangGraph, FastAPI, MongoDB | https://github.com/a/Loan_x")
    assert find_url("RagGpt", [], pt).endswith("RagGpt")
    assert find_url("Agentic Risk Engine", ["Python", "LangGraph", "FastAPI", "MongoDB"], pt).endswith("Loan_x")
    assert find_url("Unknown", ["Rust"], pt) == ""
    print("ok")
