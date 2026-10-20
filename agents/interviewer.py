"""Voice mock-interviewer.

Four kinds share one loop:
  general     first-round screen: background, experience, technical
  behavioral  "tell me about a time…" per competency, probed for STAR
  resume      technical deep-dive on the candidate's own projects/roles
  technical   tech-stack questions on chosen topics (React, SQL…), some with
              a code snippet shown on screen

At session start `plan_questions` picks the main questions. Each turn the
interviewer either asks ONE follow-up on the current main question (max
MAX_FOLLOWUPS) or moves to the next; after the last it closes. That control
flow lives here in code, the model only words the turn. Every answer is scored
separately by `evaluate`, never read aloud.

Replies are spoken by TTS, so prompts forbid markdown/lists.
"""
import json
import logging
import re

import config
from agents import tech_bank
from config import CONFIG
from llm.client import make_client

MAX_FOLLOWUPS = 2
PLAN_SIZE = {"short": 3, "standard": 5, "long": 8}

_SPOKEN = """YOUR WORDS ARE SPOKEN ALOUD BY TEXT-TO-SPEECH
- Plain conversational sentences only: no markdown, bullet points, numbered lists, headings,
  emojis, code blocks or URLs.
- Keep each turn under 60 words. Ask exactly ONE question per turn.
- Never grade, praise effusively or coach during the interview, and never comment on how good
  an answer was ("that was a bit general"); just ask the follow-up. A few neutral words of
  acknowledgement are enough. If asked to repeat or clarify, do so plainly."""

_OUTPUT = """OUTPUT: return ONLY a JSON object:
{{"reply": "<what you say next>", "action": "follow_up" | "next" | "close"}}"""

DEFAULT_INTERVIEWER = """You are {interviewer_name}, an experienced interviewer running a live, spoken first-round
screen for {title} at {company}.
STYLE: {persona}
CANDIDATE: {candidate_name}

HOW YOU INTERVIEW
- Mix background and motivation, past experience (ask for specific situations) and technical
  questions grounded in the candidate's resume and the job description.
- If an answer is vague, generic or skips the outcome, follow up on the weakest part.

""" + _SPOKEN + """

JOB DESCRIPTION
{job_description}

CANDIDATE RESUME
{resume}

""" + _OUTPUT

DEFAULT_BEHAVIORAL = """You are {interviewer_name}, a hiring manager running a live, spoken behavioral interview
for {title} at {company}.
STYLE: {persona}
CANDIDATE: {candidate_name}

HOW YOU INTERVIEW
- Each main question targets one competency and asks for ONE specific past situation.
- Listen for STAR: Situation, Task, Action (what THEY personally did), Result (ideally measurable).
- Follow up on the weakest part when the answer is hypothetical ("I would…"), generic, says only
  "we", skips their own actions, or has no result. Typical follow-ups: "What did you personally
  do?", "What was the outcome, in numbers if you have them?", "What would you do differently?"
- A complete, specific STAR answer needs no follow-up: move on.

""" + _SPOKEN + """

JOB DESCRIPTION
{job_description}

CANDIDATE RESUME
{resume}

""" + _OUTPUT

DEFAULT_RESUME = """You are {interviewer_name}, a senior engineer running a live, spoken technical deep-dive on the
candidate's own resume, for {title} at {company}.
STYLE: {persona}
CANDIDATE: {candidate_name}

HOW YOU INTERVIEW
- Each main question opens one project or role from the resume. Go deep, the way a real
  hiring-panel engineer does: architecture and why it was built that way, alternatives considered,
  trade-offs, what broke in production, how it scales, what they'd change, and their exact
  personal contribution.
- Follow-ups drill one level deeper each time: from what, to why, to what-if. When the candidate
  states a metric or a technology choice, probe it ("How did you measure that?", "Why Kafka and
  not a simple queue?").
- If an answer is shallow or technically wrong, press once, politely. Never give the answer or
  lecture.

""" + _SPOKEN + """

CANDIDATE RESUME
{resume}

CANDIDATE PROJECTS
{projects}

JOB DESCRIPTION
{job_description}

""" + _OUTPUT

