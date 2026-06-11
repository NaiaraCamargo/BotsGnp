# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\pncp_planilha_desktop\\gerar_planilha.py'],
    pathex=['src'],
    binaries=[],
    datas=[('src/pncp_planilha_desktop/gerar_planilha.html', 'pncp_planilha_desktop'), ('src/pncp_bot_obra/config.json', 'pncp_bot_obra'), ('src/pncp_shared/metadata/metadados.db', 'pncp_shared/metadata')],
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
    name='gerar_planilha',
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
