"""Loads config.json + .env into one place every agent imports from."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
_CONFIG_PATH = ROOT / "config.json"

with open(_CONFIG_PATH, encoding="utf-8") as f:
    CONFIG: dict = json.load(f)


def collect_ollama_keys() -> list[str]:
    keys = []
    i = 1
    while True:
        key = os.environ.get(f"OLLAMA_API_KEY_{i}")
        if not key:
            break
        keys.append(key)
        i += 1
    single = os.environ.get("OLLAMA_API_KEY")
    if single and single not in keys:
        keys.append(single)
    if not keys:
        raise RuntimeError("No OLLAMA_API_KEY_1.. found in environment/.env")
    return keys


def load_text_file(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"Expected file at {p}")
    return p.read_text(encoding="utf-8")


def save_text_file(path: str, content: str):
    (ROOT / path).write_text(content, encoding="utf-8")


def get_prompt(key: str, default: str) -> str:
    """Reads a user-editable LLM prompt from config.json, falling back to the
    hardcoded default if missing/blank. Reads CONFIG fresh each call (not at
    import time) so edits saved via the Prompts page apply immediately."""
    return CONFIG.get("prompts", {}).get(key) or default


def save_config(new_cfg: dict):
    """Persists to config.json and updates the in-memory CONFIG in place, so
    graphs built after this call (each `scrape`/`apply` run builds fresh) pick
    up the change without a process restart."""
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(new_cfg, f, indent=2, ensure_ascii=False)
    CONFIG.clear()
    CONFIG.update(new_cfg)
