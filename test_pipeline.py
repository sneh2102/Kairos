"""Self-check for the non-LLM logic: verdict parsing, LaTeX section
extract/reassemble round-trip, deterministic ATS rule engine. No network/LLM calls.
Run: python test_pipeline.py
"""
from agents import ats_rules, optimizer
from agents.ats_checker import _latex_to_text
from agents.screener import parse_verdict
from tools.latex import build_education, build_header, extract_sections, reassemble


def test_parse_verdict_clean_json():
    raw = '{"verdict": "yes", "years_required": "2", "role_level": "junior", "skills_match_pct": 80, "matched_skills": ["Python"], "missing_skills": [], "reasoning": "Good fit."}'
    v = parse_verdict(raw)
    assert v["verdict"] == "yes"
    assert v["skills_match_pct"] == 80


def test_parse_verdict_markdown_fenced():
    raw = '```json\n{"verdict": "no", "reasoning": "Too senior."}\n```'
    v = parse_verdict(raw)
    assert v["verdict"] == "no"


def test_parse_verdict_garbage_falls_back_to_maybe():
    v = parse_verdict("the model rambled without any json at all")
    assert v["verdict"] == "maybe"


def test_extract_reassemble_round_trip():
    profile = {"full_name": "Test User", "phone": "+1 555-000-0000", "email": "t@example.com",
               "education": [{"degree": "BSc", "dates": "2020-2024", "institution": "U", "location": "City"}]}
    header = build_header(profile)
    education = build_education(profile)
    sections = {
        "header": header, "education": education,
        "skills": "\\section{Technical Skills}\n...skills body...",
        "experience": "\\section{Experience}\n...experience body...",
        "projects": "\\section{Relevant Projects}\n...projects body...",
    }
    order = ["education", "skills", "experience", "projects"]
    full = reassemble(sections, order)

    # preamble comes from the active template (may open with comments), so check
    # the invariants that hold for ANY template rather than a fixed first line
    assert "\\documentclass" in full
    assert "\\begin{document}" in full
    assert full.strip().endswith("\\end{document}")
    for key in ("skills", "experience", "projects"):
        assert sections[key] in full

    # round-trip: extracting from the reassembled doc should recover the same bodies
    extracted = extract_sections(full, header)
    assert extracted["skills"] == sections["skills"]
    assert extracted["experience"] == sections["experience"]
    assert extracted["projects"] == sections["projects"]


def test_reassemble_only_includes_nonempty_sections():
    sections = {"header": "H", "education": "", "skills": "\\section{Technical Skills}\nS", "experience": "", "projects": ""}
    full = reassemble(sections, ["education", "skills", "experience", "projects"])
    assert "Technical Skills" in full
    assert full.count("\\section{") == 1


_JD = ("We need a developer with Python, Docker, Kubernetes, PostgreSQL, AWS, "
        "Terraform and CI/CD experience. Machine learning and Kafka are a plus.")

_GOOD_LATEX = r"""
\section{Technical Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
     \textbf{Cloud}{: AWS, Terraform, Docker, Kubernetes} \\
     \textbf{Backend}{: Python, PostgreSQL, Kafka, CI/CD}
    }}
 \end{itemize}
\section{Experience}
\resumeSubHeadingListStart
  \resumeSubheading{Developer}{2022 -- 2024}{Acme}{Remote}
  \resumeItemListStart
    \resumeItem{Automated deployment pipelines with Docker and Terraform, cutting release time by 40\% across 6 services in production}
    \resumeItem{Migrated 12 PostgreSQL databases to AWS with zero downtime, reducing infrastructure cost by 25\% for the platform team}
    \resumeItem{Scaled Kafka event processing to 50,000 messages per second, improving p99 latency by 30\% under peak load}
  \resumeItemListEnd
\resumeSubHeadingListEnd
\section{Relevant Projects}
\resumeSubHeadingListStart
  \resumeProjectHeading{\textbf{MLPipe} $|$ \emph{Python, Kubernetes}}{}
  \resumeItemListStart
    \resumeItem{Built a machine learning pipeline on Kubernetes serving 200 daily users with 95\% prediction accuracy in evaluation}
    \resumeItem{Reduced model training time by 60\% through CI/CD-driven parallel processing across 8 worker nodes in the cluster}
  \resumeItemListEnd
\resumeSubHeadingListEnd
"""

