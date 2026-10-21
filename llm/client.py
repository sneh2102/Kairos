"""One Ollama client for every agent — multi-key rotation, retries, JSON mode.

Port of the old project's agents/api_client.py (RotatingOllamaClient), extended
to also cover ai.py's screening use-case so there's a single client class
instead of two.
"""
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from ollama import Client

OLLAMA_HOST = "https://ollama.com"
_RATE_LIMIT_TOKENS = ("rate limit", "429", "401", "403", "quota", "limit exceeded")
_CONTENT_SNIFF_TOKENS = ('"score"', '"verdict"', "\\section", "\\resumeItem", "\\resumeSubheading")


_NO_CHATTER = (
    "\n\nOUTPUT RULE: return ONLY the requested content. No notes, no explanations, no "
    "comments, no LaTeX % comment lines, no mention of tools, connectors or your choices."
)


class ClaudeCliClient:
    """Drop-in for RotatingOllamaClient.complete() that shells out to the `claude`
    CLI (`claude -p`), so it uses your Claude subscription — no API key needed.
    Only used for the jobs you pick; screening/ATS/etc. stay on the Ollama model."""

    def __init__(self, model: str = "", timeout: int = 600):
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str, max_tokens: int | None = None, **_) -> str:
        # system prompt goes via a file: Windows caps command lines at ~32k chars
        with tempfile.TemporaryDirectory() as tmp:
            sys_file = Path(tmp) / "system.txt"
            sys_file.write_text(system + _NO_CHATTER, encoding="utf-8")
            cmd = ["claude", "-p", "--tools", "", "--no-session-persistence", "--disable-slash-commands",
                   "--setting-sources", "project", "--strict-mcp-config",
                   "--system-prompt-file", str(sys_file)]
            if self.model:
                cmd += ["--model", self.model]
            # cwd=tmp so the project's CLAUDE.md / memory never leaks into the prompt
            proc = subprocess.run(cmd, input=user, capture_output=True, text=True, encoding="utf-8",
                                  timeout=self.timeout, cwd=tmp, shell=(os.name == "nt"))
        out = proc.stdout.strip()
        if proc.returncode != 0 or not out:
            raise RuntimeError(f"claude CLI failed ({proc.returncode}): {(proc.stderr or out)[:300]}")
        return out
def validate_api_key(api_key: str) -> tuple[bool, str | None]:
    """Checks a key is actually accepted by Ollama, for the Settings page's
    validate-before-save flow. Returns (valid, error_message).

    /api/tags is unauthenticated (it's just the public model catalog — a
    garbage key gets 200 same as a real one), so it can't tell a valid key
    from a fake one. /api/chat does check auth first, before it even looks at
    whether the model exists, so a 401/403 here means the key itself is bad
    regardless of model name; a minimal 1-token request keeps the probe cheap."""
    if not api_key.strip():
        return False, "Key is empty"
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "gpt-oss:20b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=15,
        )
    except requests.RequestException as e:
        return False, f"Could not reach Ollama: {e}"
    if resp.status_code in (401, 403):
        return False, "Ollama rejected this key"
    return True, None


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def validate_gemini_key(api_key: str) -> tuple[bool, str | None]:
    """Listing models needs a valid key (a bad one gets 400 API_KEY_INVALID)."""
    if not api_key.strip():
        return False, "Key is empty"
    try:
        resp = requests.get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": api_key.strip()},
                            params={"pageSize": 1}, timeout=15)
    except requests.RequestException as e:
        return False, f"Could not reach Google AI Studio: {e}"
    if resp.status_code in (400, 401, 403):
        return False, "Google AI Studio rejected this key"
    return True, None


