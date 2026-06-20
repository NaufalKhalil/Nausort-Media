#!/usr/bin/env python3
"""
build_exe.py — Universal Project-to-EXE Builder
================================================
Letakkan file ini DI DALAM folder project Anda.
Nama .exe otomatis diambil dari nama folder tempat script ini berada.

Struktur contoh:
  📁 Nausort Media v1.0/    ← nama folder ini = nama .exe
      main.py
      build_exe.py          ← script ini ada di sini
      📁 ui/
          index.html
          script.js
          style.css
          📁 assets/

Cara pakai (dari dalam folder project):
  python build_exe.py                  ← onefile (default)
  python build_exe.py --onedir         ← mode folder+exe
  python build_exe.py --console        ← tampilkan terminal
  python build_exe.py --icon ui/assets/icon.ico
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DEFAULT_ENTRY_NAMES = ["main.py", "app.py", "run.py", "start.py"]

EXCLUDE_DIRS = [
    "__pycache__", ".git", ".venv", "venv", "env",
    "node_modules", "dist", "build", ".idea", ".vscode",
]

DATA_EXTENSIONS = [
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".bmp", ".webp",
    ".html", ".css", ".js", ".json", ".xml", ".yaml", ".yml",
    ".txt", ".md", ".csv",
    ".ttf", ".otf", ".woff", ".woff2",
    ".wav", ".mp3", ".ogg", ".mp4",
    ".db", ".sqlite", ".sqlite3",
    ".pdf",
]
# ─────────────────────────────────────────────


def find_entry_point(project_dir: Path) -> Path:
    for name in DEFAULT_ENTRY_NAMES:
        candidate = project_dir / name
        if candidate.exists():
            return candidate

    py_files = sorted(
        f for f in project_dir.glob("*.py")
        if f.name != "build_exe.py"
    )
    if py_files:
        print(f"[INFO] Entry point default tidak ditemukan.")
        print(f"       Menggunakan: {py_files[0].name}")
        return py_files[0]

    raise FileNotFoundError(
        f"Tidak ada file .py ditemukan di {project_dir}.\n"
        f"Pastikan ada salah satu dari: {DEFAULT_ENTRY_NAMES}"
    )


def collect_data_files(project_dir: Path) -> list:
    data_pairs = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel_root = Path(root).relative_to(project_dir)
        for file in files:
            if file == "build_exe.py":
                continue
            suffix = Path(file).suffix.lower()
            if suffix in DATA_EXTENSIONS:
                src  = Path(root) / file
                dest = str(rel_root) if str(rel_root) != "." else "."
                data_pairs.append((str(src), dest))
    return data_pairs


def check_pyinstaller():
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            check=True, capture_output=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[INFO] PyInstaller belum terinstall. Menginstall sekarang...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True
        )


def auto_find_icon(project_dir: Path):
    for ext in [".ico", ".png"]:
        candidates = [
            p for p in project_dir.rglob(f"*{ext}")
            if not any(part in EXCLUDE_DIRS for part in p.parts)
        ]
        if candidates:
            icon_named = [c for c in candidates if "icon" in c.stem.lower()]
            return icon_named[0] if icon_named else candidates[0]
    return None


def build(project_dir: Path, onefile: bool, console: bool, icon_path):
    app_name   = project_dir.name
    entry      = find_entry_point(project_dir)
    data_files = collect_data_files(project_dir)
    dist_dir   = project_dir / "dist"
    build_dir  = project_dir / "build"

    resolved_icon = icon_path or auto_find_icon(project_dir)

    print(f"\n{'='*55}")
    print(f"  Aplikasi   : {app_name}")
    print(f"  Entry point: {entry.name}")
    print(f"  Mode       : {'Onefile ✅ (1 file .exe, bisa dipindah bebas)' if onefile else 'Onedir (folder+exe)'}")
    print(f"  Console    : {'Ya' if console else 'Tidak (windowed/GUI)'}")
    print(f"  Data files : {len(data_files)} file")
    print(f"  Icon       : {resolved_icon.relative_to(project_dir) if resolved_icon else 'tidak ada'}")
    print(f"  Output     : {dist_dir}")
    print(f"{'='*55}\n")

    sep = ";" if sys.platform == "win32" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(entry),
        "--name",      app_name,
        "--distpath",  str(dist_dir),
        "--workpath",  str(build_dir),
        "--specpath",  str(project_dir),
        "--noconfirm",
        "--clean",
        "--onefile" if onefile else "--onedir",
    ]

    if not console:
        cmd.append("--windowed")

    for src, dest in data_files:
        cmd += ["--add-data", f"{src}{sep}{dest}"]

    if resolved_icon and resolved_icon.exists():
        cmd += ["--icon", str(resolved_icon)]

    print("[RUN]", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    print()

    result = subprocess.run(cmd)

    print()
    if result.returncode == 0:
        print("✅  Build BERHASIL!")
        if onefile:
            exe = dist_dir / (app_name + ".exe")
            print(f"    File EXE  : {exe}")
            print(f"\n    Siap dirilis! File .exe bisa dipindah/dibagikan ke mana saja.")
        else:
            folder = dist_dir / app_name
            print(f"    Folder    : {folder}")
            print(f"\n    Siap dirilis! Zip seluruh folder '{app_name}' lalu bagikan.")
    else:
        print("❌  Build GAGAL. Periksa pesan error di atas.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Universal Python Project → EXE Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        default=False,
        help="Mode folder+exe (startup lebih cepat, harus dipindah satu folder). Default: onefile."
    )
    parser.add_argument(
        "--console", "-c",
        action="store_true",
        default=False,
        help="Tampilkan window console/terminal (default: windowed/GUI mode)."
    )
    parser.add_argument(
        "--icon", "-i",
        default=None,
        help="Path ke file icon (.ico / .png). Jika tidak diisi, dicari otomatis."
    )
    args = parser.parse_args()

    # onefile = default, kecuali --onedir diberikan
    onefile = not args.onedir

    project_dir = Path(__file__).parent.resolve()
    icon_path   = Path(args.icon).resolve() if args.icon else None

    print(f"[INFO] Folder project : {project_dir}")
    print(f"[INFO] Nama aplikasi  : {project_dir.name}")
    print(f"[INFO] Mode build     : {'Onefile (default)' if onefile else 'Onedir'}")

    check_pyinstaller()
    build(project_dir, onefile=onefile, console=args.console, icon_path=icon_path)


if __name__ == "__main__":
    main()
