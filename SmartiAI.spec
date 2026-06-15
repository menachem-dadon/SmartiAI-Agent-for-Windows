# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['smarti_core.pyw'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['quickmachotkey', 'quickmachotkey._MinimalHIToolbox', 'quickmachotkey._MinimalHIToolbox._metadata'],
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
    name='SmartiAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/logo.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SmartiAI',
)
app = BUNDLE(
    coll,
    name='SmartiAI.app',
    icon='assets/logo.png',
    bundle_identifier='com.smartiai.agent',
    info_plist={
        'NSMicrophoneUsageDescription': 'סמארטי זקוק לגישה למיקרופון כדי לאפשר לך לתת פקודות קוליות ולהקליט הודעות בצ\'אט.',
        'NSHighResolutionCapable': 'True',
    },
)
