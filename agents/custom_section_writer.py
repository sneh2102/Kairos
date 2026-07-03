"""Writes user-defined custom resume sections (e.g. "Summary", "Achievements")
declared in config.json's `custom_sections` list. Each has its own fully
user-editable system_prompt/user_prompt (unlike the 3 core writer agents,
whose prompts are fixed for consistency). Built once per job alongside the
header/education/cover letter — not part of the iterative ATS fix loop.
"""
from agents._writer_common import clean
from llm.client import RotatingOllamaClient

_PLACEHOLDERS = ("full_name", "title", "company", "description", "existing_resume", "ats_feedback")


def write(client: RotatingOllamaClient, section_cfg: dict, full_name: str, title: str, company: str,
          description: str, existing_resume: str, ats_feedback: str = "") -> str:
    values = {
        "full_name": full_name, "title": title, "company": company,
        "description": description, "existing_resume": existing_resume,
        "ats_feedback": ats_feedback or "None — first attempt.",
    }
    user_prompt = section_cfg.get("user_prompt", "")
    for key in _PLACEHOLDERS:
        user_prompt = user_prompt.replace(f"{{{key}}}", values[key])
    system_prompt = section_cfg.get("system_prompt", "Output ONLY raw LaTeX for this resume section.")
    return clean(client.complete(system=system_prompt, user=user_prompt))
