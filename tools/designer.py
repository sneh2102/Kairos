"""Visual resume designer backend: a style dict -> LaTeX preamble (the "base template"),
saving/loading the layout (style + which sections show + their order), and a draft
preview compile so the UI can show changes live."""
import hashlib
import json
import re

import config
from config import CONFIG
from tools import templates
from tools.section_render import render_static

CORE_SECTIONS = {"skills": "Technical Skills", "experience": "Experience",
                 "projects": "Relevant Projects", "education": "Education"}
TEMPLATE_ID = "designer"

DEFAULT_STYLE = {
    "font": "computer-modern",   # computer-modern | helvetica | times | palatino
    "font_size": 11,             # 10 | 11 | 12
    "margin": "normal",          # narrow | normal | wide
    "density": "normal",         # compact | normal | relaxed
    "accent": "#000000",         # section heading + rule color
    "heading_style": "rule",     # rule | thick | none
    "heading_case": "smallcaps", # smallcaps | caps | normal
    "header_align": "center",    # center | left
    "bullet": "bullet",          # bullet | dash | circle | triangle
}
_CHOICES = {
    "font": ("computer-modern", "helvetica", "times", "palatino"),
    "font_size": (10, 11, 12),
    "margin": ("narrow", "normal", "wide"),
    "density": ("compact", "normal", "relaxed"),
    "heading_style": ("rule", "thick", "none"),
    "heading_case": ("smallcaps", "caps", "normal"),
    "header_align": ("center", "left"),
    "bullet": ("bullet", "dash", "circle", "triangle"),
}
_FONTS = {
    "computer-modern": "",
    "helvetica": "\\usepackage[T1]{fontenc}\n\\usepackage{tgheros}\n\\renewcommand*\\familydefault{\\sfdefault}\n",
    "times": "\\usepackage[T1]{fontenc}\n\\usepackage{tgtermes}\n",
    "palatino": "\\usepackage[T1]{fontenc}\n\\usepackage{tgpagella}\n",
}
_MARGINS = {"narrow": ("0.5in", "0.4in"), "normal": ("0.6in", "0.5in"), "wide": ("0.85in", "0.7in")}
_DENSITY = {"compact": ("-3pt", "0.96"), "normal": ("-2pt", "1.0"), "relaxed": ("1pt", "1.06")}
_BULLETS = {"bullet": "\\textbullet", "dash": "\\textendash", "circle": "$\\circ$", "triangle": "$\\triangleright$"}
_RULE = {"rule": "0.4pt", "thick": "2pt"}


