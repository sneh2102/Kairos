"""Screener Agent — decides yes/maybe/no per scraped job via a 5-step
LLM verdict prompt. Port of ai.py's parse_ai_verdict + app.py's screening
loop (prompt assembly, custom rules injection, blacklist override).
"""
import json
import re

from config import get_prompt
from llm.client import RotatingOllamaClient

# Default — editable via the Prompts page (config.json prompts.job_screener).
DEFAULT_JOB_SCREENER = """You are a ruthless but contextually aware IT job screener.
Your job is to evaluate whether the candidate should apply to this position.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CANDIDATE PROFILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{candidate_profile}

STRONG FIT FOR:
- Software Developer / Engineer (any stack)
- Full Stack Developer
- Backend / Frontend Developer
- Data Engineer / Analyst
- Cloud / DevOps Engineer
- AI / ML Engineer
- IT Support / Systems Analyst
- Junior to Mid-level roles (0-5 years required)

NOT A FIT FOR:
- Consulting / Recruitment / Staffing companies — immediate NO
- Pure Manual QA / Testing (no coding)
- Hardware / Embedded / FPGA Engineering
- Marketing, Sales, HR, Finance, Non-technical
- Roles requiring specific certifications they don't have (PMP, CPA, etc.)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JOB TITLE: {title}
JOB DESCRIPTION: {description}
RESUME SUMMARY: {resume_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVALUATION STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — DOMAIN CHECK
Accept if role is in: Software Dev, Data Eng, Cloud, DevOps, AI/ML, IT Support, Cybersecurity.
Reject immediately (verdict=no) if: Marketing, HR, Sales, Manual QA, Hardware, non-technical.

STEP 2 — EXPERIENCE CHECK
Extract required years from JD ("X+ years", "minimum X", "X-Y years experience").
0-4 yrs → PASS | 5 yrs → BORDERLINE | 6+ yrs → FAIL | Not mentioned → NEUTRAL
LIBERAL RULE: If candidate has equivalent project/academic experience, give benefit of doubt.

STEP 3 — SKILLS MATCH (BE LIBERAL WITH EQUIVALENTS)
List every technical skill/tool/framework in the JD.
Count each as matched if candidate has it OR a clear equivalent:
  PostgreSQL ≈ MySQL ≈ SQL | AWS ≈ GCP ≈ Azure | React ≈ Vue ≈ Angular
  Docker ≈ containerization | Kubernetes ≈ container orchestration
score = matched / total_jd_skills * 100
70%+ = Strong | 45-69% = Partial | <45% = Weak

STEP 4 — SENIORITY CALIBRATION
Junior/Entry/Associate/New Grad → BONUS (raise verdict one level if borderline)
Mid/Intermediate/no label → NEUTRAL
Senior/Lead/Staff/Principal/Manager → PENALTY (lower verdict one level)

STEP 5 — FINAL VERDICT
PASS + Strong + Any → yes
PASS + Partial + Junior/Mid → yes
PASS + Partial + Senior → maybe
PASS + Weak + Junior → maybe
PASS + Weak + Mid/Senior → no
BORDERLINE + Strong + Junior/Mid → maybe
BORDERLINE + anything else → no
FAIL + anything → no

If number of years of experience is not given, infer a reasonable number from the JD yourself — do not write "unspecified".
Also extract the key technical keywords from the Job Description."""

SCHEMA_SUFFIX = (
    "\n\nIMPORTANT: Respond with ONLY a JSON object. No explanation. No markdown. No backticks.\n"
    '{"verdict": "yes or maybe or no", "years_required": "number or unspecified", '
    '"role_level": "junior or mid or senior or unspecified", "skills_match_pct": 50, '
    '"matched_skills": [], "missing_skills": [], "reasoning": "two sentences"}'
)

_SYSTEM = "You are a ruthless but contextually aware IT job screener."


def build_profile_context(profile: dict) -> str:
    education = " | ".join(
        f"{e.get('degree','')} — {e.get('institution','')}" for e in profile.get("education", [])
    )
    return (
        f"Name:           {profile.get('full_name', 'Candidate')}\n"
        f"Experience:     ~{profile.get('experience_yrs', '3')} years\n"
        f"Education:      {education}\n"
        f"Location:       {profile.get('location', 'Canada')} — open to Remote, Hybrid, Relocation\n"
        f"Core Stack:     {profile.get('core_stack', '')}\n"
        f"Job Targets:    {profile.get('job_titles', '')}\n"
        f"NOT a fit for:  {profile.get('not_fit_for', '')}"
    )