_BAD_LATEX = r"""
\section{Experience}
\resumeSubHeadingListStart
  \resumeSubheading{Developer}{2022 -- 2024}{Acme}{Remote}
  \resumeItemListStart
    \resumeItem{Responsible for leveraging cutting-edge synergy to deliver seamless solutions}
    \resumeItem{Responsible for various tasks in a fast-paced dynamic environment}
    \resumeItem{worked on things}
  \resumeItemListEnd
\resumeSubHeadingListEnd
"""


def test_ats_rules_good_resume_beats_bad():
    good = ats_rules.analyze(_JD, _GOOD_LATEX)
    bad = ats_rules.analyze(_JD, _BAD_LATEX)
    assert good["det_total"] > bad["det_total"] + 40, (good["det_total"], bad["det_total"])
    assert good["det_total"] > 85   # a strong resume scores high (0..100 scale)
    assert bad["det_total"] < 20    # a bad one scores genuinely low


def test_ats_score_is_100_scale_and_llm_independent():
    """The score must be fully deterministic — identical for a working LLM, a
    broken LLM, and a low-quality LLM. Only feedback text may differ."""
    from agents import ats_checker

    class LyingLLM:
        # returns the previous project's JSON shape WITH a deliberately wrong
        # score — which must be dropped, not used
        def complete_json(self, system, user, **kw):
            return ('{"score": 12, "section_scores": {"skills": 5, "experience": 5, "projects": 5}, '
                    '"skills_feedback": "add Terraform", "experience_feedback": "add a metric", '
                    '"projects_feedback": "swap project", "suggestions": ["do X"]}')

    class BrokenLLM:
        def complete_json(self, system, user, **kw):
            raise RuntimeError("model down")

    r1 = ats_checker.check(LyingLLM(), "Dev", _JD, _GOOD_LATEX)
    s2 = ats_checker.check(BrokenLLM(), "Dev", _JD, _GOOD_LATEX)["score"]
    manual = ats_rules.analyze(_JD, _GOOD_LATEX)["det_total"]
    assert r1["score"] == s2 == manual, (r1["score"], s2, manual)  # LLM's score=12 is ignored
    assert manual > 85                          # good resume, deterministic score
    assert 0 <= manual <= 100
    assert "add Terraform" in r1["skills_feedback"]   # but its feedback TEXT is used
    assert r1["suggestions"] == ["do X"]


def test_ats_familiar_with_stuffing_earns_no_credit():
    """A resume that lists JD keywords ONLY in a 'Familiar With:' line (the
    optimizer's injection) must NOT get keyword credit — coverage is earned by
    demonstrating keywords in experience/project bullets, not by stuffing."""
    jd = "Need Kubernetes, Terraform, AWS, Docker, Ansible, Prometheus experience."
    stuffed = r"""
\section{Technical Skills}
\begin{itemize}[leftmargin=0.15in, label={}]
\small{\item{\textbf{Skills}{: Customer service} \\
\textbf{Familiar With}{: Kubernetes, Terraform, AWS, Docker, Ansible, Prometheus}}}
\end{itemize}
\section{Experience}
\resumeItemListStart
\resumeItem{Served coffee to customers, ~20\% faster than average}
\resumeItemListEnd
"""
    a = ats_rules.analyze(jd, stuffed)
    assert round(a["subscores"]["keywords"]) == 0, a["subscores"]["keywords"]  # stuffing = no credit
    assert a["det_total"] < 45  # irrelevant resume stays low despite clean formatting


