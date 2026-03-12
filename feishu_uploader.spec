# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


APP_NAME = "飞书附件批量上传"
ICON_PATH = "build/macos/AppIcon.icns"

datas = collect_data_files("playwright")
datas += [("media/icon.png", "media")]
hiddenimports = collect_submodules("playwright")

a = Analysis(
    ["app_main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name=APP_NAME,
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
    icon=ICON_PATH,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=ICON_PATH,
    bundle_identifier="local.feishu.videoattachmentuploader",
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        "NSHighResolutionCapable": True,
    },
)
