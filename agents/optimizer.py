"""Resume Optimizer — deterministic post-processor that runs between the
writer agents and the ATS checker, and force-fixes everything the rule engine
scores that code can fix directly:

  - injects missing JD keywords into the Skills section ("Familiar With:" line,
    so it signals awareness, not faked ownership)
  - swaps AI-tell/corporate phrases for plain language
  - de-duplicates repeated bullet-opening verbs
  - grammar-lite: doubled words, lowercase bullet starts, trailing periods
  - adds a metric to every metric-less bullet via ONE batched micro-LLM call
    per section (tiny task -> small models do it well), then VERIFIES each
    returned bullet actually gained a number before accepting it

The LLM writers produce the content; this makes the measurable parts of the
score deterministic instead of hoping the model followed instructions.
"""
import json
import logging
import re

from agents import ats_rules
from agents._writer_common import enforce_experience_years, escape_latex_specials
from config import CONFIG
from llm.client import RotatingOllamaClient

logger = logging.getLogger(__name__)

# Plain-language swaps for AI-tell phrases. Order matters: longest first so
# "leveraging" doesn't get half-replaced by "leverage".
AI_TELL_SWAPS = [
    ("proven track record", "consistent record"),
    ("results-driven", "outcome-focused"),
    ("detail-oriented", "thorough"),
    ("team player", "collaborative"),
    ("fast-paced", "high-volume"),
    ("dynamic environment", "changing environment"),
    ("state-of-the-art", "modern"),
    ("best-in-class", "high-quality"),
    ("world-class", "high-quality"),
    ("cutting-edge", "modern"),
    ("leveraging", "using"),
    ("leveraged", "used"),
    ("leverage", "use"),
    ("utilizing", "using"),
    ("utilized", "used"),
    ("utilize", "use"),
    ("seamlessly", "smoothly"),
    ("seamless", "smooth"),
    ("meticulously", "carefully"),
    ("meticulous", "careful"),
    ("furthermore", "also"),
    ("moreover", "also"),
    ("showcasing", "demonstrating"),
    ("showcases", "demonstrates"),
    ("empowering", "enabling"),
    ("empower", "enable"),
    ("elevating", "improving"),
    ("elevate", "improve"),
    ("pivotal", "key"),
    ("delving", "digging"),
    ("delve", "dig"),
    ("synergies", "collaboration"),
    ("synergy", "collaboration"),
]

# Fallback verbs handed out when a bullet opener is weak or reused. All are in
# ats_rules.STRONG_VERBS so the swap always earns the verb points back. Ordered
# so the most natural/common ones get used first; long enough to cover a whole
# resume of swaps without running dry.
SPARE_VERBS = [
    "Built", "Developed", "Designed", "Engineered", "Implemented", "Created",
    "Led", "Delivered", "Launched", "Automated", "Optimized", "Streamlined",
    "Architected", "Integrated", "Migrated", "Scaled", "Refactored", "Deployed",
    "Orchestrated", "Accelerated", "Spearheaded", "Modernized", "Consolidated",
    "Revamped", "Championed", "Standardized", "Provisioned", "Instrumented",
    "Hardened", "Diagnosed", "Resolved", "Boosted", "Established", "Authored",
    "Configured", "Validated", "Coordinated", "Monitored", "Improved", "Reduced",
]

_DISPLAY = {"aws": "AWS", "gcp": "GCP", "sql": "SQL", "nosql": "NoSQL", "api": "API",
            "apis": "APIs", "ci/cd": "CI/CD", "cicd": "CI/CD", "html": "HTML", "css": "CSS",
            "php": "PHP", "etl": "ETL", "elt": "ELT", "nlp": "NLP", "llm": "LLM", "llms": "LLMs",
            "sre": "SRE", "tdd": "TDD", "iam": "IAM", "sso": "SSO", "saml": "SAML", "vpn": "VPN",
            "dns": "DNS", "dhcp": "DHCP", "json": "JSON", "xml": "XML", "yaml": "YAML",
            "http": "HTTP", "https": "HTTPS", "tls": "TLS", "ssl": "SSL", "sdk": "SDK",
            "oop": "OOP", "k8s": "K8s", "grpc": "gRPC", "rest": "REST", "rest api": "REST API",
            "postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB",
            "dynamodb": "DynamoDB", "javascript": "JavaScript", "typescript": "TypeScript",
            "node.js": "Node.js", "next.js": "Next.js", "github actions": "GitHub Actions",
            "power bi": "Power BI", "pytorch": "PyTorch", "tensorflow": "TensorFlow",
            "devops": "DevOps", "mlops": "MLOps", "graphql": "GraphQL", "rag": "RAG",
            "genai": "GenAI", "langchain": "LangChain", "langgraph": "LangGraph",
            "openai": "OpenAI", "fastapi": "FastAPI", "vba": "VBA", "sap": "SAP"}


