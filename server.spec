# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

# tls_client ships its native libs in tls_client/dependencies. Locate the
# package by import (not by globbing the venv), so this resolves regardless of
# OS or venv layout (Windows venv/Lib vs macOS/Linux venv/lib/pythonX.Y).
_tls_datas = collect_data_files('tls_client')

a = Analysis(
    ['run_server.py'],
    pathex=[],
    binaries=[],
    datas=[('config.example.json', '.')] + _tls_datas,
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
