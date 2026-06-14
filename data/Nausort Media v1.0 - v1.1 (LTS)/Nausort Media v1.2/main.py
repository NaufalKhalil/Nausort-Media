"""
Nausort Media v1.2

=> Updates v1.2 :
- Undo now restores file to its original position in the photo list
- Undo/Redo are now mutex-locked to prevent double-trigger via simultaneous keyboard shortcut and UI button press
- Ctrl+Z and Ctrl+Y now respect e.repeat, preventing multiple undo/redo from firing when the key is held down
- Preload threads replaced with a single daemon worker + queue, eliminating race conditions when navigating quickly
- Import session ID prevents stale preload jobs from a previous folder polluting the cache after a new folder is imported
- Redo now handles filename conflicts using Keep Both numbering, matching the behaviour of the normal sort operation
- Sorting into the same folder as the source is now blocked with a warning
- Consecutive corrupt files are now auto-skipped without requiring repeated user interaction
- Category shortcuts and Undo/Redo are now no-ops when no photos are loaded
- Rename category no longer writes to disk when the name is unchanged
- A warning is logged when a missing destination folder is auto-recreated
- Windows MAX_PATH (260 chars) is validated before each file move
- Auto-install of pip packages is skipped when running as a frozen EXE
"""

# ── Auto-install ──────────────────────────────────────────
import subprocess, sys

REQUIRED = ["pywebview", "Pillow"]

def _install_missing():
    # Fix #14: Skip auto-install entirely when running as a compiled EXE
    # (PyInstaller/Nuitka set sys.frozen). Installing packages at runtime
    # inside a frozen bundle is unnecessary, slower, and can trigger
    # antivirus false positives.
    if getattr(sys, "frozen", False):
        return
    for pkg in REQUIRED:
        mod = {"pywebview": "webview", "Pillow": "PIL"}.get(pkg, pkg)
        try:
            __import__(mod)
        except ImportError:
            print(f"[INSTALL] {pkg} ...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg, "-q"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

_install_missing()

# ── Imports ───────────────────────────────────────────────
import base64, io, json, os, platform, queue, shutil, subprocess, threading, time
from collections import deque
import webview
from PIL import Image

# ── Paths ─────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR   = os.path.join(BASE_DIR, "ui")

# Data folder: Documents\Nausort Media  (cross-platform fallback)
def _get_data_dir():
    if platform.system() == "Windows":
        docs = os.path.join(os.path.expanduser("~"), "Documents")
    elif platform.system() == "Darwin":
        docs = os.path.join(os.path.expanduser("~"), "Documents")
    else:
        docs = os.path.join(os.path.expanduser("~"), "Documents")
    path = os.path.join(docs, "Nausort Media")
    os.makedirs(path, exist_ok=True)
    return path

DATA_DIR     = _get_data_dir()
CONFIG_FILE  = os.path.join(DATA_DIR, "settings.json")
CONFIG_BACKUP = os.path.join(DATA_DIR, "settings.bak.json")

# ── Constants ─────────────────────────────────────────────
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")

# Preload cache: how many neighbouring images (besides current) are
# kept fully decoded in memory at once. Keeps memory usage bounded
# even when browsing folders with thousands of photos.
CACHE_LIMIT      = 6
PRELOAD_MAX_SIZE = (1600, 1200)   # downscale cached images to save RAM

DEFAULT_CONFIG = {
    "categories": [
        {"name": "Category 1", "folder": "", "color": "#2a2a2a", "shortcut": ""},
        {"name": "Category 2", "folder": "", "color": "#2a2a2a", "shortcut": ""},
    ],
    "last_import_folder": "",
}

# ── Helpers ────────────────────────────────────────────────
def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(default))

