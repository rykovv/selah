# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\selah\\app.py'],
    pathex=['src/selah'],
    binaries=[],
    datas=[
        ('src/selah/templates', 'templates'),
        ('src/selah/static', 'static'),
    ],
    hiddenimports=[
        'config_file',
        'paths',
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
        'services.updater',
        'services.autostart',
        'services.appcontrol',
        'services.logbuffer',
        'services.hymn_set_service',
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
    name='selah',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # Windowed: the installed app runs in the background (autostart-friendly);
    # server logs go to %LOCALAPPDATA%\Selah\logs
    console=False,
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
    name='selah',
)
