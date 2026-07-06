"""PyInstaller entrypoint for the packaged build. `server.py` exposes the
FastAPI `app` for `uvicorn server:app` (dev mode's CLI invocation) — a frozen
exe needs a concrete `__main__` instead, so this just calls uvicorn directly.
"""
import os

import uvicorn

from server import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8756)))