DEFAULT_TECHNICAL = """You are {interviewer_name}, a senior engineer running a live, spoken technical interview
for {title} at {company}, on these topics: {topics}.
LEVEL: {difficulty}
STYLE: {persona}
CANDIDATE: {candidate_name}

HOW YOU INTERVIEW
- Questions are specific to each technology: how it works under the hood, common pitfalls, debugging,
  performance, and real-world trade-offs. Not trivia, not definitions for their own sake.
- Some questions come with a code snippet that is SHOWN ON THE CANDIDATE'S SCREEN. Refer to it as
  "the code on your screen". Never read code, symbols or syntax aloud.
- If an answer is wrong, vague or misses a key concept, ask ONE narrower follow-up that gives them a
  chance to get there. Never correct them, hint at the right answer or say "actually"; real
  interviewers stay neutral and just probe. If it's solid, you may go one level deeper ("what if…",
  "how would that change at scale?") or move on.
- Keep difficulty at the stated level.

""" + _SPOKEN + """

CANDIDATE RESUME (for context only — the questions are about the topics)
{resume}

""" + _OUTPUT

KINDS = {
    "general": {"prompt_key": "interviewer", "default": DEFAULT_INTERVIEWER, "label": "General screen"},
    "behavioral": {"prompt_key": "interviewer_behavioral", "default": DEFAULT_BEHAVIORAL, "label": "Behavioral"},
    "resume": {"prompt_key": "interviewer_resume", "default": DEFAULT_RESUME, "label": "Resume deep-dive"},
    "technical": {"prompt_key": "interviewer_technical", "default": DEFAULT_TECHNICAL, "label": "Tech stack"},
}

DIFFICULTY = {
    "junior": "junior (0-2 years): fundamentals and correct usage; gentle follow-ups",
    "mid": "mid-level (2-5 years): internals, debugging and trade-offs in real projects",
    "senior": "senior (5+ years): deep internals, performance at scale, architecture and edge cases",
}

PERSONAS = {
    "friendly": "warm and encouraging, but still expects concrete answers",
    "neutral": "professional and neutral, like a typical big-tech interviewer",
    "tough": "direct and skeptical; pushes back on hand-wavy answers and asks for specifics",
}


# ---- context ----------------------------------------------------------------

def _load(path_key: str, default: str) -> str:
    try:
        return config.load_text_file(CONFIG.get("pipeline", {}).get(path_key, default))
    except FileNotFoundError:
        return ""


def _render(tmpl: str, values: dict) -> str:
    # str.replace per token, so a user-edited prompt with stray braces can't raise
    out = tmpl.replace("{{", "\x00").replace("}}", "\x01")
    for k, v in values.items():
        out = out.replace("{" + k + "}", str(v))
    return out.replace("\x00", "{").replace("\x01", "}")


def _values(session: dict) -> dict:
    cfg, ctx = session["config"], session["context"]
    return {
        "interviewer_name": cfg.get("interviewer_name") or "Alex",
        "title": ctx.get("title") or cfg.get("role") or "Software Engineer",
        "company": ctx.get("company") or cfg.get("company") or "a tech company",
        "persona": PERSONAS.get(cfg.get("persona", "neutral"), PERSONAS["neutral"]),
        "candidate_name": CONFIG.get("profile", {}).get("full_name") or "the candidate",
        "job_description": (ctx.get("description") or "(none given — assume a typical description for the role)")[:6000],
        # the resume built for the linked job, else the base resume.txt
        "resume": (ctx.get("resume") or _load("resume_path", "resume.txt") or "(no resume on file)")[:8000],
        "projects": (_load("projects_path", "projects.txt") or "(none)")[:6000],
        "topics": ", ".join(cfg.get("topics") or []) or "the role's core stack",
        "difficulty": DIFFICULTY.get(cfg.get("difficulty", "mid"), DIFFICULTY["mid"]),
    }


