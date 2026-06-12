# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['PS5_FFPFSC_PRO_v1.2.2.py'],
    pathex=[],
    binaries=[],
    datas=[('backend', 'backend')],
    hiddenimports=[
        # Archive support — imported inside try/except so PyInstaller misses them
        'py7zr',
        'py7zr.helpers',
        'py7zr.compressor',
        'rarfile',
        # DnD
        'tkinterdnd2',
        # Pillow image formats
        'PIL._tkinter_finder',
        # Note: pycparser.lextab / pycparser.yacctab warnings are harmless —
        # those are PLY-generated files that pycparser creates lazily at runtime.
        # Adding them here makes no difference; the warnings come from pycparser's own hook.
    ],
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
    a.binaries,
    a.datas,
    [],
    name='PS5_FFPFSC_PRO',
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
)
