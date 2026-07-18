"""LaTeX assembly + compilation. Port of setup_wizard's header/education
builders and pipeline.py's _extract_body/_reassemble_latex + latex_compiler.py.

Uses the standard "Jake's Resume" Overleaf template macros
(\\resumeItem, \\resumeSubheading, \\resumeProjectHeading, ...).
"""
import os
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
    # "or", not .get(key, default) — a blank (not just missing) full_name,
    # e.g. before onboarding is filled in, previously left a bare "{\Huge
    # \scshape } \\" — a genuine "There's no line here to end" LaTeX error
    # under both engines, not something specific to one compiler
    name = profile.get("full_name") or "Your Name"
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
    """Split an assembled resume back into {section_id: raw latex block}.
    Preamble-agnostic: works whatever template the resume was assembled with."""
    _, _, body = latex.partition("\\begin{document}")
    body = (body or latex).replace("\\end{document}", "").strip()
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
    from tools.templates import get_active_preamble  # runtime import (templates.py imports us)
    ordered_ids = list(section_order) + [k for k in sections if k not in section_order and k != "header"]
    body_parts = [sections.get(sid, "") for sid in ordered_ids if sections.get(sid)]
    header = sections.get("header", "")
    return get_active_preamble() + header + "\n".join(body_parts) + "\n\\end{document}\n"


def find_section(full_latex: str, section_id: str, extra_name_map: dict | None = None) -> tuple[str | None, str]:
    """Locate a section in an assembled resume by its id, returning
    (heading_text, block). Heading is the resume's actual \\section{...} text (so
    it can be fed straight to replace_section); block includes that heading.
    (None, "") if the section isn't present. Used by the section rebuilder."""
    name_map = {**SECTION_NAME_TO_ID, **(extra_name_map or {})}
    matches = list(re.finditer(r"\\section\{([^}]+)\}", full_latex))
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        sid = name_map.get(name.lower(), name.lower().replace(" ", "_"))
        if sid == section_id:
            end_doc = full_latex.find("\\end{document}", m.end())
            nxt = matches[i + 1].start() if i + 1 < len(matches) else None
            bounds = [b for b in (nxt, end_doc if end_doc != -1 else None) if b is not None]
            end = min(bounds) if bounds else len(full_latex)
            return name, full_latex[m.start():end].strip()
    return None, ""


def replace_section(full_latex: str, section_name: str, new_block: str) -> str:
    """Swap the \\section{section_name} block in an assembled resume for new_block,
    used by the custom-section rebuilder. Matches the section by its \\section{...}
    heading and replaces up to the next \\section or \\end{document}. If the section
    isn't present, inserts the block before \\end{document} (else appends)."""
    new_block = new_block.strip()
    if not re.match(r"\s*\\section\{", new_block):
        new_block = f"\\section{{{section_name}}}\n{new_block}"  # model omitted the heading
    start = re.search(r"\\section\{\s*" + re.escape(section_name) + r"\s*\}", full_latex, re.IGNORECASE)
    if not start:
        idx = full_latex.rfind("\\end{document}")
        return (full_latex.rstrip() + "\n" + new_block + "\n") if idx == -1 \
            else full_latex[:idx] + new_block + "\n" + full_latex[idx:]
    nxt = re.search(r"\\section\{", full_latex[start.end():])
    end_doc = full_latex.find("\\end{document}", start.end())
    bounds = [b for b in (start.end() + nxt.start() if nxt else None,
                          end_doc if end_doc != -1 else None) if b is not None]
    end = min(bounds) if bounds else len(full_latex)
    return full_latex[:start.start()] + new_block + "\n" + full_latex[end:]


def sanitize_folder_name(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name or "unknown")
    name = re.sub(r"\s+", "_", name.strip())
    return name[:60] or "unknown"


DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Job-Hunter" / "Resumes"


def build_output_path(base_dir: str, company: str, title: str, filename: str, ext: str) -> Path:
    base = Path(base_dir) if base_dir else DEFAULT_OUTPUT_DIR
    folder = base / sanitize_folder_name(company) / sanitize_folder_name(title)
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


def get_latex_engine() -> tuple[str, str] | tuple[None, None]:
    """Picks the LaTeX compiler to shell out to. TECTONIC_PATH (set by Electron
    in a packaged build, where a bundled Tectonic binary ships with the app)
    wins over a system pdflatex (MiKTeX/TeX Live), which is the dev-machine
    fallback — nothing pre-installed required for a packaged build."""
    tectonic_cmd = os.environ.get("TECTONIC_PATH") or shutil.which("tectonic")
    if tectonic_cmd:
        return "tectonic", tectonic_cmd
    pdflatex_cmd = shutil.which("pdflatex")
    if pdflatex_cmd:
        return "pdflatex", pdflatex_cmd
    return None, None


# last human-readable compile error, keyed by output path — lets the preview
# endpoint show the REAL reason (e.g. "Font not found") instead of a generic message
_LAST_COMPILE_ERROR: dict[str, str] = {}
_FONT_MAPS_REPAIRED = False


