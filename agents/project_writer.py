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
You write the Relevant Projects section as structured data.

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
5. Each project gets exactly the bullet count given in the user message. A specific metric in
   most bullets, but not mechanically in every one — a number in every line reads as
   generated. Prefer believable, non-round figures consistent with the project's real scale.

BULLET RULES:
- Every bullet = 1.5 lines minimum (about 200-260 characters).
- Weave exact JD keywords into natural sentences; never end a bullet with a bolted-on tool
  list. Vary sentence openings — no two bullets start with the same verb, and BANNED verbs:
  spearheaded, leveraged, utilized, "responsible for".
- No arrows, no em dashes."""

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
