"""GitHub Project Importer — generates projects.txt-formatted entries from a
user's GitHub repos. Port of utils/github_importer.py's GitHubProjectImporter.
Not a LangGraph agent (no per-job JD context) — a standalone helper the
Resume Data page's Projects tab calls directly.
"""
import base64

import requests

from llm.client import RotatingOllamaClient

API = "https://api.github.com"

_SYSTEM = (
    "You are an expert resume writer. Given a GitHub repo's metadata, write ONE "
    "projects.txt-formatted entry: first line 'Name | Tech1, Tech2, Tech3 | url', "
    "then 2-3 bullet lines starting with '- ', each with a concrete outcome/metric. "
    "Infer the tech stack from the languages/README. Output ONLY those lines, nothing else."
)


def _headers(token: str = "") -> dict:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def list_repos(username: str, token: str = "") -> list[dict]:
    resp = requests.get(
        f"{API}/users/{username}/repos",
        params={"per_page": 100, "type": "owner", "sort": "updated"},
        headers=_headers(token), timeout=20,
    )
    resp.raise_for_status()
    return [
        {
            "name": r["name"], "full_name": r["full_name"], "url": r["html_url"],
            "description": r.get("description") or "", "stars": r.get("stargazers_count", 0),
            "language": r.get("language") or "", "is_fork": r.get("fork", False),
        }
        for r in resp.json()
    ]


def fetch_repo_data(repo_url: str, token: str = "") -> dict:
    owner_repo = repo_url.rstrip("/").split("github.com/")[-1]
    headers = _headers(token)

    info = requests.get(f"{API}/repos/{owner_repo}", headers=headers, timeout=20).json()
    languages = requests.get(f"{API}/repos/{owner_repo}/languages", headers=headers, timeout=20).json()

    readme_text = ""
    readme_resp = requests.get(f"{API}/repos/{owner_repo}/readme", headers=headers, timeout=20)
    if readme_resp.status_code == 200:
        content = readme_resp.json().get("content", "")
        try:
            readme_text = base64.b64decode(content).decode("utf-8", errors="ignore")[:3000]
        except Exception:
            readme_text = ""

    return {
        "name": info.get("name", owner_repo), "description": info.get("description") or "",
        "languages": list(languages.keys()), "stars": info.get("stargazers_count", 0),
        "readme": readme_text, "url": info.get("html_url", repo_url),
    }


def generate_project_entry(client: RotatingOllamaClient, repo_url: str, token: str = "") -> str:
    data = fetch_repo_data(repo_url, token)
    user = (
        f"Repo: {data['name']}\nURL: {data['url']}\nDescription: {data['description']}\n"
        f"Languages: {', '.join(data['languages'])}\nStars: {data['stars']}\n\n"
        f"README (truncated):\n{data['readme']}"
    )
    return client.complete(system=_SYSTEM, user=user).strip()