class GeminiClient:
    """Google AI Studio (Gemini / Gemma) with the same complete()/complete_json()
    surface as RotatingOllamaClient, so every agent works with either."""

    def __init__(self, api_keys: list[str], model: str, num_predict: int = 32384, temperature: float = 0.3):
        self.api_keys = [k.strip() for k in api_keys if k and k.strip()]
        if not self.api_keys:
            raise ValueError("Gemini provider selected but no Gemini API key is set (Settings > Model)")
        self.model, self.idx = model, 0
        self.num_predict, self.temperature = num_predict, temperature

    def _generate(self, system: str, user: str, max_tokens: int, temperature: float,
                  json_mode: bool, retries: int = 5, backoff: float = 2.0) -> str:
        # Gemma models on AI Studio reject system instructions and JSON mode.
        gemma = self.model.lower().startswith("gemma")
        body = {"generationConfig": {"temperature": temperature,
                                     "maxOutputTokens": min(max_tokens, 8192 if gemma else 65536)}}
        if gemma:
            body["contents"] = [{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}]
        else:
            body["systemInstruction"] = {"parts": [{"text": system}]}
            body["contents"] = [{"role": "user", "parts": [{"text": user}]}]
            if json_mode:
                body["generationConfig"]["responseMimeType"] = "application/json"
        last_err: Exception | None = None
        n = len(self.api_keys)
        for attempt in range(retries * n):
            try:
                resp = requests.post(f"{GEMINI_BASE}/models/{self.model}:generateContent",
                                     headers={"x-goog-api-key": self.api_keys[self.idx]}, json=body, timeout=180)
                if resp.status_code in (429, 500, 502, 503, 504):
                    if resp.status_code == 429:   # free tier is ~10 requests/min
                        last_err = RuntimeError(f"HTTP 429: {resp.text[:200]}")
                        self.idx = (self.idx + 1) % n
                        logging.warning("Gemini rate limit (attempt %d), rotated to key #%d", attempt + 1, self.idx + 1)
                        if (attempt + 1) % n == 0:   # every key limited: wait out the window
                            time.sleep(15 * ((attempt + 1) // n))
                        continue
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                if resp.status_code >= 400:   # bad key/model/request: retrying won't help
                    raise ValueError(f"Gemini error {resp.status_code}: {resp.text[:300]}")
                parts = resp.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if not text:
                    raise RuntimeError("AI returned an empty response")
                return text
            except ValueError:
                raise
            except Exception as e:
                last_err = e
                logging.warning("Gemini call failed (attempt %d): %s", attempt + 1, e)
                time.sleep(backoff * (attempt + 1))
        raise RuntimeError(f"All Gemini attempts failed: {last_err}")

    def complete(self, system: str, user: str, max_tokens: int | None = None, **_) -> str:
        return self._generate(system, user, max_tokens or self.num_predict, self.temperature, False)

    def complete_json(self, system: str, user: str, num_predict: int = 2048,
                      temperature: float = 0.1, **_) -> str:
        # headroom: 2.5 models spend output tokens on thinking before the JSON
        return self._generate(system, user, max(num_predict, 8192), temperature, True)


_search_key_idx = 0


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Ollama's hosted web search ([{title, url, content}]), rotating through
    the Ollama keys on auth/quota errors. Returns [] if every key fails."""
    global _search_key_idx
    from config import get_ollama_keys
    keys = get_ollama_keys()
    for _ in range(len(keys)):
        key = keys[_search_key_idx % len(keys)]
        try:
            resp = requests.post(f"{OLLAMA_HOST}/api/web_search", headers={"Authorization": f"Bearer {key}"},
                                 json={"query": query, "max_results": max_results}, timeout=30)
        except requests.RequestException as e:
            logging.warning("web search failed: %s", e)
            return []
        if resp.status_code in (401, 403, 429):
            _search_key_idx += 1
            continue
        if resp.status_code >= 400:
            logging.warning("web search HTTP %s: %s", resp.status_code, resp.text[:200])
            return []
        return resp.json().get("results") or []
    logging.warning("web search: every Ollama key is unauthorized or out of quota")
    return []


def make_client(ollama_model: str, task: str = ""):
    """The LLM client for the provider chosen in Settings > Model. `ollama_model`
    is the per-stage Ollama model; Gemini uses the single model.gemini_model.
    `task` (screener, skills, experience, projects, summary, cover_letter, ats, interview, prep_guide) picks
    the provider from model.task_providers; missing/"default" falls back to model.provider."""
    from config import CONFIG, collect_ollama_keys
    m = CONFIG["model"]
    provider = (m.get("task_providers") or {}).get(task) or "default"
    if provider == "default":
        provider = m.get("provider")
    if provider == "gemini":
        return GeminiClient(m.get("gemini_api_keys") or [m.get("gemini_api_key", "")], m.get("gemini_model") or "gemini-3.1-flash-lite",
                            num_predict=m["num_predict"], temperature=m["temperature"])
    return RotatingOllamaClient(collect_ollama_keys(), ollama_model, num_predict=m["num_predict"],
                                num_ctx=m["num_ctx"], temperature=m["temperature"])


class RotatingOllamaClient:
    def __init__(self, api_keys: list[str], model: str,
                 num_predict: int = 32384, num_ctx: int = 64768, temperature: float = 0.3):
        if not api_keys:
            raise ValueError("RotatingOllamaClient needs at least one API key")
        self.api_keys = api_keys
        self.model = model
        self.num_predict = num_predict
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.current_index = 0
        self.client = self._build_client()

    def _build_client(self) -> Client:
        key = self.api_keys[self.current_index]
        # ollama.Client defaults to no timeout at all (httpx waits forever) —
        # a single stalled request would hang the whole scrape/apply loop with
        # no exception ever raised for the retry logic below to catch.
        return Client(host=OLLAMA_HOST, headers={"Authorization": f"Bearer {key}"}, timeout=180)

    def _rotate(self):
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        self.client = self._build_client()
        logging.info("Rotated to Ollama API key #%d", self.current_index + 1)

    @staticmethod
    def _looks_like_content(err_str: str) -> str | None:
        """Ollama's cloud API sometimes raises a valid partial response as an
        exception instead of returning it. Sniff for JSON/LaTeX and use it as-is."""
        if any(tok in err_str for tok in _CONTENT_SNIFF_TOKENS):
            return err_str
        stripped = err_str.strip()
        if stripped.startswith("{"):
            return stripped
        return None

    def complete(self, system: str, user: str, max_tokens: int | None = None,
                 retries: int = 3, backoff: float = 2.0) -> str:
        """Two-message (system+user) chat completion, used by every agent."""
        total_attempts = retries * len(self.api_keys)
        last_err: Exception | None = None
        for attempt in range(total_attempts):
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    stream=False,
                    options={
                        "num_predict": max_tokens or self.num_predict,
                        "num_ctx": self.num_ctx,
                        "temperature": self.temperature,
                    },
                )
                content = response["message"]["content"].strip()
                if not content:
                    raise ValueError("AI returned an empty response")
                return content
            except Exception as e:
                last_err = e
                err_str = str(e)
                sniffed = self._looks_like_content(err_str)
                if sniffed:
                    return sniffed
                if any(tok in err_str.lower() for tok in _RATE_LIMIT_TOKENS):
                    logging.warning("Rate/auth error (attempt %d/%d): %s", attempt + 1, total_attempts, e)
                    self._rotate()
                else:
                    sleep_time = backoff * ((attempt % retries) + 1)
                    logging.warning("Model call failed (attempt %d/%d): %s. Sleeping %.1fs",
                                     attempt + 1, total_attempts, e, sleep_time)
                    time.sleep(sleep_time)
        raise RuntimeError(f"All {total_attempts} attempts across {len(self.api_keys)} keys failed: {last_err}")

    def complete_json(self, system: str, user: str, num_predict: int = 2048,
                       temperature: float = 0.1, num_ctx: int = 16384, retries: int = 3) -> str:
        """Direct HTTP call with format=json — used by the ATS checker, which
        needs Ollama's structured-output mode rather than free-text completion."""
        last_err: Exception | None = None
        retries *= len(self.api_keys)  # same budget as complete(): every key gets its turns
        for attempt in range(retries):
            key = self.api_keys[self.current_index]
            try:
                resp = requests.post(
                    f"{OLLAMA_HOST}/api/chat",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                        "stream": False,
                        "format": "json",
                        "options": {"num_predict": num_predict, "temperature": temperature, "num_ctx": num_ctx},
                    },
                    timeout=120,
                )
                if resp.status_code in (401, 403, 429):
                    last_err = RuntimeError(f"Ollama key #{self.current_index + 1}: HTTP {resp.status_code} {resp.text[:200]}")
                    self._rotate()
                    continue
                resp.raise_for_status()
                content = resp.json()["message"]["content"].strip()
                if content:
                    return content
                raise ValueError("AI returned an empty response")
            except Exception as e:
                last_err = e
                time.sleep(2.0 * (attempt + 1))
        raise RuntimeError(f"All {retries} attempts failed: {last_err}")