def build_custom_rules(screener_cfg: dict) -> str:
    max_years = int(screener_cfg.get("max_years_exp", 5))
    yes_pct = int(screener_cfg.get("yes_match_pct", 70))
    maybe_pct = int(screener_cfg.get("maybe_match_pct", 45))
    levels = screener_cfg.get("accept_role_levels", ["junior", "mid"])
    req_sk = [s.strip() for s in screener_cfg.get("required_skills", "").split(",") if s.strip()]
    pref_sk = [s.strip() for s in screener_cfg.get("preferred_skills", "").split(",") if s.strip()]
    reject_kw = [s.strip() for s in screener_cfg.get("reject_keywords", "").split(",") if s.strip()]
    accept_kw = [s.strip() for s in screener_cfg.get("accept_keywords", "").split(",") if s.strip()]
    blacklisted_companies = screener_cfg.get("blacklisted_companies", [])

    parts = [
        "\n\n-----------------------------------------------------",
        "CUSTOM SCREENING RULES (override the defaults above)",
        "-----------------------------------------------------",
        f"- Auto-REJECT if JD requires more than {max_years} years of experience.",
        f"- Verdict thresholds: YES if skills match >= {yes_pct}% | MAYBE if >= {maybe_pct}% | NO if below {maybe_pct}%.",
    ]
    if levels:
        non = [l for l in ("junior", "mid", "senior") if l not in levels]
        parts.append(f"- Accepted role levels: {', '.join(levels)}.")
        if non:
            parts.append(f"- Auto-REJECT (verdict=no) roles clearly labelled: {', '.join(non)}.")
    if req_sk:
        parts.append(f"- Required skills — prioritise matching these: {', '.join(req_sk)}.")
    if pref_sk:
        parts.append(f"- Preferred skills (bonus): {', '.join(pref_sk)}.")
    if reject_kw:
        parts.append(f"- Auto-REJECT immediately if title or JD contains: {', '.join(reject_kw)}.")
    if accept_kw:
        parts.append(f"- Boost verdict to YES if job title contains: {', '.join(accept_kw)}.")
    if blacklisted_companies:
        parts.append(f"- Auto-REJECT immediately if company name matches (case-insensitive): {', '.join(blacklisted_companies)}.")
    return "\n".join(parts)


def parse_verdict(text: str) -> dict:
    """Robust multi-strategy JSON extraction — LLMs don't always emit clean JSON."""
    default = {
        "verdict": "maybe", "years_required": "unspecified", "role_level": "unspecified",
        "skills_match_pct": 50, "matched_skills": [], "missing_skills": [],
        "reasoning": "Could not parse response.",
    }
    if not text or len(text.strip()) < 5:
        return default

    txt = text.strip()
    if "```" in txt:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt, re.IGNORECASE)
        if m:
            txt = m.group(1).strip()
    txt = re.sub(r",\s*([}\]])", r"\1", txt)

    start, end = txt.find("{"), txt.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(txt[start:end + 1])
            if "verdict" in data:
                v = str(data.get("verdict", "maybe")).lower().strip()
                if v not in ("yes", "no", "maybe"):
                    v = "maybe"
                return {
                    "verdict": v,
                    "years_required": str(data.get("years_required", "unspecified")),
                    "role_level": str(data.get("role_level", "unspecified")).lower(),
                    "skills_match_pct": int(data.get("skills_match_pct", 50)),
                    "matched_skills": data.get("matched_skills", []),
                    "missing_skills": data.get("missing_skills", []),
                    "reasoning": str(data.get("reasoning", "")),
                }
        except Exception:
            pass

    def extract(pattern, default_val):
        m = re.search(pattern, txt, re.IGNORECASE)
        return m.group(1) if m else default_val

    verdict = extract(r'"verdict"\s*:\s*"(\w+)"', "maybe").lower()
    if verdict not in ("yes", "no", "maybe"):
        verdict = "maybe"
    tl = txt.lower()
    if verdict == "maybe":
        if '"yes"' in tl or "verdict: yes" in tl:
            verdict = "yes"
        elif '"no"' in tl or "verdict: no" in tl:
            verdict = "no"

    default["verdict"] = verdict
    default["skills_match_pct"] = int(extract(r'"skills_match_pct"\s*:\s*(\d+)', "50"))
    default["reasoning"] = extract(r'"reasoning"\s*:\s*"([^"]*)"', "Auto-scored.")
    return default


def is_blacklisted(company: str, cfg: dict) -> bool:
    """Case-insensitive substring match against screener.blacklisted_companies."""
    blacklist = [c.strip().lower() for c in cfg["screener"].get("blacklisted_companies", []) if c and c.strip()]
    return any(b in str(company or "").lower() for b in blacklist)


def screen_job(client: RotatingOllamaClient, job: dict, cfg: dict, resume_text: str) -> dict:
    """Returns a verdict dict; blacklisted companies are hard-rejected before
    the LLM is ever called."""
    if is_blacklisted(job.get("company", ""), cfg):
        return {
            "verdict": "no",
            "years_required": "unspecified",
            "role_level": "unspecified",
            "skills_match_pct": 0,
            "matched_skills": [],
            "missing_skills": [],
            "reasoning": "Blacklisted company — hard reject, not screened.",
        }

    prompt_template = get_prompt("job_screener", DEFAULT_JOB_SCREENER).replace(
        "{candidate_profile}", build_profile_context(cfg["profile"])
    )
    prompt_template += build_custom_rules(cfg["screener"])

    clean_desc = re.sub(r"\n{3,}", "\n\n", str(job.get("description", ""))).strip()
    prompt = (
        prompt_template
        .replace("{title}", str(job.get("title", "N/A")))
        .replace("{description}", clean_desc)
        .replace("{resume_text}", resume_text)
    ) + SCHEMA_SUFFIX

    raw = client.complete(system=_SYSTEM, user=prompt)
    return parse_verdict(raw)


def verdict_to_job_row(job: dict, verdict: dict) -> dict:
    return {
        "ai_recommendation": verdict["verdict"],
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "link": job.get("job_url", ""),
        "location": job.get("location", ""),
        "site": job.get("site", ""),
        "years_required": verdict.get("years_required", "unspecified"),
        "role_level": verdict.get("role_level", "unspecified"),
        "skills_match_pct": verdict.get("skills_match_pct", 50),
        "matched_skills": ", ".join(verdict.get("matched_skills", []) or []),
        "missing_skills": ", ".join(verdict.get("missing_skills", []) or []),
        "reasoning": verdict.get("reasoning", ""),
        "description": job.get("description", ""),
        "posted_date": job.get("date_posted", ""),
        "application_status": "pending",
    }
