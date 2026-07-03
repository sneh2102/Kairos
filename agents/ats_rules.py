"""Deterministic ATS rule engine — every number in the ATS score comes from
here, not from the LLM (small models regress to the same mid score for
everything; code doesn't). The LLM layer in ats_checker.py only adds bounded
qualitative judgement on top.

Checks: JD keyword coverage (with equivalents), domain alignment (resume
experience must be in the JD's field), quantified-metric density, action-verb
strength + repetition, word repetition, AI-tell phrases (humanize),
grammar-lite, length/structure. Pure stdlib.
"""
import math
import re
from collections import Counter

# ---------------------------------------------------------------- vocab ----

# Common tech terms (lowercase). Multi-word phrases listed explicitly so
# "machine learning" matches as a phrase, not two stopwords-adjacent tokens.
TECH_VOCAB = {
    "python", "java", "javascript", "typescript", "golang", "rust", "scala", "kotlin",
    "swift", "ruby", "php", "perl", "bash", "powershell", "sql", "nosql", "html", "css",
    "react", "angular", "vue", "svelte", "next.js", "nextjs", "node.js", "nodejs", "express",
    "django", "flask", "fastapi", "spring", "spring boot", ".net", "dotnet", "rails",
    "laravel", "graphql", "rest", "rest api", "restful", "grpc", "websocket", "websockets",
    "microservices", "monolith", "serverless", "event-driven",
    "aws", "azure", "gcp", "google cloud", "lambda", "ec2", "s3", "cloudformation",
    "terraform", "ansible", "puppet", "chef", "docker", "kubernetes", "k8s", "helm",
    "openshift", "ecs", "eks", "fargate", "cloudwatch", "datadog", "grafana", "prometheus",
    "splunk", "new relic", "pagerduty", "nagios", "elk", "elasticsearch", "logstash", "kibana",
    "ci/cd", "cicd", "jenkins", "github actions", "gitlab", "circleci", "argocd", "devops",
    "sre", "observability", "monitoring", "logging", "alerting", "incident response",
    "postgresql", "postgres", "mysql", "mariadb", "sqlite", "oracle", "sql server", "mongodb",
    "dynamodb", "cassandra", "redis", "memcached", "kafka", "rabbitmq", "sqs", "sns",
    "airflow", "spark", "hadoop", "hive", "snowflake", "databricks", "dbt", "etl", "elt",
    "data pipeline", "data pipelines", "data warehouse", "data lake", "big data",
    "machine learning", "deep learning", "neural network", "nlp", "computer vision",
    "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn", "pandas", "numpy",
    "llm", "llms", "genai", "generative ai", "rag", "langchain", "langgraph", "prompt engineering",
    "vector database", "embeddings", "openai", "hugging face", "fine-tuning", "agents", "mlops",
    "git", "github", "bitbucket", "jira", "confluence", "agile", "scrum", "kanban",
    "unit testing", "integration testing", "tdd", "pytest", "junit", "selenium", "cypress",
    "playwright", "jest", "mocha", "qa automation", "test automation",
    "linux", "unix", "windows server", "active directory", "vmware", "hyper-v",
    "networking", "tcp/ip", "dns", "dhcp", "vpn", "firewall", "load balancing", "load balancer",
    "cybersecurity", "oauth", "sso", "saml", "encryption", "iam", "penetration testing",
    "api", "apis", "sdk", "oop", "object-oriented", "functional programming", "design patterns",
    "distributed systems", "concurrency", "multithreading", "caching", "message queue",
    "full stack", "full-stack", "frontend", "front-end", "backend", "back-end",
    "responsive design", "accessibility", "tailwind", "bootstrap", "sass", "webpack", "vite",
    "c", "c++", "c#", "objective-c", "matlab", "r", "tableau", "power bi", "excel", "vba",
    "salesforce", "sap", "servicenow", "sharepoint", "shell scripting", "cron", "regex",
    "json", "xml", "yaml", "protobuf", "http", "https", "tls", "ssl", "soap",
}

