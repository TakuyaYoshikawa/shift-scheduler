# -*- mode: python ; coding: utf-8 -*-
"""
shift_scheduler.spec

PyInstaller ビルド設定。
ビルド方法:
    pyinstaller shift_scheduler.spec
成果物: dist/shift_scheduler/ フォルダ（onedir モード）
"""

import os
import pulp

# CBC ソルバーバイナリのパス
CBC_SRC = pulp.apis.PULP_CBC_CMD().path

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[
        (CBC_SRC, "."),  # cbc.exe をルートに配置
    ],
    datas=[
        ("assets", "assets"),  # shift_colors.json 等
    ],
    hiddenimports=[
        "pulp",
        "pulp.apis",
        "pulp.apis.coin_api",
        "holidays",
        "holidays.countries",
        "PyQt6.QtPrintSupport",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="shift_scheduler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUIアプリなのでコンソール非表示
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="shift_scheduler",
)
