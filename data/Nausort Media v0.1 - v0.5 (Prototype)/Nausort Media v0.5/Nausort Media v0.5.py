"""
Nausort Media Prototype v0.5

=> Added:
- Configuration file support for:
    - Category names
    - Destination folders
    - Category colors
    - Keyboard shortcuts
- JSON-based palette loading system.
- Automatic fallback to default palettes.
- Support for additional image formats: WebP, BMP, GIF.
- Automatic Pillow installation if dependency is missing.

=> Changed:
- Introduced centralized UI theme constants.
- Added customizable button radius styling.
- Improved application configuration management.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import os, shutil, json, threading, time

try:
    from PIL import Image, ImageTk, ImageDraw
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageTk, ImageDraw

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
CONFIG_FILE      = "Nausort_Media_config.json"
SUPPORTED_EXTS   = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")

BG          = "#1c1c1e"
BG2         = "#2c2c2e"
BG3         = "#3a3a3c"
BG4         = "#48484a"
BORDER      = "#48484a"
TEXT        = "#f2f2f7"
TEXT_DIM    = "#8e8e93"
ACCENT      = "#0a84ff"
ACCENT2     = "#30d158"
WARN        = "#ff9f0a"
ERR         = "#ff453a"

TERM_BG     = "#111113"
TERM_INFO   = "#64d2ff"
TERM_MOVE   = "#a8d8a8"
TERM_UNDO   = "#ffd60a"
TERM_REDO   = "#30d158"
TERM_WARN   = "#ff6b6b"

RADIUS      = 10   # corner radius for custom buttons

DEFAULT_CONFIG = {
    "categories": [
        {"name": "Category 1", "folder": "", "color": "#2d2d2d", "shortcut": "1"},
        {"name": "Category 2", "folder": "", "color": "#2d2d2d", "shortcut": "2"},
    ]
}

PALETTE_FILE = "photo_sorter_palette.json"
DEFAULT_PALETTE = {
    "palette": [
        ["#ff5050","#ff8c50","#ffc850","#dcff50","#8cff50","#50ff78","#50ffc8","#50c8ff","#508cff","#7850ff","#c850ff","#ff50c8"],
        ["#dc4646","#dc7846","#dcb446","#bedc46","#78dc46","#46dc64","#46dcb4","#46b4dc","#4678dc","#6446dc","#b446dc","#dc46b4"],
        ["#b43c3c","#b4643c","#b4963c","#a0b43c","#64b43c","#3cb45a","#3cb496","#3c96b4","#3c64b4","#5a3cb4","#963cb4","#b43c96"],
        ["#823232","#825032","#826e32","#788232","#508232","#328246","#32826e","#326e82","#325082","#463282","#6e3282","#82326e"],
        ["#5a2828","#5a3c28","#5a5028","#505a28","#3c5a28","#285a3c","#285a50","#28505a","#283c5a","#3c285a","#50285a","#5a2850"],
    ]
}

def _load_palette():
    """Load palette from JSON file, fallback to DEFAULT_PALETTE."""
    if os.path.exists(PALETTE_FILE):
        try:
            with open(PALETTE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "palette" in data:
                return data["palette"]
        except Exception:
            pass
    return DEFAULT_PALETTE["palette"]


# ─────────────────────────────────────────────────────────────
# ROUNDED BUTTON  (Canvas-based, no ttk needed)
# ─────────────────────────────────────────────────────────────
class RoundedButton(tk.Frame):

    def __init__(self, parent, text="", command=None,
                 bg=BG2, fg=TEXT, hover_bg=BG3,
                 font=("Segoe UI", 10), radius=RADIUS,
                 padx=14, pady=8, min_width=0):
        self._bg        = bg
        self._hover_bg  = hover_bg
        self._fg        = fg
        self._text      = text
        self._font      = font
        self._command   = command
        self._enabled   = True
        self._padx      = padx
        self._pady      = pady
        self._w         = min_width  # kept for browse_btn min_width compat

        super().__init__(parent, bg=bg, cursor="hand2",
                         highlightthickness=1,
                         highlightbackground=BG4)

        self._label = tk.Label(self, text=text, bg=bg, fg=fg,
                               font=font, cursor="hand2",
                               padx=padx, pady=pady)
        self._label.pack(fill=tk.BOTH, expand=True)

        for widget in (self, self._label):
            widget.bind("<Enter>",          self._on_enter)
            widget.bind("<Leave>",          self._on_leave)
            widget.bind("<ButtonPress-1>",  self._on_press)
            widget.bind("<ButtonRelease-1>",self._on_release)

    def _set_color(self, color):
        self.configure(bg=color)
        self._label.configure(bg=color)

    def _on_enter(self, e):
        if self._enabled:
            self._set_color(self._hover_bg)

    def _on_leave(self, e):
        if self._enabled:
            self._set_color(self._bg)

    def _on_press(self, e):
        if self._enabled:
            self._set_color(BG4)

    def _on_release(self, e):
        if self._enabled:
            self._set_color(self._bg)
            if self._command:
                self._command()

    def configure_text(self, text):
        self._text = text
        self._label.configure(text=text)

    def configure_bg(self, color):
        self._bg = color
        self._set_color(color)

    def configure(self, **kw):
        # intercept command= so callers can do btn.configure(command=...)
        if "command" in kw:
            self._command = kw.pop("command")
        if kw:
            super().configure(**kw)

    def set_enabled(self, val):
        self._enabled = val
        self._label.configure(fg=self._fg if val else TEXT_DIM)

    def bind_right_click(self, callback):
        self.bind("<Button-3>", callback)
        self._label.bind("<Button-3>", callback)


# ─────────────────────────────────────────────────────────────
# DARK DIALOG  (custom Toplevel)
# ─────────────────────────────────────────────────────────────
class DarkDialog(tk.Toplevel):

    def __init__(self, parent, title="Dialog", width=320, height=160):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.configure(bg=BG2)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        # Center over parent
        px = parent.winfo_rootx() + parent.winfo_width()  // 2 - width  // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - height // 2
        self.geometry(f"{width}x{height}+{px}+{py}")
        self._build()
        self.wait_window()

    def _build(self):
        pass

    def _label(self, parent, text, **kw):
        return tk.Label(parent, text=text, bg=BG2, fg=TEXT,
                        font=("Segoe UI", 10), **kw)

    def _entry(self, parent, initial=""):
        e = tk.Entry(parent, bg=BG3, fg=TEXT, insertbackground=TEXT,
                     relief=tk.FLAT, font=("Segoe UI", 10),
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT)
        e.insert(0, initial)
        return e

    def _btn(self, parent, text, command, accent=False):
        bg = ACCENT if accent else BG3
        hv = "#1a8fff" if accent else BG4
        return RoundedButton(parent, text=text, command=command,
                             bg=bg, fg=TEXT, hover_bg=hv,
                             font=("Segoe UI", 10), radius=7,
                             padx=18, pady=7)


class AskStringDialog(DarkDialog):
    def __init__(self, parent, title, prompt, initial=""):
        self._prompt  = prompt
        self._initial = initial
        super().__init__(parent, title, 360, 155)

    def _build(self):
        tk.Label(self, text=self._prompt, bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 10)).pack(padx=20, pady=(18, 6), anchor="w")
        self._entry_var = tk.StringVar(value=self._initial)
        e = tk.Entry(self, textvariable=self._entry_var,
                     bg=BG3, fg=TEXT, insertbackground=TEXT,
                     relief=tk.FLAT, font=("Segoe UI", 11),
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=ACCENT)
        e.pack(fill=tk.X, padx=20, pady=(0, 14), ipady=6)
        e.focus_set()
        e.select_range(0, tk.END)
        e.bind("<Return>", lambda ev: self._ok())
        e.bind("<Escape>", lambda ev: self.destroy())

        row = tk.Frame(self, bg=BG2)
        row.pack(fill=tk.X, padx=20, pady=(0, 16))
        self._btn(row, "Cancel",  self.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        self._btn(row, "OK",     self._ok).pack(side=tk.RIGHT)

    def _ok(self):
        self.result = self._entry_var.get()
        self.destroy()


class ColorPickerDialog(tk.Toplevel):
    """Color picker: 12x5 palette grid from JSON + RGB sliders + HEX input."""

    def __init__(self, parent, initial="#2c2c2e"):
        super().__init__(parent)
        self.result    = None
        self._initial  = initial
        self._picked   = initial
        self._updating = False

        self.title("Pick Color")
        self.configure(bg=BG2)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        W, H = 460, 430
        px = parent.winfo_rootx() + parent.winfo_width()  // 2 - W // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - H // 2
        self.geometry(f"{W}x{H}+{px}+{py}")

        self._palette = _load_palette()  # list of rows, each row = 12 hex strings
        self._build()
        self._hex_to_sliders(initial)
        self.wait_window()

    def _build(self):
        # ── Header ──
        tk.Label(self, text="Pick Button Color", bg=BG2, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(padx=20, pady=(14, 0), anchor="w")

        # ── Palette grid 12 x 5 ──
        grid_frame = tk.Frame(self, bg=BG2)
        grid_frame.pack(padx=18, pady=(10, 0))

        self._swatch_refs = []   # keep canvas refs for highlight update
        for ri, row in enumerate(self._palette):
            for ci, color in enumerate(row):
                c = tk.Canvas(grid_frame, width=26, height=26,
                              highlightthickness=2,
                              highlightbackground=ACCENT if color == self._picked else BG2,
                              cursor="hand2", bg=color)
                c.grid(row=ri, column=ci, padx=1, pady=1)
                c.bind("<Button-1>", lambda e, col=color: self._select_color(col))
                self._swatch_refs.append((c, color))

        # ── Preview + HEX row ──
        ph_row = tk.Frame(self, bg=BG2)
        ph_row.pack(fill=tk.X, padx=20, pady=(12, 0))

        self._preview = tk.Frame(ph_row, bg=self._picked,
                                 width=52, height=32,
                                 highlightthickness=1, highlightbackground=BORDER)
        self._preview.pack(side=tk.LEFT, padx=(0, 10))
        self._preview.pack_propagate(False)
        self._preview_lbl = tk.Label(self._preview, text="Aa", bg=self._picked,
                                     fg=TEXT, font=("Segoe UI", 9, "bold"))
        self._preview_lbl.pack(expand=True)

        tk.Label(ph_row, text="HEX:", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self._hex_var = tk.StringVar(value=self._picked)
        hex_entry = tk.Entry(ph_row, textvariable=self._hex_var, width=10,
                             bg=BG3, fg=TEXT, insertbackground=TEXT,
                             relief=tk.FLAT, font=("Consolas", 10),
                             highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=ACCENT)
        hex_entry.pack(side=tk.LEFT, ipady=5)
        hex_entry.bind("<Return>",   lambda e: self._from_hex())
        hex_entry.bind("<FocusOut>", lambda e: self._from_hex())

        # ── RGB sliders ──
        sliders_frame = tk.Frame(self, bg=BG2)
        sliders_frame.pack(fill=tk.X, padx=20, pady=(10, 0))

        self._r_var = tk.IntVar()
        self._g_var = tk.IntVar()
        self._b_var = tk.IntVar()

        for label, var, color in [
            ("R", self._r_var, "#ff453a"),
            ("G", self._g_var, "#30d158"),
            ("B", self._b_var, "#0a84ff"),
        ]:
            row = tk.Frame(sliders_frame, bg=BG2)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label, bg=BG2, fg=color,
                     font=("Segoe UI", 9, "bold"), width=2).pack(side=tk.LEFT)
            sl = tk.Scale(row, from_=0, to=255, orient=tk.HORIZONTAL,
                          variable=var, command=lambda v: self._from_rgb(),
                          bg=BG2, fg=TEXT, troughcolor=BG3,
                          highlightthickness=0, sliderrelief=tk.FLAT,
                          activebackground=ACCENT, showvalue=False)
            sl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
            tk.Label(row, textvariable=var, bg=BG2, fg=TEXT_DIM,
                     font=("Consolas", 9), width=4).pack(side=tk.LEFT)

        # ── Buttons — both same neutral color ──
        btn_row = tk.Frame(self, bg=BG2)
        btn_row.pack(fill=tk.X, padx=20, pady=(14, 16))
        RoundedButton(btn_row, text="Cancel", command=self.destroy,
                      bg=BG3, fg=TEXT, hover_bg=BG4,
                      font=("Segoe UI", 10), padx=18, pady=7
                      ).pack(side=tk.RIGHT, padx=(6, 0))
        RoundedButton(btn_row, text="Apply", command=self._ok,
                      bg=BG3, fg=TEXT, hover_bg=BG4,
                      font=("Segoe UI", 10), padx=18, pady=7
                      ).pack(side=tk.RIGHT)

    # ── helpers ──
    def _select_color(self, color):
        try:
            self.winfo_rgb(color)
            self._picked = color
            self._hex_var.set(color)
            self._update_preview(color)
            self._hex_to_sliders(color)
            self._refresh_highlights()
        except Exception:
            pass

    def _refresh_highlights(self):
        for c, color in self._swatch_refs:
            c.configure(highlightbackground=ACCENT if color == self._picked else BG2)

    def _update_preview(self, color):
        self._preview.configure(bg=color)
        self._preview_lbl.configure(bg=color)

    def _from_hex(self):
        val = self._hex_var.get().strip()
        if not val.startswith("#"):
            val = "#" + val
        try:
            self.winfo_rgb(val)
            self._select_color(val)
        except Exception:
            pass

    def _rgb_to_hex(self, r, g, b):
        return f"#{max(0,min(255,int(r))):02x}{max(0,min(255,int(g))):02x}{max(0,min(255,int(b))):02x}"

    def _hex_to_rgb(self, hex_color):
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c*2 for c in h)
        return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)

    def _hex_to_sliders(self, hex_color):
        try:
            r, g, b = self._hex_to_rgb(hex_color)
            self._updating = True
            self._r_var.set(r); self._g_var.set(g); self._b_var.set(b)
            self._updating = False
        except Exception:
            self._updating = False

    def _from_rgb(self):
        if self._updating:
            return
        color = self._rgb_to_hex(self._r_var.get(), self._g_var.get(), self._b_var.get())
        self._picked = color
        self._hex_var.set(color)
        self._update_preview(color)
        self._refresh_highlights()

    def _ok(self):
        self.result = self._hex_var.get()
        self.destroy()


# ─────────────────────────────────────────────────────────────
# CONTEXT MENU  (dark)
# ─────────────────────────────────────────────────────────────
class DarkMenu(tk.Menu):
    def __init__(self, parent):
        super().__init__(parent, tearoff=0,
                         bg=BG3, fg=TEXT,
                         activebackground=ACCENT,
                         activeforeground=TEXT,
                         relief=tk.FLAT, bd=1,
                         font=("Segoe UI", 10))


# ─────────────────────────────────────────────────────────────
# WRAP FRAME  (auto-wrapping container)
# ─────────────────────────────────────────────────────────────
class WrapFrame(tk.Frame):

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.bind("<Configure>", self._relayout)
        self._children_order = []

    def add(self, widget):
        self._children_order.append(widget)
        widget.place_forget()
        self._relayout()

    def remove(self, widget):
        if widget in self._children_order:
            self._children_order.remove(widget)
        widget.destroy()
        self._relayout()

    def _relayout(self, event=None):
        self.update_idletasks()
        max_w = self.winfo_width()
        if max_w < 10:
            self.after(50, self._relayout)
            return

        x, y, row_h = 4, 4, 0
        GAP_X, GAP_Y = 8, 8

        for widget in self._children_order:
            widget.update_idletasks()
            ww = widget.winfo_reqwidth()
            wh = widget.winfo_reqheight()

            if x + ww > max_w - 4 and x > 4:
                x = 4
                y += row_h + GAP_Y
                row_h = 0

            widget.place(x=x, y=y)
            x += ww + GAP_X
            row_h = max(row_h, wh)

        total_h = y + row_h + 8
        self.configure(height=max(total_h, 10))


# ─────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────
class PhotoSorterApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Nausort Media")
        self.root.configure(bg=BG)
        self.root.geometry("1200x760")
        self.root.minsize(860, 580)

        # State
        self.photo_list      = []
        self.current_index   = -1
        self.source_folder   = ""
        self.config          = {}
        self.category_widgets = []

        # Image display
        self.zoom_factor     = 1.0
        self.pan_x           = 0
        self.pan_y           = 0
        self._pan_start      = None
        self._is_panning     = False
        self.current_pil     = None
        self._tk_img         = None
        self._after_id       = None
        self._preload_cache  = {}

        # History
        self.history         = []
        self.redo_stack      = []

        self._load_config()
        self._build_ui()
        self._apply_config()
        self._bind_shortcuts()

        self.log("[INFO] Nausort Media v0.1")
        self.log("Program running...", tag="info")
        self.log("Press number keys for button shortcuts", tag="info")
        self.log("─" * 36, tag="dim")

    # ──────────────────────────────────────────
    # CONFIG
    # ──────────────────────────────────────────
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                return
            except Exception:
                pass
        self.config = json.loads(json.dumps(DEFAULT_CONFIG))

    def _save_config(self):
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
            self.log(f"[WARN] Gagal simpan config: {e}", tag="warn")

    # ──────────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────────
    def _build_ui(self):
        # ── Horizontal PanedWindow for draggable divider ──
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                                    bg=BG, sashwidth=6, sashrelief=tk.FLAT,
                                    handlesize=0, bd=0)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self.left_col  = tk.Frame(self.paned, bg=BG)
        self.right_col = tk.Frame(self.paned, bg=BG, width=290)
        self.paned.add(self.left_col,  minsize=400, stretch="always")
        self.paned.add(self.right_col, minsize=220, stretch="never")
        self.paned.paneconfigure(self.right_col, width=290)

        # ── LEFT: View label ──
        self._section_label(self.left_col, "View")

        # File name bar
        fname_bg = tk.Frame(self.left_col, bg=BG3,
                            highlightthickness=1, highlightbackground=BORDER)
        fname_bg.pack(fill=tk.X, pady=(6, 0))
        self.filename_var = tk.StringVar()
        tk.Label(fname_bg, textvariable=self.filename_var,
                 bg=BG3, fg=TEXT, font=("Segoe UI", 10),
                 anchor="center", pady=5).pack(fill=tk.X)

        # Canvas
        self.canvas_host = tk.Frame(self.left_col, bg="black",
                                    highlightthickness=1, highlightbackground=BORDER)
        self.canvas_host.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.canvas = tk.Canvas(self.canvas_host, bg="black",
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<MouseWheel>",        self._on_wheel)
        self.canvas.bind("<ButtonPress-1>",     self._pan_start)
        self.canvas.bind("<B1-Motion>",         self._pan_move)
        self.canvas.bind("<ButtonRelease-1>",   self._pan_end)
        self.canvas.bind("<Double-Button-1>",   lambda e: self._zoom_reset())
        self.canvas.bind("<Configure>",         self._on_canvas_resize)

        # ── Progress / total label ──
        self.total_label = tk.Label(self.left_col, text="",
                                    bg=BG, fg=TEXT_DIM,
                                    font=("Segoe UI", 9), anchor="w")
        self.total_label.pack(fill=tk.X, pady=(5, 0))

        # ── Category wrap area ──
        cat_container = tk.Frame(self.left_col, bg=BG,
                                 highlightthickness=1, highlightbackground=BORDER)
        cat_container.pack(fill=tk.X, pady=(8, 0))

        # Inner canvas for scrollable wrap area
        self.cat_scroll_canvas = tk.Canvas(cat_container, bg=BG,
                                           highlightthickness=0)

        # Dark elegant custom scrollbar (Google dark mode style)
        style_frame = tk.Frame(cat_container, bg="#1a1a1c", width=8)
        style_frame.pack(side=tk.RIGHT, fill=tk.Y)
        style_frame.pack_propagate(False)

        self._sb_track = tk.Canvas(style_frame, bg="#1a1a1c",
                                   width=8, highlightthickness=0)
        self._sb_track.pack(fill=tk.BOTH, expand=True)
        self._sb_thumb = self._sb_track.create_rectangle(
            2, 0, 6, 40, fill="#3a3a3c", outline="", tags="thumb")
        self._sb_track.bind("<ButtonPress-1>",   self._sb_click)
        self._sb_track.bind("<B1-Motion>",       self._sb_drag)
        self._sb_track.bind("<Enter>",           self._sb_hover_on)
        self._sb_track.bind("<Leave>",           self._sb_hover_off)
        self._sb_drag_start = None

        self.cat_scroll_canvas.configure(yscrollcommand=self._custom_sb_set)
        self.cat_scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.cat_wrap = WrapFrame(self.cat_scroll_canvas, bg=BG)
        self.cat_wrap_window = self.cat_scroll_canvas.create_window(
            (0, 0), window=self.cat_wrap, anchor="nw")

        self.cat_wrap.bind("<Configure>", self._on_wrap_configure)
        self.cat_scroll_canvas.bind("<Configure>", self._on_scroll_canvas_resize)
        self.cat_scroll_canvas.bind("<MouseWheel>", self._on_cat_scroll)
        self.cat_wrap.bind("<MouseWheel>",          self._on_cat_scroll)

        # ── RIGHT: Terminal ──
        self._section_label(self.right_col, "Terminal")
        self.log_text = tk.Text(self.right_col, bg=TERM_BG, fg=TERM_MOVE,
                                font=("Consolas", 9), state=tk.DISABLED,
                                wrap=tk.WORD, relief=tk.FLAT, bd=0,
                                insertbackground=TEXT, pady=4, padx=6)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.log_text.tag_configure("info", foreground=TERM_INFO)
        self.log_text.tag_configure("move", foreground=TERM_MOVE)
        self.log_text.tag_configure("undo", foreground=TERM_UNDO)
        self.log_text.tag_configure("redo", foreground=TERM_REDO)
        self.log_text.tag_configure("warn", foreground=TERM_WARN)
        self.log_text.tag_configure("dim",  foreground=TEXT_DIM)

        # ── RIGHT: Navigation ──
        self._section_label(self.right_col, "Navigation", pady=(12, 0))
        nav_row = tk.Frame(self.right_col, bg=BG)
        nav_row.pack(fill=tk.X, pady=(6, 0))
        nav_row.columnconfigure(0, weight=1)
        nav_row.columnconfigure(1, weight=1)

        self._nav_prev = self._make_full_btn(
            nav_row, "Previous", self._undo_action,
            font=("Segoe UI", 10, "bold"))
        self._nav_prev.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self._nav_next = self._make_full_btn(
            nav_row, "Next", self._redo_action,
            font=("Segoe UI", 10, "bold"))
        self._nav_next.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self._make_full_btn(
            self.right_col, "Add New Button", self._add_category,
            font=("Segoe UI", 10, "bold")).pack(fill=tk.X, pady=(8, 0))

        self._make_full_btn(
            self.right_col, "Import Folder", self._import_folder,
            bg=BG2, hover_bg=BG3,
            font=("Segoe UI", 10, "bold")).pack(fill=tk.X, pady=(6, 0))

    # ──────────────────────────────────────────
    # CUSTOM DARK SCROLLBAR
    # ──────────────────────────────────────────
    def _custom_sb_set(self, first, last):

        try:
            first, last = float(first), float(last)
            h = self._sb_track.winfo_height()
            if h < 10:
                return
            thumb_h  = max(20, int((last - first) * h))
            thumb_y0 = int(first * h)
            thumb_y1 = thumb_y0 + thumb_h
            self._sb_track.coords(self._sb_thumb, 2, thumb_y0, 6, thumb_y1)
            # Hide thumb if no scrolling needed
            color = "#3a3a3c" if (last - first) < 1.0 else "#1a1a1c"
            self._sb_track.itemconfigure(self._sb_thumb, fill=color)
            self._sb_first = first
            self._sb_last  = last
        except Exception:
            pass

    def _sb_click(self, event):
        self._sb_drag_start = event.y
        coords = self._sb_track.coords(self._sb_thumb)
        if coords:
            self._sb_thumb_start = coords[1]

    def _sb_drag(self, event):
        if self._sb_drag_start is None:
            return
        h = self._sb_track.winfo_height()
        if h < 1:
            return
        delta = (event.y - self._sb_drag_start) / h
        self.cat_scroll_canvas.yview_moveto(
            max(0.0, getattr(self, "_sb_first", 0) + delta))

    def _sb_hover_on(self, event):
        self._sb_track.itemconfigure(self._sb_thumb, fill="#5a5a5e")

    def _sb_hover_off(self, event):
        self._sb_track.itemconfigure(self._sb_thumb, fill="#3a3a3c")

    def _section_label(self, parent, text, pady=(0, 0)):
        tk.Label(parent, text=text, bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 10, "bold"),
                 anchor="w").pack(fill=tk.X, pady=pady)
        tk.Frame(parent, bg=BORDER, height=1).pack(fill=tk.X)

    def _make_full_btn(self, parent, text, command,
                       bg=BG2, hover_bg=BG3, fg=TEXT,
                       font=("Segoe UI", 10)):
        btn = tk.Button(parent, text=text, command=command,
                        bg=bg, fg=fg, font=font,
                        activebackground=hover_bg, activeforeground=TEXT,
                        relief=tk.FLAT, bd=0, cursor="hand2",
                        padx=12, pady=9)
        btn.bind("<Enter>", lambda e, b=btn, h=hover_bg: b.configure(bg=h))
        btn.bind("<Leave>", lambda e, b=btn, c=bg:       b.configure(bg=c))
        return btn

    def _on_wrap_configure(self, event=None):
        self.cat_scroll_canvas.configure(
            scrollregion=self.cat_scroll_canvas.bbox("all"))
        h = min(self.cat_wrap.winfo_reqheight(), 200)
        self.cat_scroll_canvas.configure(height=max(h, 80))

    def _on_scroll_canvas_resize(self, event=None):
        w = self.cat_scroll_canvas.winfo_width()
        self.cat_scroll_canvas.itemconfigure(self.cat_wrap_window, width=w)
        self.cat_wrap._relayout()

    def _on_cat_scroll(self, event):
        self.cat_scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ──────────────────────────────────────────
    # APPLY CONFIG
    # ──────────────────────────────────────────
    def _apply_config(self):
        for w in list(self.category_widgets):
            w["frame"].destroy()
        self.category_widgets.clear()

        for cat in self.config.get("categories", []):
            self._add_category_widget(
                name=cat.get("name", "Kategori"),
                folder=cat.get("folder", ""),
                color=cat.get("color", BG2),
                shortcut=cat.get("shortcut", ""),
            )

    # ──────────────────────────────────────────
    # CATEGORY WIDGET
    # ──────────────────────────────────────────
    def _add_category_widget(self, name="New Category", folder="",
                              color=BG2, shortcut=""):
        cat_btn   = RoundedButton(
            self.cat_wrap, text=name, bg=color,
            fg=TEXT, hover_bg=BG4,
            font=("Segoe UI", 10, "bold"),
            radius=RADIUS, padx=16, pady=10,
        )

        w = {
            "frame":    cat_btn,   # kept for API compat (WrapFrame.remove uses this)
            "cat_btn":  cat_btn,
            "name":     name,
            "folder":   folder,
            "color":    color,
            "shortcut": shortcut,
        }
        self.category_widgets.append(w)

        cat_btn.configure(command=lambda wi=w: self._sort_to(wi))
        cat_btn.bind_right_click(lambda e, wi=w: self._context_menu(e, wi))

        self.cat_wrap.add(cat_btn)
        self._save_config()
        return w

    def _folder_label(self, folder, max_len=20):
        if not folder:
            return "Browse"
        name = os.path.basename(folder) or folder
        return name if len(name) <= max_len else name[:max_len - 1] + "…"

    def _update_cat_btn(self, w):
        w["cat_btn"].configure_text(w.get("name", ""))
        w["cat_btn"].configure_bg(w["color"])

    # ──────────────────────────────────────────
    # CONTEXT MENU
    # ──────────────────────────────────────────
    def _context_menu(self, event, w):
        # Show current folder as clickable label if set
        folder_info = w.get("folder", "")
        menu = DarkMenu(self.root)
        if folder_info:
            short = os.path.basename(folder_info) or folder_info
            if len(short) > 28: short = short[:27] + "…"
            menu.add_command(label=f"📁  {short} ↗",
                             command=lambda: self._open_folder_in_explorer(folder_info))
            menu.add_separator()
        menu.add_command(label="Set Destination Folder",  command=lambda: self._choose_folder(w))
        menu.add_separator()
        menu.add_command(label="Rename",             command=lambda: self._rename(w))
        menu.add_command(label="Change Color",       command=lambda: self._change_color(w))
        menu.add_command(label="Change Shortcut",    command=lambda: self._change_shortcut(w))
        menu.add_separator()
        menu.add_command(label="Delete Category",    command=lambda: self._delete_cat(w))
        menu.tk_popup(event.x_root, event.y_root)

    def _open_folder_in_explorer(self, folder):
        """Open folder in the system file explorer."""
        import subprocess, sys, platform
        try:
            if platform.system() == "Windows":
                os.startfile(folder)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            self.log(f"[WARN] Failed to open folder: {e}", tag="warn")

    def _rename(self, w):
        d = AskStringDialog(self.root, "Rename", "New category name:", w["name"])
        if d.result and d.result.strip():
            w["name"] = d.result.strip()
            self._update_cat_btn(w)
            self._save_config()

    def _change_color(self, w):
        d = ColorPickerDialog(self.root, w["color"])
        if d.result:
            w["color"] = d.result
            self._update_cat_btn(w)
            self._save_config()

    def _change_shortcut(self, w):
        d = AskStringDialog(self.root, "Shortcut", "New shortcut (1 character):",
                            w.get("shortcut", ""))
        if d.result is not None:
            w["shortcut"] = d.result.strip()[:1].upper() if d.result.strip() else ""
            self._update_cat_btn(w)
            self._save_config()
            self._bind_shortcuts()

    def _delete_cat(self, w):
        if messagebox.askyesno("Delete", f"Delete category '{w['name']}'?",
                               parent=self.root):
            self.category_widgets.remove(w)
            self.cat_wrap.remove(w["cat_btn"])
            self._save_config()

    def _add_category(self):
        self._add_category_widget(name=f"Category {len(self.category_widgets)+1}", shortcut="")
        self._bind_shortcuts()

    def _choose_folder(self, w):
        folder = filedialog.askdirectory(parent=self.root)
        if folder:
            w["folder"] = folder
            self._save_config()
            self.log(f"[INFO] Folder tujuan '{w['name']}': {os.path.basename(folder)}", tag="info")

    # ──────────────────────────────────────────
    # IMPORT
    # ──────────────────────────────────────────
    def _import_folder(self):
        folder = filedialog.askdirectory(parent=self.root)
        if not folder:
            return
        self.source_folder = folder
        self.photo_list = [
            os.path.join(folder, f)
            for f in sorted(os.listdir(folder))
            if f.lower().endswith(SUPPORTED_EXTS)
        ]
        self.current_index  = 0 if self.photo_list else -1
        self._preload_cache.clear()
        self.history.clear()
        self.redo_stack.clear()
        total = len(self.photo_list)
        self.total_label.configure(text=f"Total Photos: {total}")
        self.log(f"[INFO] Folder imported successfully: {folder}", tag="info")
        self.log(f"[INFO] {total} photos found", tag="info")
        if self.photo_list:
            self._show_photo()

    # ──────────────────────────────────────────
    # PHOTO DISPLAY
    # ──────────────────────────────────────────
    def _show_photo(self):
        if not (0 <= self.current_index < len(self.photo_list)):
            self.canvas.delete("all")
            self.filename_var.set("")
            return

        path = self.photo_list[self.current_index]
        self.filename_var.set(os.path.basename(path))

        # Always reset zoom/pan on new photo
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0

        self._load_draw(path)
        threading.Thread(target=self._preload_next, daemon=True).start()

    def _preload_next(self):
        for off in [1, 2]:
            ni = self.current_index + off
            if 0 <= ni < len(self.photo_list):
                p = self.photo_list[ni]
                if p not in self._preload_cache:
                    try:
                        img = Image.open(p)
                        img.load()
                        self._preload_cache[p] = img
                    except Exception:
                        pass
        # Trim cache
        if len(self._preload_cache) > 12:
            for k in list(self._preload_cache.keys())[:-10]:
                del self._preload_cache[k]

    def _load_draw(self, path):
        try:
            img = self._preload_cache.get(path) or Image.open(path)
            if hasattr(img, "seek"):
                try: img.seek(0)
                except Exception: pass
            img.load()
            self.current_pil = img
            self._draw_image()
        except Exception as e:
            self.canvas.delete("all")
            cw = self.canvas.winfo_width()  or 400
            ch = self.canvas.winfo_height() or 300
            self.canvas.create_text(cw//2, ch//2,
                text=f"Failed to load image:\n{e}",
                fill=TEXT_DIM, font=("Segoe UI", 10), justify="center")

    def _draw_image(self):
        if not self.current_pil:
            return
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            self.root.after(50, self._draw_image)
            return

        iw, ih = self.current_pil.size
        scale   = min(cw / iw, ch / ih)
        base_w  = int(iw * scale)
        base_h  = int(ih * scale)
        disp_w  = max(1, int(base_w * self.zoom_factor))
        disp_h  = max(1, int(base_h * self.zoom_factor))

        # Clamp pan
        half_excess_x = max(0, (disp_w - cw) // 2 + 30)
        half_excess_y = max(0, (disp_h - ch) // 2 + 30)
        self.pan_x = max(-half_excess_x, min(half_excess_x, self.pan_x))
        self.pan_y = max(-half_excess_y, min(half_excess_y, self.pan_y))

        x0 = (cw - disp_w) // 2 + self.pan_x
        y0 = (ch - disp_h) // 2 + self.pan_y

        resized     = self.current_pil.resize((disp_w, disp_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(resized)
        self.canvas.create_image(x0, y0, anchor="nw", image=self._tk_img)

    def _on_canvas_resize(self, event=None):
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(60, self._draw_image)

    # ──────────────────────────────────────────
    # ZOOM / PAN
    # ──────────────────────────────────────────
    def _zoom_in(self):
        self.zoom_factor = min(self.zoom_factor * 1.25, 12.0)
        self._draw_image()

    def _zoom_out(self):
        self.zoom_factor = max(self.zoom_factor / 1.25, 0.1)
        self._draw_image()

    def _zoom_reset(self):
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self._draw_image()

    def _on_wheel(self, event):
        if event.delta > 0:
            self._zoom_in()
        else:
            self._zoom_out()

    def _pan_start(self, event):
        self._pan_start_xy = (event.x, event.y)
        self._is_panning   = True
        self.canvas.configure(cursor="fleur")

    def _pan_move(self, event):
        if self._is_panning and self._pan_start_xy:
            dx = event.x - self._pan_start_xy[0]
            dy = event.y - self._pan_start_xy[1]
            self.pan_x += dx
            self.pan_y += dy
            self._pan_start_xy = (event.x, event.y)
            self._draw_image()

    def _pan_end(self, event):
        self._is_panning = False
        self.canvas.configure(cursor="crosshair")

    # ──────────────────────────────────────────
    # SORT
    # ──────────────────────────────────────────
    def _sort_to(self, w):
        if not (0 <= self.current_index < len(self.photo_list)):
            self.log("[WARN] No active photo.", tag="warn"); return
        if not w["folder"]:
            messagebox.showwarning("Empty Folder",
                f"Choose a destination folder for '{w['name']}' first.",
                parent=self.root); return

        src  = self.photo_list[self.current_index]
        name = os.path.basename(src)
        dst_dir  = w["folder"]
        os.makedirs(dst_dir, exist_ok=True)
        dst  = os.path.join(dst_dir, name)
        if os.path.exists(dst):
            base, ext = os.path.splitext(name)
            dst = os.path.join(dst_dir, f"{base}_{int(time.time())}{ext}")

        try:
            shutil.move(src, dst)
        except Exception as e:
            self.log(f"[WARN] Gagal pindah: {e}", tag="warn"); return

        self.history.append({"filename": name, "src": src, "dst": dst,
                             "ts": time.strftime("%H:%M:%S")})
        self.redo_stack.clear()
        self.log(f"=> {name}  →  {w['name']}", tag="move")

        self.photo_list.pop(self.current_index)
        if self.current_index >= len(self.photo_list):
            self.current_index = len(self.photo_list) - 1
        self._show_photo()

    # ──────────────────────────────────────────
    # UNDO / REDO
    # ──────────────────────────────────────────
    def _undo_action(self):
        if not self.history:
            self.log("[WARN] Nothing to undo.", tag="warn"); return
        rec = self.history.pop()
        try:
            os.makedirs(os.path.dirname(rec["src"]), exist_ok=True)
            shutil.move(rec["dst"], rec["src"])
        except Exception as e:
            self.log(f"[WARN] Undo failed: {e}", tag="warn")
            self.history.append(rec); return
        self.redo_stack.append(rec)
        self.log(f"Undo: {rec['filename']} moved back to source folder", tag="undo")
        if rec["src"] not in self.photo_list:
            pos = max(0, self.current_index)
            self.photo_list.insert(pos, rec["src"])
            self.current_index = pos
        self._show_photo()

    def _redo_action(self):
        if not self.redo_stack:
            self.log("[WARN] Nothing to redo.", tag="warn"); return
        rec = self.redo_stack.pop()
        try:
            os.makedirs(os.path.dirname(rec["dst"]), exist_ok=True)
            shutil.move(rec["src"], rec["dst"])
        except Exception as e:
            self.log(f"[WARN] Redo failed: {e}", tag="warn")
            self.redo_stack.append(rec); return
        self.history.append(rec)
        self.log(f"Redo: {rec['filename']} → destination", tag="redo")
        if rec["src"] in self.photo_list:
            self.photo_list.remove(rec["src"])
            if self.current_index >= len(self.photo_list):
                self.current_index = len(self.photo_list) - 1
        self._show_photo()

    # ──────────────────────────────────────────
    # ARROW NAV
    # ──────────────────────────────────────────
    def _go_prev(self, event=None):
        if self.photo_list:
            self.current_index = max(0, self.current_index - 1)
            self._show_photo()

    def _go_next(self, event=None):
        if self.photo_list:
            self.current_index = min(len(self.photo_list)-1, self.current_index+1)
            self._show_photo()

    # ──────────────────────────────────────────
    # LOG
    # ──────────────────────────────────────────
    def log(self, text, tag="move"):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n", tag)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    # ──────────────────────────────────────────
    # SHORTCUTS
    # ──────────────────────────────────────────
    def _bind_shortcuts(self):
        self.root.bind("<Control-z>", lambda e: self._undo_action())
        self.root.bind("<Control-Z>", lambda e: self._undo_action())
        self.root.bind("<Control-y>", lambda e: self._redo_action())
        self.root.bind("<Control-Y>", lambda e: self._redo_action())
        self.root.bind("<Left>",      self._go_prev)
        self.root.bind("<Right>",     self._go_next)
        self.root.bind("<equal>",     lambda e: self._zoom_in())
        self.root.bind("<plus>",      lambda e: self._zoom_in())
        self.root.bind("<minus>",     lambda e: self._zoom_out())
        self.root.bind("<KP_Subtract>",lambda e: self._zoom_out())
        self.root.bind("<0>",         lambda e: self._zoom_reset())
        self.root.bind("<KP_0>",      lambda e: self._zoom_reset())

        for w in self.category_widgets:
            sc = w.get("shortcut", "")
            if sc:
                self.root.bind(f"<Key-{sc.lower()}>",
                               lambda e, wi=w: self._sort_to(wi))
                self.root.bind(f"<Key-{sc.upper()}>",
                               lambda e, wi=w: self._sort_to(wi))


# ─────────────────────────────────────────────────────────────
# ENTRY
# ─────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.title("Nausort Media")

    # Dark title bar (Windows 11)
    try:
        import ctypes
        HWND = ctypes.windll.user32.GetParent(root.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            HWND, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
    except Exception:
        pass

    PhotoSorterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
