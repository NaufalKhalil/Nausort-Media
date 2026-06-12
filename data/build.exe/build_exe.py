#!/usr/bin/env python3
"""
build_exe.py — Universal Project-to-EXE Builder
================================================
Letakkan file ini di LUAR folder project Anda, lalu jalankan.
Nama .exe otomatis diambil dari nama folder project.

Struktur contoh:
  /MyProject/          ← folder project (nama ini jadi nama .exe)
    main.py
    ui/
    assets/
  build_exe.py         ← script ini

Cara pakai:
  python build_exe.py
  python build_exe.py --project ./NausortMedia
  python build_exe.py --project ./NausortMedia --onefile
  python build_exe.py --project ./NausortMedia --console
"""

import os
import sys
import subprocess
import argparse
import shutil
from pathlib import Path


# ─────────────────────────────────────────────
# CONFIG — sesuaikan bila perlu
# ─────────────────────────────────────────────
DEFAULT_ENTRY_NAMES = ["main.py", "app.py", "run.py", "start.py"]

# Folder & file yang TIDAK ikut dibundle (hemat ukuran)
EXCLUDE_DIRS  = ["__pycache__", ".git", ".venv", "venv", "env", "node_modules", "dist", "build"]
EXCLUDE_FILES = ["*.pyc", "*.pyo", "*.log", "build_exe.py"]

# Ekstensi data non-Python yang ikut dibundle otomatis
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
    """Cari file entry point (main.py, app.py, dst)."""
    for name in DEFAULT_ENTRY_NAMES:
        candidate = project_dir / name
        if candidate.exists():
            return candidate

    # Fallback: cari .py pertama di root folder
    py_files = sorted(project_dir.glob("*.py"))
    if py_files:
        print(f"[INFO] Entry point tidak ditemukan dari daftar default.")
        print(f"       Menggunakan: {py_files[0].name}")
        return py_files[0]

    raise FileNotFoundError(
        f"Tidak ada file .py ditemukan di {project_dir}.\n"
        f"Pastikan project Anda memiliki salah satu dari: {DEFAULT_ENTRY_NAMES}"
    )


def collect_data_files(project_dir: Path) -> list[tuple[str, str]]:
    """
    Kumpulkan semua file data (non-.py) di dalam project.
    Return list of (src_path, dest_folder) untuk --add-data PyInstaller.
    """
    data_pairs = []
    for root, dirs, files in os.walk(project_dir):
        # Buang folder yang dikecualikan
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        rel_root = Path(root).relative_to(project_dir)

        for file in files:
            suffix = Path(file).suffix.lower()
            if suffix in DATA_EXTENSIONS:
                src = Path(root) / file
                # dest = titik relatif di dalam bundle
                dest = str(rel_root) if str(rel_root) != "." else "."
                data_pairs.append((str(src), dest))

    return data_pairs


def check_pyinstaller():
    """Pastikan PyInstaller terinstall."""
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


def build(project_dir: Path, onefile: bool, console: bool, icon_path: Path | None):
    """Jalankan PyInstaller."""
    app_name   = project_dir.name          # ← nama folder = nama .exe
    entry      = find_entry_point(project_dir)
    data_files = collect_data_files(project_dir)

    print(f"\n{'='*55}")
    print(f"  Aplikasi   : {app_name}")
    print(f"  Entry point: {entry.relative_to(project_dir.parent)}")
    print(f"  Mode       : {'Onefile' if onefile else 'Onedir'}")
    print(f"  Console    : {'Ya' if console else 'Tidak (windowed)'}")
    print(f"  Data files : {len(data_files)} file ditemukan")
    if icon_path:
        print(f"  Icon       : {icon_path}")
    print(f"{'='*55}\n")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(entry),
        "--name", app_name,
        "--distpath", str(project_dir.parent / "dist"),
        "--workpath", str(project_dir.parent / "build"),
        "--specpath", str(project_dir.parent),
        "--noconfirm",
        "--clean",
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if not console:
        cmd.append("--windowed")

    # Tambahkan data files
    sep = ";" if sys.platform == "win32" else ":"
    for src, dest in data_files:
        cmd += ["--add-data", f"{src}{sep}{dest}"]

    # Tambahkan icon kalau ada
    if icon_path and icon_path.exists():
        cmd += ["--icon", str(icon_path)]
    else:
        # Cari icon otomatis di dalam project
        for ext in [".ico", ".png"]:
            candidates = list(project_dir.rglob(f"*{ext}"))
            if candidates:
                cmd += ["--icon", str(candidates[0])]
                print(f"[INFO] Icon otomatis: {candidates[0].relative_to(project_dir)}")
                break

    print("[RUN]", " ".join(cmd))
    print()

    result = subprocess.run(cmd)

    dist_path = project_dir.parent / "dist" / app_name
    exe_file  = project_dir.parent / "dist" / (app_name + ".exe")

    print()
    if result.returncode == 0:
        print("✅  Build BERHASIL!")
        if exe_file.exists():
            print(f"    File EXE : {exe_file}")
        elif dist_path.exists():
            print(f"    Folder   : {dist_path}")
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
        "--project", "-p",
        default=None,
        help="Path ke folder project. Default: folder di samping script ini."
    )
    parser.add_argument(
        "--onefile", "-F",
        action="store_true",
        default=False,
        help="Buat satu file .exe saja (lebih lambat startup, mudah didistribusi)."
    )
    parser.add_argument(
        "--console", "-c",
        action="store_true",
        default=False,
        help="Tampilkan jendela console/terminal (default: windowed/GUI)."
    )
    parser.add_argument(
        "--icon", "-i",
        default=None,
        help="Path ke file icon (.ico atau .png). Opsional."
    )
    args = parser.parse_args()

    # ── Tentukan folder project ──────────────────────────────
    if args.project:
        project_dir = Path(args.project).resolve()
    else:
        # Cari folder project: folder pertama di samping script ini
        script_dir = Path(__file__).parent.resolve()
        candidates = [
            d for d in script_dir.iterdir()
            if d.is_dir() and d.name not in EXCLUDE_DIRS
        ]
        if not candidates:
            print("❌  Tidak ada folder project ditemukan di samping script ini.")
            print("    Gunakan: python build_exe.py --project <path_ke_folder>")
            sys.exit(1)

        if len(candidates) == 1:
            project_dir = candidates[0]
        else:
            print("Ditemukan beberapa folder. Pilih project yang ingin di-build:\n")
            for i, c in enumerate(candidates, 1):
                print(f"  [{i}] {c.name}")
            print()
            while True:
                try:
                    choice = int(input("Masukkan nomor pilihan: "))
                    project_dir = candidates[choice - 1]
                    break
                except (ValueError, IndexError):
                    print("    Pilihan tidak valid, coba lagi.")

    if not project_dir.is_dir():
        print(f"❌  Folder tidak ditemukan: {project_dir}")
        sys.exit(1)

    icon_path = Path(args.icon).resolve() if args.icon else None

    check_pyinstaller()
    build(project_dir, onefile=args.onefile, console=args.console, icon_path=icon_path)


if __name__ == "__main__":
    main()
