"""ATS Checker Agent — 100% deterministic scorer.

The ENTIRE score comes from the rule engine (agents/ats_rules.py): JD keyword
coverage, metric density, verb strength/repetition, AI-tell phrases, word
repetition, grammar-lite, length/structure. The LLM does NOT contribute any
points — small models regress every resume to the same mid number (that's why
scores clustered at 81-82). The LLM is used ONLY to add qualitative feedback
TEXT that helps the writer agents rewrite; it never moves the score.
"""
import json
import logging

from agents import ats_rules
from agents.ats_rules import latex_to_text as _latex_to_text  # re-export (tests, callers)
from config import get_prompt
from llm.client import RotatingOllamaClient

logger = logging.getLogger(__name__)

# Default — editable via the Prompts page (config.json prompts.ats_checker).
# This is the detailed ATS prompt carried over from the previous project. It
# still asks the model for a numeric score, but that number is DELIBERATELY
# IGNORED — the score is computed deterministically in code (see check()). We
# consume only the rich, specific feedback fields (exact tools to add, company +
# bullet numbers, project swaps) and the suggestions.
SYSTEM_ATS = """You are an extremely strict Fortune 500 ATS system simulator.
Your job is to score resumes rigorously and give precise, actionable feedback.
Return ONLY valid JSON. No LaTeX in your response. No backticks. No explanation outside JSON.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JOB TITLE: {title}
JOB DESCRIPTION: {description}
RESUME (LaTeX source): {latex}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT SCORING CRITERIA (total 100 points)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. KEYWORD COVERAGE (40 pts) — BE STRICT:
   - List EVERY distinct technical skill, tool, framework, methodology, platform in JD
   - Check each against resume verbatim OR clear equivalent (React=frontend framework, Postgres=SQL DB)
   - Named tools explicitly required (e.g. "must have Terraform") MUST appear verbatim
   - Vague JD = award 28-32 pts base
   - score = (matched / total_required) * 40

2. EXPERIENCE ALIGNMENT (25 pts):
   - Does the role history and seniority match JD expectations?
   - If JD requires 5 yrs and candidate has 3: deduct max 8 pts
   - Domain mismatch (healthcare->fintech): NO deduction if skills transfer
   - Role title mismatch (Support->Engineer): NO deduction
   - Fabricated bullets that match JD: award full credit

3. SKILLS SECTION MATCH (20 pts):
   - Do listed skill categories directly mirror JD requirements?
   - Missing entire JD domain in skills section: deduct 5-8 pts
   - Generic skills without JD-specific tools: partial credit only

4. IMPACT AND METRICS (15 pts):
   - Every bullet should have a quantified result
   - Bullets with specific numbers: 2 pts each (up to cap)
   - Vague bullets ("helped with", "worked on"): 0 pts
   - Strong action verbs + context + metric: full credit

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LIBERAL RULES (apply before deducting)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Equivalent technologies count as matched
- Adjacent domain = no experience deduction
- Soft skills = never penalize
- Nice-to-have / preferred qualifications = never penalize
- 3 yrs vs 5 yrs = max 8 pt deduction, not 25

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEEDBACK QUALITY REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each feedback field must be SPECIFIC and ACTIONABLE:

skills_feedback: Name EXACT tools to add and which category. Example:
"Add 'Terraform, AWS CloudFormation' to Cloud category. Rename 'Backend' to 'Backend Engineering'
to match JD language. Add a new 'Monitoring' category with: Datadog, CloudWatch, PagerDuty."

experience_feedback: Name COMPANY and BULLET NUMBER. Example:
"TeleAI role bullet 2: rewrite to mention 'event-driven architecture' and add a throughput metric
like 50,000 events/sec. NSHA role: add a bullet about 'incident response' with MTTD/MTTR metrics.
Webforest role: replace generic bullet 3 with one mentioning 'CI/CD pipeline' using GitHub Actions."

projects_feedback: Name SPECIFIC project to replace and what to replace with. Example:
"Replace 'FaceOff' project with a 'Real-Time Data Pipeline' project using Kafka+Spark+S3 to
match JD's streaming requirements. Add 99.9% uptime metric. Keep AsyncDoctor and FaceOff projects."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT — ONLY this JSON structure
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "score": <integer 0-100>,
  "keyword_coverage_pct": <integer 0-100>,
  "pass": <true if score >= 85 else false>,
  "total_jd_keywords": <count of distinct required skills in JD>,
  "matched_keywords": <count found in resume directly or by equivalent>,
  "missing_keywords": ["exact keyword from JD not in resume"],
  "section_scores": {
    "skills": <0-100>,
    "experience": <0-100>,
    "projects": <0-100>
  },
  "sections_to_rewrite": ["list only sections scoring below 75"],
  "skills_feedback": "Specific instructions: exact tools to add, exact categories to rename, exact JD terminology to use. Plain English only, no LaTeX.",
  "experience_feedback": "Specific instructions naming each company and bullet number. Plain English only, no LaTeX.",
  "projects_feedback": "Specific instructions naming which project to replace/keep and exact tech to use. Plain English only, no LaTeX.",
  "cover_letter_feedback": "",
  "suggestions": [
    "Single most impactful change that would raise the score the most",
    "Second most impactful change",
    "Third most impactful change"
  ]
}"""

