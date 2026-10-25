# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui.py'],
    pathex=['instbox'],
    binaries=[],
    # ★ 不要把 ('instbox', 'instbox') 放进 datas：
    #   instbox 两个模块已由 hiddenimports 编译进 PYZ，运行时用
    #   sys._MEIPASS 找不到它们也没关系（_load_inst_modules 走正常 import）。
    #   作为 datas 打包时 PyInstaller 会把 .py 源码连同其 __pycache__ 一起塞进
    #   PKG，而编译该 .py 时 co_filename 记录的是【构建机绝对路径】，
    #   例如 <仓库根>\source\InstaAceImporter\instbox\xxx.py 这类开发机路径，
    #   等于把开发者的本机目录结构随发布物流出。
    datas=[('assets', 'assets')],
    hiddenimports=['inst_transplant', 'moov_rewrap'],
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
    name='InstaAceImporter',
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
    icon=['assets/app.ico'],
)