def system_prompt(session: dict) -> str:
    kind = KINDS.get(session.get("kind"), KINDS["general"])
    return _render(config.get_prompt(kind["prompt_key"], kind["default"]), _values(session))


def _client():
    return make_client(CONFIG["model"]["pipeline"], "interview")


def _json(raw: str) -> dict | None:
    txt = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt)
    if m:
        txt = m.group(1)
    start, end = txt.find("{"), txt.rfind("}")
    try:
        data = json.loads(txt[start:end + 1])
    except ValueError:
        try:   # some replies wrap the object in a list
            data = json.loads(txt[txt.find("["):txt.rfind("]") + 1])[0]
        except (ValueError, IndexError, KeyError):
            return None
    return data if isinstance(data, dict) else None


# ---- planning -----------------------------------------------------------------

_PLAN_GUIDE = {
    "general": "A first-round screen. Question 1 is background/motivation (\"walk me through your "
               "background and why this role\"). The rest mix past-experience questions and technical "
               "questions grounded in the resume and the job description.",
    "behavioral": "Pick {n} DIFFERENT competencies most relevant to this job — e.g. conflict, failure, "
                  "ownership, ambiguity, prioritization, influencing without authority, tight deadline, "
                  "customer focus, learning something fast, leadership, giving/receiving feedback. One "
                  "\"Tell me about a time…\" question per competency. topic = the competency.",
    "resume": "Pick {n} DISTINCT, substantial items from the resume/projects — the projects, roles, "
              "metrics and technology choices an interviewer would most want to probe for this job. Each "
              "question names the item and opens a deep dive (\"Walk me through how you built X…\"). "
              "topic = the project or role name.",
    "technical": "Spread the {n} questions across these topics, in this order, round-robin: {topics}. topic = "
                 "the technology name exactly as given. Vary the style: conceptual \"how does it work under the "
                 "hood\", practical scenarios (debugging, performance), and, for roughly every second or third "
                 "question where it fits, a short code snippet (max ~12 lines) with \"what does this print\" or "
                 "\"what is wrong here\". Put the snippet in \"code\" and its language in \"language\"; the "
                 "question text must not contain code. Match the level: {difficulty}.",
}

_FALLBACK = {
    "general": ["Walk me through your background and what draws you to this role.",
                "Tell me about the project you're most proud of and your part in it.",
                "Describe a hard technical problem you solved recently. How did you approach it?",
                "Tell me about a time you had to learn a new technology quickly.",
                "How do you make sure the code you ship is reliable?",
                "Tell me about a time you disagreed with a teammate on a technical decision.",
                "What's a design decision you made that you'd change today, and why?",
                "Where do you want to grow in your next role?"],
    "behavioral": ["Tell me about a time you disagreed with a teammate. How did you resolve it?",
                   "Tell me about a time you failed. What happened and what did you learn?",
                   "Tell me about a time you took ownership of something outside your responsibilities.",
                   "Tell me about a time you had to deliver under a tight deadline.",
                   "Tell me about a time you had to make a decision with incomplete information.",
                   "Tell me about a time you influenced a decision without having authority.",
                   "Tell me about a time you received critical feedback. What did you do with it?",
                   "Tell me about a time you had to juggle competing priorities."],
    "resume": ["Walk me through the most technically challenging project on your resume.",
               "Pick a system you built and explain its architecture end to end.",
               "Tell me about a technology choice on your resume. Why that over the alternatives?",
               "Tell me about a production issue in one of your projects and how you fixed it.",
               "Which result on your resume are you proudest of, and how did you measure it?",
               "If you rebuilt one of your projects today, what would you change?",
               "Walk me through your exact contribution on a team project from your resume.",
               "How would one of your projects need to change to handle ten times the load?"],
}


def _technical_fallback(topics: list[str], n: int) -> list[dict]:
    """Round-robin over the topics: bank questions first, then a generic one."""
    pools = {t: list(tech_bank.seeds(t)) for t in topics}
    out, i = [], 0
    while len(out) < n:
        t = topics[i % len(topics)]
        q = pools[t].pop(0) if pools[t] else {
            "question": f"Explain how {t} works under the hood, and a problem you'd expect to hit using it in production."}
        out.append({"topic": t, **q})
        i += 1
    return out


