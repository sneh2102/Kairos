# Building & Running Kairos on macOS

A step-by-step guide to get Kairos running on a Mac (Intel or Apple Silicon).
The desktop app runs on macOS as-is in **development mode** — the Electron main
process already picks the right Python/`cloudflared` paths per platform, so no
code changes are needed.

> **Two ways to run:** [Part A](#part-a--desktop-app) gets a working **dev**
> build going (`npm start`) in minutes. [§7](#7-build-a-single-dmg-packaged-app)
> builds a **single self-contained `.dmg`** you can install like any Mac app.
> Both must be done *on a Mac* — the packaged `.dmg` can't be cross-built from
> Windows.

---

## 0. Prerequisites (install once)

Install [Homebrew](https://brew.sh) if you don't have it, then:

```bash
brew install git node python@3.11 tectonic cloudflared
```

| Tool | Why |
|---|---|
| **git** | clone the repo |
| **node** (18+, 20 LTS recommended) | desktop + mobile apps |
| **python@3.11** (3.11+) | the backend / agents |
| **tectonic** | renders résumés to PDF (no full TeX install needed) |
| **cloudflared** | tunnels for the mobile app (optional — Part B only) |

Verify:

```bash
node -v      # v18+  (v20+ ideal)
python3 -V   # 3.11+
tectonic -V
```

---

## Part A — Desktop app

### 1. Clone and create a Python environment

```bash
git clone <this-repo-url>
cd Job-Scraper-LangGraph        # the repo root

python3 -m venv venv
source venv/bin/activate        # macOS

pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

> The venv **must** live at the repo root (`./venv`). The Electron app looks for
> `venv/bin/python` there; if it's missing it falls back to `python3` on your
> PATH.

### 2. Get an Ollama Cloud API key

Sign up at [ollama.com](https://ollama.com) → **Settings → API keys → Create
key**. Copy it. (This is the LLM the agents use — cloud inference, not a local
model.)

### 3. Create your `.env`

```bash
cp .env.example .env
```

Open `.env` and paste your key. You can add more than one — they rotate when a
key hits its rate limit:

```
OLLAMA_API_KEY_1=paste-your-ollama-key-here
```

(Leave `TUNNEL_TOKEN` blank for now — that's Part B.)

### 4. Install the desktop app's dependencies

```bash
cd desktop
npm install
```

### 5. Run it (dev mode)

```bash
npm start
```

This runs Vite + Electron together. Electron spawns the FastAPI backend
(`server.py`) on `127.0.0.1:8756` using your venv's Python, then opens the
window and walks you through onboarding (name, profile, screener rules) on the
**Setup** page. You can also paste the Ollama key on the **Settings** page
instead of editing `.env`.

That's the desktop app fully working on macOS. ✅

### (optional) Compile the frontend without running Electron

```bash
cd desktop
npm run build       # tsc -b && vite build  →  desktop/dist/
```

Useful for a type-check + production bundle of the React app. It does **not**
produce a Mac installer (see §7).

---

## Part B — Mobile app (optional)

Run Kairos on your phone from any network. Do Part A first.

### 6a. Install the mobile app's dependencies

```bash
cd ../mobile
npm install
```

### 6b. `cloudflared` is already on your PATH

You installed it in step 0 (`brew install cloudflared`). The desktop app looks
for a bundled `cloudflared.exe` (Windows only) and otherwise falls back to
`cloudflared` on your PATH — which Homebrew provides. Nothing else to do.

Verify:

```bash
cloudflared -v
```

### 6c. Set a shared secret (`TUNNEL_TOKEN`)

Generate one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the **same value** in **both** places, exactly:

- `.env` → `TUNNEL_TOKEN=<the-value>`
- `mobile/config.ts` → `export const API_TOKEN = "<the-value>";`

They must match — the backend rejects tunnel traffic whose `x-api-token`
header ≠ `TUNNEL_TOKEN`.

> You don't touch `API_BASE` in `config.ts` — the desktop app rewrites it with a
> fresh tunnel URL every time you start the bridge.

### 6d. Install Expo Go on your phone

[Expo Go](https://expo.dev/go) — App Store (iOS) or Play Store (Android).

### 6e. Start the bridge and scan

1. Run the desktop app (`cd desktop && npm start`).
2. Open the **Mobile** tab in the sidebar → click **Start mobile**.
3. Wait for the QR (first run ~20–30s while Metro bundles).
4. Open **Expo Go** and scan it.

**Stop** (or quitting the desktop app) tears the tunnels down.

---

## 7. Build a single `.dmg` (packaged app)

The `mac` / `dmg` target is wired up (`desktop/package.json` → `dist:mac`). The
resulting `.dmg` is **fully self-contained** — it bundles the frozen Python
backend, Tectonic, a portable Chromium, and `cloudflared` inside the `.app`, so
the end user installs nothing else.

> **Must be built on a Mac.** The Python backend and native binaries are
> OS-specific, so you cannot cross-build the macOS `.dmg` from Windows. The
> `.dmg` is also **single-architecture** — build on Apple Silicon for an arm64
> app, on an Intel Mac for x64.

### 7.1 One-time prep

Do [Part A](#part-a--desktop-app) first (venv, deps, Tectonic, cloudflared),
then add the packaging tool:

```bash
source venv/bin/activate
pip install pyinstaller
```

### 7.2 Freeze the Python backend

From the **repo root** (so the spec's relative paths resolve):

```bash
pyinstaller server.spec --distpath dist_backend --workpath build_backend -y
```

This produces `dist_backend/server/server` (the macOS executable + its
libraries) — exactly what `desktop/package.json` bundles.

### 7.3 Put the macOS binaries where the packager looks

electron-builder copies `desktop/build-resources/{tectonic,cloudflared,chromium}`
into the app. Populate them with **Mac** builds:

```bash
cd desktop

# Tectonic + cloudflared (installed via Homebrew in step 0)
mkdir -p build-resources/tectonic build-resources/cloudflared
cp "$(which tectonic)"    build-resources/tectonic/tectonic
cp "$(which cloudflared)" build-resources/cloudflared/cloudflared

# Playwright Chromium (from `playwright install chromium` in Part A).
# PLAYWRIGHT_BROWSERS_PATH points the packaged app at this folder.
mkdir -p build-resources/chromium
cp -R ~/Library/Caches/ms-playwright/chromium* build-resources/chromium/
```

> The binary **names matter** — the app launches `tectonic`, `cloudflared`, and
> `server` (no extension) on macOS. Keep them exactly those names.
> `build-resources/resume-icons/` is platform-agnostic and already in the repo.

### 7.4 Build the DMG

```bash
cd desktop        # if not already there
npm install
npm run dist:mac
```

Output: **`desktop/release/Kairos-<version>.dmg`** — one file, drag-to-Applications.

### 7.5 First launch (unsigned build)

`identity: null` in the config skips code-signing so it builds without an Apple
Developer account — but Gatekeeper will warn on first open. Either **right-click
the app → Open** once, or clear the quarantine flag:

```bash
xattr -dr com.apple.quarantine /Applications/Kairos.app
```

For distribution to *other* people's Macs without that step, you need an Apple
Developer ID and notarization (set `identity` to your signing identity and add
electron-builder `notarize` config) — not required for your own machine.

### 7.6 Optional: app icon

Without one, electron-builder uses the default Electron icon. To brand it, add a
`build/icon.icns` (1024×1024 source) and point `mac.icon` at it in
`desktop/package.json`.

---

## Troubleshooting

**`npm start` opens but the window is blank / "Backend health check timed
out".**
The Python backend didn't start. Confirm the venv is at the repo root and
activated, `pip install -r requirements.txt` succeeded, and try running the
backend directly to see the real error:

```bash
source venv/bin/activate
uvicorn server:app --port 8756
```

**Apple Silicon (M-series): `playwright install chromium` or a dependency
fails.** Make sure you're using an arm64 Python (the Homebrew `python@3.11` is
arm64 on Apple Silicon). Recreate the venv if you previously built it under
Rosetta/x86.

**LaTeX / PDF errors when building a résumé.** Confirm `tectonic -V` works. The
backend auto-detects `tectonic` on your PATH; a first compile downloads
packages, so it needs internet once.

**Mobile: Expo Go hangs forever on the loading bar.** That's a JS bundle that
failed to compile for Hermes (RN's engine). Check the Expo terminal for a red
error and reload after fixing.

**Mobile: `Error 530 / 1033` after scanning.** That's a Cloudflare quick-tunnel
that dropped (they're ephemeral and account-free). In the desktop **Mobile**
tab, click **Stop**, then **Start mobile** to get a fresh tunnel + QR, and
rescan.

---

## Quick reference

```bash
# Backend / CLI (venv activated, from repo root)
python main.py scrape        # scrape + AI-screen jobs
python main.py review        # browse yes/maybe jobs
python main.py apply         # build résumés + apply
uvicorn server:app --port 8756   # just the API

# Desktop (from desktop/)
npm start                    # dev app (Vite + Electron + backend)
npm run build                # compile the React frontend to desktop/dist/

# Mobile (from mobile/)
npm install                  # deps; launched via the desktop Mobile tab
```
