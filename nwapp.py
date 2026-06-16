import csv
import re
import ctypes
import io
import ipaddress
import json
import math
import pathlib
import tkinter as tk
from ctypes import wintypes
from tkinter import filedialog, messagebox, ttk

REGISTRY_FILE = pathlib.Path(__file__).parent / "networks.json"

def _load_registry():
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _save_registry(data):
    REGISTRY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

from PIL import Image, ImageDraw

# ── Color palette (yumekawa: lavender + violet) ───────────────────────
C = {
    "bg": "#F2EEFF", "card": "#FDFCFF", "card_h": "#E8E0FF",
    "accent": "#8B5CF6", "accent_dk": "#6D3DD1", "accent_lt": "#C4B5FD",
    "text": "#4C2D8F", "text_sub": "#9B87C9", "border": "#D5C9F7",
    "tab_act": "#FDFCFF", "tab_inact": "#E8E0FF",
    "entry_bg": "#EDE5FF", "shadow": "#D8CFED",
}

ICON_PALETTE = {}  # colors inlined in _make_icon_image

FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_SMALL = ("Segoe UI", 8)
FONT_SMALL_BOLD = ("Segoe UI", 8, "bold")


# ── Drawing helpers ────────────────────────────────────────────────────
def _draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    kw.setdefault("outline", "")
    r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    for ax, ay, start in (
        (x1, y1, 90), (x2 - 2 * r, y1, 0),
        (x1, y2 - 2 * r, 180), (x2 - 2 * r, y2 - 2 * r, 270),
    ):
        canvas.create_arc(ax, ay, ax + 2 * r, ay + 2 * r,
                           start=start, extent=90, style="pieslice", **kw)
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **kw)
    canvas.create_rectangle(x1, y1 + r, x2, y2 - r, **kw)


def _hover(widget, on_color, off_color):
    widget.bind("<Enter>", lambda e: widget.config(bg=on_color))
    widget.bind("<Leave>", lambda e: widget.config(bg=off_color))


def _star_points(cx, cy, r_outer, r_inner, points, rotation):
    """中心(cx,cy)を基準とした星型(point数)の頂点リストを返す"""
    pts = []
    n = points * 2
    for i in range(n):
        angle = math.radians(rotation + i * (360 / n))
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return pts


def _make_icon_pil(size):
    s = size / 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=round(7 * s),
        fill=(139, 92, 246, 255))
    # Cloud: three overlapping circles + bottom fill
    d = ImageDraw.Draw(img)
    cf = (255, 255, 255, 215)
    d.ellipse([5*s, 14*s, 15*s, 24*s], fill=cf)
    d.ellipse([9*s,  8*s, 23*s, 22*s], fill=cf)
    d.ellipse([17*s, 14*s, 27*s, 24*s], fill=cf)
    d.rectangle([5*s, 19*s, 27*s, 24*s], fill=cf)
    return img


def _make_icon_image(size):
    buf = io.BytesIO()
    _make_icon_pil(size).save(buf, format="PNG")
    return tk.PhotoImage(data=buf.getvalue())


def _apply_titlebar_theme(win):
    """Color the Windows 11 title bar to match the app palette (no-op elsewhere)."""
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()

        def cref(hex_color):
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            return (b << 16) | (g << 8) | r

        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        for attr, val in ((35, cref(C["accent"])), (36, cref("#FFFFFF")), (34, cref(C["accent_dk"]))):
            v = wintypes.DWORD(val)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:
        pass


class RoundedCard(tk.Canvas):
    """Canvas-backed container with a rounded-rectangle background."""

    def __init__(self, parent, radius=8, pad=4, autosize=True):
        super().__init__(parent, bg=C["bg"], highlightthickness=0, bd=0)
        self._radius = radius
        self._pad = pad
        self._autosize = autosize
        self.inner = tk.Frame(self, bg=C["card"])
        self._win = self.create_window(pad, pad, anchor="nw", window=self.inner)
        self.bind("<Configure>", self._redraw)
        if autosize:
            self.inner.bind("<Configure>", self._sync_height)

    def _sync_height(self, event=None):
        req_h = self.inner.winfo_reqheight() + 2 * self._pad
        if self.winfo_reqheight() != req_h:
            self.configure(height=req_h)

    def _redraw(self, event=None):
        self.delete("bg")
        w, h = self.winfo_width(), self.winfo_height()
        if w > 2 * self._pad and h > 2 * self._pad:
            _draw_rounded_rect(self, 2, 3, w - 1, h + 1, self._radius, fill=C["shadow"], tags="bg")
            _draw_rounded_rect(self, 0, 0, w - 2, h - 1, self._radius, fill=C["card"], tags="bg")
            self.tag_lower("bg")
        self.coords(self._win, self._pad, self._pad)
        kw = {"width": max(0, w - 2 * self._pad)}
        if not self._autosize:
            kw["height"] = max(0, h - 2 * self._pad)
        self.itemconfig(self._win, **kw)