def plan_questions(session: dict) -> list[dict]:
    """[{topic, question, code?, language?}] — the main questions, in order.
    Falls back to a static bank if the model fails, so a session can always start."""
    kind = session.get("kind") if session.get("kind") in KINDS else "general"
    n = PLAN_SIZE.get(session["config"].get("length", "standard"), 5)
    topics = [t for t in (session["config"].get("topics") or []) if t.strip()] or ["the role's core stack"]
    v = _values(session)
    system = ("You plan a realistic mock interview. Return ONLY JSON: "
              '{"questions": [{"topic": "<2-4 word label>", "question": "<the main question, as spoken>"'
              + (', "code": "<optional snippet>", "language": "<snippet language>"' if kind == "technical" else "")
              + "}]}")
    guide = (_PLAN_GUIDE[kind].replace("{n}", str(n)).replace("{topics}", ", ".join(topics))
             .replace("{difficulty}", v["difficulty"]))
    examples = ""
    if kind == "technical":
        bank = [f"[{t}] {q['question']}" + (f"\n{q['code']}" if q.get("code") else "")
                for t in topics for q in tech_bank.seeds(t)]
        if bank:
            examples = ("EXAMPLES OF THE DEPTH WANTED. Use AT MOST ONE of them (reworded); write every other "
                        "question fresh, on a different aspect of the topic:\n" + "\n".join(bank) + "\n\n")
    user = (f"KIND: {KINDS[kind]['label']}\nNUMBER OF MAIN QUESTIONS: {n}\nROLE: {v['title']} at {v['company']}\n\n"
            f"GUIDANCE: {guide}\n"
            "Questions are spoken aloud: one sentence or two, no lists. Don't number them.\n\n"
            f"{examples}JOB DESCRIPTION\n{v['job_description']}\n\nRESUME\n{v['resume']}\n\nPROJECTS\n{v['projects']}")
    try:
        data = _json(_client().complete_json(system, user, num_predict=4096, temperature=0.8)) or {}
        qs = []
        for q in data.get("questions", []):
            if not isinstance(q, dict) or not q.get("question"):
                continue
            item = {"topic": str(q.get("topic", "")).strip()[:40], "question": str(q["question"]).strip()}
            if kind == "technical" and str(q.get("code") or "").strip():
                item["code"] = str(q["code"]).strip("\n")
                item["language"] = str(q.get("language") or "").strip().lower()
            qs.append(item)
        if qs:
            return qs[:n]
    except Exception as e:
        logging.warning("interview planning failed, using the fallback bank: %s", e)
    if kind == "technical":
        return _technical_fallback(topics, n)
    return [{"topic": "", "question": q} for q in _FALLBACK[kind][:n]]

# ---- turns ------------------------------------------------------------------

def _transcript(turns: list[dict]) -> str:
    who = {"interviewer": "INTERVIEWER", "candidate": "CANDIDATE"}
    return "\n".join(f"{who[t['speaker']]}: {t['text']}" for t in turns) or "(nothing yet)"


def _code_note(q: dict) -> str:
    if not q.get("code"):
        return ""
    return (" [a code snippet is shown on the candidate's screen; say \"take a look at the code on your screen\" "
            f"and never read it aloud:\n{q['code']}\n]")


def position(turns: list[dict]) -> tuple[int, int]:
    """(index of the current main question, follow-ups asked on it so far)."""
    for t in reversed(turns):
        if t["speaker"] == "interviewer" and "qi" in (t.get("meta") or {}):
            return t["meta"]["qi"], t["meta"].get("followups", 0)
    return -1, 0