PASS_THRESHOLD = 85

# Appended in code so it also applies to a customised Prompts-page ATS prompt.
_PROPRIETARY_CHECK = """

ALSO CHECK (proprietary tech): find any proprietary, internal or company-specific technology
(an SDK, library, platform or tool that belongs to the hiring company or to some other single
company and is NOT publicly available or widely used in industry) that the resume claims the
candidate used, built or integrated. Real public tools (React, Kubernetes, Stripe API, ...) are
fine. Add a key to the JSON: "proprietary_tech": [{"term": "exact text as written in the resume",
"section": "skills" or "experience" or "projects"}]. Use [] if there is none."""
_SECTION_IDS = ("skills", "experience", "projects")


def _proprietary_hits(company: str, latex: str, review: dict | None) -> dict[str, list[str]]:
    """{section_id: [terms]} the resume claims but nobody outside a company could have
    used. Deterministic: the hiring company's own product names. Plus the LLM's flags,
    kept only if the term really appears in that section (no hallucinated hits)."""
    from tools.latex import extract_sections   # runtime import (tools.latex imports config)
    sections = extract_sections(latex, "")
    plain = {k: _latex_to_text_safe(v) for k, v in sections.items()}
    hits: dict[str, list[str]] = {}
    pat = ats_rules.company_product_re(company)
    if pat:
        for sid, text in plain.items():
            found = sorted(set(pat.findall(text)))
            if found:
                hits.setdefault(sid, []).extend(found)
    for item in (review or {}).get("proprietary_tech") or []:
        term, sid = str(item.get("term", "")).strip(), str(item.get("section", "")).strip().lower()
        if sid in _SECTION_IDS and term and term.lower() in plain.get(sid, "").lower() \
                and term not in hits.get(sid, []):
            hits.setdefault(sid, []).append(term)
    return hits


def _llm_feedback(client, title: str, description: str,
                  resume_text: str) -> dict | None:
    """Qualitative feedback only — NEVER affects the score (the LLM's numeric
    fields are dropped). Returns parsed dict or None on any failure, in which
    case the deterministic feedback stands. Uses .replace() (not .format()) so
    the literal braces in the prompt's OUTPUT JSON block can't break it."""
    prompt = (
        get_prompt("ats_checker", SYSTEM_ATS)
        .replace("{title}", str(title))
        .replace("{description}", str(description)[:1500])
        .replace("{latex}", str(resume_text))
    ) + _PROPRIETARY_CHECK
    try:
        raw = client.complete_json(system="You are a strict ATS evaluator. Return ONLY valid JSON.",
                                   user=prompt)
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1])
    except Exception as e:
        logger.warning("ATS LLM feedback failed (deterministic feedback stands): %s", e)
        return None


