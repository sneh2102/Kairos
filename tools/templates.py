"""Resume LaTeX template store.

A "template" is a LaTeX preamble (everything before \\begin{document}) that
controls the resume's look: fonts, margins, colors, section styling. Users
paste their own (e.g. any Overleaf resume template); the writers keep emitting
the standard macros (\\resumeItem, \\resumeSubheading, \\resumeProjectHeading,
\\resumeSubHeadingListStart/End, \\resumeItemListStart/End) and if a custom
preamble doesn't define one of them, a default definition is appended
automatically — so ANY pasted format still compiles with generated content.

Built-in "classic" = tools/latex.py's LATEX_PREAMBLE. Custom ones live in
templates/*.tex; the active one is config.json pipeline.latex_template.
"""
import re
import time
from pathlib import Path

import config
from config import CONFIG, DATA_DIR

TEMPLATES_DIR = DATA_DIR / "templates"
PREVIEWS_DIR = DATA_DIR / "previews"

# Fallback definitions appended when a custom preamble lacks a macro the
# writers emit. Deliberately plain so they blend with any style.
_MACRO_DEFAULTS = {
    "resumeItem": r"\newcommand{\resumeItem}[1]{\item\small{{#1 \vspace{-2pt}}}}",
    "resumeSubheading": (
        r"\newcommand{\resumeSubheading}[4]{\vspace{-2pt}\item"
        r"\begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}"
        r"\textbf{#1} & #2 \\ \textit{\small#3} & \textit{\small #4} \\"
        r"\end{tabular*}\vspace{-7pt}}"
    ),
    "resumeProjectHeading": (
        r"\newcommand{\resumeProjectHeading}[2]{\item"
        r"\begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}"
        r"\small#1 & #2 \\ \end{tabular*}\vspace{-7pt}}"
    ),
    "resumeSubHeadingListStart": r"\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}",
    "resumeSubHeadingListEnd": r"\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}",
    "resumeItemListStart": r"\newcommand{\resumeItemListStart}{\begin{itemize}}",
    "resumeItemListEnd": r"\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}",
}

# packages the generated header/sections rely on (\faPhone, \href, itemize opts)
_REQUIRED_PACKAGES = {
    "hyperref": r"\usepackage[hidelinks]{hyperref}",
    "fontawesome5": r"\usepackage{fontawesome5}",
    "enumitem": r"\usepackage{enumitem}",
    "tabularx": r"\usepackage{tabularx}",
}


def _slug(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name or "").strip()
    s = re.sub(r"[\s-]+", "_", s).lower()
    return s[:50]


def normalize(content: str) -> str:
    """Accepts a full .tex document OR a bare preamble; returns just the
    preamble (everything before \\begin{document}), stripped."""
    content = content.replace("\r\n", "\n")
    idx = content.find(r"\begin{document}")
    if idx != -1:
        content = content[:idx]
    return content.strip()


def ensure_compatible(preamble: str) -> str:
    """Appends any missing required packages and macro definitions so the
    writer agents' output compiles under this preamble unchanged. This is what
    lets a user paste ANY resume format and have the program adapt to it."""
    additions = []
    for pkg, decl in _REQUIRED_PACKAGES.items():
        if not re.search(rf"\\usepackage(\[[^\]]*\])?\{{{pkg}\}}", preamble):
            additions.append(decl)
    for macro, decl in _MACRO_DEFAULTS.items():
        if f"\\{macro}" not in preamble:
            additions.append(decl)
    if additions:
        preamble += ("\n\n% --- auto-added for compatibility with generated sections ---\n"
                     + "\n".join(additions))
    return preamble


def get_preamble(template_id: str) -> str:
    """Full, compatibility-ensured preamble ending with \\begin{document}."""
    from tools.latex import LATEX_PREAMBLE  # runtime import (latex.py imports us too)
    if template_id in ("", "classic"):
        return LATEX_PREAMBLE
    path = TEMPLATES_DIR / f"{template_id}.tex"
    if not path.exists():
        return LATEX_PREAMBLE  # deleted/renamed template: degrade to classic
    return ensure_compatible(normalize(path.read_text(encoding="utf-8"))) + "\n\\begin{document}\n"


def get_active_preamble() -> str:
    return get_preamble(CONFIG.get("pipeline", {}).get("latex_template", "classic"))


def list_templates() -> list[dict]:
    active = CONFIG.get("pipeline", {}).get("latex_template", "classic")
    out = [{"id": "classic", "name": "Classic (Jake's Resume)", "builtin": True,
            "active": active in ("", "classic")}]
    if TEMPLATES_DIR.exists():
        for p in sorted(TEMPLATES_DIR.glob("*.tex")):
            out.append({"id": p.stem, "name": p.stem.replace("_", " ").title(),
                        "builtin": False, "active": p.stem == active})
    return out


