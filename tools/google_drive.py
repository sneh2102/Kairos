"""Google Drive backup for built resume/cover-letter PDFs.

Plain REST calls (no google-api-python-client) — `requests` is already a
project dependency and OAuth + a single-endpoint upload don't need more.
OAuth uses the desktop-app loopback flow: Google redirects back to this same
local server (127.0.0.1), so "Connect Google Drive" only works run from the
machine hosting the backend. Once connected, uploads work from any client
(desktop or mobile) since they're all just hitting this server.
"""
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlencode

import requests

import config
from config import CONFIG

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
SCOPES = "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/userinfo.email"
FOLDER_NAME = "Job Tracker Resumes"

REDIRECT_URI = f"http://127.0.0.1:{os.environ.get('PORT', 8756)}/api/google/callback"

# single-user app: one pending OAuth attempt at a time is all we need.
_pending_state: str | None = None


def _google_cfg() -> dict:
    return CONFIG.setdefault("google", {})


def is_configured() -> bool:
    g = _google_cfg()
    return bool(g.get("client_id") and g.get("client_secret"))


def is_connected() -> bool:
    return bool(_google_cfg().get("refresh_token"))


def start_auth() -> str:
    global _pending_state
    g = _google_cfg()
    if not is_configured():
        raise RuntimeError("Set a Google client ID/secret in Settings first.")
    _pending_state = uuid.uuid4().hex
    params = {
        "client_id": g["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": _pending_state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def finish_auth(code: str, state: str) -> str:
    """Exchanges the code for tokens, stores the refresh token + connected
    email in config.json, returns the email for the callback page."""
    global _pending_state
    if not state or state != _pending_state:
        raise RuntimeError("State mismatch — start the connect flow again from Settings.")
    _pending_state = None
    g = _google_cfg()
    res = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": g["client_id"],
        "client_secret": g["client_secret"],
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=15)
    res.raise_for_status()
    tokens = res.json()
    email = _fetch_email(tokens["access_token"])
    g["refresh_token"] = tokens["refresh_token"]
    g["connected_email"] = email
    config.save_config(CONFIG)
    return email


def disconnect():
    g = _google_cfg()
    token = g.get("refresh_token")
    if token:
        try:
            requests.post(REVOKE_URL, params={"token": token}, timeout=10)
        except requests.RequestException:
            pass
    g.update({"refresh_token": "", "connected_email": "", "folder_id": ""})
    config.save_config(CONFIG)


def _fetch_email(access_token: str) -> str:
    res = requests.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    res.raise_for_status()
    return res.json().get("email", "")


def _access_token() -> str:
    g = _google_cfg()
    if not g.get("refresh_token"):
        raise RuntimeError("Google Drive isn't connected.")
    res = requests.post(TOKEN_URL, data={
        "refresh_token": g["refresh_token"],
        "client_id": g["client_id"],
        "client_secret": g["client_secret"],
        "grant_type": "refresh_token",
    }, timeout=15)
    res.raise_for_status()
    return res.json()["access_token"]


def _folder_id(access_token: str) -> str:
    g = _google_cfg()
    if g.get("folder_id"):
        return g["folder_id"]
    headers = {"Authorization": f"Bearer {access_token}"}
    q = f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    res = requests.get(DRIVE_FILES_URL, headers=headers, params={"q": q, "fields": "files(id)"}, timeout=15)
    res.raise_for_status()
    found = res.json().get("files", [])
    if found:
        folder_id = found[0]["id"]
    else:
        res = requests.post(DRIVE_FILES_URL, headers=headers, json={
            "name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder",
        }, timeout=15)
        res.raise_for_status()
        folder_id = res.json()["id"]
    g["folder_id"] = folder_id
    config.save_config(CONFIG)
    return folder_id


def upload_pdf(local_path: str, filename: str) -> str:
    """Uploads one PDF to the "Job Tracker Resumes" Drive folder, overwriting
    a same-named file already there instead of piling up duplicates on
    repeated builds. Returns the file's Drive view link."""
    access_token = _access_token()
    folder_id = _folder_id(access_token)
    headers = {"Authorization": f"Bearer {access_token}"}

    q = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    existing = requests.get(DRIVE_FILES_URL, headers=headers, params={"q": q, "fields": "files(id)"}, timeout=15)
    existing.raise_for_status()
    found = existing.json().get("files", [])

    data = Path(local_path).read_bytes()
    metadata = {"name": filename} if found else {"name": filename, "parents": [folder_id]}
    multipart = {
        "metadata": (None, json.dumps(metadata), "application/json"),
        "file": (filename, data, "application/pdf"),
    }
    if found:
        res = requests.patch(f"{DRIVE_UPLOAD_URL}/{found[0]['id']}?uploadType=multipart",
                              headers=headers, files=multipart, timeout=60)
    else:
        res = requests.post(f"{DRIVE_UPLOAD_URL}?uploadType=multipart",
                             headers=headers, files=multipart, timeout=60)
    res.raise_for_status()
    return f"https://drive.google.com/file/d/{res.json()['id']}/view"