def next_turn(session: dict) -> dict:
    """The interviewer's next line. Returns {reply, done, meta}; meta records
    which planned question it belongs to and whether it's a follow-up."""
    plan = session["context"].get("plan") or [{"topic": "", "question": q} for q in _FALLBACK["general"][:5]]
    turns = session["turns"]
    qi, fu = position(turns)
    last_skipped = bool(turns) and (turns[-1].get("meta") or {}).get("skipped")

    if qi < 0:
        allowed = {"next"}
        step = (f"Start the interview: greet the candidate by first name, introduce yourself in one sentence, "
                f"then ask main question 1 of {len(plan)}: \"{plan[0]['question']}\"{_code_note(plan[0])}. "
                "Use action \"next\".")
    else:
        cur = plan[min(qi, len(plan) - 1)]
        has_next = qi + 1 < len(plan)
        can_follow = fu < MAX_FOLLOWUPS and not last_skipped
        allowed = ({"follow_up"} if can_follow else set()) | ({"next"} if has_next else {"close"})
        opts = []
        if can_follow:
            opts.append('"follow_up": the last answer needs probing — ask ONE neutral follow-up on it. Do not '
                        'correct the candidate, state the right answer or start with "actually".')
        if has_next:
            nxt = plan[qi + 1]
            opts.append(f'"next": acknowledge briefly, then ask main question {qi + 2} of {len(plan)}'
                        f'{" (" + nxt["topic"] + ")" if nxt["topic"] else ""}: "{nxt["question"]}"{_code_note(nxt)} '
                        "— rephrase it naturally; you may tie it to something they said.")
        else:
            opts.append('"close": that was the last question. Thank them and say what happens next. Ask nothing.')
        step = (f"Current main question {qi + 1} of {len(plan)}"
                f"{' (' + cur['topic'] + ')' if cur['topic'] else ''}: \"{cur['question']}\"{_code_note(cur)}. "
                f"Follow-ups already asked on it: {fu} of {MAX_FOLLOWUPS}.\n"
                + ("The candidate chose to skip it — do not follow up.\n" if last_skipped else "")
                + "Choose exactly one action:\n- " + "\n- ".join(opts))

    user = f"TRANSCRIPT SO FAR\n{_transcript(turns)}\n\nNEXT STEP\n{step}"
    system = system_prompt(session)
    client = _client()
    out = None
    for _ in range(2):   # one retry if the model picks an action that isn't on offer
        raw = client.complete_json(system, user, num_predict=1024, temperature=0.7)
        data = _json(raw) or {}
        reply = str(data.get("reply", "")).strip() or re.sub(r"[*#`>_]", "", raw).strip()
        action = "close" if data.get("done") is True else str(data.get("action", "")).strip()
        out = (reply, action)
        if action in allowed:
            break
    reply, action = out
    if action not in allowed:   # still off-script: keep the words, force the bookkeeping
        action = "follow_up" if "follow_up" in allowed else ("next" if "next" in allowed else "close")

    if action == "follow_up":
        # ponytail: small models still open follow-ups with "Actually, <the right answer>." despite the
        # prompt; drop that sentence. Remove once the interviewer model obeys reliably.
        m = re.match(r"\s*actually\b[^.?!]*[.!]\s+(?=\S)", reply, re.IGNORECASE)
        if m:
            reply = reply[m.end():]
        meta = {"qi": qi, "followups": fu + 1, "topic": plan[qi]["topic"], "followup": True}
    elif action == "next":
        meta = {"qi": qi + 1, "followups": 0, "topic": plan[qi + 1]["topic"], "followup": False}
    else:
        meta = {"qi": qi, "followups": fu, "closing": True}
    return {"reply": reply, "done": action == "close", "meta": meta}


# ---- scoring ----------------------------------------------------------------

