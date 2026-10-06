"""JSON writers: model JSON -> valid LaTeX, with a retry when the model replies badly.
Run: python test_json_writers.py"""
from agents import experience_writer, project_writer, skills_writer


class Flaky:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def complete(self, system, user, **kw):
        self.calls += 1
        return self.replies.pop(0)


def test_skills_retries_bad_json_and_escapes():
    good = '```json\n{"categories": [{"name": "AI & ML", "items": ["RAG", "C++"]}]}\n```'
    c = Flaky(["sorry, here you go", good])            # first reply is not JSON -> retried
    out = skills_writer.write(c, "T", "C", "jd", "resume")
    assert c.calls == 2 and r"\textbf{AI \& ML}{: RAG, C++}" in out


def test_projects_bold_escape_and_link():
    proj = '{"projects": [{"name": "RagGpt", "tech": ["Python"], "bullets": ["Cut review time 80% with **RAG** & Chroma"]}]}'
    out = project_writer.write(Flaky([proj]), "T", "C", "jd", "resume",
                               "RagGpt | Python | https://github.com/a/RagGpt")
    assert r"\resumeItem{Cut review time 80\% with \textbf{RAG} \& Chroma}" in out
    assert r"\href{https://github.com/a/RagGpt}{\faGithub" in out


def test_experience_locks_title_company_dates():
    reply = ('{"roles": [{"title": "Rockstar", "company": "Wrong Co", "dates": "1999", "location": "Halifax, NS",'
             ' "bullets": ["Built **RAG** over 1,200 docs"]}]}')
    roles = [{"title": "System Analyst", "company": "NSHA", "dates": "Feb 2026 – Present"}]
    out = experience_writer.write(Flaky([reply]), "T", "C", "jd", "resume", roles)
    assert r"\resumeSubheading{System Analyst}{Feb 2026 -- Present}{NSHA}{Halifax, NS}" in out


def test_gives_up_after_three_bad_replies():
    try:
        skills_writer.write(Flaky(["nope"] * 3), "T", "C", "jd", "resume")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