def normalize_style(style: dict | None) -> dict:
    """Merge over defaults; any invalid value falls back to the default."""
    out = dict(DEFAULT_STYLE)
    for key, val in (style or {}).items():
        if key in _CHOICES and val in _CHOICES[key]:
            out[key] = val
        elif key == "accent" and isinstance(val, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", val):
            out[key] = "#" + val.lstrip("#").lower()
    return out


def build_preamble(style: dict | None) -> str:
    s = normalize_style(style)
    side, vert = _MARGINS[s["margin"]]
    gap, stretch = _DENSITY[s["density"]]
    case = {"smallcaps": "\\scshape", "caps": "\\bfseries", "normal": "\\bfseries"}[s["heading_case"]]
    upper = "\\MakeUppercase" if s["heading_case"] == "caps" else ""
    # braces around \titlerule[..]: its own ] would otherwise end titlesec's optional argument
    rule = (f"[\\color{{accent}}{{\\titlerule[{_RULE[s['heading_style']]}]}}\\vspace{{-5pt}}]"
            if s["heading_style"] in _RULE else "[\\vspace{-3pt}]")
    left_header = ("\\renewenvironment{center}{\\par\\noindent\\raggedright}{\\par}\n"
                   if s["header_align"] == "left" else "")
    return (
        f"\\documentclass[letterpaper,{s['font_size']}pt]{{article}}\n"
        "\\usepackage{latexsym}\n"
        f"\\usepackage[letterpaper,left={side},right={side},top={vert},bottom={vert}]{{geometry}}\n"
        "\\usepackage{titlesec}\n\\usepackage{marvosym}\n\\usepackage{xcolor}\n\\usepackage{verbatim}\n"
        "\\usepackage{enumitem}\n\\usepackage[hidelinks]{hyperref}\n\\usepackage{fancyhdr}\n"
        "\\usepackage[english]{babel}\n\\usepackage{tabularx}\n\\usepackage{fontawesome5}\n"
        + _FONTS[s["font"]] +
        f"\\definecolor{{accent}}{{HTML}}{{{s['accent'].lstrip('#').upper()}}}\n"
        "\\pagestyle{fancy}\n\\fancyhf{}\n\\fancyfoot{}\n"
        "\\renewcommand{\\headrulewidth}{0pt}\n\\renewcommand{\\footrulewidth}{0pt}\n"
        f"\\renewcommand{{\\baselinestretch}}{{{stretch}}}\n"
        "\\urlstyle{same}\n\\raggedbottom\n\\raggedright\n\\setlength{\\tabcolsep}{0in}\n"
        f"\\titleformat{{\\section}}{{\\vspace{{-4pt}}{case}\\raggedright\\large\\color{{accent}}}}"
        f"{{}}{{0em}}{{{upper}}}{rule}\n"
        f"{left_header}"
        f"\\renewcommand{{\\labelitemi}}{{{_BULLETS[s['bullet']]}}}\n"
        "\\renewcommand\\labelitemii{$\\vcenter{\\hbox{\\tiny$\\bullet$}}$}\n"
        "\\pdfgentounicode=1\n"
        f"\\newcommand{{\\resumeItem}}[1]{{\\item\\small{{{{#1 \\vspace{{{gap}}}}}}}}}\n"
        "\\newcommand{\\resumeSubheading}[4]{\\vspace{-2pt}\\item\n"
        "    \\begin{tabular*}{0.97\\textwidth}[t]{l@{\\extracolsep{\\fill}}r}\n"
        "      \\textbf{#1} & #2 \\\\\n      \\textit{\\small#3} & \\textit{\\small #4} \\\\\n"
        "    \\end{tabular*}\\vspace{-7pt}}\n"
        "\\newcommand{\\resumeProjectHeading}[2]{\\item\n"
        "    \\begin{tabular*}{0.97\\textwidth}{l@{\\extracolsep{\\fill}}r}\n"
        "      \\small#1 & #2 \\\\\n    \\end{tabular*}\\vspace{-7pt}}\n"
        "\\newcommand{\\resumeSubHeadingListStart}{\\begin{itemize}[leftmargin=0.15in, label={}]}\n"
        "\\newcommand{\\resumeSubHeadingListEnd}{\\end{itemize}}\n"
        "\\newcommand{\\resumeItemListStart}{\\begin{itemize}}\n"
        "\\newcommand{\\resumeItemListEnd}{\\end{itemize}\\vspace{-5pt}}\n"
    )


# ---------------------------------------------------------------- layout ----

def _custom_ok(sections: list) -> list[dict]:
    """Drop malformed custom sections; ids must be unique and not collide with core ones."""
    seen, out = set(CORE_SECTIONS) | {"header"}, []
    for sec in sections or []:
        sid = str(sec.get("id") or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sec)
    return out


def get_layout() -> dict:
    custom = CONFIG.get("custom_sections", [])
    known = list(CORE_SECTIONS) + [s["id"] for s in custom if s.get("id")]
    order = [x for x in CONFIG.get("section_order", []) if x in known]
    order += [x for x in known if x not in order]
    return {"style": normalize_style(CONFIG.get("layout_style")), "section_order": order,
            "hidden_sections": [x for x in CONFIG.get("hidden_sections", []) if x in known],
            "custom_sections": custom}


def save_layout(payload: dict) -> dict:
    """Persist style + sections and activate the generated template."""
    custom = _custom_ok(payload.get("custom_sections", []))
    known = list(CORE_SECTIONS) + [s["id"] for s in custom]
    order = [x for x in payload.get("section_order", []) if x in known]
    order += [x for x in known if x not in order]
    style = normalize_style(payload.get("style"))
    templates.save_template(TEMPLATE_ID, build_preamble(style))
    new_cfg = dict(CONFIG)
    new_cfg.update(layout_style=style, section_order=order, custom_sections=custom,
                   hidden_sections=[x for x in payload.get("hidden_sections", []) if x in known])
    new_cfg["pipeline"] = {**CONFIG["pipeline"], "latex_template": TEMPLATE_ID}
    config.save_config(new_cfg)
    (templates.PREVIEWS_DIR / f"{TEMPLATE_ID}.pdf").unlink(missing_ok=True)
    return get_layout()


# --------------------------------------------------------------- preview ----

_SAMPLE_BY_ID = {"skills": templates._SAMPLE_SKILLS, "experience": templates._SAMPLE_EXPERIENCE,
                 "projects": templates._SAMPLE_PROJECTS}


def preview(payload: dict):
    """Compile a draft resume from an UNSAVED layout. Core sections use canned sample
    text (they're AI-written per job); your static sections show their real content."""
    from tools.latex import build_education, build_header, compile_latex_to_pdf, last_compile_error

    custom = {s["id"]: s for s in _custom_ok(payload.get("custom_sections", []))}
    hidden = set(payload.get("hidden_sections", []))
    profile = CONFIG.get("profile", {})
    parts = []
    for sid in payload.get("section_order", []):
        if sid in hidden:
            continue
        if sid in _SAMPLE_BY_ID:
            parts.append(_SAMPLE_BY_ID[sid])
        elif sid == "education":
            parts.append(build_education(profile))
        elif sid in custom:
            sec = custom[sid]
            if sec.get("kind") == "static":
                parts.append(render_static(sec))
            else:   # AI-written per job — show a placeholder so its position is visible
                parts.append(render_static({"name": sec.get("name"), "layout": "text",
                                            "bullets": ["Written by the AI for each job."]}))
    style = normalize_style(payload.get("style"))
    doc = (templates.ensure_compatible(build_preamble(style)) + "\n\\begin{document}\n"
           + build_header(profile, include_links=profile.get("include_links", True))
           + "\n".join(p for p in parts if p) + "\n\\end{document}\n")

    templates.PREVIEWS_DIR.mkdir(exist_ok=True)
    key = hashlib.sha1(doc.encode("utf-8")).hexdigest()[:12]
    pdf = templates.PREVIEWS_DIR / f"draft_{key}.pdf"
    if not pdf.exists():
        if not compile_latex_to_pdf(doc, pdf):
            return None, last_compile_error(pdf)
        drafts = sorted(templates.PREVIEWS_DIR.glob("draft_*.pdf"), key=lambda p: p.stat().st_mtime)
        for old in drafts[:-6]:
            old.unlink(missing_ok=True)
    return pdf, ""
