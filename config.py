"""Loads config.json + .env into one place every agent imports from."""
import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
# Unset in source/dev mode (falls back to ROOT, today's behavior, unchanged).
# Set by Electron only in a packaged build, to the OS-appropriate per-user data
# dir (e.g. %APPDATA%\Job Scraper) — an installed app's own folder is read-only,
# so config/resume/db files can't live next to the frozen executable.
DATA_DIR = Path(os.environ.get("JOB_HUNTER_DATA_DIR", ROOT))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_CONFIG_PATH = DATA_DIR / "config.json"
_ENV_PATH = DATA_DIR / ".env"

# Find config.example.json: in source root or in PyInstaller bundle resources
def _find_config_example():
    candidates = [
        ROOT / "config.example.json",  # source mode
        Path(ROOT).parent / "config.example.json",  # one level up
    ]
    # In PyInstaller bundled app, also check the bundle directory
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "config.example.json")
    # When launched from Electron in packaged mode, check resources
    if "JOB_HUNTER_DATA_DIR" in os.environ:
        # Electron sets JOB_HUNTER_DATA_DIR; the app resources are nearby
        # For now, assume config.example.json was copied into DATA_DIR or is bundled
        candidates.insert(0, DATA_DIR / "config.example.json")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]  # return first choice anyway, error will happen on copy

_CONFIG_EXAMPLE_PATH = _find_config_example()

_ENV_PATH.touch(exist_ok=True)
load_dotenv(_ENV_PATH)

# config.json is gitignored (holds personal profile/API data) — a fresh clone
# won't have one, so seed it from the blank template rather than crashing.
if not _CONFIG_PATH.exists():
    if not _CONFIG_EXAMPLE_PATH.exists():
        raise FileNotFoundError(
            f"config.example.json not found. Searched: {_CONFIG_EXAMPLE_PATH}\n"
            f"Please ensure config.example.json is bundled with the application."
        )
    shutil.copy(_CONFIG_EXAMPLE_PATH, _CONFIG_PATH)

with open(_CONFIG_PATH, encoding="utf-8") as f:
    CONFIG: dict = json.load(f)


def _env_ollama_keys() -> list[str]:
    """Legacy .env fallback: every OLLAMA_API_KEY_1.. in order, plus the bare
    OLLAMA_API_KEY (if set and not already in the numbered list) on the end."""
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


def get_ollama_keys() -> list[str]:
    """API keys from config.json (source of truth), falling back to legacy .env
    vars for installs that haven't been migrated/saved yet."""
    return list(CONFIG.get("api_keys") or _env_ollama_keys())


def collect_ollama_keys() -> list[str]:
    keys = get_ollama_keys()
    if not keys:
        raise RuntimeError("No API keys found in config.json (api_keys) or .env")
    return keys


def has_ollama_key() -> bool:
    return bool(get_ollama_keys())


def save_ollama_key(value: str):
    """Adds a single key to config.json's api_keys (Setup page's one-key flow)."""
    keys = get_ollama_keys()
    if value not in keys:
        keys.append(value)
    save_ollama_keys(keys)


def save_ollama_keys(keys: list[str]):
    """Persists the rotation pool to config.json's api_keys — the pool in
    llm/client.py picks up the new list on the next run, no restart needed."""
    CONFIG["api_keys"] = [k.strip() for k in keys if k and k.strip()]
    save_config(CONFIG)


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
    # save_ollama_key(s) calls this with CONFIG itself as new_cfg (already
    # mutated in place) — clearing CONFIG would then also clear new_cfg
    # (same object), so the update() right after copies from an empty dict
    # and wipes every other setting. Skip the dance when there's nothing to
    # copy.
    if new_cfg is not CONFIG:
        CONFIG.clear()
        CONFIG.update(new_cfg)


# One-time migration: copy legacy .env keys into config.json so config.json is
# the single source of truth from here on (.env is left untouched as a backup).
if not CONFIG.get("api_keys") and _env_ollama_keys():
    save_ollama_keys(_env_ollama_keys())