def _display(kw: str) -> str:
    return _DISPLAY.get(kw, kw.title() if kw.islower() else kw)


# ------------------------------------------------------- keyword injection ----

def inject_missing_keywords(skills_latex: str, missing: list[str], cap: int = 8) -> str:
    """Adds up to `cap` missing JD keywords to a 'Familiar With:' line in the
    Skills section — awareness framing, not claimed ownership. Extends the
    line if the writer already made one."""
    if not missing or not skills_latex.strip():
        return skills_latex
    # escape: JD keywords routinely contain LaTeX specials (C#, R&D, C++/.NET)
    # and are injected raw, bypassing the writers' clean() pass.
    add = escape_latex_specials(", ".join(_display(k) for k in missing[:cap]))

    fam = re.search(r"(\\textbf\{Familiar With:?\}\{:?\s*)([^}]*)(\})", skills_latex)
    if fam:
        existing = fam.group(2).rstrip()
        merged = f"{existing}, {add}" if existing else f" {add}"
        return skills_latex[:fam.start(2)] + merged + skills_latex[fam.end(2):]

    cats = list(re.finditer(r"\\textbf\{[^}]*\}\{[^}]*\}", skills_latex))
    if not cats:
        return skills_latex
    last = cats[-1]
    insertion = f" \\\\\n     \\textbf{{Familiar With}}{{: {add}}}"
    return skills_latex[:last.end()] + insertion + skills_latex[last.end():]


# --------------------------------------------------- deterministic cleanup ----

def fix_ai_tells(text: str) -> str:
    for bad, good in AI_TELL_SWAPS:
        text = re.sub(rf"\b{re.escape(bad)}\b",
                      lambda m, g=good: g.capitalize() if m.group(0)[0].isupper() else g,
                      text, flags=re.IGNORECASE)
    text = text.replace("—", ", ").replace(" -> ", " to ").replace("->", " to ").replace("=>", " to ")
    return text


def _replace_bullet(latex: str, old: str, new: str) -> str:
    return latex.replace(f"\\resumeItem{{{old}", f"\\resumeItem{{{new}", 1)


def _raw_bullets(latex: str) -> list[str]:
    """resumeItem bodies with LaTeX kept intact (so we can substitute back)."""
    return re.findall(r"\\resumeItem\{((?:[^{}]|\{[^{}]*\})*)\}", latex)


def _opener(bullet_body: str) -> str:
    plain = re.sub(r"\\[a-zA-Z]+|[{}]", "", bullet_body).strip()
    return plain.split()[0].lower().strip(",.;:") if plain.split() else ""


def fix_verbs_global(sections: dict[str, str]) -> dict[str, str]:
    """Every bullet opener across ALL sections must be a strong verb used once.
    A weak opener ("Used", "Responsible", "Worked") or a repeat gets swapped for
    an unused strong verb. Runs globally so a verb used in Experience isn't also
    allowed to open a Projects bullet — the scorer judges the combined resume."""
    out = dict(sections)
    seen: set[str] = set()

    # verbs already used as openers anywhere -> not available as spares
    used = set()
    for body in out.values():
        for b in _raw_bullets(body):
            used.add(_opener(b))
    spares = [v for v in SPARE_VERBS if v.lower() not in used]

    for name in ("experience", "projects"):
        latex = out.get(name, "")
        if not latex.strip():
            continue
        for b in _raw_bullets(latex):
            opener = _opener(b)
            if not opener:
                continue
            needs_swap = opener in ats_rules.WEAK_OPENERS or opener in seen
            if not needs_swap:
                seen.add(opener)
                continue
            if not spares:
                break
            new_verb = spares.pop(0)
            # replace the opener WORD wherever it sits — bare or wrapped in
            # \textbf{...} — preserving surrounding markup. count=1 hits the
            # first (opening) occurrence only.
            new_b, n = re.subn(rf"\b{re.escape(opener)}\b", new_verb, b, count=1, flags=re.IGNORECASE)
            if n:
                latex = _replace_bullet(latex, b, new_b)
                seen.add(new_verb.lower())
            else:
                spares.insert(0, new_verb)  # couldn't apply; keep verb for next
        out[name] = latex
    return out