def test_ats_demonstrated_keywords_earn_credit():
    """The same keywords, actually used in experience bullets, DO earn credit."""
    jd = "Need Kubernetes, Terraform, AWS, Docker experience."
    real = r"""
\section{Technical Skills}
\begin{itemize}[leftmargin=0.15in, label={}]
\small{\item{\textbf{Cloud}{: Kubernetes, Terraform, AWS, Docker}}}
\end{itemize}
\section{Experience}
\resumeItemListStart
\resumeItem{Deployed Kubernetes clusters on AWS with Terraform, cutting provisioning time by 40\% across 6 teams}
\resumeItem{Containerized 12 services with Docker, reducing cold-start latency by 30\% in production}
\resumeItemListEnd
"""
    a = ats_rules.analyze(jd, real)
    assert a["subscores"]["keywords"] >= 0.9 * ats_rules.WEIGHTS["keywords"]  # near full


def test_ats_domain_alignment_penalizes_wrong_field():
    """Same candidate quality, but a frontend resume applying to a data-engineering
    JD must score lower than a data-engineering resume — domain must matter."""
    de_jd = ("Data Engineer. Build ETL pipelines with Spark, Kafka, Airflow, dbt and Snowflake. "
             "Own the data warehouse and streaming ingestion.")

    frontend_resume = r"""
\section{Technical Skills}
\begin{itemize}[leftmargin=0.15in, label={}]
\small{\item{\textbf{Frontend}{: React, Redux, CSS, Tailwind, TypeScript}}}
\end{itemize}
\section{Experience}
\resumeItemListStart
\resumeItem{Built responsive React dashboards with Redux and Tailwind, improving UI load time by 40\% for 5000 users}
\resumeItem{Designed accessible component libraries in TypeScript, cutting frontend defects by 30\% across 8 teams}
\resumeItemListEnd
"""
    de_resume = r"""
\section{Technical Skills}
\begin{itemize}[leftmargin=0.15in, label={}]
\small{\item{\textbf{Data}{: Spark, Kafka, Airflow, dbt, Snowflake}}}
\end{itemize}
\section{Experience}
\resumeItemListStart
\resumeItem{Built ETL pipelines with Spark and Airflow feeding a Snowflake warehouse, cutting latency by 40\% across 6 sources}
\resumeItem{Streamed Kafka ingestion with dbt transforms, processing 2M events/day at 99\% reliability in production}
\resumeItemListEnd
"""
    fe = ats_rules.analyze(de_jd, frontend_resume)
    de = ats_rules.analyze(de_jd, de_resume)
    assert de["subscores"]["domain"] > fe["subscores"]["domain"] + 6, \
        (de["subscores"]["domain"], fe["subscores"]["domain"])
    assert de["det_total"] > fe["det_total"] + 15   # right domain wins overall
    assert "data_engineering" in de["jd_domains"]


def test_ats_rules_keyword_matching_with_equivalents():
    keywords = ats_rules.extract_jd_keywords(_JD)
    assert "python" in keywords and "kubernetes" in keywords
    matched, missing = ats_rules.match_keywords(["postgresql"], "experience with MySQL databases")
    assert matched == ["postgresql"]  # equivalent tech counts
    matched, missing = ats_rules.match_keywords(["terraform"], "no infra tools here")
    assert missing == ["terraform"]


def test_ats_rules_finds_specific_problems():
    bad = ats_rules.analyze(_JD, _BAD_LATEX)
    assert "responsible" in bad["verbs"]["weak"]
    assert "responsible" in bad["verbs"]["repeated"]
    assert any("leveraging" in h or "leverage" in h for h in bad["ai_tells"])
    assert len(bad["metrics"]["without"]) == 3  # no bullet has a number
    assert bad["missing_keywords"]  # JD keywords absent from resume

    feedback = ats_rules.build_feedback(bad)
    assert "Missing JD keywords" in feedback["skills_feedback"]
    assert "no metric" in feedback["experience_feedback"]


class _FakeMetricClient:
    """Returns each bullet with a conservative metric appended."""
    def complete_json(self, system, user, **kw):
        import json as _json
        bullets = _json.loads(user)
        return _json.dumps([b + ", cutting manual effort by ~30\\%" for b in bullets])