# Interchangeable-technology groups: if the JD wants one and the resume has
# another from the same group, count it matched (screener uses the same idea).
EQUIV_GROUPS = [
    {"postgresql", "postgres", "mysql", "mariadb", "sql", "sql server", "oracle", "sqlite"},
    {"aws", "azure", "gcp", "google cloud"},
    {"react", "vue", "angular", "svelte"},
    {"docker", "kubernetes", "k8s", "containers", "containerization", "openshift", "ecs", "eks"},
    {"node.js", "nodejs", "express"},
    {"next.js", "nextjs", "react"},
    {"jenkins", "github actions", "gitlab", "circleci", "ci/cd", "cicd"},
    {"terraform", "cloudformation", "ansible", "puppet", "chef"},
    {"kafka", "rabbitmq", "sqs", "message queue"},
    {"datadog", "grafana", "prometheus", "cloudwatch", "splunk", "new relic", "monitoring", "observability"},
    {"pytorch", "tensorflow", "keras"},
    {"pytest", "junit", "jest", "mocha", "unit testing", "tdd"},
    {"selenium", "cypress", "playwright", "qa automation", "test automation"},
    {"rest", "rest api", "restful", "api", "apis"},
    {"golang", "go"},
    {"elasticsearch", "elk", "logstash", "kibana"},
    {"mongodb", "dynamodb", "cassandra", "nosql"},
    {"llm", "llms", "genai", "generative ai", "openai"},
    {"langchain", "langgraph", "agents", "rag"},
    {"frontend", "front-end", "full stack", "full-stack"},
    {"backend", "back-end", "full stack", "full-stack"},
]

# ── Domain taxonomy ─────────────────────────────────────────────────────────
# A JD and a resume each get a domain "fingerprint" (how much they lean toward
# each field). Alignment = cosine similarity of the two fingerprints, so a
# frontend candidate applying to a data-engineering role scores low even if a
# few generic keywords overlap. Terms are the most DISCRIMINATIVE per domain.
DOMAIN_SIGNALS = {
    "frontend": {"react", "vue", "angular", "svelte", "css", "html", "tailwind", "redux",
                 "next.js", "jsx", "frontend", "front-end", "responsive design", "ui", "ux",
                 "webpack", "vite", "sass", "accessibility", "typescript"},
    "backend": {"api", "rest", "rest api", "graphql", "microservices", "backend", "back-end",
                "express", "django", "flask", "fastapi", "spring", "spring boot", "node.js",
                "grpc", "message queue", "middleware", "server"},
    "devops": {"kubernetes", "k8s", "terraform", "ansible", "ci/cd", "cicd", "jenkins", "helm",
               "gitops", "argocd", "infrastructure", "sre", "prometheus", "grafana",
               "cloudformation", "observability", "monitoring", "docker", "openshift"},
    "cloud": {"aws", "azure", "gcp", "google cloud", "lambda", "ec2", "s3", "serverless",
              "cloudwatch", "fargate", "eks", "ecs"},
    "data_engineering": {"etl", "elt", "spark", "kafka", "airflow", "hadoop", "hive",
                         "data pipeline", "data pipelines", "data warehouse", "data lake",
                         "snowflake", "databricks", "dbt", "big data"},
    "data_science_ml": {"machine learning", "deep learning", "neural network", "pytorch",
                        "tensorflow", "keras", "scikit-learn", "sklearn", "pandas", "numpy",
                        "computer vision", "nlp", "mlops", "model", "regression", "classification"},
    "ai_llm": {"llm", "llms", "genai", "generative ai", "langchain", "langgraph", "rag",
               "prompt engineering", "vector database", "embeddings", "openai", "hugging face",
               "fine-tuning", "agents"},
    "mobile": {"android", "ios", "swift", "kotlin", "react native", "flutter", "mobile",
               "objective-c"},
    "qa": {"selenium", "cypress", "playwright", "qa automation", "test automation", "junit",
           "pytest", "unit testing", "integration testing", "manual testing"},
    "security": {"cybersecurity", "penetration testing", "encryption", "oauth", "sso", "saml",
                 "iam", "vulnerability", "cryptography", "security"},
    "data_analytics": {"tableau", "power bi", "excel", "vba", "dashboard", "reporting",
                       "data analysis", "analytics", "visualization", "sql"},
    "embedded": {"embedded", "firmware", "fpga", "rtos", "microcontroller", "verilog", "hardware"},
}