def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def _load_config_with_recovery():
    """Load settings.json. If it's missing -> defaults (silently).
    If it exists but is corrupt -> try to recover from the last good
    backup, and let the caller know so the user can be notified.
    Returns (config, notice) where notice is None or a human message.
    """
    if not os.path.exists(CONFIG_FILE):
        return json.loads(json.dumps(DEFAULT_CONFIG)), None

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception:
        # Main config is corrupt - try the backup copy
        if os.path.exists(CONFIG_BACKUP):
            try:
                with open(CONFIG_BACKUP, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data, ("Konfigurasi rusak terdeteksi. "
                               "Pengaturan dipulihkan dari backup terakhir.")
            except Exception:
                pass
        # Nothing usable - fall back to defaults but tell the user
        return json.loads(json.dumps(DEFAULT_CONFIG)), (
            "Konfigurasi rusak dan backup tidak tersedia. "
            "Pengaturan dikembalikan ke default."
        )

def _save_config_with_backup(data):
    """Back up the previous good config before overwriting it, so a
    corrupted write never wipes out the only copy of the user's
    category setup."""
    try:
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)
    except Exception:
        pass
    _save_json(CONFIG_FILE, data)

def _open_in_explorer(folder):
    try:
        if platform.system() == "Windows":
            os.startfile(folder)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception as e:
        return str(e)
    return None

