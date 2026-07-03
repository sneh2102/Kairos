"""Shared helpers for the three writer agents (skills/experience/projects) —
response cleanup and the surgical-rebuild system prompt they all reuse."""
import re

_PREAMBLE_LINE = re.compile(
    r"^\s*\\(documentclass|usepackage|newcommand|renewcommand|begin\{document\}|pagestyle|addtolength).*$",
    re.MULTILINE,
)

SYSTEM_SURGICAL = (
    "You are an expert resume editor performing a SURGICAL fix on one resume section.\n"
    "Apply ONLY the changes requested in the feedback. Keep company names, role titles, "
    "dates, project names, and overall structure exactly as they are unless the feedback "
    "explicitly says to change them. Output ONLY the raw LaTeX for this section — no "
    "backticks, no explanation, no \\documentclass/\\usepackage/\\begin{document}/\\end{document}."
)


def strip_backticks(text: str) -> str:
    m = re.search(r"```(?:latex)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    return m.group(1).strip() if m else text.strip()


def strip_to_body(text: str) -> str:
    text = text.replace("\\end{document}", "")
    text = _PREAMBLE_LINE.sub("", text)
    return text.strip()


def clean(text: str) -> str:
    return strip_to_body(strip_backticks(text))
