"""Interview prep guide for one job: company research, role fit, practice Q&A,
questions to ask, and study resources.

Company facts come from live web searches (Ollama web search) and the model
may only use those results, citing them by number — so nothing about the
company is invented from stale model memory. If search is unavailable the
guide still builds from the JD + resume, and says the company part is
unverified.
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import requests

import config
from config import CONFIG
from llm.client import make_client, web_search

QA_COUNT = 16


def _client():
    return make_client(CONFIG["model"]["pipeline"], "interview")


def _json(raw: str) -> dict:
    txt = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt)
    if m:
        txt = m.group(1)
    start, end = txt.find("{"), txt.rfind("}")
    try:
        data = json.loads(txt[start:end + 1])
    except ValueError:
        raise RuntimeError(f"AI returned invalid JSON: {raw[:200]}")
    if not isinstance(data, dict):
        raise RuntimeError("AI returned an unexpected shape")
    return data


def _resume() -> str:
    try:
        return config.load_text_file(CONFIG.get("pipeline", {}).get("resume_path", "resume.txt"))[:8000]
    except FileNotFoundError:
        return ""


# ---- company research -------------------------------------------------------

def _search_company(company: str, title: str) -> list[dict]:
    """A few targeted searches in parallel, de-duplicated by URL."""
    queries = [f"{company} company overview products",
               f"{company} news 2026",
               f"{company} interview process {title}".strip(),
               f"{company} engineering tech stack culture"]
    with ThreadPoolExecutor(len(queries)) as pool:
        batches = list(pool.map(lambda q: web_search(q, 4), queries))
    seen, out = set(), []
    for r in (r for batch in batches for r in batch):
        url = r.get("url", "")
        key = url.rstrip("/").lower()
        if url and key not in seen:
            seen.add(key)
            out.append({"title": r.get("title") or url, "url": url, "content": (r.get("content") or "")[:1800]})
    return out[:14]


COMPANY_SYSTEM = """You brief a job candidate on a company before their interview.
Use ONLY the numbered search results provided. Cite facts with the result number in square brackets, e.g.
"Founded in 1998 [2]". If something isn't in the results, leave it out — never fill gaps from memory.
If the results are about a DIFFERENT company with a similar name, ignore them.

Return ONLY JSON:
{
  "overview": "<2-3 sentences: what they do, for whom, how big>",
  "facts": [{"label": "<Founded | Headquarters | Employees | Ownership | Industry | Revenue …>", "value": "<value [n]>"}],
  "products": ["<main product or business line, one line each [n]>"],
  "values": ["<stated mission or value, short [n]>"],
  "recent_news": [{"headline": "<what happened [n]>", "date": "<when, if known>"}],
  "tech_stack": ["<technology they use>"],
  "interview_process": ["<step, as reported by candidates or the company [n]>"],
  "culture": ["<culture/work-style note [n]>"],
  "talking_points": ["<a specific, genuine reason this candidate could give for 'why this company', tied to the research>"]
}"""


def research_company(company: str, title: str, description: str) -> dict:
    results = _search_company(company, title)
    if not results:
        return {"web": False, "sources": []}
    numbered = "\n\n".join(f"[{i + 1}] {r['title']} — {r['url']}\n{r['content']}" for i, r in enumerate(results))
    user = (f"COMPANY: {company}\nROLE THEY'RE INTERVIEWING FOR: {title}\n\n"
            f"JOB DESCRIPTION (for context)\n{description[:3000]}\n\nSEARCH RESULTS\n{numbered}")
    data = _json(_client().complete_json(COMPANY_SYSTEM, user, num_predict=4096, temperature=0.2))
    data["web"] = True
    data["sources"] = [{"n": i + 1, "title": r["title"], "url": r["url"]} for i, r in enumerate(results)]
    return data


# ---- role prep ----------------------------------------------------------------

PREP_SYSTEM = """You are an expert interview coach preparing a candidate for one specific interview.

Return ONLY JSON:
{
  "role_summary": "<2-3 sentences: what this role really does day to day and what they'll be judged on>",
  "focus_areas": [{"topic": "<skill/area to prepare>", "why": "<why it matters for THIS role, citing the JD>"}],
  "fit": {
    "strengths": ["<a requirement the candidate clearly meets, with the resume evidence>"],
    "gaps": [{"gap": "<requirement the resume doesn't show>", "how_to_prepare": "<concrete prep or how to address it honestly in the interview>"}]
  },
  "qa": [{"category": "Behavioral | Technical | Resume | Role | Company",
          "question": "<a question this interviewer is likely to ask>",
          "answer": "<a strong sample answer in the candidate's voice, 4-7 sentences, built ONLY from facts on their resume; where a specific is missing write a placeholder like [your metric]>",
          "tip": "<one line: what the interviewer is really checking>"}],
  "questions_to_ask": ["<a sharp question the candidate can ask the interviewer, specific to this company/role>"],
  "resources": [{"topic": "<focus area>", "title": "<resource name>", "url": "<https URL>", "why": "<what to study there>"}]
}

RULES
- Exactly {qa_count} Q&A items: about 5 Technical (from the JD's stack), 4 Behavioral, 3 Resume deep-dive,
  2 Role, 2 Company (only if company research is provided; otherwise more Technical).
- 5-7 focus areas, 5 questions to ask, 6-10 resources.
- Resources: ONLY official documentation, official tutorials or long-established learning sites
  (react.dev, docs.python.org, developer.mozilla.org, learn.microsoft.com, docs.aws.amazon.com, postgresql.org/docs,
  roadmap.sh, freecodecamp.org, leetcode.com, neetcode.io, the company's own engineering blog from the research…).
  Prefer section/landing URLs you are certain exist over deep links you might be guessing."""


def build_prep(company: str, title: str, description: str, research: dict) -> dict:
    research_txt = json.dumps({k: v for k, v in research.items() if k not in ("sources", "web")}, ensure_ascii=False)
    user = (f"ROLE: {title or 'Software Engineer'}\nCOMPANY: {company or '(not specified)'}\n\n"
            f"JOB DESCRIPTION\n{(description or '(none given — assume a typical description for the role)')[:6000]}\n\n"
            f"CANDIDATE RESUME\n{_resume() or '(no resume on file)'}\n\n"
            f"COMPANY RESEARCH\n{research_txt if research.get('web') else '(none)'}")
    system = PREP_SYSTEM.replace("{qa_count}", str(QA_COUNT))
    return _json(_client().complete_json(system, user, num_predict=12000, temperature=0.4))


def _link_ok(url: str) -> bool:
    """Drops links that are clearly dead. Bot-blocking statuses (403/405/429) count as alive."""
    if not url.startswith("https://"):
        return False
    try:
        r = requests.head(url, allow_redirects=True, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 405:
            r = requests.get(url, allow_redirects=True, timeout=6, stream=True, headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code < 400 or r.status_code in (403, 429)
    except requests.RequestException:
        return False


def generate(company: str, title: str, description: str) -> dict:
    """The full guide. Raises if the prep step fails; company research failing
    only downgrades that section."""
    research = {"web": False, "sources": []}
    if company:
        try:
            research = research_company(company, title, description)
        except Exception as e:
            logging.warning("company research failed: %s", e)
    prep = build_prep(company, title, description, research)
    resources = [r for r in prep.get("resources") or [] if isinstance(r, dict) and r.get("url")]
    with ThreadPoolExecutor(8) as pool:
        alive = list(pool.map(lambda r: _link_ok(r["url"]), resources))
    prep["resources"] = [r for r, ok in zip(resources, alive) if ok]
    return {"company_info": research, **prep}
