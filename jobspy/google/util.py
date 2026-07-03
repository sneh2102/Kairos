import re
import json

from jobspy.util import create_logger

log = create_logger("Google")

# Google periodically rotates these internal data keys. List known ones in priority order.
_KNOWN_JOB_KEYS = ["520084652", "462133579", "437964852", "638187921"]


def find_job_info(jobs_data: list | dict) -> list | None:
    """Iterates through JSON data to find job listings by known Google data keys."""
    if isinstance(jobs_data, dict):
        for key, value in jobs_data.items():
            if key in _KNOWN_JOB_KEYS and isinstance(value, list):
                return value
            result = find_job_info(value)
            if result:
                return result
    elif isinstance(jobs_data, list):
        for item in jobs_data:
            result = find_job_info(item)
            if result:
                return result
    return None


def find_job_info_initial_page(html_text: str) -> list:
    """
    Extract Google's internal job JSON arrays from page HTML.
    Tries known data keys, then falls back to a generic pattern that looks for
    any 9-digit key whose value is a nested array containing job-like URLs.
    """
    results = []

    # --- Strategy 1: known hardcoded keys ---
    for key in _KNOWN_JOB_KEYS:
        pattern = re.compile(
            re.escape(f'"{key}":') + r'(\[.*?\]\s*])\s*}\s*]\s*]\s*]\s*]\s*]',
            re.DOTALL,
        )
        for match in pattern.finditer(html_text):
            try:
                parsed = json.loads(match.group(1))
                results.append(parsed)
            except json.JSONDecodeError:
                pass
        if results:
            return results

    # --- Strategy 2: generic 9-digit key with large array containing a URL ---
    pattern_generic = re.compile(r'"(\d{9})"\s*:\s*(\[(?:[^[\]]*|\[(?:[^[\]]*|\[[^\[\]]*\])*\])*\])')
    for match in pattern_generic.finditer(html_text):
        blob = match.group(2)
        # Quick heuristic: must contain a URL and be fairly large
        if 'https://' not in blob or len(blob) < 200:
            continue
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, list):
                results.append(parsed)
        except json.JSONDecodeError:
            pass
        if len(results) >= 20:
            break

    return results