# Grammar-safe synonyms for the words the writers overuse in metric phrasing
# ("...reducing X by Y%"). Each list is the SAME part of speech / form as the
# key, so substitution never breaks a sentence. First 3 uses are kept; later
# ones rotate through the synonyms.
SAFE_SYNONYMS = {
    "reducing": ["lowering", "trimming", "curbing", "shrinking", "cutting"],
    "reduced": ["lowered", "trimmed", "curbed", "shrank", "cut"],
    "cutting": ["trimming", "lowering", "paring", "slashing"],
    "increasing": ["raising", "boosting", "growing", "lifting"],
    "increased": ["raised", "boosted", "grew", "lifted"],
    "improving": ["boosting", "enhancing", "strengthening", "sharpening"],
    "improved": ["boosted", "enhanced", "strengthened", "sharpened"],
    "lowering": ["trimming", "curbing", "shrinking", "paring"],
    "automated": ["streamlined", "scripted", "mechanized"],
    "automating": ["streamlining", "scripting", "mechanizing"],
    "boosting": ["raising", "lifting", "strengthening"],
    "enhancing": ["strengthening", "sharpening", "refining"],
    "through": ["via", "using"],
    "handling": ["managing", "processing", "servicing"],
    "building": ["developing", "creating", "constructing"],
}


def fix_repetition_global(sections: dict[str, str]) -> dict[str, str]:
    """Rotates synonyms for over-repeated filler words across ALL sections
    together (keeps the first 2 uses, so the combined resume stays under the
    scorer's >3 threshold). Only touches SAFE_SYNONYMS words — grammatically
    interchangeable, so meaning and tense are preserved."""
    counts: dict[str, int] = {}
    rotation: dict[str, int] = {}
    keys = "|".join(sorted(SAFE_SYNONYMS, key=len, reverse=True))
    pattern = re.compile(rf"\b({keys})\b", flags=re.IGNORECASE)

    def repl(m: re.Match) -> str:
        word = m.group(0)
        low = word.lower()
        counts[low] = counts.get(low, 0) + 1
        if counts[low] <= 2:
            return word
        syns = SAFE_SYNONYMS[low]
        pick = syns[rotation.get(low, 0) % len(syns)]
        rotation[low] = rotation.get(low, 0) + 1
        return pick.capitalize() if word[0].isupper() else pick

    out = dict(sections)
    for name in ("experience", "projects"):
        if out.get(name, "").strip():
            out[name] = pattern.sub(repl, out[name])
    return out


def fix_grammar_lite(latex: str) -> str:
    """Doubled words, lowercase bullet starts, strip trailing periods."""
    for b in _raw_bullets(latex):
        new_b = re.sub(r"\b(\w+)(\s+\1)+\b", r"\1", b, flags=re.IGNORECASE)
        stripped = new_b.strip()
        if stripped and stripped[0].islower():
            new_b = new_b.replace(stripped[0], stripped[0].upper(), 1)
        new_b = re.sub(r"\.\s*$", "", new_b)
        if new_b != b:
            latex = _replace_bullet(latex, b, new_b)
    return latex


# ------------------------------------------------------- metric micro-fix ----

SYSTEM_METRICS = """You fix resume bullets that lack numbers. For EACH bullet given, rewrite it
to include exactly one conservative, plausible metric (a %, count, time saved, or scale) prefixed
with "~" when estimated (e.g. "~25\\%"). Keep the meaning, technologies, and length (max 2 lines).
Escape % as \\%. Never invent a new technology or claim.
Return ONLY a JSON array of the rewritten bullet strings, same order, same length. No markdown."""


