#!/usr/bin/env python
"""Download Tectonic binary to be bundled with the installer."""
import subprocess
import sys
import os
from pathlib import Path
import zipfile
import urllib.request

def download_tectonic():
    """Download Tectonic binary for bundling with the app."""
    tectonic_dir = Path("desktop/build-resources/tectonic")
    tectonic_dir.mkdir(parents=True, exist_ok=True)

    print("Downloading Tectonic binary...")

    # Tectonic v0.14.1 for Windows (latest stable)
    url = "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.14.1/tectonic-0.14.1-x86_64-pc-windows-msvc.zip"
    zip_path = tectonic_dir / "tectonic.zip"

    try:
        print(f"Downloading from {url}...")
        urllib.request.urlretrieve(url, zip_path)
        print(f"Downloaded to {zip_path}")

        # Extract
        print("Extracting...")
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(tectonic_dir)

        # Verify executable exists
        exe_path = tectonic_dir / "tectonic.exe"
        if not exe_path.exists():
            print(f"ERROR: tectonic.exe not found at {exe_path}")
            return False

        # Cleanup zip
        zip_path.unlink()

        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"[OK] Tectonic bundled successfully")
        print(f"[OK] Size: {size_mb:.1f} MB")
        print(f"[OK] Location: {exe_path}")

        return True

    except Exception as e:
        print(f"ERROR: Failed to download Tectonic: {e}")
        return False

if __name__ == "__main__":
    success = download_tectonic()
    sys.exit(0 if success else 1)
