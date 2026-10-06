"""Turns the writers' JSON into the resume template's LaTeX.

The model never writes LaTeX. It returns plain JSON strings, where `**word**`
marks bold text; this module escapes every special character and converts the
bold markers to \\textbf{}. That makes a LaTeX syntax error from the model
impossible — the only LaTeX in the output is what's written here.
"""
import json
import re

_ESCAPES = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
            "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}
# characters pdflatex/tectonic templates choke on or that read as AI tells
_UNICODE = {"\u2013": "--", "\u2014": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
            "\u2192": "to", "\u2022": "-", "\u00a0": " ", "\u2026": "..."}
_TEXTBF = re.compile(r"\\textbf\{([^{}]*)\}")


# inline markup: [text](url)  **bold**  *italic*
_INLINE = re.compile(r"\[([^\]]+)\]\(((?:https?://|mailto:|tel:)[^)\s]+)\)"
                     r"|\*\*(.+?)\*\*"
                     r"|(?<![\w*])\*(?!\s)([^*]+?)\*(?![\w*])")


def _esc(s: str) -> str:
    return "".join(_ESCAPES.get(c, c) for c in s)


def _url(u: str) -> str:
    return u.replace("%", r"\%").replace("#", r"\#").replace("&", r"\&")


def _inline(text: str) -> str:
    out, pos = [], 0
    for m in _INLINE.finditer(text):
        out.append(_esc(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append("\\href{%s}{\\underline{%s}}" % (_url(m.group(2)), _inline(m.group(1))))
        elif m.group(3) is not None:
            inner = _inline(m.group(3))
            out.append("\\textbf{%s}" % inner if inner.strip() else "")
        else:
            out.append("\\textit{%s}" % _inline(m.group(4)))
        pos = m.end()
    out.append(_esc(text[pos:]))
    return "".join(out)


def tex(text) -> str:
    """Plain text -> safe LaTeX. `**x**` (or a stray \\textbf{x}) = bold, `*x*` = italic,
    `[label](https://url)` = link; everything else is escaped."""
    text = _TEXTBF.sub(r"**\1**", str(text or ""))
    for k, v in _UNICODE.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", _inline(text).replace("**", "")).strip()


def plain(text) -> str:
    """Like tex() but without bold markers (names, categories, dates)."""
    return tex(str(text or "").replace("**", ""))


def render_static(cfg: dict) -> str:
    """A user-authored section from the visual designer — no model involved.
    cfg: {name, layout: "bullets"|"text"|"entries", bullets: [...],
          entries: [{title, subtitle, date, location, link, bullets: [...]}]}.
    Returns "" for an empty section so it is simply left out of the resume."""
    name = plain(cfg.get("name") or "Section")
    layout = cfg.get("layout", "bullets")
    if layout == "entries":
        blocks = []
        for e in cfg.get("entries", []):
            title = str(e.get("title") or "").strip()
            if not title:
                continue
            if e.get("link") and "](" not in title:
                title = f"[{title}]({str(e['link']).strip()})"
            head = (f"  \\resumeSubheading{{{tex(title)}}}{{{plain(e.get('date'))}}}"
                    f"{{{tex(e.get('subtitle'))}}}{{{plain(e.get('location'))}}}")
            bullets = [b for b in e.get("bullets", []) if str(b or "").strip()]
            blocks.append(head + ("\n" + _bullets(bullets) if bullets else ""))
        if not blocks:
            return ""
        return f"\\section{{{name}}}\n\\resumeSubHeadingListStart\n" + "\n".join(blocks) + "\n\\resumeSubHeadingListEnd"
    bullets = [b for b in cfg.get("bullets", []) if str(b or "").strip()]
    if not bullets:
        return ""
    if layout == "text":    # label-less list: reads as paragraphs, like the Summary section
        items = "\n".join(f"  \\resumeItem{{{tex(b)}}}" for b in bullets)
        return f"\\section{{{name}}}\n\\resumeSubHeadingListStart\n{items}\n\\resumeSubHeadingListEnd"
    items = "\n".join(f"    \\resumeItem{{{tex(b)}}}" for b in bullets)
    return (f"\\section{{{name}}}\n\\begin{{itemize}}[leftmargin=0.25in, itemsep=0pt, topsep=2pt, parsep=0pt]\n"
            f"{items}\n\\end{{itemize}}\\vspace{{-5pt}}")


def parse_json(raw: str) -> dict:
    """First JSON object in the model reply (tolerates code fences / chatter)."""
    raw = re.sub(r"```(?:json)?", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model reply")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("model JSON is not an object")
    return data


def _bullets(items) -> str:
    lines = [f"    \\resumeItem{{{tex(b)}}}" for b in items if str(b or "").strip()]
    if not lines:
        raise ValueError("section has no bullets")
    return "  \\resumeItemListStart\n" + "\n".join(lines) + "\n  \\resumeItemListEnd"


def render_skills(data: dict) -> str:
    rows = []
    for cat in data.get("categories", []):
        items = [plain(i) for i in cat.get("items", []) if str(i or "").strip()]
        if cat.get("name") and items:
            rows.append(f"     \\textbf{{{plain(cat['name'])}}}{{: {', '.join(items)}}}")
    if not rows:
        raise ValueError("skills JSON has no categories")
    body = " \\\\\n".join(rows)
    return ("\\section{Technical Skills}\n \\begin{itemize}[leftmargin=0.15in, label={}]\n"
            "    \\small{\\item{\n" + body + "\n    }}\n \\end{itemize}")


def render_experience(data: dict, locked_roles: list[dict] | None = None) -> str:
    """`locked_roles` (from config) override title/company/dates by position, so the
    model can't alter them; location still comes from the model's JSON."""
    roles = data.get("roles", [])
    if not roles:
        raise ValueError("experience JSON has no roles")
    locked = locked_roles if locked_roles and len(locked_roles) == len(roles) else None
    blocks = []
    for i, role in enumerate(roles):
        src = {**role, **{k: v for k, v in (locked[i] if locked else {}).items()
                          if k in ("title", "company", "dates") and v}}
        blocks.append(
            f"  \\resumeSubheading{{{plain(src.get('title'))}}}{{{plain(src.get('dates'))}}}"
            f"{{{plain(src.get('company'))}}}{{{plain(src.get('location'))}}}\n"
            + _bullets(role.get("bullets", [])))
    return "\\section{Experience}\n\\resumeSubHeadingListStart\n" + "\n".join(blocks) + "\n\\resumeSubHeadingListEnd"


def render_projects(data: dict, url_for=lambda name, techs: "") -> str:
    """`url_for(name, techs)` -> GitHub URL or '' (looked up from projects.txt in code)."""
    projects = data.get("projects", [])
    if not projects:
        raise ValueError("projects JSON has no projects")
    blocks = []
    for p in projects:
        techs = [str(t) for t in p.get("tech", []) if str(t).strip()]
        url = url_for(str(p.get("name", "")), techs)
        link = f"\\href{{{url}}}{{\\faGithub\\ \\underline{{GitHub}}}}" if url else ""
        blocks.append(
            f"  \\resumeProjectHeading\n    {{\\textbf{{{plain(p.get('name'))}}} \\textbar{{}} "
            f"\\emph{{{', '.join(plain(t) for t in techs)}}}}}{{{link}}}\n" + _bullets(p.get("bullets", [])))
    return ("\\section{Relevant Projects}\n\\resumeSubHeadingListStart\n" + "\n".join(blocks)
            + "\n\\resumeSubHeadingListEnd")


if __name__ == "__main__":
    assert tex("Cut costs 50% with **C#** & R_D") == r"Cut costs 50\% with \textbf{C\#} \& R\_D"
    assert tex(r"Built \textbf{FastAPI} {x}") == r"Built \textbf{FastAPI} \{x\}"
    assert tex("a **b") == "a b"                                  # unbalanced marker dropped
    assert tex("See [my repo](https://github.com/a/my_repo) and *italic*") == \
        r"See \href{https://github.com/a/my_repo}{\underline{my repo}} and \textit{italic}"
    assert tex("**[Docs](https://x.io/a#b)**") == r"\textbf{\href{https://x.io/a\#b}{\underline{Docs}}}"
    assert tex("2*3 and snake_case") == r"2*3 and snake\_case"
    assert render_static({"name": "Awards", "layout": "bullets", "bullets": ["Won **1st** place", ""]}) == \
        ("\\section{Awards}\n\\begin{itemize}[leftmargin=0.25in, itemsep=0pt, topsep=2pt, parsep=0pt]\n"
         "    \\resumeItem{Won \\textbf{1st} place}\n\\end{itemize}\\vspace{-5pt}")
    assert render_static({"name": "X", "layout": "entries", "entries": []}) == ""
    en = render_static({"name": "Volunteering", "layout": "entries", "entries": [
        {"title": "Mentor", "subtitle": "Code Club", "date": "2024", "location": "Halifax", "link": "https://a.org",
         "bullets": ["Taught 20 students"]}]})
    assert r"\resumeSubheading{\href{https://a.org}{\underline{Mentor}}}{2024}{Code Club}{Halifax}" in en
    assert tex("A \u2014 B \u2192 C") == "A - B to C"
    assert parse_json('Here:\n```json\n{"a": 1}\n```')["a"] == 1
    sk = render_skills({"categories": [{"name": "AI & ML", "items": ["RAG", "C++"]}, {"name": "Cloud", "items": ["AWS"]}]})
    assert r"\textbf{AI \& ML}{: RAG, C++} \\" in sk and sk.count(r"\\") == 1
    ex = render_experience({"roles": [{"title": "X", "company": "Y", "dates": "z", "location": "Halifax, NS",
                                       "bullets": ["Did **it** 5%"]}]},
                           [{"title": "Analyst", "company": "NSHA", "dates": "Feb 2026 \u2013 Present"}])
    assert r"\resumeSubheading{Analyst}{Feb 2026 -- Present}{NSHA}{Halifax, NS}" in ex
    assert r"\resumeItem{Did \textbf{it} 5\%}" in ex
    pr = render_projects({"projects": [{"name": "RagGpt", "tech": ["Python"], "bullets": ["b"]}]},
                         lambda n, t: "https://github.com/a/RagGpt")
    assert r"\href{https://github.com/a/RagGpt}{\faGithub\ \underline{GitHub}}" in pr and r"\textbar{}" in pr
    print("ok")
