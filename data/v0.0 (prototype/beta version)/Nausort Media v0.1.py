"""
Nausort Media Prototype v0.1

=> Features v0.1:
- Manage and categorize image files.
- Load source folder containing images.
- View thumbnails and preview images.
- Categorize or move images to destination folder based on specified categories.
- Provide category configuration and support for common image formats.
- Provide a simple interface for navigation and color/shortcut category settings.
"""


import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
import os
import shutil
import json
import threading
from PIL import Image, ImageTk
import time

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
CONFIG_FILE = "Nausort_Media_config.json"
SUPPORTED_FORMATS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")

DEFAULT_CONFIG = {
    "categories": [
        {"name": "Memory 1", "folder": "", "color": "#2d2d2d", "shortcut": "1"},
        {"name": "Memory 2", "folder": "", "color": "#2d2d2d", "shortcut": "2"},
    ]
}

# ─────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────
BG         = "#1a1a1a"
BG2        = "#232323"
BG3        = "#2d2d2d"
BORDER     = "#3a3a3a"
TEXT       = "#e8e8e8"
TEXT_DIM   = "#888888"
ACCENT     = "#ffffff"
BTN_NAV    = "#2d2d2d"
BTN_HOVER  = "#3a3a3a"
BTN_CAT    = "#2d2d2d"
TERM_BG    = "#141414"
TERM_TEXT  = "#a8d8a8"
TERM_INFO  = "#6ab0de"
PROGRESS_BG = "#2d2d2d"
PROGRESS_FG = "#4a9eff"


