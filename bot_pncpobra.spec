# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\pncp_bot_obra\\bots\\bot_pncpobra.py'],
    pathex=['src'],
    binaries=[],
    datas=[('src/pncp_bot_obra/config.json', 'pncp_bot_obra'), ('src/pncp_shared/metadata/metadados.db', 'pncp_shared/metadata')],
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
    a.binaries,
    a.datas,
    [],
    name='bot_pncpobra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
