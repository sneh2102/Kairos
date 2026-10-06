"""Minimal self-check for tools/google_drive.py's OAuth state handling and the
upload-vs-overwrite branch — the two places a bug would either leak a Drive
upload to the wrong account or silently duplicate files. No live network
calls: requests.get/post/patch are monkeypatched.
"""
from unittest.mock import patch

from config import CONFIG
from tools import google_drive as gd


class FakeResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


def _with_google_config(client_id="cid", client_secret="secret", **extra):
    CONFIG["google"] = {"client_id": client_id, "client_secret": client_secret, **extra}


def test_start_auth_url_carries_client_id_and_state():
    _with_google_config()
    url = gd.start_auth()
    assert "client_id=cid" in url
    assert f"state={gd._pending_state}" in url
    assert gd._pending_state is not None


def test_finish_auth_rejects_mismatched_state():
    _with_google_config()
    gd.start_auth()
    try:
        gd.finish_auth("some-code", "not-the-real-state")
        assert False, "expected a state-mismatch RuntimeError"
    except RuntimeError as e:
        assert "state" in str(e).lower()


def test_upload_pdf_overwrites_existing_file_via_patch():
    _with_google_config(refresh_token="rt", folder_id="folder123")
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResponse({"files": [{"id": "existing-file-id"}]})

    def fake_patch(url, headers=None, files=None, timeout=None):
        calls.append(("PATCH", url))
        return FakeResponse({"id": "existing-file-id"})

    def fake_post(url, headers=None, params=None, json=None, data=None, timeout=None):
        # only the token refresh should POST here; the upload itself must PATCH
        if "oauth2" in url:
            return FakeResponse({"access_token": "at"})
        calls.append(("POST", url))
        return FakeResponse({"id": "new-file-id"})

    with patch.object(gd.requests, "get", fake_get), \
         patch.object(gd.requests, "post", fake_post), \
         patch.object(gd.requests, "patch", fake_patch), \
         patch("pathlib.Path.read_bytes", lambda self: b"%PDF-1.4 fake"):
        link = gd.upload_pdf("fake/resume.pdf", "Acme - Resume.pdf")

    assert calls == [("PATCH", f"{gd.DRIVE_UPLOAD_URL}/existing-file-id?uploadType=multipart")]
    assert link == "https://drive.google.com/file/d/existing-file-id/view"


def demo():
    test_start_auth_url_carries_client_id_and_state()
    test_finish_auth_rejects_mismatched_state()
    test_upload_pdf_overwrites_existing_file_via_patch()
    print("google_drive self-check: OK")


if __name__ == "__main__":
    demo()