def domain_vector(text: str) -> dict[str, int]:
    """How many of each domain's signal terms appear in `text`."""
    tl = text.lower()
    return {dom: sum(1 for t in terms if _text_has(t, tl)) for dom, terms in DOMAIN_SIGNALS.items()}


def top_domains(text: str, n: int = 3) -> list[str]:
    vec = domain_vector(text)
    return [d for d, c in sorted(vec.items(), key=lambda kv: -kv[1]) if c > 0][:n]


def domain_alignment(jd_text: str, resume_text: str) -> float:
    """Cosine similarity of JD vs resume domain fingerprints (0..1). 0 if either
    side shows no domain signal at all (e.g. a non-technical resume)."""
    jv, rv = domain_vector(jd_text), domain_vector(resume_text)
    dot = sum(jv[d] * rv[d] for d in jv)
    nj = math.sqrt(sum(v * v for v in jv.values()))
    nr = math.sqrt(sum(v * v for v in rv.values()))
    if nj == 0 or nr == 0:
        return 0.0
    return dot / (nj * nr)

STRONG_VERBS = {
    "architected", "streamlined", "spearheaded", "delivered", "accelerated", "reduced",
    "implemented", "integrated", "migrated", "optimized", "optimised", "automated", "launched",
    "refactored", "scaled", "orchestrated", "designed", "collaborated", "deployed", "monitored",
    "resolved", "boosted", "coordinated", "authored", "established", "configured", "revamped",
    "consolidated", "validated", "championed", "diagnosed", "built", "developed", "created",
    "engineered", "led", "improved", "increased", "decreased", "eliminated", "modernized",
    "containerized", "provisioned", "instrumented", "maintained", "shipped", "owned",
    "pioneered", "standardized", "hardened", "profiled", "debugged", "tuned",
    # broader set of legitimate resume action verbs (writers use these too)
    "constructed", "produced", "managed", "translated", "programmed", "decomposed",
    "deconstructed", "applied", "wrote", "facilitated", "triaged", "executed", "synthesized",
    "analyzed", "analysed", "administered", "scripted", "generated", "initiated", "transformed",
    "unified", "redesigned", "rearchitected", "rebuilt", "overhauled", "simplified", "mentored",
    "reviewed", "partnered", "negotiated", "forecasted", "modeled", "modelled", "mapped",
    "ported", "upgraded", "patched", "secured", "encrypted", "authenticated", "cached",
    "indexed", "queried", "aggregated", "cleansed", "labeled", "trained", "evaluated",
    "benchmarked", "traced", "fixed", "remediated", "mitigated", "prevented", "detected",
    "visualized", "reported", "presented", "documented", "specified", "drafted", "formalized",
    "templated", "parameterized", "generalized", "abstracted", "modularized", "componentized",
    "released", "observed", "logged", "drove", "enabled", "enhanced", "expanded", "extended",
    "restructured", "reorganized", "prototyped", "researched", "investigated", "assembled",
    "composed", "formulated", "devised", "crafted", "architectured", "bootstrapped", "productionized",
    # common gerund openers (acceptable; writers sometimes use them)
    "building", "designing", "developing", "implementing", "creating", "automating",
    "optimizing", "engineering", "leading", "managing", "deploying", "migrating",
}

WEAK_OPENERS = {
    "responsible", "worked", "helped", "assisted", "participated", "involved", "tasked",
    "duties", "was", "were", "did", "made", "used", "using", "utilized", "handled",
}

