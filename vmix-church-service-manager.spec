# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\vmix-hymnal-manager\\app.py'],
    pathex=['src/vmix-hymnal-manager'],
    binaries=[],
    datas=[('src/vmix-hymnal-manager/templates', 'templates')],
    hiddenimports=[
        'routes.dashboard',
        'routes.hymns',
        'routes.programs',
        'routes.templates_mgr',
        'routes.api',
        'routes.data_tables',
        'routes.monitoring',
        'routes.settings',
        'services.program_service',
        'services.pptx_service',
        'services.monitoring',
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
    [],
    exclude_binaries=True,
    name='vmix-hymnal-manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon='app.ico',
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
    name='vmix-hymnal-manager',
)