def add_metrics_to_bullets(client: RotatingOllamaClient, latex: str) -> str:
    """One batched LLM call rewrites every metric-less bullet in the section;
    each result is verified (has a digit now, kept its length sane) before
    replacing — a bad rewrite keeps the original."""
    bullets = _raw_bullets(latex)
    targets = [b for b in bullets
               if not ats_rules._METRIC_RE.search(re.sub(r"\\[a-zA-Z]+|[{}]", "", b))]
    if not targets:
        return latex
    try:
        raw = client.complete_json(system=SYSTEM_METRICS,
                                    user=json.dumps(targets[:8], ensure_ascii=False))
        start, end = raw.find("["), raw.rfind("]")
        rewritten = json.loads(raw[start:end + 1])
    except Exception as e:
        logger.warning("Metric micro-fix failed (bullets kept as-is): %s", e)
        return latex

    for old, new in zip(targets, rewritten):
        new = str(new).strip().rstrip(".")
        plain_new = re.sub(r"\\[a-zA-Z]+|[{}]", "", new)
        # accept only if it actually gained a number and stayed bullet-sized
        if re.search(r"\d", plain_new) and 20 <= len(new) <= 300:
            latex = _replace_bullet(latex, old, new)
    return latex


# ------------------------------------------------------------- entrypoint ----

def optimize_sections(client: RotatingOllamaClient, sections: dict[str, str],
                       description: str) -> dict[str, str]:
    """Returns updated {skills, experience, projects}. Deterministic fixes
    always run; the metric micro-fix degrades gracefully if the LLM is down.

    Order matters: AI-tell swaps first (they can turn 'Leveraged' into a weak
    'Used' opener), THEN the global verb pass fixes weak/repeated openers, so
    nothing the earlier steps introduce survives into the score."""
    out = {}
    full_text = ats_rules.latex_to_text("\n".join(
        sections.get(s, "") for s in ("skills", "experience", "projects")))
    keywords = ats_rules.extract_jd_keywords(description)
    _, missing = ats_rules.match_keywords(keywords, full_text)

    # AI-tell/filler cleanup + experience-year honesty applies to EVERY section
    # (header, education, custom summary, skills, ...), because "proven track
    # record" and fabricated "N years of experience" often live in a summary line
    # outside the three writer sections.
    real_years = CONFIG.get("profile", {}).get("experience_yrs", "")
    for name, body in sections.items():
        if body and body.strip():
            out[name] = enforce_experience_years(fix_ai_tells(body), real_years)

    skills = out.get("skills", sections.get("skills", ""))
    if skills.strip():
        out["skills"] = inject_missing_keywords(skills, missing)

    body_sections = {}
    for name in ("experience", "projects"):
        body = out.get(name, "")
        if not body.strip():
            continue
        body = fix_grammar_lite(body)
        body = add_metrics_to_bullets(client, body)
        body_sections[name] = body

    # global passes across experience + projects together, AFTER the metric
    # micro-fix (which can itself add repeated words). Verbs last, so it fixes
    # any weak openers the AI-tell swaps introduced.
    body_sections = fix_repetition_global(body_sections)
    body_sections = fix_verbs_global(body_sections)
    out.update(body_sections)
    return out


def keyword_hint(description: str, top_n: int = 20) -> str:
    """Feed-forward for the writer agents: name the JD keywords AND the JD's
    domain upfront so the first draft targets them, instead of discovering them
    via ATS feedback."""
    keywords = ats_rules.extract_jd_keywords(description)
    domains = ats_rules.top_domains(description)
    parts = []
    if domains:
        dom = ", ".join(d.replace("_", " ") for d in domains)
        parts.append(
            f"\n\nTARGET DOMAIN: this is a {dom} role. Frame EVERY bullet around {dom} work — "
            f"lead with the {dom}-relevant part of each real accomplishment and use {dom} "
            f"terminology, so the whole resume reads as a {dom} candidate.")
    if keywords:
        parts.append(
            "\n\nATS KEYWORDS EXTRACTED FROM THIS JD (weave in every one the candidate "
            "can honestly claim; exact spelling matters): "
            + ", ".join(_display(k) for k in keywords[:top_n]))
    return "".join(parts)