# Phrases that read as LLM-generated or corporate filler — each hit costs
# humanize points and gets named in the feedback so the writers remove it.
AI_TELL_PHRASES = [
    "leverage", "leveraging", "leveraged", "delve", "delving", "cutting-edge",
    "state-of-the-art", "seamless", "seamlessly", "synergy", "synergies",
    "passionate", "results-driven", "detail-oriented", "team player", "fast-paced",
    "dynamic environment", "proven track record", "think outside the box",
    "meticulously", "meticulous", "furthermore", "moreover", "showcasing", "showcases",
    "underscores", "underscoring", "pivotal", "testament", "tapestry", "notably",
    "in today's", "ever-evolving", "game-changing", "best-in-class", "world-class",
    "utilize", "utilized", "utilizing", "empower", "empowering", "elevate", "elevating",
]

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by", "at",
    "is", "are", "was", "were", "be", "been", "as", "it", "its", "this", "that", "these",
    "those", "from", "into", "over", "under", "up", "down", "out", "we", "you", "our",
    "your", "their", "will", "can", "may", "must", "should", "have", "has", "had", "not",
    "but", "if", "than", "then", "so", "such", "per", "via", "across", "within", "using",
    "able", "etc", "eg", "ie", "new", "more", "other", "all", "any", "each", "both",
    "years", "year", "experience", "work", "working", "team", "teams", "strong", "skills",
    "ability", "knowledge", "understanding", "including", "required", "preferred", "plus",
}

_EQUIV_LOOKUP: dict[str, set[str]] = {}
for group in EQUIV_GROUPS:
    for term in group:
        _EQUIV_LOOKUP.setdefault(term, set()).update(group)


# ------------------------------------------------------------ extraction ----

