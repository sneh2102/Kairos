#!/usr/bin/env python
"""Download Playwright browsers to be bundled with the installer."""
import subprocess
import sys
import os
from pathlib import Path

def download_browsers():
    """Download Playwright browsers for bundling with the app."""
    # Browsers go to desktop/build-resources so electron-builder includes them
    browsers_dir = Path("desktop/build-resources/browsers")
    browsers_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading Playwright browsers to {browsers_dir}...")
    print("This may take 5-10 minutes (~200-300MB for Chromium only)...\n")

    # Set PLAYWRIGHT_BROWSERS_PATH so playwright installs to our target directory
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir.resolve())

    # Download chromium only (smallest, most widely compatible)
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        env=env
    )

    if result.returncode != 0:
        print("\nERROR: Failed to download Playwright browsers")
        return False

    # Verify browsers were downloaded
    chromium_dirs = list(browsers_dir.glob("chromium-*"))
    if not chromium_dirs:
        print("\nERROR: Chromium not found after download")
        return False

    # Check size
    size_mb = sum(f.stat().st_size for f in browsers_dir.rglob("*") if f.is_file()) / (1024 * 1024)
    print(f"\n✓ Playwright Chromium bundled successfully")
    print(f"✓ Total size: {size_mb:.0f} MB")
    print(f"✓ Location: {browsers_dir.resolve()}")

    return True

if __name__ == "__main__":
    success = download_browsers()
    sys.exit(0 if success else 1)