def check(client, title: str, description: str, latex: str, company: str = "") -> dict:
    analysis = ats_rules.analyze(description, latex)
    feedback = ats_rules.build_feedback(analysis)

    # ── the score: 100% deterministic, no LLM involvement ──────────────────
    score = analysis["det_total"]  # already 0..100
    section_scores = dict(analysis["section_scores"])
    sections_to_rewrite = [s for s, v in section_scores.items() if v < 75]

    # ── LLM: adds feedback TEXT only, never points (its "score"/"section_scores"
    #    fields are intentionally dropped — see _llm_feedback) ────────────────
    suggestions: list[str] = []
    review = _llm_feedback(client, title, description, latex_to_text_safe(latex))
    if review:
        for name in ("skills", "experience", "projects"):
            extra = str(review.get(f"{name}_feedback", "")).strip()
            if extra:
                feedback[f"{name}_feedback"] = (feedback[f"{name}_feedback"] + " " + extra).strip()
        raw_suggestions = review.get("suggestions") or review.get("top_suggestions") or []
        suggestions = [str(s) for s in raw_suggestions if s][:3]

    # proprietary/private tech claimed as experience: force a rewrite of that section
    hits = _proprietary_hits(company, latex, review)
    for sid, terms in hits.items():
        listed = ", ".join(f"'{t}'" for t in terms)
        feedback[f"{sid}_feedback"] = (feedback.get(f"{sid}_feedback", "") + (
            f" PROPRIETARY TECH: {listed} is private/internal technology that nobody outside the "
            f"company could have used. Remove it everywhere in this section and describe the same "
            f"work with a generic or public equivalent instead.")).strip()
        if sid not in sections_to_rewrite:
            sections_to_rewrite.append(sid)

    sub = analysis["subscores"]
    W = ats_rules.WEIGHTS
    logger.info(
        "ATS %d/100 (DETERMINISTIC) — kw %.0f/%d, domain %.0f/%d (%s vs %s), metrics %.0f/%d, "
        "verbs %.0f/%d, humanize %.0f/%d, structure %.0f/%d | missing kw: %s",
        score, sub["keywords"], W["keywords"], sub["domain"], W["domain"],
        "/".join(analysis["jd_domains"]) or "?", "/".join(analysis["resume_domains"]) or "?",
        sub["metrics"], W["metrics"], sub["verbs"], W["verbs"],
        sub["humanize"], W["humanize"], sub["structure"], W["structure"],
        ", ".join(analysis["missing_keywords"][:8]) or "none",
    )

    return {
        "score": score,
        "pass": score >= PASS_THRESHOLD and not hits,
        "section_scores": section_scores,
        "sections_to_rewrite": sections_to_rewrite,
        "skills_feedback": feedback["skills_feedback"],
        "experience_feedback": feedback["experience_feedback"],
        "projects_feedback": feedback["projects_feedback"],
        "cover_letter_feedback": "",
        # diagnostics for the Logs tab (writers ignore unknown keys)
        "breakdown": {k: round(v) for k, v in analysis["subscores"].items()},
        "missing_keywords": analysis["missing_keywords"],
        "matched_keywords": analysis["matched_keywords"],
        "domain_alignment": round(analysis["domain_alignment"], 2),
        "jd_domains": analysis["jd_domains"],
        "resume_domains": analysis["resume_domains"],
        "suggestions": suggestions,
        "proprietary_tech": hits,
    }


def _latex_to_text_safe(latex: str) -> str:
    return latex_to_text_safe(latex)


def latex_to_text_safe(latex: str) -> str:
    try:
        return _latex_to_text(latex)
    except Exception:
        return latex