def latex_to_text(latex: str) -> str:
    text = latex
    text = re.sub(r"\\textbf\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\(textit|emph|underline|small)\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\section\{([^}]*)\}", r"\n\n=== \1 ===\n", text)
    text = re.sub(r"\\resumeItem\{([^}]*)\}", r"- \1", text)
    text = re.sub(r"\\resumeSubheading\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}", r"\3, \1 (\2)", text)
    text = re.sub(r"\\resumeProjectHeading\s*\{([^}]*)\}\{([^}]*)\}", r"Project: \1 (\2)", text)
    # strip wrapper command tokens WITHOUT their brace groups (their content must
    # survive) before the generic strip, which consumes {group} content
    text = re.sub(r"\\(small|item|textbf|emph|textit)\b", "", text)
    text = re.sub(r"\\[a-zA-Z]+(\[[^\]]*\])?(\{[^}]*\})?", "", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_SUMMARY_RE = re.compile(
    r"years of (professional |industry |relevant )?experience|"
    r"^\w+ (developer|engineer|analyst|scientist|architect|programmer) with ",
    re.IGNORECASE,
)


def is_summary_bullet(bullet: str) -> bool:
    """A profile/objective line ('X Developer with over N years of experience…')
    is descriptive, not an accomplishment bullet — it shouldn't be judged for
    action verbs or metrics."""
    return bool(_SUMMARY_RE.search(bullet.strip()))


def extract_bullets(latex: str, skip_summary: bool = False) -> list[str]:
    """resumeItem bodies, LaTeX markup stripped, in document order.
    skip_summary drops profile/objective lines (for verb/metric scoring)."""
    bullets = re.findall(r"\\resumeItem\{((?:[^{}]|\{[^{}]*\})*)\}", latex)
    cleaned = [re.sub(r"\\[a-zA-Z]+|[{}\\]", "", b).strip() for b in bullets]
    if skip_summary:
        cleaned = [b for b in cleaned if not is_summary_bullet(b)]
    return cleaned


def strip_familiar_with(skills_latex: str) -> str:
    """Removes the trailing 'Familiar With:' category from a Skills block. Those
    are aspirational/adjacent tools (often injected), not claimed proficiency, so
    they must not count toward genuine keyword coverage in the score."""
    return re.sub(r"\\textbf\{Familiar With:?\}\{[^}]*\}", "", skills_latex, flags=re.IGNORECASE)


def split_latex_sections(latex: str) -> dict[str, str]:
    """{'skills': ..., 'experience': ..., 'projects': ...} bodies from full LaTeX."""
    mapping = {"technical skills": "skills", "experience": "experience", "relevant projects": "projects"}
    out = {"skills": "", "experience": "", "projects": ""}
    parts = re.split(r"\\section\{([^}]*)\}", latex)
    for i in range(1, len(parts) - 1, 2):
        key = mapping.get(parts[i].strip().lower())
        if key:
            out[key] = parts[i + 1]
    return out


def extract_jd_keywords(description: str) -> list[str]:
    """JD keywords, most-frequent first: known tech vocab (incl. phrases) plus
    tech-shaped tokens (CamelCase, dotted, ALLCAPS acronyms) the vocab misses."""
    desc_lower = description.lower()
    found: Counter = Counter()

    for term in TECH_VOCAB:
        hits = len(re.findall(rf"(?<![\w+#./-]){re.escape(term)}(?![\w+#])", desc_lower))
        if hits:
            found[term] += hits

    # Tech-shaped unknowns: FooBar, foo.js, ABC/ABCD acronyms
    for token in re.findall(r"\b[A-Z][a-z]+[A-Z]\w*\b|\b\w+\.(?:js|py|net|io)\b|\b[A-Z]{2,6}\b", description):
        t = token.lower()
        if t not in STOPWORDS and len(t) > 1 and t not in found:
            # keep acronyms only if repeated or clearly technical — one-off ALLCAPS
            # words are often just shouting ("MUST", "FTE")
            hits = len(re.findall(rf"\b{re.escape(token)}\b", description))
            if not token.isupper() or hits >= 2:
                found[t] += hits

    return [term for term, _ in found.most_common(40)]


def _text_has(term: str, text_lower: str) -> bool:
    return re.search(rf"(?<![\w+#./-]){re.escape(term)}(?![\w+#])", text_lower) is not None


def match_keywords(keywords: list[str], resume_text: str) -> tuple[list[str], list[str]]:
    """(matched, missing). A keyword is matched directly or via an equivalent."""
    resume_lower = resume_text.lower()
    matched, missing = [], []
    for kw in keywords:
        candidates = {kw} | _EQUIV_LOOKUP.get(kw, set())
        if any(_text_has(c, resume_lower) for c in candidates):
            matched.append(kw)
        else:
            missing.append(kw)
    return matched, missing


# ---------------------------------------------------------------- checks ----

_METRIC_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|\\%|percent|x\b|k\b|K\b|M\b|ms\b|s\b|sec|min|hours?|days?|weeks?)"
    r"|~?\$?\d[\d,]*(?:\.\d+)?\+?\b"
)


def check_metrics(bullets: list[str]) -> dict:
    """Every bullet should carry a number. Returns ratio + which lack one."""
    if not bullets:
        return {"ratio": 0.0, "without": []}
    without = [b[:60] for b in bullets if not _METRIC_RE.search(b)]
    return {"ratio": 1 - len(without) / len(bullets), "without": without}


def check_verbs(bullets: list[str]) -> dict:
    """Openers should be strong verbs, never reused."""
    openers = [b.split()[0].lower().strip(",.;:") for b in bullets if b.split()]
    weak = sorted({o for o in openers if o in WEAK_OPENERS})
    repeated = sorted([v for v, n in Counter(openers).items() if n > 1])
    strong = sum(1 for o in openers if o in STRONG_VERBS)
    quality = strong / len(openers) if openers else 0.0
    return {"quality": quality, "weak": weak, "repeated": repeated}


def check_ai_tells(text: str) -> dict:
    """Humanize scan: AI/corporate phrases, em dashes, arrows."""
    tl = text.lower()
    hits = sorted({p for p in AI_TELL_PHRASES if re.search(rf"\b{re.escape(p)}\b", tl)})
    if "—" in text:
        hits.append("em dash (—)")
    if re.search(r"->|=>", text):
        hits.append("arrow symbols (->, =>)")
    return {"hits": hits}