def _image_to_base64(pil_img, max_w=1400, max_h=900):
    img = pil_img.copy()
    if hasattr(img, "n_frames") and img.n_frames > 1:
        img.seek(0)
    img = img.convert("RGB")
    img.thumbnail((max_w, max_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"

# ── Log buffer ─────────────────────────────────────────────
_log_buffer = deque(maxlen=500)
_window = None

def _log(msg, tag="info"):
    _log_buffer.append({"msg": msg, "tag": tag})
    if _window:
        try:
            safe = msg.replace("\\","\\\\").replace("`","\\`").replace("$","\\$")
            _window.evaluate_js(f"window._appendLog(`{safe}`, `{tag}`)")
        except Exception:
            pass

# ── App State ──────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.config, self.config_notice = _load_config_with_recovery()
        self.config.setdefault("last_import_folder", "")
        self.photo_list     = []
        self.current_index  = -1
        self.source_folder  = ""
        self.history        = []
        self.redo_stack     = []
        self._preload_cache = {}
        self._cache_lock    = threading.Lock()
        # Held while a move/undo/redo file operation is in progress so the
        # app can finish that operation before the window closes.
        self._busy_lock     = threading.Lock()
        # Mutex to prevent undo/redo from being triggered simultaneously
        # via both keyboard shortcut and UI button.
        self._undo_redo_lock = threading.Lock()
        # Session counter: incremented each time a new folder is imported.
        # The preload worker compares against this to cancel stale jobs.
        self._import_session = 0

    def save_config(self):
        _save_config_with_backup(self.config)

_state = AppState()

# ── Preload worker (single daemon thread + queue) ─────────
# All preload requests are serialised through this queue so many concurrent
# threads can never pile up when the user navigates quickly. A sentinel
# (session_id, index) is put on the queue; the worker skips entries whose
# session_id no longer matches _state._import_session, which automatically
# cancels all pending work from the previous folder when a new one is imported.

_preload_queue: queue.Queue = queue.Queue()

def _preload_worker():
    while True:
        try:
            session_id, state = _preload_queue.get(timeout=1)
        except queue.Empty:
            continue
        try:
            # Skip stale preload jobs from a previous import session.
            if session_id != state._import_session:
                continue
            _preload_next(session_id, state)
        except Exception:
            pass
        finally:
            _preload_queue.task_done()

def _request_preload(state: AppState):
    """Enqueue a preload job for the current session."""
    try:
        _preload_queue.put_nowait((state._import_session, state))
    except queue.Full:
        pass  # queue full; a preload is already pending

threading.Thread(target=_preload_worker, daemon=True, name="preload-worker").start()


def _preload_next(session_id: int, state: AppState):
    # Decode the next couple of images ahead of time so navigation feels
    # instant, but keep them downscaled and capped so memory stays bounded
    # even on folders with thousands of photos.
    for off in [1, 2]:
        # Bail out if a new import has started since this job was queued.
        if session_id != state._import_session:
            return
        ni = state.current_index + off
        if 0 <= ni < len(state.photo_list):
            p = state.photo_list[ni]
            with state._cache_lock:
                already = p in state._preload_cache
            if not already:
                try:
                    img = Image.open(p)
                    if hasattr(img, "n_frames") and img.n_frames > 1:
                        img.seek(0)
                    img = img.convert("RGB")
                    img.thumbnail(PRELOAD_MAX_SIZE, Image.LANCZOS)
                    img.load()
                    with state._cache_lock:
                        state._preload_cache[p] = img
                except Exception:
                    pass

    _trim_cache(state)

def _trim_cache(state: AppState):
    """Keep only images near the current position cached; dispose the rest
    so PIL doesn't keep their decoded pixel buffers around forever."""
    keep_paths = set()
    for off in (-1, 0, 1, 2):
        ni = state.current_index + off
        if 0 <= ni < len(state.photo_list):
            keep_paths.add(state.photo_list[ni])

    with state._cache_lock:
        for path in list(state._preload_cache.keys()):
            if path not in keep_paths or len(state._preload_cache) > CACHE_LIMIT:
                if path not in keep_paths:
                    img = state._preload_cache.pop(path, None)
                    if img is not None:
                        try:
                            img.close()
                        except Exception:
                            pass
        # Final safety: if still over the limit, drop the oldest entries
        while len(state._preload_cache) > CACHE_LIMIT:
            oldest_path = next(iter(state._preload_cache))
            if oldest_path in keep_paths:
                break
            img = state._preload_cache.pop(oldest_path, None)
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass

# ═══════════════════════════════════════════════════════════
#  JS-Bridge API
# ═══════════════════════════════════════════════════════════
class NausortAPI:

    def get_init_data(self):
        notice = _state.config_notice
        _state.config_notice = None  # only show once
        return {
            "categories":    _state.config.get("categories", []),
            "photo_count":   len(_state.photo_list),
            "current_index": _state.current_index,
            "log":           list(_log_buffer),
            "data_dir":      DATA_DIR,
            "config_notice": notice,
        }

    def import_folder(self):
        last_dir = _state.config.get("last_import_folder", "")
        dialog_kwargs = {}
        if last_dir and os.path.isdir(last_dir):
            # Reopen the dialog where the user left off last time
            dialog_kwargs["directory"] = last_dir
        # If no folder has ever been imported, omit `directory` so the OS
        # uses its own default starting point (e.g. "This PC" on Windows).

        folder = _window.create_file_dialog(webview.FOLDER_DIALOG, **dialog_kwargs)
        if not folder:
            return {"ok": False}
        folder = folder[0] if isinstance(folder, (list, tuple)) else folder

        # Scan the folder in the API thread (which is already off the main/UI
        # thread in pywebview), so large folders don't freeze the renderer.
        photos = sorted([
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(SUPPORTED_EXTS)
        ])
        _state.source_folder  = folder
        _state.photo_list     = photos
        _state.current_index  = 0 if photos else -1
        _state.history.clear()
        _state.redo_stack.clear()
        # Bump the session ID so any in-flight preload jobs for the old
        # folder are silently discarded by the preload worker.
        _state._import_session += 1
        with _state._cache_lock:
            for img in _state._preload_cache.values():
                try:
                    img.close()
                except Exception:
                    pass
            _state._preload_cache.clear()

        # Remember this folder so the next "Import Folder" opens here
        _state.config["last_import_folder"] = folder
        _state.save_config()

        total = len(photos)
        _log(f"[INFO] Imported: {os.path.basename(folder)}", "info")
        _log(f"[INFO] {total} photo(s) found", "info")

        if photos:
            _request_preload(_state)
            return {"ok": True, "total": total,
                    "current_index": _state.current_index,
                    **self._get_current_image_data()}
        return {"ok": True, "total": 0, "current_index": -1}

    def _get_current_image_data(self):
        idx = _state.current_index
        if not (0 <= idx < len(_state.photo_list)):
            return {"filename": "", "image_data": "", "index": -1, "total": 0}

        # Fix #8: Auto-skip consecutive corrupt files rather than forcing the
        # user to click "Skip" repeatedly. We try up to (remaining) photos
        # forward; if we exhaust the list we stop at the last position.
        MAX_AUTO_SKIP = len(_state.photo_list)
        for _ in range(MAX_AUTO_SKIP):
            idx = _state.current_index
            if not (0 <= idx < len(_state.photo_list)):
                break
            path = _state.photo_list[idx]
            image_data = ""
            error = None
            try:
                with _state._cache_lock:
                    pil = _state._preload_cache.get(path)
                if not pil:
                    pil = Image.open(path); pil.load()
                image_data = _image_to_base64(pil)
            except Exception as e:
                error = str(e)
                _log(f"[WARN] File rusak, dilewati otomatis: {os.path.basename(path)} ({e})", "warn")
                # Auto-advance past this corrupt file if there are more photos.
                if _state.current_index < len(_state.photo_list) - 1:
                    _state.current_index += 1
                    continue
                # No more photos to skip to; stay here and report the error.
                break
            # Successfully loaded; return this photo.
            return {
                "filename":   os.path.basename(path),
                "image_data": image_data,
                "index":      idx,
                "total":      len(_state.photo_list),
                "error":      None,
            }

        # Fell through: current photo is corrupt and there's nothing to skip to.
        path = _state.photo_list[_state.current_index] if _state.photo_list else ""
        return {
            "filename":   os.path.basename(path) if path else "",
            "image_data": "",
            "index":      _state.current_index,
            "total":      len(_state.photo_list),
            "error":      "File rusak dan tidak ada foto berikutnya.",
        }

    def get_current_image(self):
        return self._get_current_image_data()

    def go_prev(self):
        if not _state.photo_list or _state.current_index <= 0:
            return self._get_current_image_data()
        _state.current_index -= 1
        _request_preload(_state)
        return self._get_current_image_data()

    def go_next(self):
        if not _state.photo_list or _state.current_index >= len(_state.photo_list) - 1:
            return self._get_current_image_data()
        _state.current_index += 1
        _request_preload(_state)
        return self._get_current_image_data()

    def sort_to(self, category_index, conflict_action=None):
        """Move the current photo into a category folder.

        conflict_action is None on the first call. If the destination
        already has a file with the same name, we don't touch anything
        yet - we report the conflict back to the UI so the user can pick
        Replace / Cancel / Keep Both, then this is called again with that
        choice.
        """
        cats = _state.config.get("categories", [])
        if not (0 <= category_index < len(cats)):
            return {"ok": False, "error": "Category not found"}
        cat = cats[category_index]
        if not cat.get("folder"):
            return {"ok": False, "error": f"No destination folder set for '{cat['name']}'"}
        idx = _state.current_index
        if not (0 <= idx < len(_state.photo_list)):
            return {"ok": False, "error": "No active photo"}

        src  = _state.photo_list[idx]
        name = os.path.basename(src)
        dst_dir = cat["folder"]

        # Fix #7: Prevent sorting into the same folder the file already lives in.
        if os.path.abspath(os.path.dirname(src)) == os.path.abspath(dst_dir):
            _log(f"[WARN] Source and destination folder are the same: {dst_dir}", "warn")
            return {"ok": False, "error": "Folder tujuan sama dengan folder sumber."}

        # Fix #12: Warn when the destination folder no longer exists before
        # silently recreating it, so the user knows their folder was missing.
        if not os.path.isdir(dst_dir):
            _log(f"[WARN] Folder tujuan tidak ditemukan, dibuat ulang: {dst_dir}", "warn")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, name)

        if os.path.exists(dst) and conflict_action is None:
            # Ask the UI what to do, don't move anything yet.
            return {
                "ok": False, "conflict": True,
                "filename": name, "category_index": category_index,
            }

        if os.path.exists(dst):
            if conflict_action == "cancel":
                _log(f"[INFO] Sorting dibatalkan: {name}", "info")
                return {"ok": False, "cancelled": True}
            elif conflict_action == "keep_both":
                base, ext = os.path.splitext(name)
                n = 1
                while True:
                    candidate = os.path.join(dst_dir, f"{base} ({n}){ext}")
                    if not os.path.exists(candidate):
                        dst = candidate
                        break
                    n += 1
            elif conflict_action == "replace":
                pass  # fall through, overwrite below
            else:
                return {"ok": False, "error": "Unknown conflict_action"}

        # Hold the busy lock for the actual filesystem operation so the
        # app can wait for it to finish before shutting down.
        # Fix #13: Check for Windows MAX_PATH limit (260 chars) before moving.
        if platform.system() == "Windows" and len(dst) >= 260:
            _log(f"[WARN] Path terlalu panjang ({len(dst)} chars): {os.path.basename(dst)}", "warn")
            return {"ok": False, "error": f"Path terlalu panjang ({len(dst)} karakter). Gunakan nama folder/file yang lebih pendek."}

        with _state._busy_lock:
            try:
                if conflict_action == "replace" and os.path.exists(dst):
                    os.replace(src, dst)
                else:
                    shutil.move(src, dst)
            except Exception as e:
                _log(f"[WARN] Move failed: {e}", "warn")
                return {"ok": False, "error": str(e)}

            _state.history.append({"filename": name, "src": src, "dst": dst,
                                    "original_index": idx,
                                    "ts": time.strftime("%H:%M:%S")})
            _state.redo_stack.clear()
            _log(f"=> {name}  ->  {cat['name']}", "move")

            _state.photo_list.pop(idx)
            if _state.current_index >= len(_state.photo_list):
                _state.current_index = len(_state.photo_list) - 1

        return {"ok": True, **self._get_current_image_data()}

    def undo(self):
        if not _state._undo_redo_lock.acquire(blocking=False):
            return {"ok": False}
        try:
            if not _state.history:
                _log("[WARN] Nothing to undo.", "warn")
                return {"ok": False}
            rec = _state.history.pop()
            with _state._busy_lock:
                try:
                    os.makedirs(os.path.dirname(rec["src"]), exist_ok=True)
                    shutil.move(rec["dst"], rec["src"])
                except Exception as e:
                    _log(f"[WARN] Undo failed: {e}", "warn")
                    _state.history.append(rec)
                    return {"ok": False}
            _state.redo_stack.append(rec)
            _log(f"Undo: {rec['filename']} returned to source", "undo")
            if rec["src"] not in _state.photo_list:
                # Restore to the original position in the list, not the current
                # cursor position, so the order of photos is preserved correctly.
                original_index = rec.get("original_index", _state.current_index)
                pos = max(0, min(original_index, len(_state.photo_list)))
                _state.photo_list.insert(pos, rec["src"])
                _state.current_index = pos
            return {"ok": True, **self._get_current_image_data()}
        finally:
            _state._undo_redo_lock.release()

    def redo(self):
        if not _state._undo_redo_lock.acquire(blocking=False):
            return {"ok": False}
        try:
            if not _state.redo_stack:
                _log("[WARN] Nothing to redo.", "warn")
                return {"ok": False}
            rec = _state.redo_stack.pop()
            src = rec["src"]
            dst = rec["dst"]
            dst_dir = os.path.dirname(dst)

            # Fix #6: Handle filename conflict on redo (same as sort_to).
            if os.path.exists(dst):
                base, ext = os.path.splitext(os.path.basename(dst))
                n = 1
                candidate = dst
                while os.path.exists(candidate):
                    candidate = os.path.join(dst_dir, f"{base} ({n}){ext}")
                    n += 1
                dst = candidate
                rec = dict(rec, dst=dst)

            with _state._busy_lock:
                try:
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.move(src, dst)
                except Exception as e:
                    _log(f"[WARN] Redo failed: {e}", "warn")
                    _state.redo_stack.append(rec)
                    return {"ok": False}
            _state.history.append(rec)
            _log(f"Redo: {rec['filename']} -> destination", "redo")
            if src in _state.photo_list:
                _state.photo_list.remove(src)
                if _state.current_index >= len(_state.photo_list):
                    _state.current_index = len(_state.photo_list) - 1
            return {"ok": True, **self._get_current_image_data()}
        finally:
            _state._undo_redo_lock.release()

    # ── Categories ─────────────────────────────────────────
    def add_category(self, name="New Category"):
        cats = _state.config.setdefault("categories", [])
        cats.append({"name": name, "folder": "", "color": "#2a2a2a", "shortcut": ""})
        _state.save_config()
        _log(f"[INFO] Category added: {name}", "info")
        return {"ok": True, "categories": cats}

    def delete_category(self, index):
        cats = _state.config.get("categories", [])
        if 0 <= index < len(cats):
            removed = cats.pop(index)
            _state.save_config()
            _log(f"[INFO] Category deleted: {removed['name']}", "info")
            return {"ok": True, "categories": cats}
        return {"ok": False, "error": "Index out of range"}

    def rename_category(self, index, name):
        cats = _state.config.get("categories", [])
        if 0 <= index < len(cats) and name.strip():
            # Fix #11: Skip unnecessary disk write if the name hasn't changed.
            if cats[index]["name"] == name.strip():
                return {"ok": True, "categories": cats}
            cats[index]["name"] = name.strip()
            _state.save_config()
            return {"ok": True, "categories": cats}
        return {"ok": False}

    def set_category_color(self, index, color):
        cats = _state.config.get("categories", [])
        if 0 <= index < len(cats):
            cats[index]["color"] = color
            _state.save_config()
            return {"ok": True, "categories": cats}
        return {"ok": False}

    def set_category_shortcut(self, index, shortcut):
        cats = _state.config.get("categories", [])
        if not (0 <= index < len(cats)):
            return {"ok": False}
        sc = shortcut.strip()[:1].upper() if shortcut.strip() else ""
        if sc:
            for i, c in enumerate(cats):
                if i != index and (c.get("shortcut") or "").upper() == sc:
                    return {"ok": False, "error": "Shortcut ini sudah digunakan."}
        cats[index]["shortcut"] = sc
        _state.save_config()
        return {"ok": True, "categories": cats}

    def choose_category_folder(self, index):
        folder = _window.create_file_dialog(
            webview.FOLDER_DIALOG, directory=os.path.expanduser("~")
        )
        if not folder:
            return {"ok": False}
        folder = folder[0] if isinstance(folder, (list, tuple)) else folder
        cats = _state.config.get("categories", [])
        if 0 <= index < len(cats):
            cats[index]["folder"] = folder
            _state.save_config()
            _log(f"[INFO] '{cats[index]['name']}' -> {os.path.basename(folder)}", "info")
            return {"ok": True, "categories": cats, "folder": folder}
        return {"ok": False}

    def open_category_folder(self, index):
        cats = _state.config.get("categories", [])
        if 0 <= index < len(cats):
            folder = cats[index].get("folder", "")
            if folder:
                err = _open_in_explorer(folder)
                if err:
                    _log(f"[WARN] Cannot open folder: {err}", "warn")
        return {"ok": True}

    def get_categories(self):
        return _state.config.get("categories", [])

    def get_log(self):
        return list(_log_buffer)

# ── Icon helper ───────────────────────────────────────────
def _find_icon():
    assets = os.path.join(UI_DIR, "assets")
    for name in ("icon.ico", "icon.png", "icon.svg"):
        path = os.path.join(assets, name)
        if os.path.exists(path):
            return path
    return None

# ── Entry point ───────────────────────────────────────────
def main():
    global _window
    api  = NausortAPI()
    icon = _find_icon()

    _window = webview.create_window(
        title            = "Nausort Media v1.2",
        url              = os.path.join(UI_DIR, "index.html"),
        js_api           = api,
        width            = 1200,
        height           = 760,
        min_size         = (860, 580),
        background_color = "#111113",
        resizable        = True,
    )

    def on_loaded():
        time.sleep(0.4)
        _log("[INFO] Nausort Media v1.2")
        time.sleep(0.1)
        _log("[INFO] Created by Naufal Khalil 🇮🇩")
        time.sleep(0.1)
        _log(f"[INFO] Data folder: {DATA_DIR}")
        time.sleep(0.1)
        _log("[INFO] Right-click a category button for options")
        _log("-" * 36, "dim")

    def on_closing():
        # If a sort/undo/redo file move is still running, give it a moment
        # to finish so we don't leave files half-moved on shutdown.
        acquired = _state._busy_lock.acquire(timeout=5)
        if acquired:
            _state._busy_lock.release()
        return True  # always allow the window to close

    _window.events.loaded  += on_loaded
    _window.events.closing += on_closing

    start_kwargs = {"debug": False}
    if icon:
        start_kwargs["icon"] = icon
    webview.start(**start_kwargs)

if __name__ == "__main__":
    main()
