"""Resume designer: style -> preamble, layout save, hidden sections, static sections.
Run: python test_designer.py  (never touches your config.json or templates)"""
import tempfile
from pathlib import Path

import config
from config import CONFIG
from tools import designer, latex, templates


def test_style_validation_and_preamble():
    s = designer.normalize_style({"font": "comic-sans", "accent": "red", "font_size": 12, "bullet": "dash",
                                  "heading_case": "caps"})
    assert s["font"] == "computer-modern" and s["accent"] == "#000000" and s["font_size"] == 12
    pre = designer.build_preamble({**s, "accent": "#1F4E79", "font": "times", "header_align": "left"})
    assert "[letterpaper,12pt]" in pre and "{accent}{HTML}{1F4E79}" in pre and "tgtermes" in pre
    assert "\\textendash" in pre and "\\MakeUppercase" in pre and "\\renewenvironment{center}" in pre
    for macro in ("resumeItem", "resumeSubheading", "resumeProjectHeading",
                  "resumeSubHeadingListStart", "resumeItemListEnd"):
        assert f"\\newcommand{{\\{macro}}}" in pre              # writers' macros always defined


def test_save_layout_activates_template_and_hides_sections():
    saved = {}
    orig = (config.save_config, templates.TEMPLATES_DIR, templates.PREVIEWS_DIR, dict(CONFIG))
    with tempfile.TemporaryDirectory() as tmp:
        templates.TEMPLATES_DIR, templates.PREVIEWS_DIR = Path(tmp) / "t", Path(tmp) / "p"
        config.save_config = lambda cfg: (saved.update(cfg), CONFIG.update(cfg))
        try:
            static = {"id": "awards", "name": "Awards", "kind": "static", "layout": "bullets", "bullets": ["Won **1st**"]}
            clash = {"id": "skills", "name": "Dup", "kind": "static"}          # collides with a core id: dropped
            out = designer.save_layout({"style": {"font": "palatino"}, "custom_sections": [static, clash],
                                        "section_order": ["awards", "experience"], "hidden_sections": ["projects", "nope"]})
            assert saved["pipeline"]["latex_template"] == "designer"
            assert (templates.TEMPLATES_DIR / "designer.tex").exists()
            assert [s["id"] for s in out["custom_sections"]] == ["awards"]
            assert out["section_order"][:2] == ["awards", "experience"] and "skills" in out["section_order"]
            assert out["hidden_sections"] == ["projects"]
            sections = {"header": "", "skills": "\\section{Technical Skills}", "projects": "\\section{Relevant Projects}",
                        "experience": "\\section{Experience}", "awards": "\\section{Awards}"}
            doc = latex.reassemble(sections, out["section_order"])
            assert "Relevant Projects" not in doc and doc.index("Awards") < doc.index("Experience")
        finally:
            config.save_config = orig[0]
            templates.TEMPLATES_DIR, templates.PREVIEWS_DIR = orig[1], orig[2]
            CONFIG.clear()
            CONFIG.update(orig[3])


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
