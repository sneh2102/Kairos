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


_QUALIFIERS = ("over", "nearly", "more than", "with", "around", "about", "approximately", "almost")
_YEARS_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*(years?|yrs?)\b", re.IGNORECASE)


def enforce_experience_years(text: str, real_years) -> str:
    """Deterministically correct any fabricated 'N years [of] experience' claim
    to the candidate's real total. Small models invent seniority to match the
    JD ('5 years' when the candidate has 2); this guarantees the number is honest
    no matter what the model wrote. Only touches genuine experience claims (a
    number next to 'experience' or after 'over/with/nearly...'), not unrelated
    numbers like metrics."""
    real = str(real_years or "").strip()
    if not real.isdigit():
        return text

    def repl(m: "re.Match") -> str:
        pre = text[max(0, m.start() - 25):m.start()].lower()
        post = text[m.end():m.end() + 30].lower()
        is_claim = "experience" in post or any(q in pre for q in _QUALIFIERS)
        if not is_claim or m.group(1) == real:
            return m.group(0)
        return f"{real} {m.group(2)}"  # normalized; drops any inflating '+'

    return _YEARS_RE.sub(repl, text)
