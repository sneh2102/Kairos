[33mcommit 69f6ce1c04cbbe7a267541ea3da710eacbcc3912[m[33m ([m[1;36mHEAD[m[33m -> [m[1;32mfeature/desktop-bg-runner[m[33m)[m
Author: Krishna Vaibhav <krishvaibav@gmail.com>
Date:   Sat Oct 3 14:03:50 2026 -0400

    fix: auto-install Playwright browsers on first run for packaged app
    
    - Add background initialization to install Playwright browsers
    - Prevents 'Executable doesn't exist' errors on first scrape
    - Runs silently in background without blocking app startup
    - Falls back gracefully if installation fails

[33mcommit 0ef64a63ae4c495cdfd5f9ad5ad6ac32a0a70ff5[m
Author: Krishna Vaibhav <krishvaibav@gmail.com>
Date:   Sat Oct 3 13:49:39 2026 -0400

    fix: add config migration and defensive error handling for missing keys
    
    - Add automatic migration to seed missing 'pipeline' key in old configs
    - Fix get_resume_data and put_resume_data to use .get() with defaults
    - Prevent KeyError crashes when accessing CONFIG['pipeline']
    - Improve resilience for incomplete config files
    - Use sensible defaults that match config.example.json

[33mcommit ffc3dbbd600eaccb041fc15f33280d9532a17b78[m
Author: Krishna Vaibhav <krishvaibav@gmail.com>
Date:   Sat Oct 3 13:42:51 2026 -0400

    fix: improve backend path resolution and NSIS installer config
    
    - Make backend executable path lookup more robust with fallback locations
    - Add explicit NSIS configuration for consistent installation directory
    - Better error messages showing all searched paths
    - Handle both possible directory structure layouts

[33mcommit 0ce96ac97213a4b0947827b978928e54903e7e3d[m
Author: Krishna Vaibhav <krishvaibav@gmail.com>
Date:   Sat Oct 3 13:32:07 2026 -0400

    fix: resolve critical packaging bugs preventing bundled app from working
    
    Fixed 7 critical bugs that prevented the packaged .exe from functioning:
    
    1. Backend executable path: Corrected path from
       resources/backend/server.exe to resources/backend/server/server.exe
       (Bug #3 - Critical)
    
    2. Silent backend failures: Added error dialog when backend fails to start,
       instead of silently logging error and continuing (Bug #1 - Critical)
    
    3. Backend output logging: All backend stdout/stderr now logged to
       app.log file in userData directory for debugging (Bug #2 - High)
    
    4. Backend working directory: Changed from executable's _internal folder
       to userData folder to prevent path lookup issues (Bug #4 - Medium)
    
    5. Config file bundling: Added config.example.json to extraResources
       so it's included in packaged app and used to seed config.json (Bug #5 - Medium)
    
    6. Backend crash recovery: Added error dialog when backend crashes after
       startup, with log file path for investigation (Bug #6 - Medium)
    
    7. Improved health check errors: Now includes backend error code and
       specific failure reasons to help with debugging (Enhancement)
    
    Changes:
    - desktop/electron/main.cjs: Complete error handling overhaul
      - File logging for all backend I/O
      - Error dialogs for startup failures
      - Backend crash detection and recovery
      - Better health check error messages
    
    - desktop/package.json: Bundle config.example.json as resource
    
    - config.py: Enhanced config.example.json lookup to work in packaged
      mode, with fallback search paths for PyInstaller bundles
    
    The packaged app will now:
    ✓ Show clear error messages if backend fails
    ✓ Log all errors to app.log for debugging
    ✓ Detect and alert on backend crashes
    ✓ Properly seed config.json on first run
    ✓ Handle all edge cases gracefully

[33mcommit 722f9c1e76a5559518d4a6190c34a2a416a5a7c8[m[33m ([m[1;31morigin/feature/desktop-bg-runner[m[33m)[m
Author: Krishna Vaibhav <krishvaibav@gmail.com>
Date:   Sun Aug 30 19:44:47 2026 -0400

    feat: enhance job scraping with concurrency limits and improved logging

[33mcommit f4feb48ce8573221923b6567ae433dce22ad1d8c[m
Author: Krishna Vaibhav <krishvaibav@gmail.com>
Date:   Sun Aug 30 10:55:42 2026 -0400

    feat: implement validation for GitHub and Ollama API keys in settings and setup

[33mcommit 1c4b00142f9c22e1e5e35e736d47914dc2b04820[m
Author: Krishna Vaibhav <krishvaibav@gmail.com>
Date:   Sun Aug 30 07:39:26 2026 -0400

    fix: prevent config clobbering during settings save and improve background run handling

[33mcommit 3072dfbbe610c9c427d1239da48aaa3c99a8537c[m
Author: Krishna Vaibhav <krishvaibav@gmail.com>
Date:   Sun Aug 30 06:35:23 2026 -0400

    feat: add desktop settings for background running and startup launch

[33mcommit 86d10f7541d9d10fe6f7d54ec943a2759b055fe6[m
Merge: cb277bd d6a5ab2
Author: Sneh Jayeshbhai Patel <125440906+sneh2102@users.noreply.github.com>
Date:   Sat Jul 18 02:02:44 2026 -0300

    Merge pull request #4 from sneh2102/feat/custom-section-rebuilder
    
    CI: fetch Tectonic via gh CLI to dodge the unauthenticated API rate l…

[33mcommit cb277bd94671736aae1729408d968999a30276d2[m
Merge: a02deac 026cf34
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Sat Jul 18 01:58:45 2026 -0300

    Merge origin/main into main: combine rebuilder/mobile with the Tectonic CI fix
    
    origin/main (PR #3) carried the section rebuilder + mobile app but merged
    before the Tectonic gh-release CI fix; local main had the fix. This merge
    brings both together so main has every feature and a green workflow.

[33mcommit a02deac1f5f0340451737da0f9382cb875608acb[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Sat Jul 18 01:39:49 2026 -0300

    CI: fetch Tectonic via gh CLI to dodge the unauthenticated API rate limit
    
    The raw api.github.com releases call was getting rate-limited on the runners,
    returning an error object so jq saw .assets as null and failed. Use gh release
    download (preinstalled, auth'd with github.token) with an asset pattern.

[33mcommit d6a5ab2ca427e4a2d5d0a7ad3dc06515335ec66a[m[33m ([m[1;31morigin/feat/custom-section-rebuilder[m[33m)[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Sat Jul 18 01:39:49 2026 -0300

    CI: fetch Tectonic via gh CLI to dodge the unauthenticated API rate limit
    
    The raw api.github.com releases call was getting rate-limited on the runners,
    returning an error object so jq saw .assets as null and failed. Use gh release
    download (preinstalled, auth'd with github.token) with an asset pattern.

[33mcommit 026cf342631dca6ac72cee8937650620b5c60af9[m
Merge: 6b687c4 53b0654
Author: Sneh Jayeshbhai Patel <125440906+sneh2102@users.noreply.github.com>
Date:   Sat Jul 18 01:12:15 2026 -0300

    Merge pull request #3 from sneh2102/feat/custom-section-rebuilder
    
    Feat/custom section rebuilder

[33mcommit 53b06542bb0af1deccc77df346200afb54a224f7[m
Merge: c74f1bf 6b687c4
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Sat Jul 18 01:04:26 2026 -0300

    Merge branch 'main' into feat/custom-section-rebuilder

[33mcommit c74f1bff23557edb7728338e113aadf98b23182b[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Sat Jul 18 00:30:01 2026 -0300

    Rebuilder: cover core writer sections, not just custom ones
    
    The dropdown listed only config custom sections (e.g. Summary). Add a
    /api/rebuildable-sections endpoint returning Skills/Experience/Projects plus
    custom sections, and dispatch each in rebuild-section: core sections use their
    writer's surgical rebuild when a message is given (else a fresh write), custom
    sections regenerate with the message as an instruction. find_section locates
    the target block by id and its real heading so the fresh block splices back in
    place.

[33mcommit a6bc4b91a45e1bbc93a0dcc2bb5c820afb8cb8b9[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Sat Jul 18 00:04:22 2026 -0300

    Add custom-section rebuilder to the LaTeX editor
    
    Lets you regenerate a single custom resume section for a built job from the
    editor, optionally steered by a free-text instruction; leaving it blank just
    rebuilds the section with its own prompts. The fresh block is spliced into the
    editor's current LaTeX (in place, via latex.replace_section) and returned for
    review before Compile & Save — nothing is persisted until then. The user
    instruction is applied above the non-negotiable experience-years honesty rule
    so it can't inflate seniority.

[33mcommit 6b687c43471033a1d091d7519b5a667f67f25768[m
Merge: 81ced15 f5e2d05
Author: Sneh Jayeshbhai Patel <125440906+sneh2102@users.noreply.github.com>
Date:   Fri Jul 17 21:07:58 2026 -0300

    Merge pull request #2 from sneh2102/ci/build-desktop
    
    Ci/build desktop

[33mcommit f5e2d057dfefbae3b3d5e55f94381a3234d2c6ba[m[33m ([m[1;31morigin/ci/build-desktop[m[33m)[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Fri Jul 17 21:06:53 2026 -0300

    Fix macOS PyInstaller build: locate tls_client libs by import
    
    The glob over venv/**/tls_client/dependencies resolved to a Windows-style
    path on the macOS runner and PyInstaller couldn't find it. Use PyInstaller's
    collect_data_files('tls_client') instead, which finds the package by import
    and bundles its native libs regardless of OS or venv layout.

[33mcommit a96523ff2312b9036fd71bf813ed10382113f5fe[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Fri Jul 17 20:48:19 2026 -0300

    Add mobile app, macOS build guide, and desktop mobile-bridge support
    
    Adds the Expo mobile app (mobile/) that reaches the desktop backend over
    a Cloudflare tunnel, the desktop Mobile page and Electron bridge that
    starts the tunnel and mints a per-install token, and BUILD-MACOS.md.
    Ships mobile/config.ts with empty placeholders — the desktop app fills in
    the tunnel URL and token at runtime.

[33mcommit 81ced151e10deb6dbe77e91a3e31ec81a124384d[m
Merge: 6ff133e 486176d
Author: Sneh Jayeshbhai Patel <125440906+sneh2102@users.noreply.github.com>
Date:   Fri Jul 17 20:43:06 2026 -0300

    Merge pull request #1 from sneh2102/ci/build-desktop
    
    Add GitHub Actions CI to build Windows .exe and macOS .dmg

[33mcommit 486176d655d2f179e85352229a64f53b9c47b2ea[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Fri Jul 17 19:48:43 2026 -0300

    Add GitHub Actions CI to build Windows .exe and macOS .dmg
    
    Builds the desktop installers on tag push (v*) or manual dispatch:
    freeze the backend with PyInstaller, fetch the OS-specific native
    binaries (Chromium/Tectonic/cloudflared) into build-resources, then
    run electron-builder. Track the small resume-icons source assets so
    CI has them; heavy binaries stay gitignored and are fetched per run.

[33mcommit 6ff133e297a41e0add014b3bff2beb7862900e85[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Wed Jul 8 19:51:47 2026 -0300

    Add MIT license

[33mcommit cf9f40ec840228e6ab9d2345e979bf8feaabd465[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Wed Jul 8 19:44:07 2026 -0300

    Add overview screenshot to README

[33mcommit 8626e8121ad660a8ec1abad4d047c62a83017995[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Wed Jul 8 19:31:14 2026 -0300

    Add README with Review jobs screenshot

[33mcommit a7a1cbe3e9799aa222bb1544301264fd25a09523[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Wed Jul 8 12:59:05 2026 -0300

    Add job board, province, resume and years-of-experience filters to review jobs; preserve filters and scroll on back navigation

[33mcommit db02a6de86071119be49a5ce43d96f05d96bf88b[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Tue Jul 7 22:21:07 2026 -0300

    Improve writer prompts, move API keys to config.json, hard blacklist checks, fix setup wizard loop
    
    - Rewrite experience/projects/skills/cover-letter prompts: exact JD keyword
      casing, acronym dual-forms, reframe-not-invent guardrails, human tone rules
    - Store Ollama API keys in config.json (api_keys) with one-time .env migration
      and legacy fallback; put_config preserves api_keys if a stale client omits them
    - Blacklisted companies are hard-rejected before the LLM call; new cleanup
      action on Review jobs removes all jobs from blacklisted companies
    - Setup wizard no longer relaunches after finishing (onboarded flag now
      updates in-memory, no app restart needed)

[33mcommit 26d1f17dd62021424baa85a8d53e5c7894e63f0d[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Mon Jul 6 12:27:59 2026 -0300

    updated Ui

[33mcommit c85ede6cd760677ca1267539bbf99361e8a071b1[m
Author: Sneh Patel <patel.sneh2102@gmail.com>
Date:   Fri Jul 3 17:33:30 2026 -0300

    Langgraph version of the project