# Technical/domain words are SUPPOSED to repeat on a tech resume (ATS rewards
# it) — only generic filler counts as "overused". This is the single-token
# tech vocab plus common legit resume nouns.
_REPEAT_OK = {
    "data", "system", "systems", "pipeline", "pipelines", "api", "apis", "application",
    "applications", "architecture", "cloud", "service", "services", "database", "databases",
    "software", "code", "platform", "infrastructure", "deployment", "production", "model",
    "models", "feature", "features", "user", "users", "server", "client", "web", "backend",
    "frontend", "framework", "workflow", "workflows", "automation", "integration", "security",
    "network", "analytics", "dashboard", "microservices", "container", "test", "testing",
    # measurement / domain nouns that legitimately recur on a tech resume
    "time", "times", "days", "node", "management", "processing", "performance", "latency",
    "throughput", "patient", "technical", "reporting", "response", "real-time", "runtime",
    "requests", "records", "accuracy", "uptime", "queries", "endpoints", "coverage",
} | {w for term in TECH_VOCAB for w in term.split() if len(w) > 3}


def check_word_repetition(bullets: list[str]) -> dict:
    """Generic (non-technical) filler words overused across bullets (>3×).
    Technical/domain words are excluded — repeating them is correct, not a flaw."""
    words = []
    for b in bullets:
        words += [w.lower().strip(",.;:()") for w in re.findall(r"[A-Za-z][A-Za-z-]+", b)]
    counts = Counter(w for w in words if w not in STOPWORDS and w not in _REPEAT_OK and len(w) > 3)
    overused = sorted([(w, n) for w, n in counts.items() if n > 4], key=lambda t: -t[1])
    return {"overused": overused[:8]}


def check_grammar_lite(bullets: list[str]) -> dict:
    """Cheap deterministic grammar signals: doubled words, lowercase starts,
    inconsistent trailing periods."""
    issues = []
    for b in bullets:
        m = re.search(r"\b(\w+)\s+\1\b", b, re.IGNORECASE)
        if m:
            issues.append(f'doubled word "{m.group(1)}" in: "{b[:50]}..."')
        if b and b[0].islower():
            issues.append(f'bullet starts lowercase: "{b[:50]}..."')
    enders = [b.rstrip().endswith(".") for b in bullets if b.strip()]
    if enders and 0 < sum(enders) < len(enders):
        issues.append("inconsistent trailing periods across bullets — pick one style")
    return {"issues": issues[:8]}


def check_structure(latex: str, bullets: list[str]) -> dict:
    """Length/shape: sections present, bullet count, bullet length, word count."""
    issues = []
    text = latex_to_text(latex)
    words = len(text.split())
    sections = split_latex_sections(latex)
    for name, body in sections.items():
        if not body.strip():
            issues.append(f"missing section: {name}")
    n = len(bullets)
    if n and n < 8:
        issues.append(f"only {n} bullets total — aim for 12-20")
    elif n > 30:
        issues.append(f"{n} bullets — too dense, trim to under 26")
    short = [b[:50] for b in bullets if len(b) < 50]
    # first bullet is often a summary/objective line — legitimately longer
    long_ = [b[:50] for b in bullets[1:] if len(b) > 330]
    if short:
        issues.append(f"{len(short)} bullet(s) too short (<1 line), e.g. \"{short[0]}...\"")
    if long_:
        issues.append(f"{len(long_)} bullet(s) too long (>2 lines), e.g. \"{long_[0]}...\"")
    if words and words < 280:
        issues.append(f"resume body only ~{words} words — likely under one page")
    elif words > 1000:
        issues.append(f"resume body ~{words} words — likely over one page")
    return {"issues": issues}


# ----------------------------------------------------------------- score ----

# The ENTIRE 100-point score is computed here, deterministically. The LLM does
# NOT contribute any points (small models regress every resume to the same mid
# number) — it only supplies qualitative feedback text in ats_checker.
WEIGHTS = {"keywords": 33, "domain": 12, "metrics": 15, "verbs": 10, "humanize": 15, "structure": 15}