# ── Widget builder helpers ─────────────────────────────────────────────
def _card_title(parent, row, text, columnspan=2):
    tk.Label(parent, text=text, bg=C["card"], fg=C["accent_dk"], font=FONT_BOLD).grid(
        row=row, column=0, columnspan=columnspan, sticky="w", pady=(0, 2))


def _field_row(parent, row, label_text, default=""):
    tk.Label(parent, text=label_text, bg=C["card"], fg=C["text_sub"], font=FONT_SMALL).grid(
        row=row, column=0, sticky="w", padx=(0, 8), pady=1)
    entry = tk.Entry(parent, font=FONT, bg=C["entry_bg"], fg=C["text"],
                      insertbackground=C["accent"], relief="flat",
                      highlightthickness=0, bd=0)
    entry.insert(0, default)
    entry.grid(row=row, column=1, sticky="ew", pady=1)
    return entry


def _hint_label(parent, row, text):
    tk.Label(parent, text=text, bg=C["card"], fg=C["text_sub"], font=FONT_SMALL).grid(
        row=row, column=2, sticky="w", padx=(8, 0))


def _result_row(parent, row, label_text):
    tk.Label(parent, text=label_text, bg=C["card"], fg=C["text_sub"], font=FONT_SMALL).grid(
        row=row, column=0, sticky="w", padx=(0, 16), pady=0)
    value = tk.Label(parent, text="-", bg=C["card"], fg=C["text"], font=FONT_BOLD)
    value.grid(row=row, column=1, sticky="w", pady=0)
    return value


def _make_button(parent, text, command):
    btn = tk.Button(parent, text=text, command=command, font=FONT_BOLD,
                     bg=C["accent"], fg="#FFFFFF", activebackground=C["accent_dk"],
                     activeforeground="#FFFFFF", relief="flat", bd=0,
                     cursor="hand2", padx=6, pady=3)
    _hover(btn, C["accent_dk"], C["accent"])
    return btn


def _make_back_button(parent, command):
    btn = tk.Button(parent, text="← Back", command=command, font=FONT_SMALL,
                    bg=C["bg"], fg=C["text_sub"], activebackground=C["card_h"],
                    activeforeground=C["accent_dk"], relief="flat", bd=0,
                    cursor="hand2", padx=4, pady=2)
    return btn


# ── Subnet calculation logic ───────────────────────────────────────────
def parse_prefix(mask_text):
    """サブネットマスク文字列('/24', '24', '255.255.255.0')をプレフィックス長(int)に変換する"""
    text = mask_text.strip()
    if text.startswith('/'):
        text = text[1:]
    if not text:
        raise ValueError("サブネットマスクを入力してください")
    if text.isdigit():
        prefix = int(text)
        if not (0 <= prefix <= 32):
            raise ValueError("プレフィックス長は0~32の範囲で指定してください")
        return prefix
    return ipaddress.IPv4Network(f"0.0.0.0/{text}").prefixlen


def usable_host_count(prefixlen):
    """プレフィックス長から利用可能ホスト数を求める(/31, /32の特殊ケースを考慮)"""
    if prefixlen == 32:
        return 1
    if prefixlen == 31:
        return 2
    return 2 ** (32 - prefixlen) - 2


def required_prefix(host_count):
    """必要端末数から必要なプレフィックス長を求める"""
    if host_count <= 0:
        raise ValueError("必要端末数は1以上で指定してください")
    if host_count == 1:
        return 32
    if host_count == 2:
        return 31
    bits = math.ceil(math.log2(host_count + 2))
    prefix = 32 - bits
    if prefix < 0:
        raise ValueError("必要端末数が大きすぎます")
    return prefix


