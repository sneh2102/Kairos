"""LaTeX assembly + compilation. Port of setup_wizard's header/education
builders and pipeline.py's _extract_body/_reassemble_latex + latex_compiler.py.

Uses the standard "Jake's Resume" Overleaf template macros
(\\resumeItem, \\resumeSubheading, \\resumeProjectHeading, ...).
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

LATEX_PREAMBLE = r"""\documentclass[letterpaper,11pt]{article}
\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\usepackage{fontawesome5}
\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}
\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}
\urlstyle{same}
\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}
\titleformat{\section}{\vspace{-4pt}\scshape\raggedright\large}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]
\pdfgentounicode=1
\newcommand{\resumeItem}[1]{\item\small{{#1 \vspace{-2pt}}}}
\newcommand{\resumeSubheading}[4]{\vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-7pt}}
\newcommand{\resumeProjectHeading}[2]{\item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \small#1 & #2 \\
    \end{tabular*}\vspace{-7pt}}
\renewcommand\labelitemii{$\vcenter{\hbox{\tiny$\bullet$}}$}
\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}
\begin{document}
"""

SECTION_NAME_TO_ID = {
    "education": "education", "technical skills": "skills", "skills": "skills",
    "experience": "experience", "work experience": "experience",
    "relevant projects": "projects", "projects": "projects",
    "summary": "summary", "achievements": "achievements",
}


def build_header(profile: dict, location_override: str | None = None, include_links: bool = True) -> str:
    name = profile.get("full_name", "Your Name")
    phone = profile.get("phone", "")
    email = profile.get("email", "")
    linkedin = profile.get("linkedin", "")
    github = profile.get("github", "")
    location = location_override or profile.get("location", "")

    parts = []
    if phone:
        ph_clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        parts.append(f"\\href{{tel:{ph_clean}}}{{\\raisebox{{-0.2\\height}}\\faPhone\\ \\underline{{{phone}}}}}")
    if email:
        parts.append(f"\\href{{mailto:{email}}}{{\\raisebox{{-0.2\\height}}\\faEnvelope\\ \\underline{{{email}}}}}")
    if include_links:
        if linkedin:
            handle = linkedin.split("/in/")[-1].strip("/") if "/in/" in linkedin else linkedin
            url = linkedin if linkedin.startswith("linkedin") else f"linkedin.com/in/{handle}"
            parts.append(f"\\href{{https://{url}}}{{\\raisebox{{-0.2\\height}}\\faLinkedin\\ \\underline{{{handle}}}}}")
        if github:
            gh_handle = github.split("github.com/")[-1].strip("/") if "github.com" in github else github
            parts.append(f"\\href{{https://github.com/{gh_handle}}}{{\\raisebox{{-0.2\\height}}\\faGithub\\ \\underline{{{gh_handle}}}}}")
    contact_line = " ~\n    ".join(parts)

    return f"""
\\begin{{center}}
    {{\\Huge \\scshape {name}}} \\\\ \\vspace{{6pt}}
    \\faMapMarker*\\ {location} \\\\
    \\vspace{{2pt}}
    {contact_line}
\\end{{center}}
\\vspace{{2pt}}
"""


def build_education(profile: dict) -> str:
    edu_list = profile.get("education", [])
    if not edu_list:
        return ""
    items = "\n".join(
        f"  \\resumeSubheading{{{e.get('degree','')}}}{{{e.get('dates','')}}}"
        f"{{{e.get('institution','')}}}{{{e.get('location','')}}}"
        for e in edu_list
    )
    return f"\n\\section{{Education}}\n\\resumeSubHeadingListStart\n{items}\n\\resumeSubHeadingListEnd\n"


def extract_sections(latex: str, header: str, extra_name_map: dict | None = None) -> dict[str, str]:
    """Split an assembled resume back into {section_id: raw latex block}."""
    body = latex.replace(LATEX_PREAMBLE, "").replace("\\end{document}", "").strip()
    name_map = {**SECTION_NAME_TO_ID, **(extra_name_map or {})}
    matches = list(re.finditer(r"\\section\{([^}]+)\}", body))
    sections: dict[str, str] = {"header": header}
    for i, m in enumerate(matches):
        sec_id = name_map.get(m.group(1).lower(), m.group(1).lower().replace(" ", "_"))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[sec_id] = body[m.start():end].strip()
    for key in ("skills", "experience", "projects"):
        sections.setdefault(key, "")
    return sections


def reassemble(sections: dict[str, str], section_order: list[str]) -> str:
    ordered_ids = list(section_order) + [k for k in sections if k not in section_order and k != "header"]
    body_parts = [sections.get(sid, "") for sid in ordered_ids if sections.get(sid)]
    header = sections.get("header", "")
    return LATEX_PREAMBLE + header + "\n".join(body_parts) + "\n\\end{document}\n"


def sanitize_folder_name(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name or "unknown")
    name = re.sub(r"\s+", "_", name.strip())
    return name[:60] or "unknown"


def build_output_path(base_dir: str, company: str, title: str, filename: str, ext: str) -> Path:
    folder = Path(base_dir) / sanitize_folder_name(company) / sanitize_folder_name(title)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{filename}.{ext}"


def is_pdflatex_available() -> bool:
    if shutil.which("pdflatex"):
        return True
    try:
        subprocess.run(["pdflatex", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def compile_latex_to_pdf(latex_code: str, output_pdf_path: Path) -> bool:
    pdflatex_cmd = shutil.which("pdflatex")
    if not pdflatex_cmd:
        _save_latex_fallback(latex_code, output_pdf_path)
        return False

    safe_tmp = Path("C:/tmp/latex_work")
    safe_tmp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=safe_tmp) as tmpdir:
        tex_file = Path(tmpdir) / "resume.tex"
        tex_file.write_text(latex_code, encoding="utf-8")
        result = None
        for _ in range(2):  # double-compile for stable rendering
            result = subprocess.run(
                [pdflatex_cmd, "-interaction=nonstopmode", "-output-directory", tmpdir, str(tex_file)],
                capture_output=True, timeout=300,
            )
        pdf_path = Path(tmpdir) / "resume.pdf"
        if result is not None and result.returncode == 0 and pdf_path.exists():
            shutil.copy2(pdf_path, output_pdf_path)
            return True

    _save_latex_fallback(latex_code, output_pdf_path)
    return False


def _save_latex_fallback(latex_code: str, output_pdf_path: Path):
    output_pdf_path.with_suffix(".tex").write_text(latex_code, encoding="utf-8")
