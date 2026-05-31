# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(SPECPATH)
block_cipher = None

a = Analysis(
    [str(ROOT / 'run.py')],
    pathex=[str(ROOT / 'src')],
    binaries=[],
    datas=[],
    hiddenimports=[
        'phoneclone',
        'phoneclone.main',
        'phoneclone.config',
        'phoneclone.qemu',
        'phoneclone.adb',
        'phoneclone.vnc',
        'phoneclone.display',
        'phoneclone.location',
        'phoneclone.instances',
        'phoneclone.spoof',
        'phoneclone.paths',
        'phoneclone.downloads',
        'phoneclone.setup_wizard',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PhoneClone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