def _run_latex_engine(engine: str, cmd: str, latex_code: str, output_pdf_path: Path) -> tuple[bool, str]:
    """Compiles with whichever engine `get_latex_engine()` picked. Returns (ok, log_text)."""
    # realpath, not the raw value: on Windows, %TEMP% can resolve to an 8.3
    # short name (e.g. C:\Users\SNEHPA~1\...) when the profile name has a
    # space — pdflatex's tokenizer breaks on the bare `~`, aborting before
    # it even opens the input file. realpath() expands it back to the long
    # form; a no-op on POSIX and on machines without this quirk.
    safe_tmp = Path(os.path.realpath(tempfile.gettempdir())) / "latex_work"
    safe_tmp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=safe_tmp) as tmpdir:
        tex_file = Path(tmpdir) / "resume.tex"
        tex_file.write_text(latex_code, encoding="utf-8")
        pdf_path = Path(tmpdir) / "resume.pdf"
        log_path = Path(tmpdir) / "resume.log"

        if engine == "tectonic":
            # single pass — tectonic resolves multi-pass/package-fetching internally
            result = subprocess.run(
                [cmd, "--outdir", tmpdir, str(tex_file)],
                capture_output=True, timeout=300,
            )
            log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else (
                (result.stdout + result.stderr).decode("utf-8", errors="ignore")
            )
        else:
            result = None
            for _ in range(2):
                result = subprocess.run(
                    [cmd, "-interaction=nonstopmode", "-output-directory", tmpdir, str(tex_file)],
                    capture_output=True, timeout=300,
                )
            log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""

        if result is not None and result.returncode == 0 and pdf_path.exists():
            shutil.copy2(pdf_path, output_pdf_path)
            return True, log
        return False, log


def _is_font_map_error(log: str) -> bool:
    return bool(re.search(r"Font \S+ (at \d+ )?not found|mktexpk|\bec-\w+\b", log))