def analyze(description: str, latex: str) -> dict:
    """Runs every deterministic check. Returns subscores (0..weight), raw
    findings, and per-section 0-100 scores."""
    bullets = extract_bullets(latex)
    accomplishment_bullets = extract_bullets(latex, skip_summary=True)  # excludes profile line
    resume_text = latex_to_text(latex)
    sections = split_latex_sections(latex)

    keywords = extract_jd_keywords(description)
    matched, missing = match_keywords(keywords, resume_text)  # whole-resume (for feedback/injection)

    # ── keyword SCORE: credit by WHERE the keyword appears, so stuffing a
    #    "Familiar With:" line can't fake coverage. A keyword only earns full
    #    credit if it's DEMONSTRATED in an experience/project bullet; merely
    #    listed in a real skills category earns partial; "Familiar With:"
    #    (aspirational) earns nothing.
    demonstrated_text = latex_to_text(
        sections.get("experience", "") + "\n" + sections.get("projects", "")).lower()
    listed_text = latex_to_text(strip_familiar_with(sections.get("skills", ""))).lower()
    if keywords:
        dem = sum(1 for k in keywords
                  if any(_text_has(c, demonstrated_text) for c in {k} | _EQUIV_LOOKUP.get(k, set())))
        lst = sum(1 for k in keywords
                  if any(_text_has(c, listed_text) for c in {k} | _EQUIV_LOOKUP.get(k, set())))
        dem_ratio, list_ratio = dem / len(keywords), lst / len(keywords)
        kw_ratio = min(1.0, 0.65 * dem_ratio + 0.45 * list_ratio)
    else:
        kw_ratio = 0.7  # vague JD with no extractable keywords: neutral-ish

    # ── domain alignment: the resume's OVERALL experience (experience + projects
    #    + real skills) must be in the JD's field. A frontend resume applying to
    #    a data-engineering JD scores low here even if a few generic keywords overlap.
    experience_text = latex_to_text(
        sections.get("experience", "") + "\n" + sections.get("projects", "")
        + "\n" + strip_familiar_with(sections.get("skills", "")))
    align = domain_alignment(description, experience_text)
    jd_domains = top_domains(description)
    resume_domains = top_domains(experience_text)

    metrics = check_metrics(accomplishment_bullets)
    verbs = check_verbs(accomplishment_bullets)
    ai = check_ai_tells(resume_text)
    rep = check_word_repetition(bullets)
    grammar = check_grammar_lite(bullets)
    structure = check_structure(latex, bullets)

    humanize_ratio = max(0.0, 1 - 0.15 * len(ai["hits"]) - 0.05 * len(rep["overused"]))
    structure_ratio = max(0.0, 1 - 0.15 * len(structure["issues"]) - 0.1 * len(grammar["issues"]))
    verb_ratio = max(0.0, verbs["quality"] - 0.1 * len(verbs["repeated"]) - 0.1 * len(verbs["weak"]))

    # Relevance gate: metrics/verbs measure BULLET CONTENT quality, but a nicely
    # formatted bullet about the wrong job shouldn't earn ATS-fit points. Scale
    # them by how relevant the resume is (keyword coverage AND domain fit), so an
    # off-target resume (barista → DevOps) can't score high on polish alone.
    relevance = 0.30 + 0.70 * (0.6 * dem_ratio + 0.4 * align) if keywords else 1.0

    subscores = {
        "keywords": kw_ratio * WEIGHTS["keywords"],
        "domain": align * WEIGHTS["domain"],
        "metrics": metrics["ratio"] * relevance * WEIGHTS["metrics"],
        "verbs": verb_ratio * relevance * WEIGHTS["verbs"],
        "humanize": humanize_ratio * WEIGHTS["humanize"],
        "structure": structure_ratio * WEIGHTS["structure"],
    }

    # Per-section 0-100: skills = its keyword coverage; experience/projects =
    # keyword presence + metric density + verb quality inside that section.
    def section_score(name: str) -> int:
        body = sections.get(name, "")
        if not body.strip():
            return 0
        body_lower = latex_to_text(body).lower()
        top = keywords[:15]
        kw_here = (sum(1 for k in top if any(_text_has(c, body_lower) for c in {k} | _EQUIV_LOOKUP.get(k, set())))
                   / len(top)) if top else 0.7
        if name == "skills":
            return round(kw_here * 100)
        sec_bullets = extract_bullets(body, skip_summary=True)
        m = check_metrics(sec_bullets)["ratio"]
        v = check_verbs(sec_bullets)["quality"]
        return round((0.45 * kw_here + 0.35 * m + 0.2 * v) * 100)

    return {
        "subscores": subscores,
        "det_total": round(sum(subscores.values())),
        "det_max": sum(WEIGHTS.values()),
        "section_scores": {s: section_score(s) for s in ("skills", "experience", "projects")},
        "keywords": keywords,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "domain_alignment": align,
        "jd_domains": jd_domains,
        "resume_domains": resume_domains,
        "metrics": metrics,
        "verbs": verbs,
        "ai_tells": ai["hits"],
        "overused_words": rep["overused"],
        "grammar_issues": grammar["issues"],
        "structure_issues": structure["issues"],
    }


