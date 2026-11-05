# -*- mode: python ; coding: utf-8 -*-

EXCLUDE = (
    "Qt6WebEngineCore",
    "Qt6WebEngineQuick",
    "Qt6WebEngineQuickDelegatesQml",
    "QtWebEngineProcess",
    "Qt6Pdf",
    "Qt6Quick3D",
    "Qt6Quick3DRuntimeRender",
    "Qt6Quick3DUtils",
    "Qt6Quick3DAssetImport",
    "Qt6Quick3DAssetTools",
    "Qt6Quick3DParticle",
    "Qt6Quick3DEffects",
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('qml', 'qml')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtQuick3D',
        'PySide6.QtQuick3DUtils',
        'PySide6.QtQuick3DAssetImport',
    ],
    noarchive=False,
    optimize=0,
)

a.binaries = [b for b in a.binaries if not any(k in b[0] for k in EXCLUDE)]
a.datas = [d for d in a.datas if not any(k in d[0] for k in EXCLUDE)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InstaAceQml',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
    upx=False,
    name='InstaAceQml',
)