def network_info(network):
    """ipaddress.IPv4Networkから表示用の情報をまとめる"""
    prefixlen = network.prefixlen
    usable = usable_host_count(prefixlen)

    if prefixlen >= 31:
        first_usable = network.network_address
        last_usable = network.broadcast_address
    else:
        first_usable = network.network_address + 1
        last_usable = network.broadcast_address - 1

    return {
        "network": str(network.network_address),
        "broadcast": str(network.broadcast_address),
        "netmask": str(network.netmask),
        "wildcard": str(network.hostmask),
        "cidr": f"/{prefixlen}",
        "total": 2 ** (32 - prefixlen),
        "usable": usable,
        "first_usable": str(first_usable),
        "last_usable": str(last_usable),
        "range": f"{first_usable} ~ {last_usable}",
    }



# ── Application ─────────────────────────────────────────────────────────
class SubnetCalculatorApp(tk.Tk):
    def __init__(self):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "nwapp.subnet_calculator.1")
        except Exception:
            pass

        super().__init__()
        self.title("Subnet Calculator")
        self.configure(bg=C["bg"])

        self._icon_images = [_make_icon_image(s) for s in (64, 32, 16)]
        self.iconphoto(True, *self._icon_images)

        try:
            _ico_path = pathlib.Path(__file__).parent / "_icon.ico"
            _make_icon_pil(256).save(
                str(_ico_path), format="ICO",
                sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
            self.iconbitmap(str(_ico_path))
            hicon = ctypes.windll.user32.LoadImageW(
                0, str(_ico_path), 1, 0, 0, 0x0010 | 0x0040)
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)
            ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)
        except Exception:
            pass

        self.after(50, lambda: _apply_titlebar_theme(self))

        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                    foreground=C["text"], borderwidth=0, font=FONT_SMALL, rowheight=18)
        s.configure("Treeview.Heading", background=C["card_h"], foreground=C["accent_dk"],
                    font=FONT_SMALL_BOLD, relief="flat", padding=2)
        s.map("Treeview", background=[("selected", C["accent_lt"])],
              foreground=[("selected", C["text"])])
        s.map("Treeview.Heading", background=[("active", C["card_h"])])
        s.layout("Slim.Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {"children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})],
             "sticky": "ns"})])
        s.configure("Slim.Vertical.TScrollbar", troughcolor=C["bg"], background=C["accent_lt"],
                    bordercolor=C["bg"], lightcolor=C["accent_lt"], darkcolor=C["accent_lt"],
                    gripcount=0, relief="flat", width=8)
        s.map("Slim.Vertical.TScrollbar",
              background=[("pressed", C["accent_dk"]), ("active", C["accent"])])

        # カスタムタブバー
        tab_bar = tk.Frame(self, bg=C["bg"])
        tab_bar.pack(fill="x", padx=4, pady=(4, 0))
        self._tab_btns = []
        for i, label in enumerate(["Subnet Info", "Network Book"]):
            btn = tk.Button(tab_bar, text=label, font=FONT_SMALL, relief="flat", bd=0,
                            cursor="hand2", padx=6, pady=2,
                            command=lambda idx=i: self._show_tab(idx))
            btn.pack(side="left", padx=(0, 2))
            self._tab_btns.append(btn)

        # コンテンツエリア（枠なし）
        content = tk.Frame(self, bg=C["bg"])
        content.pack(fill="both", expand=True, padx=4, pady=(4, 4))

        self.tab1 = tk.Frame(content, bg=C["bg"])
        self.tab3 = tk.Frame(content, bg=C["bg"])

        self._tabs = [self.tab1, self.tab3]
        self._active_tab = -1

        self._build_tab1()
        self._build_tab3()

        self._show_tab(0)

        # コンテンツに合わせてウィンドウサイズを自動決定
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry(f"{w}x{h}")
        self.minsize(w, h)

    def _show_tab(self, idx):
        for i, (tab, btn) in enumerate(zip(self._tabs, self._tab_btns)):
            if i == idx:
                tab.pack(fill="both", expand=True)
                btn.config(bg=C["accent"], fg="#FFFFFF",
                           activebackground=C["accent_dk"], activeforeground="#FFFFFF")
            else:
                tab.pack_forget()
                btn.config(bg=C["tab_inact"], fg=C["text_sub"],
                           activebackground=C["card_h"], activeforeground=C["text"])
        self._active_tab = idx

    def _switch_view(self, hide, show):
        hide.pack_forget()
        show.pack(fill="both", expand=True)
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    # ------------------------------------------------------------------
    # Tab1: 複数ネットワーク一括検索
    # ------------------------------------------------------------------
    def _build_tab1(self):
        iv = tk.Frame(self.tab1, bg=C["bg"])
        iv.pack(fill="both", expand=True)
        self._tab1_iv = iv

        card = RoundedCard(iv)
        card.pack(fill="x", pady=(2, 3), padx=2)
        body = card.inner
        body.columnconfigure(0, weight=1)
        _card_title(body, 0, "Input", columnspan=1)

        self.tab1_input = tk.Text(body, font=FONT, bg=C["entry_bg"], fg=C["text"],
                                  insertbackground=C["accent"], relief="flat",
                                  highlightthickness=0, bd=0, height=4, wrap="none")
        self.tab1_input.insert("1.0", "192.168.1.0/24\n10.0.0.0/8")
        self.tab1_input.grid(row=1, column=0, sticky="ew", pady=1)

        tk.Label(body, text="One network per line  (e.g. 192.168.1.0/24  or  192.168.1.0 255.255.255.0)",
                 bg=C["card"], fg=C["text_sub"], font=FONT_SMALL).grid(
                 row=2, column=0, sticky="w", pady=(2, 0))
        _make_button(body, "Calculate", self._calc_tab1).grid(
            row=3, column=0, sticky="ew", pady=(4, 0))

        rv = tk.Frame(self.tab1, bg=C["bg"])
        self._tab1_rv = rv
        nav = tk.Frame(rv, bg=C["bg"])
        nav.pack(fill="x", padx=2, pady=(2, 1))
        _make_back_button(nav, lambda: self._switch_view(rv, iv)).pack(side="left")
        _make_button(nav, "Export CSV", self._export_tab1_csv).pack(side="right")

        rcard = RoundedCard(rv, autosize=False)
        rcard.pack(fill="both", expand=True, padx=2)
        rbody = rcard.inner
        rbody.columnconfigure(0, weight=1)
        rbody.rowconfigure(1, weight=1)
        _card_title(rbody, 0, "Results", columnspan=1)

        rc_frame = tk.Frame(rbody, bg=C["card"])
        rc_frame.grid(row=1, column=0, sticky="nsew")
        rc_frame.columnconfigure(0, weight=1)
        rc_frame.rowconfigure(0, weight=1)

        self._results_canvas = tk.Canvas(rc_frame, bg=C["card"],
                                          highlightthickness=0, bd=0, height=120)
        self._results_canvas.grid(row=0, column=0, sticky="nsew")

        ysb = ttk.Scrollbar(rc_frame, orient="vertical",
                             style="Slim.Vertical.TScrollbar",
                             command=self._results_canvas.yview)
        ysb.grid(row=0, column=1, sticky="ns")
        self._results_canvas.configure(yscrollcommand=ysb.set)

        self._results_inner = tk.Frame(self._results_canvas, bg=C["card"])
        self._results_win = self._results_canvas.create_window(
            (0, 0), window=self._results_inner, anchor="nw")

        def _sync(e=None):
            self._results_canvas.configure(
                scrollregion=self._results_canvas.bbox("all"))
            self._results_canvas.itemconfig(
                self._results_win, width=self._results_canvas.winfo_width())

        self._results_inner.bind("<Configure>", _sync)
        self._results_canvas.bind("<Configure>", _sync)
        self._results_canvas.bind("<MouseWheel>",
            lambda e: self._results_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def _export_tab1_csv(self):
        results = getattr(self, "_tab1_results", [])
        if not results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export results")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["CIDR", "Network", "Usable Range", "Hosts"])
            for info in results:
                w.writerow([info["cidr"], info["network"], info["range"], info["usable"]])
        messagebox.showinfo("Export", f"Saved {len(results)} row(s) to:\n{path}")

    def _calc_tab1(self):
        lines = self.tab1_input.get("1.0", tk.END).splitlines()
        for w in self._results_inner.winfo_children():
            w.destroy()

        self._tab1_results = []
        errors = []

        for lineno, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            try:
                if '/' in line:
                    parts = line.split('/', 1)
                    net = ipaddress.ip_network(
                        f"{parts[0].strip()}/{parse_prefix('/' + parts[1].strip())}", strict=False)
                else:
                    parts = line.split(None, 1)
                    if len(parts) < 2:
                        raise ValueError("マスクを指定してください")
                    net = ipaddress.ip_network(
                        f"{parts[0]}/{parse_prefix(parts[1])}", strict=False)
                info = network_info(net)
                self._tab1_results.append(info)

                # Result card
                card_f = tk.Frame(self._results_inner, bg=C["card"])
                card_f.pack(fill="x", pady=(0, 3))
                tk.Frame(card_f, bg=C["accent"], width=3).pack(side="left", fill="y")
                body = tk.Frame(card_f, bg=C["card_h"])
                body.pack(side="left", fill="x", expand=True)
                body.columnconfigure(1, weight=1)
                tk.Label(body, text=f"{info['network']}{info['cidr']}",
                         font=FONT_BOLD, bg=C["card_h"], fg=C["accent_dk"],
                         padx=6, pady=2).grid(row=0, column=0, columnspan=2, sticky="w")
                net_key = f"{info['network']}{info['cidr']}"
                book_name = next(
                    (e["name"] for e in self._registry if e["network"] == net_key), None)
                rows = []
                if book_name:
                    rows.append(("Name", book_name, FONT_SMALL_BOLD, C["accent_dk"]))
                rows += [
                    ("Netmask",   info["netmask"],   FONT_SMALL, C["text"]),
                    ("Broadcast", info["broadcast"], FONT_SMALL, C["text"]),
                    ("Range",     info["range"],     FONT_SMALL, C["text"]),
                    ("Hosts",     f"{info['usable']}  (Total {info['total']})", FONT_SMALL, C["text"]),
                    ("Wildcard",  info["wildcard"],  FONT_SMALL, C["text"]),
                ]
                for r, (lbl, val, font, fg) in enumerate(rows, 1):
                    tk.Label(body, text=lbl, font=FONT_SMALL, bg=C["card_h"],
                             fg=C["text_sub"], padx=6).grid(row=r, column=0, sticky="w")
                    tk.Label(body, text=val, font=font, bg=C["card_h"],
                             fg=fg, pady=1).grid(row=r, column=1, sticky="w")

            except ValueError as e:
                errors.append(f"Line {lineno}: {e}")

        if errors:
            messagebox.showwarning("Parse errors", "\n".join(errors))
        if self._tab1_results:
            card_h = sum(
                118 if f"{r['network']}{r['cidr']}" in {e["network"] for e in self._registry}
                else 102
                for r in self._tab1_results)
            self._results_canvas.configure(height=min(card_h, 340))
            self._switch_view(self._tab1_iv, self._tab1_rv)

    # ------------------------------------------------------------------
    # Tab3: Network Book
    # ------------------------------------------------------------------
    def _build_tab3(self):
        self._registry = _load_registry()
        self._filtered = []

        # 登録フォーム
        form_card = RoundedCard(self.tab3)
        form_card.pack(fill="x", pady=(2, 3), padx=2)
        body = form_card.inner
        body.columnconfigure(1, weight=1)
        _card_title(body, 0, "Register")
        self.tab3_net  = _field_row(body, 1, "Network Address", "10.0.0.16/28")
        self.tab3_name = _field_row(body, 2, "LAN Name", "")
        btn_row = tk.Frame(body, bg=C["card"])
        btn_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        _make_button(btn_row, "Register", self._register_network).grid(
            row=0, column=0, sticky="ew", padx=(0, 2))
        _make_button(btn_row, "Import CSV", self._import_csv).grid(
            row=0, column=1, sticky="ew")

        # 検索カード
        search_card = RoundedCard(self.tab3)
        search_card.pack(fill="x", padx=2)
        sbody = search_card.inner
        sbody.columnconfigure(0, weight=1)
        _card_title(sbody, 0, "Search", columnspan=1)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_registry())
        self._search_var_entry = tk.Entry(
            sbody, textvariable=self._search_var, font=FONT,
            bg=C["entry_bg"], fg=C["text"], insertbackground=C["accent"],
            relief="flat", highlightthickness=0, bd=0)
        self._search_var_entry.grid(row=1, column=0, sticky="ew", pady=(0, 2))

        # 結果リスト（Listbox）
        self._listbox = tk.Listbox(sbody, font=FONT_SMALL, height=0,
                                   bg=C["card"], fg=C["text"],
                                   selectbackground=C["accent_lt"],
                                   selectforeground=C["text"],
                                   relief="flat", bd=0, highlightthickness=0,
                                   activestyle="none", exportselection=False,
                                   selectmode=tk.EXTENDED)
        self._listbox.grid(row=2, column=0, sticky="ew")
        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self._listbox.bind("<Double-Button-1>", lambda e: self._edit_selected())

        # 選択時アクションボタン（初期非表示）
        self._action_frame = tk.Frame(sbody, bg=C["card"])
        self._action_frame.columnconfigure(0, weight=1)
        self._action_frame.columnconfigure(1, weight=1)
        self._action_frame.columnconfigure(2, weight=1)
        _make_button(self._action_frame, "→ Tab 1", self._load_selected).grid(
            row=0, column=0, sticky="ew", padx=(0, 2), pady=(2, 0))
        _make_button(self._action_frame, "Edit", self._edit_selected).grid(
            row=0, column=1, sticky="ew", padx=(0, 2), pady=(2, 0))
        _make_button(self._action_frame, "Delete", self._delete_selected).grid(
            row=0, column=2, sticky="ew", pady=(2, 0))

        # IP逆引きカード
        lcard = RoundedCard(self.tab3)
        lcard.pack(fill="x", pady=(3, 2), padx=2)
        lbody = lcard.inner
        lbody.columnconfigure(0, weight=1)
        _card_title(lbody, 0, "IP Lookup", columnspan=2)
        lrow = tk.Frame(lbody, bg=C["card"])
        lrow.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        lrow.columnconfigure(0, weight=1)
        self._lookup_ip_var = tk.StringVar()
        lip_entry = tk.Entry(lrow, textvariable=self._lookup_ip_var, font=FONT,
                             bg=C["entry_bg"], fg=C["text"], insertbackground=C["accent"],
                             relief="flat", highlightthickness=0, bd=0)
        lip_entry.grid(row=0, column=0, sticky="ew")
        lip_entry.bind("<Return>", lambda e: self._do_ip_lookup())
        _make_button(lrow, "Lookup", self._do_ip_lookup).grid(row=0, column=1, padx=(4, 0))
        self._lookup_result_lbl = tk.Label(lbody, text="", bg=C["card"], fg=C["text"],
                                           font=FONT_SMALL, justify="left", anchor="w")
        self._lookup_result_lbl.grid(row=2, column=0, columnspan=2, sticky="ew")

    def _filter_registry(self):
        query = self._search_var.get().strip()
        self._listbox.delete(0, tk.END)
        self._action_frame.grid_forget()
        self._filtered = []

        if query:
            try:
                pat = re.compile(query, re.IGNORECASE)
                self._search_var_entry.config(fg=C["text"])
            except re.error:
                self._search_var_entry.config(fg="#E05555")
                self._listbox.configure(height=0)
                self.update_idletasks()
                self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")
                return

            self._filtered = [e for e in self._registry
                              if pat.search(e["name"]) or pat.search(e["network"])]
            for e in self._filtered:
                self._listbox.insert(tk.END, f"  {e['name']}  —  {e['network']}")

        self._listbox.configure(height=min(len(self._filtered), 6))
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    def _on_list_select(self, _event):
        if self._listbox.curselection():
            self._action_frame.grid(row=3, column=0, sticky="ew")
            self.update_idletasks()
            self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    def _refresh_registry_list(self):
        self._filter_registry()

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title="CSVファイルを選択",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return

        added, skipped = 0, []
        with open(path, encoding="utf-8-sig", newline="") as f:
            for lineno, row in enumerate(csv.reader(f), 1):
                if len(row) < 2:
                    continue
                net_str, name = row[0].strip(), row[1].strip()
                if not net_str or not name:
                    continue
                try:
                    network = str(ipaddress.ip_network(net_str, strict=False))
                except ValueError:
                    skipped.append(f"行{lineno}: {net_str}")
                    continue
                if any(e["network"] == network for e in self._registry):
                    skipped.append(f"行{lineno}: {net_str} (重複)")
                    continue
                self._registry.append({"name": name, "network": network})
                added += 1

        if added:
            _save_registry(self._registry)
            self._refresh_registry_list()
            self.update_idletasks()
            self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

        msg = f"{added}件を登録しました。"
        if skipped:
            msg += f"\nスキップ({len(skipped)}件):\n" + "\n".join(skipped)
        messagebox.showinfo("インポート完了", msg)

    def _register_network(self):
        net_str = self.tab3_net.get().strip()
        name    = self.tab3_name.get().strip()
        if not net_str or not name:
            messagebox.showerror("入力エラー", "ネットワークと名前を入力してください")
            return
        try:
            network = str(ipaddress.ip_network(net_str, strict=False))
        except ValueError as e:
            messagebox.showerror("入力エラー", str(e))
            return
        if any(e["network"] == network for e in self._registry):
            messagebox.showerror("重複エラー", f"{network} はすでに登録されています")
            return
        self._registry.append({"name": name, "network": network})
        _save_registry(self._registry)
        self.tab3_name.delete(0, tk.END)
        self._refresh_registry_list()
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    def _selected_entry(self):
        sel = self._listbox.curselection()
        if not sel:
            return None
        return self._filtered[sel[0]]

    def _delete_selected(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        to_del = {self._filtered[i]["network"] for i in sel}
        self._registry = [e for e in self._registry if e["network"] not in to_del]
        _save_registry(self._registry)
        self._filter_registry()

    def _load_selected(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        entries = [self._filtered[i] for i in sel]
        current = self.tab1_input.get("1.0", tk.END).strip()
        new_nets = "\n".join(e["network"] for e in entries)
        self.tab1_input.delete("1.0", tk.END)
        self.tab1_input.insert("1.0", (current + "\n" + new_nets).strip())
        self._show_tab(0)
        self._tab1_rv.pack_forget()
        self._tab1_iv.pack(fill="both", expand=True)
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    def _do_ip_lookup(self):
        ip_str = self._lookup_ip_var.get().strip()
        if not ip_str:
            return
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            self._lookup_result_lbl.config(text="Invalid IP address", fg="#E05555")
            self.update_idletasks()
            self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")
            return
        matches = []
        for e in self._registry:
            try:
                if ip in ipaddress.ip_network(e["network"]):
                    matches.append(f"{e['name']}  —  {e['network']}")
            except ValueError:
                pass
        if matches:
            self._lookup_result_lbl.config(text="\n".join(matches), fg=C["text"])
        else:
            self._lookup_result_lbl.config(text="No matching network", fg=C["text_sub"])
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    def _edit_selected(self):
        sel = self._listbox.curselection()
        if len(sel) != 1:
            return
        entry = self._filtered[sel[0]]

        dlg = tk.Toplevel(self)
        dlg.title("Edit Entry")
        dlg.configure(bg=C["bg"])
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.after(50, lambda: _apply_titlebar_theme(dlg))

        card = RoundedCard(dlg)
        card.pack(fill="both", padx=6, pady=6)
        body = card.inner
        body.columnconfigure(1, weight=1)
        _card_title(body, 0, "Edit Entry")
        net_f  = _field_row(body, 1, "Network Address", entry["network"])
        name_f = _field_row(body, 2, "LAN Name", entry["name"])

        def _save():
            net_str = net_f.get().strip()
            name    = name_f.get().strip()
            if not net_str or not name:
                messagebox.showerror("Error", "Both fields are required", parent=dlg)
                return
            try:
                network = str(ipaddress.ip_network(net_str, strict=False))
            except ValueError as e:
                messagebox.showerror("Error", str(e), parent=dlg)
                return
            if any(e2["network"] == network and e2 is not entry for e2 in self._registry):
                messagebox.showerror("Error", f"{network} already exists", parent=dlg)
                return
            entry["network"] = network
            entry["name"]    = name
            _save_registry(self._registry)
            self._filter_registry()
            dlg.destroy()

        _make_button(body, "Save", _save).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        dlg.update_idletasks()
        dlg.geometry(f"{max(dlg.winfo_reqwidth(), 240)}x{dlg.winfo_reqheight()}")


if __name__ == "__main__":
    app = SubnetCalculatorApp()
    app.mainloop()
