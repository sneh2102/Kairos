"""Interview prep: plan/follow-up/close control flow and answer scoring with a
fake LLM, plus a real speech round trip (Kokoro -> Whisper) when the models
are downloaded.
Run: python test_interview.py"""
import json
import tempfile

from agents import interviewer
from db.manager import InterviewDB


class FakeLLM:
    """Always wants to follow up — the code must cap it and still move on."""

    def __init__(self, reply=None):
        self.users, self.systems = [], []
        self.reply = reply

    def complete_json(self, system, user, **kw):
        self.systems.append(system)
        self.users.append(user)
        if self.reply is not None:
            return self.reply
        return '```json\n{"reply": "Turn %d?", "action": "follow_up"}\n```' % len(self.users)


def _session(db, kind="behavioral", plan_len=2):
    sid = db.create_session(kind, "SWE @ Acme", {"length": "short"}, {"title": "SWE", "company": "Acme"})
    ctx = {"title": "SWE", "company": "Acme",
           "plan": [{"topic": f"T{i}", "question": f"Main question {i}?"} for i in range(plan_len)]}
    db.update_context(sid, ctx)
    return sid


def _say(db, sid, out):
    db.add_turn(sid, "interviewer", out["reply"], meta=out["meta"])


def test_followups_capped_then_next_then_close():
    fake = FakeLLM()
    interviewer.make_client = lambda *a, **k: fake
    db = InterviewDB(tempfile.mktemp(suffix=".db"))
    sid = _session(db)

    out = interviewer.next_turn(db.get_session(sid))   # opener: only "next" allowed -> forced
    assert out["meta"] == {"qi": 0, "followups": 0, "topic": "T0", "followup": False} and not out["done"]
    assert "Main question 0?" in fake.users[-1]
    _say(db, sid, out)

    for n in (1, 2):   # two follow-ups on question 0 are allowed
        db.add_turn(sid, "candidate", "answer")
        out = interviewer.next_turn(db.get_session(sid))
        assert out["meta"]["qi"] == 0 and out["meta"]["followups"] == n and out["meta"]["followup"]
        _say(db, sid, out)

    db.add_turn(sid, "candidate", "answer")
    out = interviewer.next_turn(db.get_session(sid))   # cap reached: follow_up not offered, forced to next
    assert '"follow_up"' not in fake.users[-1].split("Choose exactly one action")[1]
    assert out["meta"]["qi"] == 1 and not out["meta"]["followup"]
    _say(db, sid, out)

    db.add_turn(sid, "candidate", "(skipped this question)", meta={"skipped": True})
    out = interviewer.next_turn(db.get_session(sid))   # skipped last question: no follow-up -> close
    assert out["done"] and out["meta"]["closing"]
    assert "chose to skip" in fake.users[-1]


def test_followup_drops_correcting_actually_sentence():
    fake = FakeLLM('{"reply": "Actually, React diffs a virtual DOM. How does batching work?", "action": "follow_up"}')
    interviewer.make_client = lambda *a, **k: fake
    db = InterviewDB(tempfile.mktemp(suffix=".db"))
    sid = _session(db, "technical")
    db.add_turn(sid, "interviewer", "Q0", meta={"qi": 0, "followups": 0})
    db.add_turn(sid, "candidate", "wrong answer")
    assert interviewer.next_turn(db.get_session(sid))["reply"] == "How does batching work?"


def test_plan_falls_back_when_model_fails():
    class Broken:
        def complete_json(self, *a, **k):
            raise RuntimeError("down")
    interviewer.make_client = lambda *a, **k: Broken()
    plan = interviewer.plan_questions({"kind": "resume", "config": {"length": "standard"}, "context": {}})
    assert len(plan) == 5 and all(q["question"] for q in plan)


def test_plan_parses_model_output():
    reply = json.dumps({"questions": [{"topic": "Conflict", "question": "Tell me about a disagreement."},
                                      {"topic": "x", "question": ""}]})
    interviewer.make_client = lambda *a, **k: FakeLLM(reply)
    plan = interviewer.plan_questions({"kind": "behavioral", "config": {"length": "short"}, "context": {}})
    assert plan == [{"topic": "Conflict", "question": "Tell me about a disagreement."}]


def test_evaluate_scores_whole_exchange_and_clamps():
    fake = FakeLLM('{"score": 14, "star": {"situation": true}, "strengths": [], "improvements": ["x"]}')
    interviewer.make_client = lambda *a, **k: fake
    db = InterviewDB(tempfile.mktemp(suffix=".db"))
    sid = _session(db)
    db.add_turn(sid, "interviewer", "Main question 0?", meta={"qi": 0, "followups": 0})
    db.add_turn(sid, "candidate", "first answer")
    db.add_turn(sid, "interviewer", "Follow-up?", meta={"qi": 0, "followups": 1, "followup": True})
    last = db.add_turn(sid, "candidate", "second answer")
    ev = interviewer.evaluate(db.get_session(sid), last["id"])
    assert ev["score"] == 10
    assert "Main question 0?" in fake.users[-1] and "second answer" in fake.users[-1]
    assert "STAR" in fake.systems[-1]
    skipped = db.add_turn(sid, "candidate", "(skipped)", meta={"skipped": True})
    assert interviewer.evaluate(db.get_session(sid), skipped["id"]) is None


