# ============================================================
#  Nausort Media v2.0 — PyWebView Desktop App
#  Backend: Python  |  Frontend: HTML/CSS/JS via pywebview
#  Data stored in: C:\Users\<user>\Documents\Nausort Media\
# ============================================================

# ── Auto-install ──────────────────────────────────────────
import subprocess, sys

REQUIRED = ["pywebview", "Pillow"]

def _install_missing():
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
import base64, io, json, os, platform, shutil, threading, time
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

DATA_DIR    = _get_data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "settings.json")

# ── Constants ─────────────────────────────────────────────
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")

DEFAULT_CONFIG = {
    "categories": [
        {"name": "Category 1", "folder": "", "color": "#2a2a2a", "shortcut": ""},
        {"name": "Category 2", "folder": "", "color": "#2a2a2a", "shortcut": ""},
    ]
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
        self.config         = _load_json(CONFIG_FILE, DEFAULT_CONFIG)
        self.photo_list     = []
        self.current_index  = -1
        self.source_folder  = ""
        self.history        = []
        self.redo_stack     = []
        self._preload_cache = {}
        self._cache_lock    = threading.Lock()

    def save_config(self):
        _save_json(CONFIG_FILE, self.config)

_state = AppState()

def _preload_next(state: AppState):
    for off in [1, 2]:
        ni = state.current_index + off
        if 0 <= ni < len(state.photo_list):
            p = state.photo_list[ni]
            with state._cache_lock:
                if p not in state._preload_cache:
                    try:
                        img = Image.open(p); img.load()
                        state._preload_cache[p] = img
                    except Exception:
                        pass
    with state._cache_lock:
        keys = list(state._preload_cache.keys())
        if len(keys) > 12:
            for k in keys[:-10]:
                del state._preload_cache[k]

# ═══════════════════════════════════════════════════════════
#  JS-Bridge API
# ═══════════════════════════════════════════════════════════
class NausortAPI:

    def get_init_data(self):
        return {
            "categories":    _state.config.get("categories", []),
            "photo_count":   len(_state.photo_list),
            "current_index": _state.current_index,
            "log":           list(_log_buffer),
            "data_dir":      DATA_DIR,
        }

    def import_folder(self):
        folder = _window.create_file_dialog(
            webview.FOLDER_DIALOG, directory=os.path.expanduser("~")
        )
        if not folder:
            return {"ok": False}
        folder = folder[0] if isinstance(folder, (list, tuple)) else folder

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
        with _state._cache_lock:
            _state._preload_cache.clear()

        total = len(photos)
        _log(f"[INFO] Imported: {os.path.basename(folder)}", "info")
        _log(f"[INFO] {total} photo(s) found", "info")

        if photos:
            threading.Thread(target=_preload_next, args=(_state,), daemon=True).start()
            return {"ok": True, "total": total,
                    "current_index": _state.current_index,
                    **self._get_current_image_data()}
        return {"ok": True, "total": 0, "current_index": -1}

    def _get_current_image_data(self):
        idx = _state.current_index
        if not (0 <= idx < len(_state.photo_list)):
            return {"filename": "", "image_data": "", "index": -1, "total": 0}
        path = _state.photo_list[idx]
        try:
            with _state._cache_lock:
                pil = _state._preload_cache.get(path)
            if not pil:
                pil = Image.open(path); pil.load()
            image_data = _image_to_base64(pil)
        except Exception as e:
            image_data = ""
            _log(f"[WARN] Failed to load photo: {e}", "warn")
        return {
            "filename":   os.path.basename(path),
            "image_data": image_data,
            "index":      idx,
            "total":      len(_state.photo_list),
        }

    def get_current_image(self):
        return self._get_current_image_data()

    def go_prev(self):
        if _state.photo_list and _state.current_index > 0:
            _state.current_index -= 1
            threading.Thread(target=_preload_next, args=(_state,), daemon=True).start()
        return self._get_current_image_data()

    def go_next(self):
        if _state.photo_list and _state.current_index < len(_state.photo_list) - 1:
            _state.current_index += 1
            threading.Thread(target=_preload_next, args=(_state,), daemon=True).start()
        return self._get_current_image_data()

    def sort_to(self, category_index):
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
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, name)
        if os.path.exists(dst):
            base, ext = os.path.splitext(name)
            dst = os.path.join(dst_dir, f"{base}_{int(time.time())}{ext}")
        try:
            shutil.move(src, dst)
        except Exception as e:
            _log(f"[WARN] Move failed: {e}", "warn")
            return {"ok": False, "error": str(e)}

        _state.history.append({"filename": name, "src": src, "dst": dst,
                                "ts": time.strftime("%H:%M:%S")})
        _state.redo_stack.clear()
        _log(f"=> {name}  ->  {cat['name']}", "move")

        _state.photo_list.pop(idx)
        if _state.current_index >= len(_state.photo_list):
            _state.current_index = len(_state.photo_list) - 1
        return {"ok": True, **self._get_current_image_data()}

    def undo(self):
        if not _state.history:
            _log("[WARN] Nothing to undo.", "warn")
            return {"ok": False}
        rec = _state.history.pop()
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
            pos = max(0, _state.current_index)
            _state.photo_list.insert(pos, rec["src"])
            _state.current_index = pos
        return {"ok": True, **self._get_current_image_data()}

    def redo(self):
        if not _state.redo_stack:
            _log("[WARN] Nothing to redo.", "warn")
            return {"ok": False}
        rec = _state.redo_stack.pop()
        try:
            os.makedirs(os.path.dirname(rec["dst"]), exist_ok=True)
            shutil.move(rec["src"], rec["dst"])
        except Exception as e:
            _log(f"[WARN] Redo failed: {e}", "warn")
            _state.redo_stack.append(rec)
            return {"ok": False}
        _state.history.append(rec)
        _log(f"Redo: {rec['filename']} -> destination", "redo")
        if rec["src"] in _state.photo_list:
            _state.photo_list.remove(rec["src"])
            if _state.current_index >= len(_state.photo_list):
                _state.current_index = len(_state.photo_list) - 1
        return {"ok": True, **self._get_current_image_data()}

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
        if 0 <= index < len(cats):
            cats[index]["shortcut"] = shortcut.strip()[:1].upper() if shortcut.strip() else ""
            _state.save_config()
            return {"ok": True, "categories": cats}
        return {"ok": False}

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
        title            = "Nausort Media",
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
        _log("[INFO] Nausort Media v2.0")
        time.sleep(0.1)
        _log("[INFO] Created by Naufal Khalil 🇮🇩")
        time.sleep(0.1)
        _log(f"[INFO] Data folder: {DATA_DIR}")
        time.sleep(0.1)
        _log("[INFO] Right-click a category button for options")
        time.sleep(0.1)
        _log("[INFO] Ctrl+Z = Undo")
        time.sleep(0.1)
        _log("[INFO] Ctrl+Y = Redo")
        time.sleep(0.1)
        _log("[INFO] Arrow keys = navigate")
        time.sleep(0.1)
        _log("[INFO] Scroll = zoom")
        time.sleep(0.1)
        _log("[INFO] Backspace = reset photo position")
        time.sleep(0.1)
        _log("-" * 36, "dim")

    _window.events.loaded += on_loaded

    start_kwargs = {"debug": False}
    if icon:
        start_kwargs["icon"] = icon
    webview.start(**start_kwargs)

if __name__ == "__main__":
    main()
