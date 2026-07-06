"""Writes user-defined custom resume sections (e.g. "Summary", "Achievements")
declared in config.json's `custom_sections` list. Each has its own fully
user-editable system_prompt/user_prompt (unlike the 3 core writer agents,
whose prompts are fixed for consistency). Built once per job alongside the
header/education/cover letter — not part of the iterative ATS fix loop.
"""
from agents._writer_common import clean, enforce_experience_years
from llm.client import RotatingOllamaClient

_PLACEHOLDERS = ("full_name", "title", "company", "description", "existing_resume",
                 "ats_feedback", "experience_yrs")


def write(client: RotatingOllamaClient, section_cfg: dict, full_name: str, title: str, company: str,
          description: str, existing_resume: str, ats_feedback: str = "", experience_yrs: str = "") -> str:
    values = {
        "full_name": full_name, "title": title, "company": company,
        "description": description, "existing_resume": existing_resume,
        "ats_feedback": ats_feedback or "None — first attempt.",
        "experience_yrs": str(experience_yrs or ""),
    }
    user_prompt = section_cfg.get("user_prompt", "")
    for key in _PLACEHOLDERS:
        user_prompt = user_prompt.replace(f"{{{key}}}", values[key])
    system_prompt = section_cfg.get("system_prompt", "Output ONLY raw LaTeX for this resume section.")
    # Hard honesty rule enforced in code (independent of the user-editable prompt),
    # so the model can't claim seniority the candidate doesn't have.
    if str(experience_yrs or "").strip().isdigit():
        system_prompt += (
            f"\n\nNON-NEGOTIABLE: the candidate has EXACTLY {experience_yrs} years of professional "
            f"experience. NEVER state any other number of years, and NEVER claim more experience than "
            f"{experience_yrs} years even if the job asks for more.")
    result = clean(client.complete(system=system_prompt, user=user_prompt))
    # Belt-and-suspenders: correct any fabricated year count deterministically.
    return enforce_experience_years(result, experience_yrs)
