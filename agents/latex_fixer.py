"""LaTeX Fixer — last-resort auto-repair when the assembled resume fails to
compile. The writer agents occasionally invent a macro name that isn't
defined in the template preamble (e.g. \\resumeSubHeadingListEntry instead of
\\resumeSubheading), or leave an unescaped special character; this feeds the
compiler's own error back to the model and asks for a minimal fix, so a
build doesn't silently degrade to a raw .tex fallback with no PDF.
"""
from pathlib import Path
from typing import Callable

from agents._writer_common import strip_backticks
from config import get_prompt
from llm.client import RotatingOllamaClient

# Default — editable via the Prompts page (config.json prompts.latex_fix).
SYSTEM_LATEX_FIX = r"""You are a LaTeX compile-error fixer. You will be given a full LaTeX
resume document and the exact error the compiler produced. Fix ONLY what's needed to make it
compile — do not rewrite content, bullets, wording, or reorder anything.

The ONLY custom macros defined in the preamble are:
\resumeItem{bullet text}
\resumeSubheading{title}{dates}{company}{location}   (exactly 4 arguments)
\resumeProjectHeading{heading}{}                       (exactly 2 arguments)
\resumeSubHeadingListStart / \resumeSubHeadingListEnd
\resumeItemListStart / \resumeItemListEnd
Never invent a different macro name (e.g. \resumeSubHeadingListEntry does not exist) — if a
line uses an undefined command, replace it with the correct one from this list, keeping the
same content in the same argument positions.

Other common causes: unbalanced braces, an unescaped %, &, _, #, or $ in body text (escape it
with a backslash), or a missing closing brace/environment.

Output ONLY the full corrected LaTeX document, from \documentclass through \end{document}.
No backticks, no explanation, no commentary."""


def fix(client: RotatingOllamaClient, latex_code: str, compile_error: str) -> str:
    user = f"COMPILE ERROR:\n{compile_error}\n\nFULL LATEX DOCUMENT:\n{latex_code}"
    return strip_backticks(client.complete(system=get_prompt("latex_fix", SYSTEM_LATEX_FIX), user=user))


def compile_with_autofix(
    client: RotatingOllamaClient,
    latex_code: str,
    output_pdf_path: Path,
    compile_fn: Callable[[str, Path], bool],
    error_fn: Callable[[Path], str],
    max_attempts: int = 2,
    on_attempt: Callable[[int, str], None] = lambda attempt, error: None,
) -> tuple[bool, str]:
    """Compiles latex_code; on failure, feeds the compiler's own error back to
    the model and retries, up to max_attempts extra tries. Stops early if an
    attempt produces the identical error as the one before it (no progress).
    Returns (compiled_ok, final_latex_code) — final_latex_code is the last
    candidate tried, so callers save/display whatever was actually compiled
    (or attempted) rather than the original broken draft."""
    if compile_fn(latex_code, output_pdf_path):
        return True, latex_code

    error = error_fn(output_pdf_path)
    for attempt in range(1, max_attempts + 1):
        if not error:
            break
        on_attempt(attempt, error)
        try:
            candidate = fix(client, latex_code, error)
        except Exception:
            break
        latex_code = candidate
        if compile_fn(latex_code, output_pdf_path):
            return True, latex_code
        new_error = error_fn(output_pdf_path)
        if new_error == error:
            break
        error = new_error
    return False, latex_code


if __name__ == "__main__":
    # No network/LaTeX engine needed — compile_fn/error_fn are injected, so the
    # retry/stop logic is fully testable with fakes.
    class _FakeClient:
        def __init__(self, replies):
            self.replies = list(replies)

        def complete(self, system, user):
            return self.replies.pop(0)

    # 1. First try already compiles -> no fix call needed.
    ok, code = compile_with_autofix(
        _FakeClient([]), "good code", Path("out.pdf"),
        compile_fn=lambda code, path: True, error_fn=lambda path: "",
    )
    assert ok and code == "good code"

    # 2. Fails once, fix succeeds on first retry.
    attempts_seen = []
    ok, code = compile_with_autofix(
        _FakeClient(["fixed code"]), "broken code", Path("out.pdf"),
        compile_fn=lambda code, path: code == "fixed code",
        error_fn=lambda path: "Undefined control sequence",
        on_attempt=lambda attempt, error: attempts_seen.append((attempt, error)),
    )
    assert ok and code == "fixed code"
    assert attempts_seen == [(1, "Undefined control sequence")]

    # 3. Same error twice in a row -> stops early instead of burning all attempts.
    calls = []
    ok, code = compile_with_autofix(
        _FakeClient(["still broken", "still broken", "still broken"]), "broken code", Path("out.pdf"),
        compile_fn=lambda code, path: (calls.append(code), False)[1],
        error_fn=lambda path: "same error",
        max_attempts=5,
    )
    assert not ok and calls == ["broken code", "still broken"]

    # 4. Exhausts max_attempts when the error keeps changing but never resolves.
    errors = iter(["e1", "e2", "e3", "e4"])
    ok, code = compile_with_autofix(
        _FakeClient(["v1", "v2", "v3"]), "broken code", Path("out.pdf"),
        compile_fn=lambda code, path: False,
        error_fn=lambda path: next(errors),
        max_attempts=3,
    )
    assert not ok and code == "v3"

    print("ok")
