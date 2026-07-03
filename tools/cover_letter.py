"""Cover letter PDF rendering — ReportLab, not LaTeX (the LLM's output is
plain text, not a LaTeX section). Port of utils/latex_compiler.py's
save_cover_letter_pdf: a small state machine that maps the cover-letter
prompt's fixed EXACT FORMAT block into styled paragraphs.
"""
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from config import get_prompt
from llm.client import RotatingOllamaClient

_CLOSING_TRIGGERS = ("warm regards", "sincerely", "best regards", "kind regards")

# Default — editable via the Prompts page (config.json prompts.cover_letter).
# Rendered with str.format(), so edits are validated (see agents/prompt_registry.py)
# before they're allowed to save — a stray '{' or '}' here would raise at generation time.
SYSTEM_COVER_LETTER = """You are writing a cover letter. Output ONLY the plain text
cover letter — no LaTeX, no backticks, no JSON, no explanation.

TONE: semi-formal but genuinely human, like a smart person wrote it. Contractions are
fine. Enthusiastic but not desperate. Reference specific things from the JD, not generic
phrases. Never use em dashes, arrow symbols (->, =>, <>), or corporate filler
("leverage synergies", "passionate team player"). No bullet points. Max 4 paragraphs.

EXACT FORMAT:
{full_name}
{phone}
{email}

{today}

Hiring Manager,
{company}

Subject: Application for {title}

Dear Hiring Manager,

[Paragraph 1 — 3-5 sentences: what specifically attracted you to this role, referencing
one concrete thing from the JD.]

[Paragraph 2 — 4-6 sentences: 2-3 concrete examples from the candidate's experience that
map to JD requirements, at least one with a specific number.]

[Paragraph 3 — 3-4 sentences: approach to learning and problem-solving, honest and
specific, not generic.]

[Paragraph 4 — 2-3 sentences: one specific reason the company appeals to the candidate,
then a confident close.]

Warm regards,
{full_name}
{email}

Plain text ONLY. No formatting symbols."""


def generate(client: RotatingOllamaClient, title: str, company: str, description: str,
             existing_resume: str, profile: dict) -> str:
    system = get_prompt("cover_letter", SYSTEM_COVER_LETTER).format(
        full_name=profile.get("full_name", ""), phone=profile.get("phone", ""),
        email=profile.get("email", ""), today=date.today().strftime("%B %d, %Y"),
        company=company, title=title,
    )
    user = (
        f"JOB TITLE: {title}\nCOMPANY: {company}\nJOB DESCRIPTION:\n{description}\n\n"
        f"CANDIDATE'S RESUME (real experiences/technologies to reference):\n{existing_resume}"
    )
    return clean(client.complete(system=system, user=user))

_NAME = ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=13, spaceAfter=2)
_CONTACT = ParagraphStyle("contact", fontName="Helvetica", fontSize=10, spaceAfter=2)
_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=15, spaceAfter=10)
_SUBJECT = ParagraphStyle("subject", fontName="Helvetica-Bold", fontSize=10.5, spaceAfter=10)


def clean(text: str) -> str:
    return (
        text.replace("—", ", ").replace("–", "-")
        .replace("->", ", ").replace("=>", ", ")
        .replace("&", "and").replace("<", "").replace(">", "")
    )


def _parse(text: str) -> list[tuple[str, str]]:
    """Returns a list of (style_name, text) blocks. States: header -> date ->
    hiring -> subject -> salute -> body -> closing, driven by blank lines and
    the "Subject:"/"Dear"/closing-phrase markers the cover-letter prompt emits."""
    lines = [ln.strip() for ln in clean(text).splitlines()]
    blocks: list[tuple[str, str]] = []
    state = "header"
    body_para: list[str] = []

    def flush_body():
        if body_para:
            blocks.append(("body", " ".join(body_para)))
            body_para.clear()

    for line in lines:
        low = line.lower()
        if state == "header":
            if not line:
                continue
            if line.lower().startswith(("subject:", "dear")) or any(t in low for t in ("hiring manager",)):
                state = "hiring"
            else:
                blocks.append(("contact", line))
                continue
        if state == "hiring":
            if line.lower().startswith("subject:"):
                blocks.append(("subject", line))
                state = "subject"
                continue
            if line.lower().startswith("dear"):
                blocks.append(("salute", line))
                state = "body"
                continue
            if line:
                blocks.append(("contact", line))
            continue
        if state == "subject":
            if line.lower().startswith("dear"):
                blocks.append(("salute", line))
                state = "body"
            continue
        if state == "body":
            if any(t in low for t in _CLOSING_TRIGGERS):
                flush_body()
                blocks.append(("closing", line))
                state = "closing"
                continue
            if not line:
                flush_body()
            else:
                body_para.append(line)
            continue
        if state == "closing":
            if line:
                blocks.append(("closing", line))
    flush_body()
    return blocks


def save_cover_letter_pdf(cover_letter_text: str, output_pdf_path: Path) -> bool:
    try:
        blocks = _parse(cover_letter_text)
        doc = SimpleDocTemplate(str(output_pdf_path), pagesize=letter,
                                 topMargin=0.85 * inch, bottomMargin=0.85 * inch,
                                 leftMargin=0.9 * inch, rightMargin=0.9 * inch)
        story = []
        for i, (kind, text) in enumerate(blocks):
            if not text:
                continue
            style = {"contact": _CONTACT, "subject": _SUBJECT, "salute": _BODY,
                      "body": _BODY, "closing": _CONTACT}.get(kind, _BODY)
            if kind == "contact" and i == 0:
                style = _NAME
            story.append(Paragraph(text, style))
            if kind in ("subject", "salute"):
                story.append(Spacer(1, 6))
        doc.build(story)
        return True
    except Exception:
        output_pdf_path.with_suffix(".txt").write_text(cover_letter_text, encoding="utf-8")
        return False
