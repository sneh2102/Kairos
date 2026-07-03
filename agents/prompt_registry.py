"""Central registry of every user-editable LLM prompt, for the Prompts page.

Each writer/agent module owns its own hardcoded default and reads the live
value via config.get_prompt(key, default) — this module just re-exports that
same metadata so server.py can serve/validate/reset any of them generically
without hardcoding per-key logic there.
"""
from agents import ats_checker, experience_writer, project_writer, screener, skills_writer
from agents._writer_common import SYSTEM_SURGICAL
from config import CONFIG
from tools.cover_letter import SYSTEM_COVER_LETTER

REGISTRY: dict[str, dict] = {
    "job_screener": {
        "label": "Job Screener",
        "description": "Decides yes/maybe/no for every scraped job.",
        "default": screener.DEFAULT_JOB_SCREENER,
        "placeholders": ["candidate_profile", "title", "description", "resume_text"],
        # Rendered with str.replace(), one literal token at a time — a stray
        # '{'/'}' just passes through untouched, so this can never raise.
        "format_safe": True,
    },
    "skills_section": {
        "label": "Skills Section",
        "description": "System prompt for writing the Technical Skills LaTeX section.",
        "default": skills_writer.SYSTEM_SKILLS,
        "placeholders": [],
        "format_safe": True,  # used as-is, never passed through str.format()
    },
    "experience_section": {
        "label": "Experience Section",
        "description": "System prompt for writing the Experience LaTeX section.",
        "default": experience_writer.SYSTEM_EXPERIENCE,
        "placeholders": [],
        "format_safe": True,
    },
    "projects_section": {
        "label": "Projects Section",
        "description": "System prompt for writing the Relevant Projects LaTeX section.",
        "default": project_writer.SYSTEM_PROJECTS,
        "placeholders": [],
        "format_safe": True,
    },
    "surgical_rewrite": {
        "label": "Surgical Rewrite (ATS feedback fixes)",
        "description": "Shared system prompt used to patch a section after an ATS feedback pass, "
                        "for Skills, Experience, and Projects alike.",
        "default": SYSTEM_SURGICAL,
        "placeholders": [],
        "format_safe": True,
    },
    "cover_letter": {
        "label": "Cover Letter",
        "description": "System prompt for the plain-text cover letter.",
        "default": SYSTEM_COVER_LETTER,
        "placeholders": ["full_name", "phone", "email", "today", "company", "title"],
        # Rendered with str.format(**kwargs) — an unescaped '{'/'}' (e.g. pasted
        # LaTeX) would raise KeyError/IndexError at generation time.
        "format_safe": False,
    },
    "ats_checker": {
        "label": "ATS Checker (feedback only)",
        "description": "Generates the written ATS feedback the writer agents act on. The SCORE is "
                        "computed deterministically in code — this prompt's numeric fields are "
                        "ignored, only its feedback text and suggestions are used.",
        "default": ats_checker.SYSTEM_ATS,
        "placeholders": ["title", "description", "latex"],
        # rendered with str.replace(), so its literal { } (in the OUTPUT JSON
        # block) are safe — never passed through str.format()
        "format_safe": True,
    },
}


def list_prompts() -> dict[str, dict]:
    saved = CONFIG.get("prompts", {})
    return {
        key: {
            "label": meta["label"],
            "description": meta["description"],
            "text": saved.get(key) or meta["default"],
            "default": meta["default"],
            "placeholders": meta["placeholders"],
            "is_default": not saved.get(key),
        }
        for key, meta in REGISTRY.items()
    }


def validate(key: str, text: str) -> tuple[bool, str]:
    """Dry-runs the exact substitution the prompt is rendered with at
    generation time. Returns (ok, error_message)."""
    meta = REGISTRY.get(key)
    if meta is None or meta["format_safe"]:
        return True, ""
    dummy = {name: "SAMPLE" for name in meta["placeholders"]}
    try:
        text.format(**dummy)
        return True, ""
    except (KeyError, IndexError, ValueError) as e:
        return False, (
            f"Unmatched curly brace near {{{e}}}. If you need a literal '{{' or '}}' "
            f"(e.g. LaTeX like \\textbf{{}}), double it: '{{{{' / '}}}}'."
        )