def build_feedback(analysis: dict) -> dict[str, str]:
    """Turns findings into the concrete, actionable per-section feedback the
    writer agents consume on the rebuild pass."""
    missing = analysis["missing_keywords"]
    skills_parts, exp_parts, proj_parts = [], [], []

    # Domain mismatch is the highest-priority fix — surface it first.
    if analysis.get("domain_alignment", 1.0) < 0.6 and analysis.get("jd_domains"):
        jd_dom = ", ".join(d.replace("_", " ") for d in analysis["jd_domains"])
        res_dom = ", ".join(d.replace("_", " ") for d in analysis["resume_domains"]) or "unclear"
        note = (f"DOMAIN MISMATCH — this JD is a {jd_dom} role, but the resume reads as {res_dom}. "
                f"Re-angle every bullet toward {jd_dom}: lead with the {jd_dom}-relevant part of each "
                f"real accomplishment, and use {jd_dom} terminology throughout.")
        exp_parts.append(note)
        proj_parts.append(f"Select and frame projects that showcase {jd_dom} work.")

    if missing:
        skills_parts.append(
            "Missing JD keywords — add the ones the candidate genuinely has (or list adjacent ones "
            f"under 'Familiar With:'): {', '.join(missing[:12])}."
        )
        exp_parts.append(
            f"Work these JD keywords into bullets where honestly applicable: {', '.join(missing[:8])}."
        )
        proj_parts.append(
            f"Prefer projects demonstrating: {', '.join(missing[:6])} — swap one in if the list has a better match."
        )
    if analysis["metrics"]["without"]:
        n = len(analysis["metrics"]["without"])
        example = analysis["metrics"]["without"][0]
        exp_parts.append(
            f"{n} bullet(s) have no metric — add a conservative number (%, count, time saved) to each. "
            f'E.g. the bullet starting "{example}..." needs one.'
        )
        proj_parts.append("Every project bullet needs one concrete number (users, %, latency, accuracy).")
    if analysis["verbs"]["repeated"]:
        exp_parts.append(f"Repeated opening verbs — each may be used once total: {', '.join(analysis['verbs']['repeated'])}.")
    if analysis["verbs"]["weak"]:
        exp_parts.append(f"Weak bullet openers — replace with strong action verbs: {', '.join(analysis['verbs']['weak'])}.")
    if analysis["ai_tells"]:
        exp_parts.append(f"Remove AI/corporate-sounding phrases everywhere: {', '.join(analysis['ai_tells'][:8])}.")
    if analysis["overused_words"]:
        words = ", ".join(f"{w} (×{n})" for w, n in analysis["overused_words"][:5])
        exp_parts.append(f"Overused words — vary the wording: {words}.")
    for issue in analysis["grammar_issues"] + analysis["structure_issues"]:
        exp_parts.append(f"Fix: {issue}")

    return {
        "skills_feedback": " ".join(skills_parts),
        "experience_feedback": " ".join(exp_parts),
        "projects_feedback": " ".join(proj_parts),
    }
