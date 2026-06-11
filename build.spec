# ============================================================
#  Nausort Media v2.0 — PyInstaller build spec
#  Run:  pyinstaller build.spec
#  Output: dist\Nausort Media\Nausort Media.exe
# ============================================================

import os
block_cipher = None

# All UI files bundled into the exe
ui_datas = []
for root, dirs, files in os.walk('ui'):
    for f in files:
        src  = os.path.join(root, f)
        dest = root.replace('\\', '/')
        ui_datas.append((src, dest))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=ui_datas,
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',   # Windows
        'webview.platforms.cocoa',      # macOS
        'webview.platforms.gtk',        # Linux
        'PIL',
        'PIL.Image',
        'PIL._imaging',
        'clr',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Nausort Media',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='ui/assets/icon.ico',   # use icon.ico if available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Nausort Media',
)
