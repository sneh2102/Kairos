# Job Scraper — desktop GUI

Electron + React + TypeScript UI for the LangGraph job-scraper pipeline in `..`
(the parent `Job-Scraper-LangGraph` folder). Talks to a local FastAPI backend
(`../server.py`) over HTTP + WebSocket — Electron spawns and manages it.

## Run

```
npm install          # once
npm start             # launches Vite + Electron together; backend auto-spawns
```

Requires the parent project's Python venv to already exist with dependencies
installed (`../venv`, `pip install -r ../requirements.txt`).

## Layout

- `electron/main.cjs` — spawns `../venv/Scripts/python.exe -m uvicorn server:app`, waits for `/api/health`, opens the window, kills the backend on quit.
- `electron/preload.cjs` — minimal; the renderer talks to `http://127.0.0.1:8756` directly.
- `src/lib/api.ts` — REST client for the backend.
- `src/lib/eventStream.tsx` — WebSocket client (`/ws/events`) + React Context for live scrape/apply progress, logs, and desktop notifications.
- `src/pages/` — Dashboard, Scraper, Review, Apply, Applied, Resume Data, Settings, Logs.

## Build (dev-mode only for now, no installer)

```
npm run build          # tsc + vite build -> dist/
```