_RUBRIC = {
    "general": ('"criteria": {"relevance": 1-5, "specificity": 1-5, "clarity": 1-5, "structure": 1-5}',
                "relevance to the question and role, concrete specifics over generalities, clarity, "
                "a logical structure"),
    "behavioral": ('"star": {"situation": true|false, "task": true|false, "action": true|false, "result": true|false},\n'
                   ' "criteria": {"specificity": 1-5, "ownership": 1-5, "impact": 1-5, "relevance": 1-5}',
                   "STAR completeness across the whole exchange on this question; a real, specific past "
                   "situation (hypotheticals score low); personal ownership (\"I\" not just \"we\"); a "
                   "clear, ideally measurable result; fit to the competency asked"),
    "technical": ('"criteria": {"correctness": 1-5, "depth": 1-5, "practical": 1-5, "clarity": 1-5},\n'
                  ' "missed_concepts": ["<key concepts a strong answer would have covered but this one did not>"]',
                  "technical correctness, depth beyond the surface (how it works, why), practical "
                  "experience (real pitfalls, debugging, trade-offs) and clear explanation, at the stated level"),
    "resume": ('"criteria": {"depth": 1-5, "accuracy": 1-5, "tradeoffs": 1-5, "clarity": 1-5}',
               "technical depth beyond surface description, technical correctness, awareness of "
               "alternatives and trade-offs, clear explanation of their own contribution"),
}


def evaluate(session: dict, turn_id: int) -> dict | None:
    """Scores one candidate answer in the context of its main question and any
    follow-ups. Returns the eval dict, or None if the turn is gone/skipped."""
    turns = session["turns"]
    idx = next((i for i, t in enumerate(turns) if t["id"] == turn_id), None)
    if idx is None or turns[idx]["speaker"] != "candidate" or (turns[idx].get("meta") or {}).get("skipped"):
        return None
    # the exchange on this main question: back to the interviewer turn that opened it
    qi, _ = position(turns[:idx])
    start = next((i for i, t in enumerate(turns[:idx])
                  if t["speaker"] == "interviewer" and (t.get("meta") or {}).get("qi") == qi), max(0, idx - 1))
    exchange = _transcript(turns[start:idx + 1])
    plan = session["context"].get("plan") or []
    planned = plan[qi] if 0 <= qi < len(plan) else {}
    if planned.get("code"):
        exchange = f"CODE SHOWN TO THE CANDIDATE\n{planned['code']}\n\n{exchange}"
    kind = session.get("kind") if session.get("kind") in KINDS else "general"
    fields, what = _RUBRIC[kind]
    v = _values(session)
    system = (f"You are an expert interview coach scoring ONE answer from a {KINDS[kind]['label'].lower()} "
              f"mock interview for {v['title']} at {v['company']}"
              + (f" (level: {v['difficulty']})" if kind == "technical" else "")
              + f". Judge: {what}. Be honest and calibrated: "
              "5/10 is an average real candidate, 8+ is genuinely strong. Score the LAST candidate answer, "
              "using the earlier lines only as context.\n"
              "Return ONLY JSON:\n"
              '{"score": 1-10,\n ' + fields + ',\n'
              ' "strengths": ["<max 2 short points>"],\n'
              ' "improvements": ["<max 3 short, specific, actionable points>"],\n'
              ' "better_answer": "<2-4 sentences showing how a strong candidate would have answered. Build on '
              'facts from their resume; never invent specifics that are not there — use a placeholder like '
              '[your metric] instead. Aim it at the job description\'s responsibilities: even a generic question '
              '(a challenging problem, a conflict) gets the resume story closest to this role\'s work, told in '
              'the JD\'s terms>"}')
    user = (f"EXCHANGE\n{exchange}\n\nJOB DESCRIPTION (for context)\n{v['job_description'][:3000]}\n\n"
            f"CANDIDATE RESUME (for context)\n{v['resume'][:4000]}")
    client = _client()
    for attempt in range(2):   # the model occasionally returns malformed JSON; one retry fixes it
        raw = client.complete_json(system, user, num_predict=2048, temperature=0.2)
        data = _json(raw)
        if data and "score" in data:
            break
        logging.warning("evaluator reply unparseable (attempt %d): %.300s", attempt + 1, raw)
    else:
        raise RuntimeError("evaluator returned no score")
    try:
        data["score"] = max(1, min(10, round(float(data["score"]))))
    except (TypeError, ValueError):
        raise RuntimeError(f"evaluator returned a bad score: {data.get('score')!r}")
    return data
