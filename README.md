# Kairos

An AI job-hunting pipeline: scrape postings from a dozen job boards, screen
them against your profile with an LLM, and generate a tailored,
ATS-optimized resume + cover letter for every job worth applying to — all
driven by [LangGraph](https://github.com/langchain-ai/langgraph) multi-agent
graphs. Ships as a desktop app (Electron + React) with a headless CLI
underneath for scripting.

![Review jobs screen — every scraped job with its AI screener verdict and match score](images/Review.jpg)

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Desktop app](#desktop-app)
  - [CLI](#cli)
- [Building a Windows installer](#building-a-windows-installer)
- [Project layout](#project-layout)
- [Supported job boards](#supported-job-boards)
- [Tech stack](#tech-stack)
- [License](#license)

## How it works

Three LangGraph graphs, chained by shared SQLite state:

1. **Scrape graph** (`graph/scrape_graph.py`) — the vendored `jobspy` scraper
   pulls postings from your configured sites/search terms, then a
   **Screener Agent** rates each one (`yes` / `maybe` / `no`) against your
   profile, required skills, and experience level. Results land in `jobs.db`.
2. **Review** (`main.py review` or the desktop Applied/Dashboard views) —
   browse `yes`/`maybe` jobs and override a verdict you disagree with.
3. **Apply graph** (`graph/apply_graph.py`) — for every unbuilt `yes` job:
   Skills/Experience/Project/Custom-Section writer agents draft a resume in
   LaTeX, an **ATS Checker** scores it against the job description, and an
   **Optimizer** agent rewrites weak sections in a loop (up to
   `max_ats_iterations`) until it passes `ats_pass_threshold` or stops
   improving. The final LaTeX is compiled to PDF and the job is marked
   applied in `applied.db`.

All LLM calls go through [Ollama's cloud API](https://ollama.com) via a
rotating multi-key client (`llm/client.py`), so a rate-limited key
automatically falls over to the next one.

## Requirements

- **Python 3.11+**
- **Node.js 18+** and npm (desktop app only)
- An [Ollama](https://ollama.com) account + API key (cloud inference, not a
  local model server)
- A LaTeX engine to render resumes to PDF — either:
  - [Tectonic](https://tectonic-typesetting.github.io/) (no local TeX
    install needed, resolves packages on the fly), or
  - `pdflatex` from a MiKTeX/TeX Live install
- [Playwright](https://playwright.dev/) Chromium (needed for
  cookie-gated sites like Glassdoor/Google jobs)

## Installation

```bash
git clone <this-repo-url>
cd Kairos

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
playwright install chromium
```

Install a LaTeX engine (either works, Tectonic is the path of least
resistance):

```bash
# Tectonic (recommended)
winget install --id TectonicTypesetting.Tectonic   # Windows
# brew install tectonic                             # macOS

# or a full TeX Live/MiKTeX install for pdflatex
```

For the desktop app:

```bash
cd desktop
npm install
```

## Configuration

Nothing to hand-edit before first run — `config.py` auto-copies
[`config.example.json`](config.example.json) to `config.json` (gitignored,
holds your personal profile/prompts) the first time anything imports it.
From there, configure through the desktop app's **Setup** and **Settings**
pages, or edit `config.json` directly:

| Section | Purpose |
|---|---|
| `scraper` | sites to search, location, search terms, results wanted |
| `profile` | your name, contact info, experience, `not_fit_for` roles |
| `screener` | pass/fail thresholds, required/preferred skills, blacklisted companies |
| `pipeline` | ATS iteration limits, output filenames, LaTeX template |
| `prompts` | every LLM prompt (screener, section writers, ATS checker) — user-editable |
| `custom_sections` | resume sections beyond the built-in skills/experience/projects |

Two more inputs live next to `config.json`:

- **`resume.txt`** / **`projects.txt`** — your source resume and project
  list the writer agents draw from.
- **`.env`** — holds `OLLAMA_API_KEY_1`, `OLLAMA_API_KEY_2`, ... (multiple
  keys enable rotation on rate limits). Set via the Settings page, or by
  hand:

  ```
  OLLAMA_API_KEY_1=your-key-here
  ```

## Usage

### Desktop app

```bash
cd desktop
npm start
```

This runs Vite (dev server) and Electron together, with Electron spawning
the FastAPI backend (`server.py`) as a subprocess on `127.0.0.1:8756`. The
app walks you through onboarding (Setup page) on first launch.

### CLI

The headless path — same agents/graphs, no Electron:

```bash
python main.py scrape   # scrape + AI-screen new jobs into jobs.db
python main.py review   # browse yes/maybe jobs, flip a verdict if you disagree
python main.py apply    # build + apply for every unbuilt "yes" job
```

Or run just the API backend (e.g. to point a different frontend at it):

```bash
uvicorn server:app --port 8756
```

## Building a Windows installer

```bash
cd desktop
npm run dist:win
```

This bundles the React app, freezes `server.py` into `server.exe` via
PyInstaller (`server.spec`), and packages both — plus Tectonic, a portable
Chromium, and resume icons — into an NSIS installer with `electron-builder`.
A packaged build stores user data (config/resume/dbs) in the OS per-user
app-data directory instead of next to the executable.

## Project layout

```
agents/       LangGraph agent nodes — screener, resume section writers, ATS checker/optimizer
graph/        Graph wiring (scrape_graph, apply_graph) + state schema
jobspy/       Vendored multi-site job scraper (this repo's own fork)
llm/          Rotating Ollama Cloud client shared by every agent
db/           SQLite-backed JobsDB / AppliedDB managers
tools/        LaTeX compilation + resume template management
desktop/      Electron + React + Tailwind frontend
server.py     FastAPI backend the desktop app talks to
main.py       Headless CLI entry point (scrape / review / apply)
config.py     Loads config.json + .env; config.example.json is the template
```

## Supported job boards

Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs, JobRight, Wellfound,
Naukri, Bayt, BDJobs.

## Tech stack

**Backend:** Python, LangGraph, FastAPI, SQLite, Ollama Cloud, Playwright
**Frontend:** React, TypeScript, Vite, Tailwind CSS, Electron
**Resume rendering:** LaTeX (Tectonic / pdflatex)

## License

MIT — see [LICENSE](LICENSE).