def _repair_font_maps():
    """Register font maps (MiKTeX) so Type1 fonts like tex-gyre/Fira resolve
    instead of falling back to missing bitmaps. Best-effort, runs once."""
    for cmd in (["updmap"], ["initexmf", "--mkmaps"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, capture_output=True, timeout=240)
            except Exception:
                pass


def _summarize_error(log: str) -> str:
    if not log:
        return "pdflatex produced no log output."
    hits: list[str] = []
    for ln in log.splitlines():
        s = ln.strip()
        if (s.startswith("!") or "not found" in s.lower()
                or "undefined control sequence" in s.lower()) and s not in hits:
            hits.append(s)
    return " | ".join(hits[:4]) or "Compile failed — check the template's LaTeX."


_FA_PACKAGE_RE = re.compile(r"\\usepackage(\[[^\]]*\])?\{fontawesome5\}\n?")
_FA_ICON_RE = re.compile(r"(\\raisebox\{[^}]*\})?\\fa([A-Z]\w*)(\*)?\\?\s*")
_PDFTEX_ONLY_RE = re.compile(r"\\pdfgentounicode\s*=\s*1\n?")
_DOCUMENTCLASS_RE = re.compile(r"(\\documentclass(\[[^\]]*\])?\{[^}]*\}\n?)")

# \faXxx macro name -> bundled PNG (rendered once from the FontAwesome5 OTFs,
# see build-resources/resume-icons). Starred variants (e.g. \faMapMarker*)
# use the "-alt"/solid glyph, matched separately below.
_FA_ICON_FILES = {
    ("Phone", False): "phone.png",
    ("Envelope", False): "envelope.png",
    ("Linkedin", False): "linkedin.png",
    ("Github", False): "github.png",
    ("MapMarker", True): "map-marker.png",
}


def _resume_icon_dir() -> Path:
    return Path(os.environ.get("RESUME_ICON_DIR") or Path(__file__).resolve().parent.parent
                / "desktop" / "build-resources" / "resume-icons")


def _adapt_for_tectonic(latex_code: str) -> str:
    """Tectonic's engine is XeTeX-based, not pdfTeX — two incompatibilities
    with this app's templates, both confirmed empirically:
    1. fontawesome5's OTF icon fonts crash Tectonic outright on Windows (engine
       abort, not a recoverable TeX error — fontconfig overrides, -Z
       search-path, and placing the font alongside the .tex file all hit the
       same silent failure, even with a fontconfig.conf pointing at a real
       font dir). Fix: swap each \\faXxx macro for a pre-rendered PNG of that
       exact glyph (rendered once from the FontAwesome5 OTFs) via
       \\includegraphics — that's pure image embedding, no font lookup, so it
       works identically on both engines. pdflatex (dev) keeps using the font
       directly since it isn't affected.
    2. \\pdfgentounicode is a pdfTeX-only primitive — undefined under Tectonic.
    """
    latex_code = _FA_PACKAGE_RE.sub("", latex_code)
    icon_dir = _resume_icon_dir()

    def _icon_sub(m: re.Match) -> str:
        name, star = m.group(2), bool(m.group(3))
        filename = _FA_ICON_FILES.get((name, star))
        icon_path = icon_dir / filename if filename else None
        if not icon_path or not icon_path.exists():
            # "~" (a tie space, real content) not "" or "{}": a bare \\ with no
            # actual material before it on its line is a LaTeX error ("There's
            # no line here to end") — confirmed even "{}" doesn't count as
            # content. Falls back here for icons with no bundled PNG.
            return "~"
        return f"\\includegraphics[height=0.9em]{{{icon_path.as_posix()}}}\\ "

    latex_code = _FA_ICON_RE.sub(_icon_sub, latex_code)
    if "{graphicx}" not in latex_code:
        latex_code = _DOCUMENTCLASS_RE.sub(r"\1\\usepackage{graphicx}\n", latex_code, count=1)
    return _PDFTEX_ONLY_RE.sub("", latex_code)


def compile_latex_to_pdf(latex_code: str, output_pdf_path: Path) -> bool:
    global _FONT_MAPS_REPAIRED
    _LAST_COMPILE_ERROR.pop(str(output_pdf_path), None)

    engine, cmd = get_latex_engine()
    if not engine:
        _LAST_COMPILE_ERROR[str(output_pdf_path)] = "No LaTeX engine found (pdflatex/tectonic)."
        _save_latex_fallback(latex_code, output_pdf_path)
        return False

    if engine == "tectonic":
        latex_code = _adapt_for_tectonic(latex_code)

    ok, log = _run_latex_engine(engine, cmd, latex_code, output_pdf_path)
    # auto-recover from unregistered font maps (common fresh-MiKTeX issue), once — pdflatex-only
    if not ok and engine == "pdflatex" and not _FONT_MAPS_REPAIRED and _is_font_map_error(log):
        _FONT_MAPS_REPAIRED = True
        _repair_font_maps()
        ok, log = _run_latex_engine(engine, cmd, latex_code, output_pdf_path)
    if ok:
        return True

    _LAST_COMPILE_ERROR[str(output_pdf_path)] = _summarize_error(log)
    _save_latex_fallback(latex_code, output_pdf_path)
    return False


def last_compile_error(output_pdf_path: Path) -> str:
    return _LAST_COMPILE_ERROR.get(str(output_pdf_path), "")


def _save_latex_fallback(latex_code: str, output_pdf_path: Path):
    output_pdf_path.with_suffix(".tex").write_text(latex_code, encoding="utf-8")


if __name__ == "__main__":
    import shutil as _shutil

    default_path = build_output_path("", "Acme Inc", "Backend Dev", "resume", "pdf")
    assert default_path == DEFAULT_OUTPUT_DIR / "Acme_Inc" / "Backend_Dev" / "resume.pdf"
    _shutil.rmtree(DEFAULT_OUTPUT_DIR / "Acme_Inc")

    custom_dir = Path(tempfile.gettempdir()) / "custom_resumes"
    custom_path = build_output_path(str(custom_dir), "Acme Inc", "Backend Dev", "resume", "pdf")
    assert custom_path == custom_dir / "Acme_Inc" / "Backend_Dev" / "resume.pdf"
    _shutil.rmtree(custom_dir)

    header = build_header({"full_name": "Test", "phone": "555", "email": "a@b.com",
                            "linkedin": "linkedin.com/in/x", "github": "github.com/y",
                            "location": "Earth"})
    adapted = _adapt_for_tectonic(LATEX_PREAMBLE + header)
    assert "fontawesome5" not in adapted
    assert adapted.count("\\includegraphics") == 5, adapted.count("\\includegraphics")
    assert "\\usepackage{graphicx}" in adapted

    no_icon_dir = _adapt_for_tectonic("\\documentclass{article}\n\\faBeer\n")
    assert "~" in no_icon_dir  # unmapped icon falls back to a tie space, not a blank line

    # replace_section: swap in place, stop at next section, keep the rest
    doc = "\\begin{document}\nHEAD\n\\section{Summary}\nold\n\\section{Skills}\nkeep\n\\end{document}\n"
    out = replace_section(doc, "Summary", "\\section{Summary}\nnew")
    assert "\\section{Summary}\nnew\n\\section{Skills}\nkeep" in out and "old" not in out, out
    # missing section → inserted before \end{document}; heading auto-added when omitted
    out2 = replace_section(doc, "Awards", "won things")
    assert "\\section{Awards}\nwon things\n\\end{document}" in out2 and "\\section{Skills}\nkeep" in out2, out2

    # find_section: map heading → id, return real heading + block; None when absent
    resume = "\\begin{document}\nHEAD\n\\section{Technical Skills}\ns1\n\\section{Summary}\nsum\n\\end{document}\n"
    assert find_section(resume, "skills") == ("Technical Skills", "\\section{Technical Skills}\ns1"), find_section(resume, "skills")
    assert find_section(resume, "summary")[0] == "Summary"
    assert find_section(resume, "projects") == (None, "")

    print("ok")