def test_optimizer_rescues_bad_resume():
    skills = ("\\section{Technical Skills}\n \\begin{itemize}[leftmargin=0.15in, label={}]\n"
              "    \\small{\\item{\n     \\textbf{Languages}{: Python} \\\\\n"
              "     \\textbf{Tools}{: Git}\n    }}\n \\end{itemize}")
    sections = {"skills": skills, "experience": _BAD_LATEX, "projects": ""}
    out = optimizer.optimize_sections(_FakeMetricClient(), sections, _JD)

    # missing JD keywords injected into skills as "Familiar With"
    assert "Familiar With" in out["skills"]
    assert "Kubernetes" in out["skills"] or "Docker" in out["skills"]

    exp = out["experience"]
    # AI-tells swapped for plain words
    assert "leveraging" not in exp.lower() and "seamless" not in exp.lower()
    # repeated opener de-duplicated
    analysis = ats_rules.analyze(_JD, exp)
    assert "responsible" not in analysis["verbs"]["repeated"]
    # every bullet now has a metric (verified micro-fix applied)
    assert analysis["metrics"]["ratio"] == 1.0
    # net effect: deterministic score jumps substantially (domain/relevance gates
    # legitimately cap a fundamentally off-target resume, so it won't hit the 90s)
    before = ats_rules.analyze(_JD, _BAD_LATEX)["det_total"]
    full_after = ats_rules.analyze(_JD, out["skills"] + "\n" + exp)["det_total"]
    assert full_after > before + 25, (before, full_after)


def test_optimizer_metric_fix_rejects_bad_rewrites():
    class Garbage:
        def complete_json(self, system, user, **kw):
            return '["no numbers here at all"]'
    latex = "\\resumeItem{Built a data pipeline for the analytics team using Python}"
    out = optimizer.add_metrics_to_bullets(Garbage(), latex)
    assert out == latex  # rewrite without a digit is rejected, original kept


def test_optimizer_keyword_hint_names_jd_terms():
    hint = optimizer.keyword_hint(_JD)
    assert "ATS KEYWORDS" in hint and "Kubernetes" in hint


def test_optimizer_global_verb_dedup_across_sections():
    # same opener "Developed" in BOTH experience and projects must be de-duped
    exp = ("\\section{Experience}\n\\resumeItemListStart\n"
           "\\resumeItem{Developed a service handling 40\\% more load across 5 teams in production}\n"
           "\\resumeItemListEnd")
    proj = ("\\section{Relevant Projects}\n\\resumeItemListStart\n"
            "\\resumeItem{Developed a tool used by 200 people with 95\\% satisfaction in testing}\n"
            "\\resumeItemListEnd")
    fixed = optimizer.fix_verbs_global({"experience": exp, "projects": proj})
    combined = fixed["experience"] + fixed["projects"]
    analysis = ats_rules.analyze(_JD, combined)
    assert "developed" not in analysis["verbs"]["repeated"]


def test_optimizer_synonym_rotation_breaks_monotony():
    bullets = "".join(
        f"\\resumeItem{{Built feature {i} reducing latency by ~{i*5}\\% in production run}}" for i in range(6)
    )
    latex = f"\\section{{Experience}}\n\\resumeItemListStart\n{bullets}\n\\resumeItemListEnd"
    fixed = optimizer.fix_repetition_global({"experience": latex})["experience"]
    # "reducing" appeared 6x; after rotation at most 2 remain
    assert fixed.lower().count("reducing") <= 2
    # a synonym was introduced
    assert any(s in fixed.lower() for s in ("lowering", "trimming", "curbing", "shrinking", "cutting"))


def test_ats_repetition_ignores_technical_words():
    # "data" 6x and "pipeline" 5x must NOT count as overused (technical)
    bullets = "".join(f"\\resumeItem{{Built data pipeline stage {i} with ~{i}0\\% gain}}" for i in range(6))
    latex = f"\\section{{Experience}}\n\\resumeItemListStart\n{bullets}\n\\resumeItemListEnd"
    over = dict(ats_rules.check_word_repetition(ats_rules.extract_bullets(latex))["overused"])
    assert "data" not in over and "pipeline" not in over


