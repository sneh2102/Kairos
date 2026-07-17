# -*- mode: python ; coding: utf-8 -*-

import glob

# tls_client ships per-OS native libs; the venv layout differs by platform
# (Windows: venv/Lib/site-packages/..., macOS/Linux: venv/lib/pythonX.Y/site-packages/...).
# Glob both so the same spec freezes on Windows and macOS.
_tls = glob.glob('venv/**/tls_client/dependencies', recursive=True)
_tls_binaries = [(_tls[0], 'tls_client/dependencies')] if _tls else []

a = Analysis(
    ['run_server.py'],
    pathex=[],
    binaries=_tls_binaries,
    datas=[('config.example.json', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='server',
)