# ─────────────────────────────────────────────
# MAIN APPLICATION
# ─────────────────────────────────────────────
class PhotoSorterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Nausort Media")
        self.root.configure(bg=BG)
        self.root.geometry("1200x750")
        self.root.minsize(900, 600)

        # State
        self.photo_list = []
        self.current_index = -1
        self.source_folder = ""
        self.config = {}
        self.category_widgets = []  # list of dicts: {frame, cat_btn, browse_btn}

        # Image zoom/pan state
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.pan_start = None
        self.current_pil_image = None
        self._after_id = None
        self._preload_cache = {}

        # History for undo/redo
        self.history = []       # list of {filename, src, dst, timestamp}
        self.redo_stack = []

        # Load config
        self.load_config()

        # Build UI
        self.build_ui()
        self.apply_config()
        self.bind_shortcuts()

        self.log("[INFO] Program running...")
        self.log("Press numbers for button shortcuts")
        self.log("-" * 34)

    # ──────────────────────────────────────────
    # CONFIG
    # ──────────────────────────────────────────
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                return
            except Exception:
                pass
        self.config = json.loads(json.dumps(DEFAULT_CONFIG))

    def save_config(self):
        data = {"categories": []}
        for w in self.category_widgets:
            data["categories"].append({
                "name":     w["name"],
                "folder":   w["folder"],
                "color":    w["color"],
                "shortcut": w["shortcut"],
            })
        self.config = data
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"[WARN] Gagal simpan config: {e}")

    # ──────────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────────
    def build_ui(self):
        # ── Main horizontal split ──
        self.main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                                        bg=BG, sashwidth=4, sashrelief=tk.FLAT)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        # ── LEFT PANEL ──
        self.left_frame = tk.Frame(self.main_pane, bg=BG)
        self.main_pane.add(self.left_frame, minsize=500)

        # View label
        view_label = tk.Label(self.left_frame, text="View", bg=BG, fg=TEXT_DIM,
                              font=("Consolas", 10, "bold"), anchor="w")
        view_label.pack(fill=tk.X, padx=10, pady=(8, 0))

        sep1 = tk.Frame(self.left_frame, bg=BORDER, height=1)
        sep1.pack(fill=tk.X, padx=10)

        # File name bar
        self.filename_var = tk.StringVar(value="")
        fname_frame = tk.Frame(self.left_frame, bg=BG3, bd=0, highlightthickness=1,
                                highlightbackground=BORDER)
        fname_frame.pack(fill=tk.X, padx=10, pady=6)
        self.filename_label = tk.Label(fname_frame, textvariable=self.filename_var,
                                       bg=BG3, fg=TEXT, font=("Consolas", 10),
                                       anchor="center", pady=4)
        self.filename_label.pack(fill=tk.X)

        # Canvas for image
        self.canvas_frame = tk.Frame(self.left_frame, bg="black",
                                     highlightthickness=1, highlightbackground=BORDER)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 6))

        self.canvas = tk.Canvas(self.canvas_frame, bg="black",
                                cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Canvas bindings
        self.canvas.bind("<ButtonPress-2>",   self.pan_start_cb)
        self.canvas.bind("<B2-Motion>",        self.pan_move_cb)
        self.canvas.bind("<ButtonPress-3>",    self.pan_start_cb)
        self.canvas.bind("<B3-Motion>",        self.pan_move_cb)
        self.canvas.bind("<MouseWheel>",       self.on_mousewheel)
        self.canvas.bind("<Configure>",        self.on_canvas_resize)

        # ── Progress bar area ──
        prog_frame = tk.Frame(self.left_frame, bg=BG)
        prog_frame.pack(fill=tk.X, padx=10, pady=(0, 4))

        self.progress_label = tk.Label(prog_frame, text="0 / 0 foto  (0%)",
                                       bg=BG, fg=TEXT_DIM, font=("Consolas", 9))
        self.progress_label.pack(side=tk.LEFT)

        self.progress_bar_bg = tk.Frame(prog_frame, bg=PROGRESS_BG, height=6)
        self.progress_bar_bg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.progress_bar_fg = tk.Frame(self.progress_bar_bg, bg=PROGRESS_FG, height=6)
        self.progress_bar_fg.place(x=0, y=0, relheight=1.0, width=0)

        # ── Category panel (scrollable horizontal) ──
        cat_outer = tk.Frame(self.left_frame, bg=BG)
        cat_outer.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.cat_canvas = tk.Canvas(cat_outer, bg=BG, height=90,
                                    highlightthickness=0)
        self.cat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cat_scroll = tk.Scrollbar(cat_outer, orient=tk.HORIZONTAL,
                                  command=self.cat_canvas.xview)
        cat_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.cat_canvas.configure(xscrollcommand=cat_scroll.set)

        self.cat_inner = tk.Frame(self.cat_canvas, bg=BG)
        self.cat_canvas_window = self.cat_canvas.create_window(
            (0, 0), window=self.cat_inner, anchor="nw")
        self.cat_inner.bind("<Configure>", self._on_cat_inner_configure)

        # ── RIGHT PANEL ──
        self.right_frame = tk.Frame(self.main_pane, bg=BG, width=290)
        self.main_pane.add(self.right_frame, minsize=220)

        # Terminal label
        term_label = tk.Label(self.right_frame, text="Terminal", bg=BG, fg=TEXT_DIM,
                               font=("Consolas", 10, "bold"), anchor="w")
        term_label.pack(fill=tk.X, padx=10, pady=(8, 0))
        sep2 = tk.Frame(self.right_frame, bg=BORDER, height=1)
        sep2.pack(fill=tk.X, padx=10)

        # Log text
        self.log_text = tk.Text(self.right_frame, bg=TERM_BG, fg=TERM_TEXT,
                                font=("Consolas", 9), state=tk.DISABLED,
                                wrap=tk.WORD, relief=tk.FLAT, bd=0,
                                insertbackground=TERM_TEXT)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        self.log_text.tag_configure("info",  foreground=TERM_INFO)
        self.log_text.tag_configure("undo",  foreground="#e8a87c")
        self.log_text.tag_configure("redo",  foreground="#c3e88d")
        self.log_text.tag_configure("move",  foreground=TERM_TEXT)
        self.log_text.tag_configure("warn",  foreground="#f07178")

        # Navigation label
        nav_label = tk.Label(self.right_frame, text="Navigation", bg=BG, fg=TEXT_DIM,
                              font=("Consolas", 10, "bold"), anchor="w")
        nav_label.pack(fill=tk.X, padx=10, pady=(4, 0))
        sep3 = tk.Frame(self.right_frame, bg=BORDER, height=1)
        sep3.pack(fill=tk.X, padx=10)

        nav_frame = tk.Frame(self.right_frame, bg=BG)
        nav_frame.pack(fill=tk.X, padx=10, pady=6)
        nav_frame.columnconfigure(0, weight=1)
        nav_frame.columnconfigure(1, weight=1)

        self.btn_prev = self._make_btn(nav_frame, "Previous", self.undo_action,
                                       font=("Consolas", 10, "bold"))
        self.btn_prev.grid(row=0, column=0, padx=(0, 3), sticky="ew")

        self.btn_next = self._make_btn(nav_frame, "Next", self.redo_action,
                                       font=("Consolas", 10, "bold"))
        self.btn_next.grid(row=0, column=1, padx=(3, 0), sticky="ew")

        self.btn_add = self._make_btn(self.right_frame, "Add New Button",
                                      self.add_category,
                                      font=("Consolas", 10, "bold"))
        self.btn_add.pack(fill=tk.X, padx=10, pady=(2, 4))

        self.btn_import = self._make_btn(self.right_frame, "Import Folder",
                                         self.import_folder,
                                         font=("Consolas", 10, "bold"))
        self.btn_import.pack(fill=tk.X, padx=10, pady=(0, 10))

    def _on_cat_inner_configure(self, event=None):
        self.cat_canvas.configure(scrollregion=self.cat_canvas.bbox("all"))

    # ──────────────────────────────────────────
    # BUTTON FACTORY
    # ──────────────────────────────────────────
    def _make_btn(self, parent, text, command, bg=BTN_NAV, fg=TEXT,
                  font=("Consolas", 10), **kwargs):
        btn = tk.Button(parent, text=text, command=command,
                        bg=bg, fg=fg, font=font,
                        activebackground=BTN_HOVER, activeforeground=ACCENT,
                        relief=tk.FLAT, bd=0, cursor="hand2",
                        padx=8, pady=8, **kwargs)
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=BTN_HOVER))
        btn.bind("<Leave>", lambda e, b=btn, c=bg: b.configure(bg=c))
        return btn

    # ──────────────────────────────────────────
    # APPLY CONFIG → BUILD CATEGORIES
    # ──────────────────────────────────────────
    def apply_config(self):
        # Clear existing
        for w in self.cat_inner.winfo_children():
            w.destroy()
        self.category_widgets.clear()

        for cat in self.config.get("categories", []):
            self._add_category_widget(
                name=cat.get("name", "Kategori"),
                folder=cat.get("folder", ""),
                color=cat.get("color", BTN_CAT),
                shortcut=cat.get("shortcut", ""),
            )

    def _add_category_widget(self, name="Kategori Baru", folder="",
                              color=BTN_CAT, shortcut=""):
        idx = len(self.category_widgets)

        frame = tk.Frame(self.cat_inner, bg=BG, padx=4, pady=4)
        frame.pack(side=tk.LEFT, fill=tk.Y)

        # Category button
        cat_btn = tk.Button(frame, text=name, bg=color, fg=TEXT,
                            font=("Consolas", 10, "bold"),
                            activebackground=BTN_HOVER, activeforeground=ACCENT,
                            relief=tk.FLAT, bd=0, cursor="hand2",
                            width=14, height=2)
        cat_btn.pack(fill=tk.X, pady=(0, 4))

        # Browse button
        folder_lbl = folder if folder else "Browse"
        if folder:
            folder_lbl = os.path.basename(folder) or folder
        browse_btn = tk.Button(frame, text=folder_lbl, bg=BG3, fg=TEXT_DIM,
                               font=("Consolas", 9),
                               activebackground=BTN_HOVER, activeforeground=ACCENT,
                               relief=tk.FLAT, bd=0, cursor="hand2",
                               width=14)
        browse_btn.pack(fill=tk.X)

        w = {
            "frame":      frame,
            "cat_btn":    cat_btn,
            "browse_btn": browse_btn,
            "name":       name,
            "folder":     folder,
            "color":      color,
            "shortcut":   shortcut,
        }
        self.category_widgets.append(w)

        # Commands (use closure)
        cat_btn.configure(command=lambda wi=w: self.sort_to_category(wi))
        browse_btn.configure(command=lambda wi=w: self.choose_folder(wi))

        # Right-click context menu
        cat_btn.bind("<Button-3>", lambda e, wi=w: self.show_cat_context_menu(e, wi))

        # Hover for cat_btn
        cat_btn.bind("<Enter>", lambda e, b=cat_btn: b.configure(bg=BTN_HOVER))
        cat_btn.bind("<Leave>", lambda e, b=cat_btn, c=color: b.configure(bg=w["color"]))

        # Shortcut label
        if shortcut:
            self._update_cat_btn_text(w)

        self.save_config()
        self._on_cat_inner_configure()
        return w

    def _update_cat_btn_text(self, w):
        sc = w.get("shortcut", "")
        name = w.get("name", "")
        if sc:
            w["cat_btn"].configure(text=f"[{sc}] {name}")
        else:
            w["cat_btn"].configure(text=name)

    # ──────────────────────────────────────────
    # CONTEXT MENU
    # ──────────────────────────────────────────
    def show_cat_context_menu(self, event, w):
        menu = tk.Menu(self.root, tearoff=0, bg=BG3, fg=TEXT,
                       activebackground=BTN_HOVER, activeforeground=ACCENT,
                       relief=tk.FLAT, bd=1)
        menu.add_command(label="Rename",          command=lambda: self.rename_category(w))
        menu.add_command(label="Change Color",    command=lambda: self.change_color(w))
        menu.add_command(label="Change Shortcut", command=lambda: self.change_shortcut(w))
        menu.add_separator()
        menu.add_command(label="Delete Category", command=lambda: self.delete_category(w))
        menu.tk_popup(event.x_root, event.y_root)

    def rename_category(self, w):
        new_name = simpledialog.askstring("Rename", "Nama kategori baru:",
                                          initialvalue=w["name"], parent=self.root)
        if new_name and new_name.strip():
            w["name"] = new_name.strip()
            self._update_cat_btn_text(w)
            self.save_config()

    def change_color(self, w):
        color = colorchooser.askcolor(color=w["color"], parent=self.root)
        if color and color[1]:
            w["color"] = color[1]
            w["cat_btn"].configure(bg=color[1])
            self.save_config()

    def change_shortcut(self, w):
        sc = simpledialog.askstring("Shortcut", "Tekan shortcut baru (1 karakter):",
                                    initialvalue=w.get("shortcut", ""), parent=self.root)
        if sc is not None:
            w["shortcut"] = sc.strip()[:1].upper() if sc.strip() else ""
            self._update_cat_btn_text(w)
            self.save_config()
            self.bind_shortcuts()

    def delete_category(self, w):
        if messagebox.askyesno("Hapus", f"Hapus kategori '{w['name']}'?", parent=self.root):
            w["frame"].destroy()
            self.category_widgets.remove(w)
            self.save_config()
            self._on_cat_inner_configure()

    def add_category(self):
        idx = len(self.category_widgets) + 1
        sc = str(idx) if idx <= 9 else ""
        self._add_category_widget(name=f"Kategori {idx}", shortcut=sc)

    def choose_folder(self, w):
        folder = filedialog.askdirectory(parent=self.root)
        if folder:
            w["folder"] = folder
            lbl = os.path.basename(folder) or folder
            w["browse_btn"].configure(text=lbl, fg=TEXT)
            self.save_config()

    # ──────────────────────────────────────────
    # IMPORT FOLDER
    # ──────────────────────────────────────────
    def import_folder(self):
        folder = filedialog.askdirectory(parent=self.root)
        if not folder:
            return
        self.source_folder = folder
        self.photo_list = []
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(SUPPORTED_FORMATS):
                self.photo_list.append(os.path.join(folder, f))

        self.current_index = 0 if self.photo_list else -1
        self._preload_cache.clear()
        self.history.clear()
        self.redo_stack.clear()
        self.update_progress()
        self.log(f"[INFO] Import folder berhasil: {folder}")
        self.log(f"[INFO] {len(self.photo_list)} foto ditemukan")
        if self.photo_list:
            self.show_current_photo()

    # ──────────────────────────────────────────
    # PHOTO DISPLAY
    # ──────────────────────────────────────────
    def show_current_photo(self):
        if self.current_index < 0 or self.current_index >= len(self.photo_list):
            self.canvas.delete("all")
            self.filename_var.set("")
            return

        path = self.photo_list[self.current_index]
        self.filename_var.set(os.path.basename(path))
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self._load_and_draw(path)
        self.update_progress()

        # Preload next
        threading.Thread(target=self._preload_next, daemon=True).start()

    def _preload_next(self):
        for offset in [1, 2]:
            ni = self.current_index + offset
            if 0 <= ni < len(self.photo_list):
                p = self.photo_list[ni]
                if p not in self._preload_cache:
                    try:
                        img = Image.open(p)
                        img.load()
                        self._preload_cache[p] = img
                    except Exception:
                        pass
        # Limit cache size
        if len(self._preload_cache) > 10:
            keys = list(self._preload_cache.keys())
            for k in keys[:-8]:
                del self._preload_cache[k]

    def _load_and_draw(self, path):
        try:
            if path in self._preload_cache:
                img = self._preload_cache[path]
            else:
                img = Image.open(path)
                if img.format == "GIF":
                    img.seek(0)
                img.load()
            self.current_pil_image = img
            self._draw_image()
        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text=f"Gagal load: {e}", fill=TEXT_DIM,
                font=("Consolas", 10))

    def _draw_image(self):
        if not self.current_pil_image:
            return
        self.canvas.delete("all")

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            self.root.after(50, self._draw_image)
            return

        img = self.current_pil_image
        iw, ih = img.size

        # Fit to canvas
        scale = min(cw / iw, ch / ih)
        base_w = int(iw * scale)
        base_h = int(ih * scale)

        # Apply zoom
        disp_w = max(1, int(base_w * self.zoom_factor))
        disp_h = max(1, int(base_h * self.zoom_factor))

        # Clamp pan
        max_pan_x = max(0, (disp_w - cw) // 2 + 20)
        max_pan_y = max(0, (disp_h - ch) // 2 + 20)
        self.pan_x = max(-max_pan_x, min(max_pan_x, self.pan_x))
        self.pan_y = max(-max_pan_y, min(max_pan_y, self.pan_y))

        x_offset = (cw - disp_w) // 2 + self.pan_x
        y_offset = (ch - disp_h) // 2 + self.pan_y

        resized = img.resize((disp_w, disp_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(resized)
        self.canvas.create_image(x_offset, y_offset, anchor="nw", image=self._tk_img)

    def on_canvas_resize(self, event=None):
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(50, self._draw_image)

    # ──────────────────────────────────────────
    # ZOOM / PAN
    # ──────────────────────────────────────────
    def zoom_in(self):
        self.zoom_factor = min(self.zoom_factor * 1.2, 10.0)
        self._draw_image()

    def zoom_out(self):
        self.zoom_factor = max(self.zoom_factor / 1.2, 0.1)
        self._draw_image()

    def zoom_reset(self):
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self._draw_image()

    def on_mousewheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def pan_start_cb(self, event):
        self.pan_start = (event.x, event.y)

    def pan_move_cb(self, event):
        if self.pan_start:
            dx = event.x - self.pan_start[0]
            dy = event.y - self.pan_start[1]
            self.pan_x += dx
            self.pan_y += dy
            self.pan_start = (event.x, event.y)
            self._draw_image()

    # ──────────────────────────────────────────
    # SORT / MOVE
    # ──────────────────────────────────────────
    def sort_to_category(self, w):
        if self.current_index < 0 or self.current_index >= len(self.photo_list):
            self.log("[WARN] Tidak ada foto aktif", tag="warn")
            return
        if not w["folder"]:
            messagebox.showwarning("Folder", f"Pilih folder tujuan untuk '{w['name']}' dulu.",
                                   parent=self.root)
            return

        src_path = self.photo_list[self.current_index]
        fname    = os.path.basename(src_path)
        dst_dir  = w["folder"]
        os.makedirs(dst_dir, exist_ok=True)
        dst_path = os.path.join(dst_dir, fname)

        # Handle name collision
        if os.path.exists(dst_path):
            base, ext = os.path.splitext(fname)
            ts = int(time.time())
            dst_path = os.path.join(dst_dir, f"{base}_{ts}{ext}")

        try:
            shutil.move(src_path, dst_path)
        except Exception as e:
            self.log(f"[WARN] Gagal pindah: {e}", tag="warn")
            return

        # Save to history
        record = {
            "filename":  fname,
            "src":       src_path,
            "dst":       dst_path,
            "timestamp": time.strftime("%H:%M:%S"),
        }
        self.history.append(record)
        self.redo_stack.clear()

        self.log(f"{fname} -> {w['name']}", tag="move")

        # Remove from list and show next
        self.photo_list.pop(self.current_index)
        if self.current_index >= len(self.photo_list):
            self.current_index = len(self.photo_list) - 1
        self.show_current_photo()

    # ──────────────────────────────────────────
    # UNDO / REDO
    # ──────────────────────────────────────────
    def undo_action(self):
        if not self.history:
            self.log("[WARN] Tidak ada aksi untuk di-undo", tag="warn")
            return

        record = self.history.pop()
        src = record["src"]  # original source path
        dst = record["dst"]  # where file is now

        try:
            os.makedirs(os.path.dirname(src), exist_ok=True)
            shutil.move(dst, src)
        except Exception as e:
            self.log(f"[WARN] Undo gagal: {e}", tag="warn")
            self.history.append(record)
            return

        self.redo_stack.append(record)
        self.log(f"Undo: {record['filename']} kembali ke folder sumber", tag="undo")

        # Re-insert into photo list
        if os.path.exists(src):
            if src not in self.photo_list:
                insert_pos = self.current_index if self.current_index >= 0 else 0
                self.photo_list.insert(insert_pos, src)
                self.current_index = insert_pos
        self.show_current_photo()

    def redo_action(self):
        if not self.redo_stack:
            self.log("[WARN] Tidak ada aksi untuk di-redo", tag="warn")
            return

        record = self.redo_stack.pop()
        src = record["src"]
        dst = record["dst"]

        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
        except Exception as e:
            self.log(f"[WARN] Redo gagal: {e}", tag="warn")
            self.redo_stack.append(record)
            return

        self.history.append(record)
        self.log(f"Redo: {record['filename']} -> tujuan", tag="redo")

        if src in self.photo_list:
            self.photo_list.remove(src)
            if self.current_index >= len(self.photo_list):
                self.current_index = len(self.photo_list) - 1
        self.show_current_photo()

    # ──────────────────────────────────────────
    # NAVIGATION (Arrow keys)
    # ──────────────────────────────────────────
    def go_prev(self, event=None):
        if not self.photo_list:
            return
        self.current_index = max(0, self.current_index - 1)
        self.show_current_photo()

    def go_next(self, event=None):
        if not self.photo_list:
            return
        self.current_index = min(len(self.photo_list) - 1, self.current_index + 1)
        self.show_current_photo()

    # ──────────────────────────────────────────
    # PROGRESS
    # ──────────────────────────────────────────
    def update_progress(self):
        total = len(self.photo_list)
        if total == 0:
            self.progress_label.configure(text="0 / 0 foto  (0%)")
            self.progress_bar_fg.place(width=0)
            return

        pos = self.current_index + 1
        pct = pos / total * 100
        self.progress_label.configure(text=f"{pos} / {total} foto  ({pct:.1f}%)")

        # Update bar
        self.root.update_idletasks()
        bar_w = self.progress_bar_bg.winfo_width()
        fill_w = int(bar_w * pos / total)
        self.progress_bar_fg.place(x=0, y=0, relheight=1.0, width=fill_w)

    # ──────────────────────────────────────────
    # LOG
    # ──────────────────────────────────────────
    def log(self, text, tag="info"):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n", tag)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    # ──────────────────────────────────────────
    # KEYBOARD SHORTCUTS
    # ──────────────────────────────────────────
    def bind_shortcuts(self):
        self.root.unbind_all("<Key>")
        self.root.bind("<Control-z>", lambda e: self.undo_action())
        self.root.bind("<Control-Z>", lambda e: self.undo_action())
        self.root.bind("<Control-y>", lambda e: self.redo_action())
        self.root.bind("<Control-Y>", lambda e: self.redo_action())
        self.root.bind("<Left>",      self.go_prev)
        self.root.bind("<Right>",     self.go_next)
        self.root.bind("<equal>",     lambda e: self.zoom_in())
        self.root.bind("<plus>",      lambda e: self.zoom_in())
        self.root.bind("<minus>",     lambda e: self.zoom_out())
        self.root.bind("<KP_Subtract>",lambda e: self.zoom_out())
        self.root.bind("<0>",          lambda e: self.zoom_reset())
        self.root.bind("<KP_0>",       lambda e: self.zoom_reset())

        # Category shortcuts
        for w in self.category_widgets:
            sc = w.get("shortcut", "")
            if sc:
                self.root.bind(f"<Key-{sc.lower()}>",
                               lambda e, wi=w: self.sort_to_category(wi))
                self.root.bind(f"<Key-{sc.upper()}>",
                               lambda e, wi=w: self.sort_to_category(wi))


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
def main():
    try:
        from PIL import Image, ImageTk  # noqa: F401
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])

    root = tk.Tk()
    root.title("Photo Sorter")

    # Dark title bar on Windows
    try:
        root.wm_attributes("-alpha", 1.0)
        import ctypes
        HWND = ctypes.windll.user32.GetParent(root.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, 20,
            ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
    except Exception:
        pass

    app = PhotoSorterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
