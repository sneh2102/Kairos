"""Loads config.json + .env into one place every agent imports from."""
import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv, set_key, unset_key

ROOT = Path(__file__).parent
# Unset in source/dev mode (falls back to ROOT, today's behavior, unchanged).
# Set by Electron only in a packaged build, to the OS-appropriate per-user data
# dir (e.g. %APPDATA%\Job Scraper) — an installed app's own folder is read-only,
# so config/resume/db files can't live next to the frozen executable.
DATA_DIR = Path(os.environ.get("JOB_HUNTER_DATA_DIR", ROOT))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_CONFIG_PATH = DATA_DIR / "config.json"
_CONFIG_EXAMPLE_PATH = ROOT / "config.example.json"
_ENV_PATH = DATA_DIR / ".env"

_ENV_PATH.touch(exist_ok=True)
load_dotenv(_ENV_PATH)

# config.json is gitignored (holds personal profile/API data) — a fresh clone
# won't have one, so seed it from the blank template rather than crashing.
if not _CONFIG_PATH.exists():
    shutil.copy(_CONFIG_EXAMPLE_PATH, _CONFIG_PATH)

with open(_CONFIG_PATH, encoding="utf-8") as f:
    CONFIG: dict = json.load(f)


def get_ollama_keys() -> list[str]:
    """Every OLLAMA_API_KEY_1.. in order, plus the legacy bare OLLAMA_API_KEY
    (if set and not already in the numbered list) tacked on the end."""
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
    return keys


def collect_ollama_keys() -> list[str]:
    keys = get_ollama_keys()
    if not keys:
        raise RuntimeError("No OLLAMA_API_KEY_1.. found in environment/.env")
    return keys


def has_ollama_key() -> bool:
    return bool(get_ollama_keys())


def save_ollama_key(value: str):
    """Writes OLLAMA_API_KEY to .env (creating it if needed) and updates the
    running process's env so it's usable immediately, no restart required."""
    _ENV_PATH.touch(exist_ok=True)
    set_key(str(_ENV_PATH), "OLLAMA_API_KEY", value)
    os.environ["OLLAMA_API_KEY"] = value


def save_ollama_keys(keys: list[str]):
    """Rewrites OLLAMA_API_KEY_1.. in .env from `keys` (renumbered from 1),
    clearing the legacy bare OLLAMA_API_KEY and any now-unused numbered slots
    — so the rotation pool in llm/client.py picks up the new list immediately."""
    _ENV_PATH.touch(exist_ok=True)
    old_count = 0
    while os.environ.get(f"OLLAMA_API_KEY_{old_count + 1}"):
        old_count += 1
    unset_key(str(_ENV_PATH), "OLLAMA_API_KEY")
    os.environ.pop("OLLAMA_API_KEY", None)
    for i in range(1, max(old_count, len(keys)) + 1):
        env_key = f"OLLAMA_API_KEY_{i}"
        if i <= len(keys):
            set_key(str(_ENV_PATH), env_key, keys[i - 1])
            os.environ[env_key] = keys[i - 1]
        else:
            unset_key(str(_ENV_PATH), env_key)
            os.environ.pop(env_key, None)


def load_text_file(path: str) -> str:
    p = DATA_DIR / path
    if not p.exists():
        raise FileNotFoundError(f"Expected file at {p}")
    return p.read_text(encoding="utf-8")


def save_text_file(path: str, content: str):
    (DATA_DIR / path).write_text(content, encoding="utf-8")


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
