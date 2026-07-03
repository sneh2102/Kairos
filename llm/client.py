"""One Ollama client for every agent — multi-key rotation, retries, JSON mode.

Port of the old project's agents/api_client.py (RotatingOllamaClient), extended
to also cover ai.py's screening use-case so there's a single client class
instead of two.
"""
import logging
import time

import requests
from ollama import Client

OLLAMA_HOST = "https://ollama.com"
_RATE_LIMIT_TOKENS = ("rate limit", "429", "401", "403", "quota", "limit exceeded")
_CONTENT_SNIFF_TOKENS = ('"score"', '"verdict"', "\\section", "\\resumeItem", "\\resumeSubheading")


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
        return Client(host=OLLAMA_HOST, headers={"Authorization": f"Bearer {key}"})

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
