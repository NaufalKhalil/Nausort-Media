# ============================================================
#  Nausort Media v1.0 — PyInstaller build spec
# ============================================================

import os

block_cipher = None

APP_NAME = "Nausort Media v1.0"

# ============================================================
# Collect UI files
# ============================================================
ui_datas = []
for root, dirs, files in os.walk('ui'):
    for f in files:
        src = os.path.join(root, f)
        dest = root.replace('\\', '/')
        ui_datas.append((src, dest))

# ============================================================
# Analysis
# ============================================================
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=ui_datas,
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.cocoa',
        'webview.platforms.gtk',
        'PIL',
        'PIL.Image',
        'PIL._imaging',
        'clr',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ============================================================
# EXE (nama file .exe)
# ============================================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,          # 👉 Nausort Media v1.0.exe
    debug=False,
    console=False,
    icon='ui/assets/icon.ico' if os.path.exists('ui/assets/icon.ico') else None,
)

# ============================================================
# COLLECT (folder output)
# ============================================================
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name=APP_NAME,          # 👉 folder dist\Nausort Media v1.0\
)