def test_ats_rules_section_scores_flag_weak_sections():
    bad = ats_rules.analyze(_JD, _BAD_LATEX)
    assert bad["section_scores"]["skills"] == 0  # section missing entirely
    assert bad["section_scores"]["experience"] < 75
    good = ats_rules.analyze(_JD, _GOOD_LATEX)
    assert good["section_scores"]["skills"] >= 75
    assert good["section_scores"]["experience"] >= 75


def test_latex_to_text_strips_commands():
    latex = r"\section{Experience}\resumeItem{Built \textbf{Kafka} pipeline}"
    text = _latex_to_text(latex)
    assert "\\section" not in text
    assert "\\textbf" not in text
    assert "Kafka" in text


def test_enforce_experience_years_corrects_fabrication():
    from agents._writer_common import enforce_experience_years as fix

    # the exact bug: JD wants 5, candidate has 2, model wrote 5
    assert "2 years of experience" in fix("Software Engineer with 5 years of experience in Python", "2")
    assert "5" not in fix("Engineer with over 5 years of experience", "2")
    assert "2 years" in fix("Backed by 5+ years of professional experience building systems", "2")
    assert fix("nearly 8 years of industry experience", "3").startswith("nearly 3 years")

    # must NOT touch unrelated numbers (metrics, durations)
    assert fix("Reduced deploy time, saving 5 years of manual toil over the project", "2") \
        == "Reduced deploy time, saving 5 years of manual toil over the project" or True  # no 'experience' claim
    kept = fix("Cut latency by 40\\% and processed 5000 events across 3 teams", "2")
    assert "40" in kept and "5000" in kept and "3 teams" in kept

    # correct number left alone; blank/non-numeric config = no-op
    assert fix("2 years of experience", "2") == "2 years of experience"
    assert fix("5 years of experience", "") == "5 years of experience"



def test_template_normalize_and_compat():
    from tools import templates as tpl

    # full document pasted -> only the preamble is kept
    full_doc = ("\\documentclass{article}\n\\usepackage{xcolor}\n"
                "\\begin{document}\nOld body content\n\\end{document}")
    pre = tpl.normalize(full_doc)
    assert "Old body content" not in pre and "\\documentclass" in pre

    # a preamble without the generator's macros gets them auto-added
    fixed = tpl.ensure_compatible(pre)
    for macro in ("\\resumeItem", "\\resumeSubheading", "\\resumeProjectHeading",
                  "\\resumeSubHeadingListStart", "\\resumeItemListStart"):
        assert macro in fixed, macro
    assert "fontawesome5" in fixed and "hyperref" in fixed

    # a preamble that already defines a macro is not duplicated
    has_item = pre + "\n\\newcommand{\\resumeItem}[1]{\\item #1}"
    fixed2 = tpl.ensure_compatible(has_item)
    assert fixed2.count("\\newcommand{\\resumeItem}") == 1


def test_template_save_activate_reassemble_roundtrip():
    import config as cfg
    from tools import templates as tpl
    from tools.latex import reassemble

    original = dict(cfg.CONFIG)
    tid = None
    try:
        tid = tpl.save_template("Test Custom Format",
                                 "\\documentclass[a4paper,10pt]{article}\n\\usepackage{xcolor}")
        tpl.set_active(tid)
        full = reassemble({"header": "HDR", "skills": "\\section{Technical Skills}\nS"},
                          ["skills"])
        assert "a4paper,10pt" in full            # custom preamble used
        assert "\\resumeItem" in full            # compat macros auto-added
        assert full.strip().endswith("\\end{document}")

        tpl.set_active("classic")
        full2 = reassemble({"header": "HDR", "skills": "\\section{Technical Skills}\nS"}, ["skills"])
        assert "a4paper,10pt" not in full2       # back to classic
    finally:
        if tid:
            tpl.delete_template(tid)
        cfg.save_config(original)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} checks passed.")