def test_technical_fallback_round_robins_bank_then_generic():
    class Broken:
        def complete_json(self, *a, **k):
            raise RuntimeError("down")
    interviewer.make_client = lambda *a, **k: Broken()
    plan = interviewer.plan_questions({"kind": "technical", "context": {},
                                       "config": {"length": "standard", "topics": ["ReactJS", "Elixir"]}})
    assert [q["topic"] for q in plan] == ["ReactJS", "Elixir", "ReactJS", "Elixir", "ReactJS"]
    assert plan[1]["question"].startswith("Explain how Elixir works")   # no bank -> generic
    assert any(q.get("code") for q in plan)                               # React bank has a snippet


def test_technical_plan_keeps_code_and_turn_mentions_it():
    reply = json.dumps({"questions": [
        {"topic": "Python", "question": "What does this print?", "code": "\nprint(1)\n", "language": "Python"},
        {"topic": "SQL", "question": "How do indexes work?"}]})
    fake = FakeLLM(reply)
    interviewer.make_client = lambda *a, **k: fake
    plan = interviewer.plan_questions({"kind": "technical", "context": {},
                                       "config": {"length": "short", "topics": ["Python", "SQL"]}})
    assert plan[0] == {"topic": "Python", "question": "What does this print?", "code": "print(1)", "language": "python"}
    assert "code" not in plan[1]
    assert "[Python] What does this print" in fake.users[-1] or "EXAMPLES" in fake.users[-1]

    fake.reply = '{"reply": "Hi, take a look at the code on your screen.", "action": "next"}'
    db = InterviewDB(tempfile.mktemp(suffix=".db"))
    sid = db.create_session("technical", "x", {"topics": ["Python", "SQL"]}, {"plan": plan})
    interviewer.next_turn(db.get_session(sid))
    assert "never read it aloud" in fake.users[-1] and "print(1)" in fake.users[-1]
    assert "Python, SQL" in fake.systems[-1]

    db.add_turn(sid, "interviewer", "q", meta={"qi": 0, "followups": 0})
    ans = db.add_turn(sid, "candidate", "it prints 1")
    fake.reply = '{"score": 7, "criteria": {"correctness": 4}, "missed_concepts": []}'
    interviewer.evaluate(db.get_session(sid), ans["id"])
    assert "CODE SHOWN TO THE CANDIDATE\nprint(1)" in fake.users[-1]


def test_prep_guide_cites_sources_and_drops_dead_links():
    from agents import prep_guide
    hits = [{"title": "Acme home", "url": "https://acme.com/", "content": "Acme makes rockets."},
            {"title": "Acme home dup", "url": "https://acme.com", "content": "dup"}]
    prep_guide.web_search = lambda q, n: hits
    replies = iter(['{"overview": "Acme makes rockets [1]."}',
                    '{"qa": [{"category": "Technical", "question": "Q?", "answer": "A."}], '
                    '"resources": [{"topic": "SQL", "title": "ok", "url": "https://good"}, '
                    '{"topic": "SQL", "title": "dead", "url": "https://dead"}]}'])

    class Fake:
        def complete_json(self, system, user, **kw):
            return next(replies)
    prep_guide.make_client = lambda *a, **k: Fake()
    prep_guide._link_ok = lambda url: url == "https://good"
    g = prep_guide.generate("Acme", "SWE", "jd")
    ci = g["company_info"]
    assert ci["web"] and ci["overview"].endswith("[1].")
    assert ci["sources"] == [{"n": 1, "title": "Acme home", "url": "https://acme.com/"}]   # duplicate URL merged
    assert [r["title"] for r in g["resources"]] == ["ok"]

    # no search results: company part is marked unverified, the rest still builds
    prep_guide.web_search = lambda q, n: []
    replies = iter(['{"qa": [], "resources": []}'])
    g = prep_guide.generate("Acme", "SWE", "jd")
    assert g["company_info"] == {"web": False, "sources": []} and g["qa"] == []


def test_prompt_render():
    for kind in interviewer.KINDS:
        sp = interviewer.system_prompt({"kind": kind, "config": {"persona": "tough"},
                                        "context": {"title": "Data Eng", "company": "X"}})
        assert "Data Eng at X" in sp and '"action"' in sp and "{title}" not in sp and "{{" not in sp


def test_speech_round_trip():
    from tools import speech
    if not (speech.kokoro_ready() and speech.whisper_ready(speech.settings()["whisper_model"])):
        print("  (speech models not downloaded, skipped)")
        return
    audio, mime = speech.synthesize("Walk me through your most recent project.", {"tts_engine": "kokoro"})
    text = speech.transcribe(audio, ".wav")["text"].lower()
    assert "recent project" in text, text


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