def get_content(template_id: str) -> str | None:
    if template_id == "classic":
        from tools.latex import LATEX_PREAMBLE
        return LATEX_PREAMBLE.replace("\\begin{document}\n", "").strip()
    path = TEMPLATES_DIR / f"{template_id}.tex"
    return path.read_text(encoding="utf-8") if path.exists() else None


def save_template(name: str, content: str) -> str:
    tid = _slug(name)
    if not tid or tid == "classic":
        raise ValueError("Invalid template name")
    preamble = normalize(content)
    if not preamble or "\\documentclass" not in preamble:
        raise ValueError("Template must contain a \\documentclass line (paste your full .tex or its preamble)")
    TEMPLATES_DIR.mkdir(exist_ok=True)
    (TEMPLATES_DIR / f"{tid}.tex").write_text(preamble, encoding="utf-8")
    return tid


def delete_template(template_id: str):
    if template_id == "classic":
        raise ValueError("Cannot delete the built-in template")
    (TEMPLATES_DIR / f"{template_id}.tex").unlink(missing_ok=True)
    (PREVIEWS_DIR / f"{template_id}.pdf").unlink(missing_ok=True)
    if CONFIG.get("pipeline", {}).get("latex_template") == template_id:
        set_active("classic")


def set_active(template_id: str):
    if template_id != "classic" and not (TEMPLATES_DIR / f"{template_id}.tex").exists():
        raise ValueError(f"Unknown template: {template_id}")
    new_cfg = dict(CONFIG)
    new_cfg["pipeline"] = {**CONFIG["pipeline"], "latex_template": template_id}
    config.save_config(new_cfg)


# ------------------------------------------------------------- preview ----

_SAMPLE_SKILLS = r"""
\section{Technical Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
     \textbf{Languages}{: Python, TypeScript, SQL, Go} \\
     \textbf{Cloud \& DevOps}{: AWS, Docker, Kubernetes, Terraform, CI/CD} \\
     \textbf{Frameworks}{: React, Node.js, FastAPI, Django}
    }}
 \end{itemize}
"""

_SAMPLE_EXPERIENCE = r"""
\section{Experience}
\resumeSubHeadingListStart
  \resumeSubheading{Software Developer}{Jan 2023 -- Present}{Sample Company Inc.}{Toronto, ON}
  \resumeItemListStart
    \resumeItem{Engineered a real-time data pipeline using \textbf{Kafka} and \textbf{Python}, cutting processing latency by 45\% across 12 services}
    \resumeItem{Automated deployment workflows with \textbf{Terraform} and GitHub Actions, trimming release time from 2 days to 3 hours}
  \resumeItemListEnd
\resumeSubHeadingListEnd
"""

_SAMPLE_PROJECTS = r"""
\section{Relevant Projects}
\resumeSubHeadingListStart
  \resumeProjectHeading{\textbf{Sample Project} $|$ \emph{React, FastAPI, PostgreSQL}}{}
  \resumeItemListStart
    \resumeItem{Built a full-stack analytics dashboard serving 500+ daily users with sub-200ms response times}
    \resumeItem{Designed a caching layer with \textbf{Redis}, lowering database load by 60\% at peak traffic}
  \resumeItemListEnd
\resumeSubHeadingListEnd
"""


def build_preview(template_id: str) -> tuple[Path | None, str]:
    """Compiles a sample resume (user's real header/education + canned sections)
    under the given template. Cached by mtime. Returns (pdf_path, "") on success
    or (None, error_message) if the LaTeX failed to compile."""
    from tools.latex import build_education, build_header, compile_latex_to_pdf, last_compile_error

    PREVIEWS_DIR.mkdir(exist_ok=True)
    pdf_path = PREVIEWS_DIR / f"{template_id}.pdf"

    tpl_path = TEMPLATES_DIR / f"{template_id}.tex"
    src_mtime = tpl_path.stat().st_mtime if tpl_path.exists() else 0
    if pdf_path.exists() and pdf_path.stat().st_mtime >= src_mtime and template_id == "classic":
        return pdf_path, ""  # classic never changes
    if pdf_path.exists() and pdf_path.stat().st_mtime >= src_mtime and src_mtime:
        return pdf_path, ""

    profile = CONFIG.get("profile", {})
    header = build_header(profile, include_links=profile.get("include_links", True))
    education = build_education(profile)
    latex_code = (get_preamble(template_id) + header + _SAMPLE_SKILLS
                  + _SAMPLE_EXPERIENCE + _SAMPLE_PROJECTS + education
                  + "\n\\end{document}\n")
    if compile_latex_to_pdf(latex_code, pdf_path):
        pdf_path.touch()  # bump mtime past the template's so the cache check holds
        return pdf_path, ""
    return None, last_compile_error(pdf_path)
