import sys
if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr:
    sys.stderr.reconfigure(encoding="utf-8")

import ctypes
_hw = ctypes.windll.kernel32.GetConsoleWindow()
if _hw:
    ctypes.windll.user32.ShowWindow(_hw, 0)

import os
import re
import json
import io
import time
import math
import threading
import random
from datetime import datetime
import webbrowser
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

import config
import content_generator
import image_generator
import gemini_scraper

C = {
    "bg":       "#F4F6FB",
    "card":     "#FFFFFF",
    "border":   "#D0D7E8",
    "accent":   "#4F6FE8",
    "accent_h": "#3A58D0",
    "accent_bg":"#EBF0FD",
    "text":     "#1A2340",
    "subtext":  "#6B7899",
    "input_bg": "#F8FAFF",
    "ok":       "#2A9D6F",
    "err":      "#D04040",
    "disabled": "#A0AABF",
}

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
ENV_PATH = _BASE_DIR / ".env"
APP_VERSION = "v2.0.19"
APP_TITLE   = f"Bamhobak Blog Bot {APP_VERSION}"

_DEFAULT_GITHUB_TOKEN  = ""
_DEFAULT_GIST_URL      = "https://gist.githubusercontent.com/bamhobak/2550df522ba15e6fbd6ea353144253fe/raw/prompts.json"
_DEFAULT_UPDATE_CHECK_URL = "https://api.github.com/gists/2550df522ba15e6fbd6ea353144253fe"
_DEFAULT_GITHUB_REPO   = "bamhobak/BamhobakBlogBot"
_DEFAULT_CF_ACCOUNT_ID = "cb255eaa4a45f4bf2ec980beb268f769"
_DEFAULT_CF_API_TOKEN  = ""


F     = ("Malgun Gothic", 13)
F_B   = ("Malgun Gothic", 13, "bold")
F_SM  = ("Malgun Gothic", 12)
F_SMB = ("Malgun Gothic", 12, "bold")
F_LG  = ("Malgun Gothic", 18, "bold")


def _inline(text: str) -> str:
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*',     r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*',         r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`',           r'<code>\1</code>', text)
    return text


import tkinter as tk

class RichText(tk.Text):
    """마크다운을 시각적으로 렌더링하는 텍스트 위젯"""

    _FF = "Malgun Gothic"

    def __init__(self, parent, bg="#F8FAFF", fg="#1A2340", **kw):
        super().__init__(
            parent,
            bg=bg, fg=fg,
            relief="flat", bd=0,
            font=(self._FF, 11),
            wrap="word",
            state="normal",
            cursor="xterm",
            selectbackground="#4F6FE8",
            selectforeground="white",
            padx=10, pady=4,
            spacing1=0, spacing3=0,
            **kw,
        )
        self._bg = bg
        self._fg = fg
        self._sep_widgets = []
        self._setup_tags()
        self.bind("<<Paste>>", self._on_paste)

    def _setup_tags(self):
        ff = self._FF
        fg = self._fg
        self.tag_configure("h1",   font=(ff, 18, "bold"), spacing1=3, spacing3=1,  foreground=fg)
        self.tag_configure("h2",   font=(ff, 15, "bold"), spacing1=2, spacing3=1,  foreground=fg)
        self.tag_configure("h3",   font=(ff, 12, "bold"), spacing1=2, spacing3=0,  foreground=fg)
        self.tag_configure("bold", font=(ff, 11, "bold"), foreground=fg)
        self.tag_configure("italic", font=(ff, 11, "italic"), foreground=fg)
        self.tag_configure("normal", font=(ff, 11), foreground=fg)
        self.tag_configure("blockquote",
                           font=(ff, 11), lmargin1=18, lmargin2=18,
                           background="#EBF0FD", foreground="#3A58D0",
                           spacing1=1, spacing3=1)
        self.tag_configure("bullet",
                           font=(ff, 11), lmargin1=18, lmargin2=32,
                           foreground=fg, spacing1=0, spacing3=0)

    @staticmethod
    def _strip_md(line: str) -> str:
        t = line.strip()
        t = re.sub(r'^#+\s*', '', t)
        t = re.sub(r'^>\s*', '', t)
        t = re.sub(r'^[\*\-•]\s*', '', t)
        t = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', t)
        t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)
        t = re.sub(r'\*(.+?)\*', r'\1', t)
        t = re.sub(r'`(.+?)`', r'\1', t)
        return t

    def _insert_copy_btn(self, line: str):
        clean = self._strip_md(line)
        if not clean:
            return
        holder = [None]

        def _on_click():
            try:
                root = self.winfo_toplevel()
                root.clipboard_clear()
                root.clipboard_append(clean)
            except Exception:
                pass
            if holder[0]:
                holder[0].config(fg="#A0AABF")  # 클릭 후 회색 유지

        btn_w = tk.Button(
            self, text="📋", cursor="hand2",
            bg=self._bg, fg="#2A9D6F",
            font=(self._FF, 12),
            bd=0, padx=3, pady=1,
            activebackground=self._bg, activeforeground="#1E7A55",
            relief="flat",
            command=_on_click,
        )
        holder[0] = btn_w
        self.window_create("end", window=btn_w, padx=2)
        self._sep_widgets.append(btn_w)

    def _on_paste(self, event):
        try:
            text = self.winfo_toplevel().clipboard_get()
            if text.strip():
                self.set_markdown(text)
                return "break"
        except Exception:
            pass

    def set_markdown(self, md: str):
        self.delete("1.0", "end")
        for w in self._sep_widgets:
            try: w.destroy()
            except Exception: pass
        self._sep_widgets.clear()

        lines = md.splitlines()
        first = True
        for line in lines:
            if not first:
                self.insert("end", "\n")
            first = False
            stripped = line.strip()
            is_hr = re.match(r'^---+$', stripped) or re.match(r'^===+$', stripped)
            if stripped and not is_hr:
                self._insert_copy_btn(line)
            self._insert_line(line)

    def _insert_line(self, line):
        stripped = line.strip()
        if re.match(r'^---+$', stripped) or re.match(r'^===+$', stripped):
            self._insert_hr()
        elif line.startswith('# ') and not line.startswith('## '):
            self._insert_inline(line[2:].strip(), "h1")
        elif line.startswith('## ') and not line.startswith('### '):
            self._insert_inline(line[3:].strip(), "h2")
        elif line.startswith('### '):
            self._insert_inline(line[4:].strip(), "h3")
        elif line.startswith('> '):
            self.insert("end", line[2:].strip(), "blockquote")
        elif re.match(r'^[\*\-\•] ', line):
            self._insert_inline("• " + line[2:].strip(), "bullet")
        elif re.match(r'^\d+\. ', line):
            m = re.match(r'^(\d+)\. (.*)', line)
            if m:
                self._insert_inline(f"{m.group(1)}. {m.group(2)}", "bullet")
        elif stripped == '':
            pass
        else:
            self._insert_inline(line, "normal")

    def _insert_inline(self, text, base_tag):
        pat = r'(\*\*\*[^*]+?\*\*\*|\*\*[^*]+?\*\*|\*[^*]+?\*|`[^`]+?`)'
        parts = re.split(pat, text)
        for part in parts:
            if part.startswith('***') and part.endswith('***'):
                self.insert("end", part[3:-3], (base_tag, "bold"))
            elif part.startswith('**') and part.endswith('**'):
                self.insert("end", part[2:-2], (base_tag, "bold"))
            elif part.startswith('*') and part.endswith('*') and len(part) > 2:
                self.insert("end", part[1:-1], (base_tag, "italic"))
            elif part.startswith('`') and part.endswith('`'):
                self.insert("end", part[1:-1], base_tag)
            else:
                self.insert("end", part, base_tag)

    def _insert_hr(self):
        sep = tk.Frame(self, height=2, bg="#D0D7E8", bd=0)
        self._sep_widgets.append(sep)
        self.window_create("end", window=sep, stretch=True, padx=4, pady=8)

    def get_plain(self) -> str:
        return self.get("1.0", "end")


def _card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=C["card"],
                        border_color=C["border"], border_width=1,
                        corner_radius=12, **kw)

def _lbl(parent, text, font=None, color=None, **kw):
    return ctk.CTkLabel(parent, text=text,
                        font=font or F, text_color=color or C["text"], **kw)

def _btn(parent, text, cmd, w=None, h=36, small=False, color=None, hover=None, **kw):
    return ctk.CTkButton(
        parent, text=text, command=cmd,
        width=w or (90 if small else 140), height=h,
        font=F_SM if small else F_B,
        fg_color=color or C["accent"],
        hover_color=hover or C["accent_h"],
        text_color="white", corner_radius=8, **kw)

def _link(parent, text, url):
    return ctk.CTkButton(
        parent, text=text,
        fg_color="transparent", hover_color=C["accent_bg"],
        text_color=C["accent"],
        font=("Malgun Gothic", 12, "underline"),
        height=24, corner_radius=6,
        command=lambda: webbrowser.open(url),
        cursor="hand2", anchor="w",
    )


_PREFS_PATH = _BASE_DIR / ".prefs.json"


def _get_mac_address() -> str:
    """인터넷 연결에 실제 사용되는 어댑터의 MAC 주소를 반환합니다."""
    import subprocess, re as _re, socket as _sock
    try:
        # 외부 연결 시 사용되는 로컬 IP 확인 (실제 패킷 전송 없음)
        s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
        finally:
            s.close()
        # ipconfig /all 에서 해당 IP를 가진 어댑터의 MAC 검색
        out = subprocess.check_output(
            ['ipconfig', '/all'],
            encoding='cp949', errors='replace', timeout=8,
            creationflags=0x08000000,
        )
        current_mac = None
        for line in out.splitlines():
            if '물리적 주소' in line or 'Physical Address' in line:
                m = _re.search(r'([0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})', line)
                if m:
                    current_mac = m.group(1).upper().replace('-', ':')
            if local_ip in line and current_mac:
                return current_mac
    except Exception:
        pass
    # fallback: uuid.getnode()
    import uuid
    node = uuid.getnode()
    return ':'.join(f'{(node >> i) & 0xff:02X}' for i in range(40, -8, -8))


def _urlopen_ssl(req, timeout=15):
    """SSL 인증서 오류 발생 시 자동으로 검증 우회하여 재시도."""
    import urllib.request as _ur
    import ssl
    try:
        return _ur.urlopen(req, timeout=timeout)
    except Exception as e:
        if any(k in str(e).upper() for k in ("SSL", "CERT", "CERTIFICATE")):
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode   = ssl.CERT_NONE
            return _ur.urlopen(req, timeout=timeout, context=ctx)
        raise


class LoopyScrollbar(tk.Scrollbar):
    """일반 수평 스크롤바 (기존 enable 인터페이스 호환)"""
    def __init__(self, parent, **kw):
        super().__init__(parent, orient="horizontal", **kw)

    def enable(self, on=True):
        pass  # 표준 스크롤바는 xscrollcommand로 자동 제어됨


class _UndoEntry(ctk.CTkEntry):
    """Ctrl+Z undo를 지원하는 CTkEntry (단어 단위 히스토리)."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._undo_stack: list = []
        self._prev_val: str = ""
        self._after_id = None
        self._entry.bind("<KeyRelease>", self._on_key, add="+")
        self._entry.bind("<Control-z>", self._do_undo, add="+")
        self._entry.bind("<Control-Z>", self._do_undo, add="+")

    def _checkpoint(self):
        val = self.get()
        if val != self._prev_val:
            self._undo_stack.append(self._prev_val)
            if len(self._undo_stack) > 1:
                self._undo_stack.pop(0)
            self._prev_val = val

    def _on_key(self, event):
        if event.state & 0x4:  # Ctrl 조합키 무시
            return
        val = self.get()
        if event.keysym == "space" or abs(len(val) - len(self._prev_val)) >= 5:
            self._checkpoint()
        else:
            if self._after_id:
                self.after_cancel(self._after_id)
            self._after_id = self.after(1200, self._checkpoint)

    def _do_undo(self, event):
        cur = self.get()
        if cur != self._prev_val:
            self._undo_stack.append(cur)
        if self._undo_stack:
            val = self._undo_stack.pop()
            self._prev_val = val
            self.delete(0, "end")
            self.insert(0, val)
        return "break"


class _TopicPicker(ctk.CTkFrame):
    """주제 선택용 3열 팝업 picker (CTkOptionMenu 대체)."""

    def __init__(self, parent, values=None, font=None, fg_color=None,
                 button_color=None, button_hover_color=None, text_color=None,
                 corner_radius=8, **kwargs):
        super().__init__(parent, fg_color=fg_color or C["accent_bg"],
                         corner_radius=corner_radius)
        self._values = list(values or ["(저장된 목록 없음)"])
        self._current = self._values[0] if self._values else ""
        self._font = font or F
        self._btn_color = button_color or C["accent"]
        self._btn_hover = button_hover_color or C["accent_h"]
        self._txt_color = text_color or C["text"]
        self._groups = None  # list[list[str]] – 행별 그룹
        self._popup = None

        self._lbl = ctk.CTkButton(
            self, text=self._current,
            command=self._toggle,
            height=38, font=self._font,
            fg_color=fg_color or C["accent_bg"],
            hover_color=C["accent_bg"],
            text_color=self._txt_color,
            corner_radius=corner_radius, anchor="w",
        )
        self._lbl.pack(side="left", fill="x", expand=True)

        self._arrow = ctk.CTkButton(
            self, text="▼",
            command=self._toggle,
            width=34, height=38, font=("Malgun Gothic", 9),
            fg_color=self._btn_color,
            hover_color=self._btn_hover,
            text_color="white", corner_radius=corner_radius,
        )
        self._arrow.pack(side="right")

    def configure(self, **kwargs):
        if "values" in kwargs:
            self._values = list(kwargs.pop("values"))
        if "groups" in kwargs:
            self._groups = kwargs.pop("groups")
            if self._groups:
                self._values = [k for g in self._groups for k in g]
        if kwargs:
            try:
                super().configure(**kwargs)
            except Exception:
                pass

    def get(self):
        return self._current

    def set(self, value):
        self._current = value
        self._lbl.configure(text=value)

    def _toggle(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        self._show_popup()

    def _show_popup(self):
        popup = ctk.CTkToplevel()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=C["border"])

        inner = ctk.CTkScrollableFrame(popup, fg_color=C["card"], corner_radius=8,
                                        scrollbar_button_color=C["border"])
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        if self._groups and any(self._groups):
            # 열별 그룹 배치: 1열=행1, 2열=행2, 3열=행3
            COLS = len(self._groups)
            for col, group in enumerate(self._groups):
                for row, v in enumerate(group):
                    is_sel = (v == self._current)
                    btn = ctk.CTkButton(
                        inner, text=v,
                        command=lambda val=v: self._select(val, popup),
                        height=30, font=F_SM,
                        fg_color=C["accent"] if is_sel else "transparent",
                        hover_color=C["accent_bg"],
                        text_color="white" if is_sel else C["text"],
                        corner_radius=5, anchor="w",
                    )
                    btn.grid(row=row, column=col, padx=2, pady=1, sticky="ew")
            for c in range(COLS):
                inner.grid_columnconfigure(c, weight=1)
            n_rows = max((len(g) for g in self._groups), default=1)
        else:
            COLS = 3
            for i, v in enumerate(self._values):
                r, c = divmod(i, COLS)
                is_sel = (v == self._current)
                btn = ctk.CTkButton(
                    inner, text=v,
                    command=lambda val=v: self._select(val, popup),
                    height=30, font=F_SM,
                    fg_color=C["accent"] if is_sel else "transparent",
                    hover_color=C["accent_bg"],
                    text_color="white" if is_sel else C["text"],
                    corner_radius=5, anchor="w",
                )
                btn.grid(row=r, column=c, padx=2, pady=1, sticky="ew")
            for c in range(COLS):
                inner.grid_columnconfigure(c, weight=1)
            n_rows = math.ceil(max(len(self._values), 1) / COLS)

        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        screen_h = self.winfo_screenheight()
        max_h = max(120, screen_h - y - 24)
        popup_h = min(n_rows * 36 + 16, max_h)
        popup_w = max(self.winfo_width(), 500)
        popup.geometry(f"{popup_w}x{popup_h}+{x}+{y}")
        self._popup = popup

        _cid = [None]
        def _outside(e):
            try:
                if not popup.winfo_exists():
                    return
                px, py = popup.winfo_rootx(), popup.winfo_rooty()
                pw, ph = popup.winfo_width(), popup.winfo_height()
                if not (px <= e.x_root <= px + pw and py <= e.y_root <= py + ph):
                    popup.destroy()
                    self._popup = None
                    self.winfo_toplevel().unbind("<Button-1>", _cid[0])
            except Exception:
                pass
        _cid[0] = self.winfo_toplevel().bind("<Button-1>", _outside, add="+")

    def _select(self, value, popup):
        self.set(value)
        try:
            if popup.winfo_exists():
                popup.destroy()
        except Exception:
            pass
        self._popup = None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.configure(fg_color=C["bg"])
        self.title(APP_TITLE)
        self.minsize(940, 700)
        self._img_refs   = []
        self._img_pil    = []
        self._last_body  = ""
        self._stop_event = threading.Event()
        self._prompts    = [""] * 15
        self._prompts2   = [""] * 15
        self._kw2_enabled = [False] * 15
        self._option_enabled = [True] * 15
        self._topic_enabled = [False] * 15
        self._collect_enabled = [False] * 15
        self._collect_count    = 5
        self._collect_skip     = 0
        self._collect_chunk    = "0"
        self._collect_maxchars = 0
        self._collect_header   = "[인기글 참조]"
        self._collect_delimiters = ""
        self._collect_ending     = ""
        self._collect_bottom     = ""
        self.kw2_var = tk.BooleanVar(value=False)
        self._topic_lists = {}
        self._topic_rows: list = []
        self._prompt_names = [f"옵션 {i+1}" for i in range(15)]
        self._selected_prompt_idx = 0
        self._kw_per_option: list = [""] * 15
        self._kw2_per_option: list = [""] * 15
        self._collect_kw_per_option: list = [""] * 15
        self._remote_url = _DEFAULT_GIST_URL
        self._local_img_folder = ""
        self._variation_output_dir = ""
        self._last_out_dir: Path | None = None
        self._img_source = "AI"
        self._img_count_by_source: dict = {"AI": "3", "픽숨": "3", "플리커": "3"}
        self._img_source_per_option: list = ["AI"] * 15
        self._mac_entries = []
        self._is_guest = False
        self._guest_prompt_enabled = [False] * 15
        self._max_width = 0
        self._var_settings = {
            "crop_pct_min":        0.5,  "crop_pct_max":        3.5,
            "brightness_pct_min": -6.0,  "brightness_pct_max":  6.0,
            "contrast_pct_min":   -6.0,  "contrast_pct_max":    6.0,
            "color_pct_min":      -6.0,  "color_pct_max":       6.0,
            "rotation_deg_min":    0.2,  "rotation_deg_max":    1.5,
            "noise_min":           1.0,  "noise_max":           4.0,
            "hue_shift_min":      -8.0,  "hue_shift_max":       8.0,
            "sharpness_min":     -25.0,  "sharpness_max":      40.0,
            "temperature_min":    -6.0,  "temperature_max":     6.0,
            "gamma_min":          -6.0,  "gamma_max":           6.0,
            "aspect_ratio_min":   -5.0,  "aspect_ratio_max":    5.0,
            "jpeg_quality_min":    1.0,  "jpeg_quality_max":   15.0,
            "translate_min":       1.0,  "translate_max":       7.0,
            "rgb_offset_min":     -6.0,  "rgb_offset_max":      6.0,
            "watermark_min":       0.1,  "watermark_max":       1.5,
            "hflip_prob":          0.0,
        }
        self._var_settings_picsum = {
            "crop_pct_min":        0.5,  "crop_pct_max":        3.5,
            "brightness_pct_min": -6.0,  "brightness_pct_max":  6.0,
            "contrast_pct_min":   -6.0,  "contrast_pct_max":    6.0,
            "color_pct_min":      -6.0,  "color_pct_max":       6.0,
            "rotation_deg_min":    0.2,  "rotation_deg_max":    1.5,
            "noise_min":           1.0,  "noise_max":           4.0,
            "hue_shift_min":      -8.0,  "hue_shift_max":       8.0,
            "sharpness_min":     -25.0,  "sharpness_max":      40.0,
            "temperature_min":    -6.0,  "temperature_max":     6.0,
            "gamma_min":          -6.0,  "gamma_max":           6.0,
            "aspect_ratio_min":   -5.0,  "aspect_ratio_max":    5.0,
            "jpeg_quality_min":    1.0,  "jpeg_quality_max":   15.0,
            "translate_min":       1.0,  "translate_max":       7.0,
            "rgb_offset_min":     -6.0,  "rgb_offset_max":      6.0,
            "watermark_min":       0.1,  "watermark_max":       1.5,
            "hflip_prob":          0.0,
        }
        self._picsum_width  = 900
        self._picsum_height = 700
        self._var_settings_flickr = {
            "crop_pct_min":        0.5,  "crop_pct_max":        3.5,
            "brightness_pct_min": -6.0,  "brightness_pct_max":  6.0,
            "contrast_pct_min":   -6.0,  "contrast_pct_max":    6.0,
            "color_pct_min":      -6.0,  "color_pct_max":       6.0,
            "rotation_deg_min":    0.2,  "rotation_deg_max":    1.5,
            "noise_min":           1.0,  "noise_max":           4.0,
            "hue_shift_min":      -8.0,  "hue_shift_max":       8.0,
            "sharpness_min":     -25.0,  "sharpness_max":      40.0,
            "temperature_min":    -6.0,  "temperature_max":     6.0,
            "gamma_min":          -6.0,  "gamma_max":           6.0,
            "aspect_ratio_min":   -5.0,  "aspect_ratio_max":    5.0,
            "jpeg_quality_min":    1.0,  "jpeg_quality_max":   15.0,
            "translate_min":       1.0,  "translate_max":       7.0,
            "rgb_offset_min":     -6.0,  "rgb_offset_max":      6.0,
            "watermark_min":       0.1,  "watermark_max":       1.5,
            "hflip_prob":          0.0,
        }
        self._flickr_width   = 1000
        self._flickr_height  = 1000
        self._flickr_keyword = ""
        self._prefs      = self._load_prefs()
        self._build_ui()
        self._apply_prefs()
        self._fetch_mac_from_gist()   # MAC 체크 전에 Gist 최신 목록 수신
        if not self._check_mac_allowed():
            return
        if self._is_guest:
            self._apply_guest_mode()
        threading.Thread(target=self._auto_start_browser, daemon=True).start()
        threading.Thread(target=self._auto_warmup_hf, daemon=True).start()
        threading.Thread(target=self._chrome_launch_watcher, daemon=True).start()
        threading.Thread(target=self._sync_remote_prompts, daemon=True).start()
        threading.Thread(target=self._check_for_update, daemon=True).start()
        self.after(2000, self._check_update_log)
        self.update_idletasks()
        w, h = 1080, 840
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}")
        self.lift(); self.focus_force()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_icon()

    def _set_icon(self):
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            s = 64
            img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)

            # 파란 배경 (둥근 사각형)
            d.rounded_rectangle([0, 0, s-1, s-1], radius=14, fill=(58, 88, 208))
            d.rounded_rectangle([2, 2, s-3, s-3], radius=12, fill=(79, 111, 232))

            # 흰색 'B' 텍스트
            try:
                font = ImageFont.truetype("arialbd.ttf", 46)
            except Exception:
                try:
                    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 46)
                except Exception:
                    font = ImageFont.load_default()
            bbox = d.textbbox((0, 0), "B", font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (s - tw) // 2 - bbox[0]
            ty = (s - th) // 2 - bbox[1] - 2
            d.text((tx, ty), "B", font=font, fill=(255, 255, 255))

            photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, photo)
            self._icon_photo = photo
        except Exception:
            pass

    def _load_prefs(self) -> dict:
        try:
            return json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_prefs(self):
        _idx = self._selected_prompt_idx
        _kw_now = (self.keyword_textbox.get("1.0","end").strip() if self._is_secret_mode() else self.keyword_entry.get().strip())
        _kw2_now = (self.kw2_entry._entry.get() if hasattr(self.kw2_entry, '_entry') else self.kw2_entry.get()).strip()
        _collect_kw_now = self.collect_kw_entry.get().strip()
        self._kw_per_option[_idx] = _kw_now
        self._kw2_per_option[_idx] = _kw2_now
        self._collect_kw_per_option[_idx] = _collect_kw_now
        self._img_count_by_source[self._img_source] = self.img_count_entry.get().strip() or "3"
        self._img_source_per_option[_idx] = self._img_source
        prefs = {
            "keyword":              _kw_now,
            "keyword2":             _kw2_now,
            "img_count":            self.img_count_entry.get().strip(),
            "prompts":              self._prompts,
            "prompts2":             self._prompts2,
            "kw2_enabled":          self._kw2_enabled,
            "option_enabled":       self._option_enabled,
            "topic_enabled":        self._topic_enabled,
            "collect_enabled":      self._collect_enabled,
            "collect_count":        self._collect_count,
            "collect_skip":         self._collect_skip,
            "collect_chunk":        self._collect_chunk,
            "collect_maxchars":     self._collect_maxchars,
            "collect_header":       self._collect_header,
            "collect_delimiters":   self._collect_delimiters,
            "collect_ending":       self._collect_ending,
            "collect_bottom":       self._collect_bottom,
            "topic_lists":          self._topic_lists,
            "topic_rows":           self._topic_rows,
            "prompt_names":         self._prompt_names,
            "selected_prompt_idx":  self._selected_prompt_idx,
            "remote_url":           self._remote_url,
            "local_img_folder":     self._local_img_folder,
            "variation_output_dir": self._variation_output_dir,
            "var_settings":         {k: v for k, v in self._var_settings.items()},
            "var_settings_picsum":  {k: v for k, v in self._var_settings_picsum.items()},
            "var_settings_flickr":  {k: v for k, v in self._var_settings_flickr.items()},
            "max_width":            self._max_width,
            "picsum_width":         self._picsum_width,
            "picsum_height":        self._picsum_height,
            "flickr_width":         self._flickr_width,
            "flickr_height":        self._flickr_height,
            "flickr_keyword":       self._flickr_keyword,
            "mac_entries":          self._mac_entries,
            "guest_prompt_enabled": self._guest_prompt_enabled,
            "kw_per_option":        self._kw_per_option,
            "kw2_per_option":       self._kw2_per_option,
            "collect_kw_per_option": self._collect_kw_per_option,
            "img_count_by_source":  self._img_count_by_source,
            "img_source_per_option":self._img_source_per_option,
        }
        try:
            _PREFS_PATH.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _apply_prefs(self):
        if kp := self._prefs.get("kw_per_option"):
            if isinstance(kp, list):
                self._kw_per_option = [str(v) for v in kp]
        if kp2 := self._prefs.get("kw2_per_option"):
            if isinstance(kp2, list):
                self._kw2_per_option = [str(v) for v in kp2]
        if ckp := self._prefs.get("collect_kw_per_option"):
            if isinstance(ckp, list):
                self._collect_kw_per_option = [str(v) for v in ckp]
        # selected_prompt_idx를 먼저 복원해야 img_source/keyword 등이 올바른 옵션에서 읽힘
        try:
            _n = max(1, len(self._kw_per_option))
            self._selected_prompt_idx = max(0, min(_n - 1, int(self._prefs.get("selected_prompt_idx", 0))))
        except Exception:
            pass
        _idx = self._selected_prompt_idx
        kw = self._kw_per_option[_idx] or self._prefs.get("keyword", "")
        if kw:
            self.keyword_entry.delete(0, "end")
            self.keyword_entry.insert(0, kw)
        kw2 = self._kw2_per_option[_idx] or self._prefs.get("keyword2", "")
        if kw2:
            self.kw2_entry.configure(state="normal")
            self.kw2_entry.delete(0, "end")
            self.kw2_entry.insert(0, kw2)
        collect_kw = self._collect_kw_per_option[_idx] if _idx < len(self._collect_kw_per_option) else ""
        if collect_kw:
            self.collect_kw_entry.delete(0, "end")
            self.collect_kw_entry.insert(0, collect_kw)
        if isp := self._prefs.get("img_source_per_option"):
            if isinstance(isp, list):
                _src_normalize = {"PICSUM": "픽숨", "FLICKR": "플리커"}
                self._img_source_per_option = [_src_normalize.get(str(v), str(v)) for v in isp]
        if ibs := self._prefs.get("img_count_by_source"):
            if isinstance(ibs, dict):
                _src_compat = {"PICSUM": "픽숨", "FLICKR": "플리커"}
                for k in ("AI", "픽숨", "플리커"):
                    old_k = {v: kk for kk, v in _src_compat.items()}.get(k, k)
                    val = ibs.get(k) or ibs.get(old_k)
                    if val:
                        self._img_count_by_source[k] = str(val)
        # 구버전 fallback: 단일 img_count → 모든 소스
        if not self._prefs.get("img_count_by_source"):
            if cnt := self._prefs.get("img_count"):
                for k in ("AI", "픽숨", "플리커"):
                    self._img_count_by_source[k] = cnt
        self._img_source = self._img_source_per_option[_idx]
        self.img_src_menu.set(self._img_source)
        _cnt_val = self._img_count_by_source.get(self._img_source, "3")
        self.img_count_entry.delete(0, "end")
        self.img_count_entry.insert(0, _cnt_val)
        if saved_prompts := self._prefs.get("prompts"):
            if isinstance(saved_prompts, list) and saved_prompts:
                self._prompts = [str(p) if p else "" for p in saved_prompts]
        elif cp := self._prefs.get("custom_prompt"):
            self._prompts[0] = cp
        if saved_p2 := self._prefs.get("prompts2"):
            if isinstance(saved_p2, list):
                self._prompts2 = [str(p) if p else "" for p in saved_p2]
        if saved_kw2 := self._prefs.get("kw2_enabled"):
            if isinstance(saved_kw2, list):
                self._kw2_enabled = [bool(v) for v in saved_kw2]
        if saved_oe := self._prefs.get("option_enabled"):
            if isinstance(saved_oe, list):
                self._option_enabled = [bool(v) for v in saved_oe]
        if saved_te := self._prefs.get("topic_enabled"):
            if isinstance(saved_te, list):
                self._topic_enabled = [bool(v) for v in saved_te]
        if saved_ce := self._prefs.get("collect_enabled"):
            if isinstance(saved_ce, list):
                self._collect_enabled = [bool(v) for v in saved_ce]
        if saved_gpe := self._prefs.get("guest_prompt_enabled"):
            if isinstance(saved_gpe, list):
                self._guest_prompt_enabled = [bool(v) for v in saved_gpe]
        if cc := self._prefs.get("collect_count"):
            try: self._collect_count = int(cc)
            except Exception: pass
        if cs := self._prefs.get("collect_skip"):
            try: self._collect_skip = int(cs)
            except Exception: pass
        if ck := self._prefs.get("collect_chunk"):
            self._collect_chunk = str(ck)
        if cm := self._prefs.get("collect_maxchars"):
            try: self._collect_maxchars = int(cm)
            except Exception: pass
        if ch := self._prefs.get("collect_header"):
            self._collect_header = str(ch)
        if cd := self._prefs.get("collect_delimiters"):
            self._collect_delimiters = str(cd)
        if ce := self._prefs.get("collect_ending"):
            self._collect_ending = str(ce)
        if cb := self._prefs.get("collect_bottom"):
            self._collect_bottom = str(cb)
        if tl := self._prefs.get("topic_lists"):
            if isinstance(tl, dict):
                for k, v in tl.items():
                    if isinstance(v, list):
                        self._topic_lists[str(k)] = [str(t) for t in v if t]
        if tr := self._prefs.get("topic_rows"):
            if isinstance(tr, list):
                self._topic_rows = [
                    [str(k) for k in row if k]
                    for row in tr if isinstance(row, list)
                ]
        if saved_names := self._prefs.get("prompt_names"):
            if isinstance(saved_names, list):
                self._prompt_names = [str(n) if n else f"옵션 {i+1}" for i, n in enumerate(saved_names)]
        idx = self._prefs.get("selected_prompt_idx", 0)
        self._selected_prompt_idx = max(0, min(max(0, len(self._prompts)-1), int(idx)))
        if folder := self._prefs.get("local_img_folder"):
            self._local_img_folder = folder
        if outdir := self._prefs.get("variation_output_dir"):
            self._variation_output_dir = outdir
            try:
                self.var_out_lbl.configure(text=outdir, text_color=C["ok"])
            except Exception:
                pass
        if vs := self._prefs.get("var_settings"):
            if isinstance(vs, dict):
                for k in self._var_settings:
                    if k in vs:
                        self._var_settings[k] = float(vs[k])
                # 구버전 단일값 → 신버전 min/max 마이그레이션
                _old_map = {
                    "crop_pct": "crop_pct", "brightness_pct": "brightness_pct",
                    "contrast_pct": "contrast_pct", "color_pct": "color_pct",
                    "rotation_deg": "rotation_deg", "noise": "noise",
                }
                for old_k, base in _old_map.items():
                    if old_k in vs and f"{base}_max" not in vs:
                        self._var_settings[f"{base}_max"] = float(vs[old_k])
        if url := self._prefs.get("remote_url"):
            # 저장된 URL에서 커밋 해시 자동 제거
            self._remote_url = re.sub(r'/raw/[0-9a-f]{40}/', '/raw/', url)
        if mw := self._prefs.get("max_width"):
            try:
                self._max_width = int(mw)
            except Exception:
                pass
        if vsp := self._prefs.get("var_settings_picsum"):
            if isinstance(vsp, dict):
                for k in self._var_settings_picsum:
                    if k in vsp:
                        self._var_settings_picsum[k] = float(vsp[k])
        if pw := self._prefs.get("picsum_width"):
            try: self._picsum_width = max(100, int(pw))
            except Exception: pass
        if ph := self._prefs.get("picsum_height"):
            try: self._picsum_height = max(100, int(ph))
            except Exception: pass
        if vsf := self._prefs.get("var_settings_flickr"):
            if isinstance(vsf, dict):
                for k in self._var_settings_flickr:
                    if k in vsf:
                        self._var_settings_flickr[k] = float(vsf[k])
        if fw := self._prefs.get("flickr_width"):
            try: self._flickr_width = max(100, int(fw))
            except Exception: pass
        if fh := self._prefs.get("flickr_height"):
            try: self._flickr_height = max(100, int(fh))
            except Exception: pass
        if fkw := self._prefs.get("flickr_keyword"):
            self._flickr_keyword = str(fkw)
        if me := self._prefs.get("mac_entries"):
            if isinstance(me, list) and me:
                parsed = []
                for item in me:
                    if isinstance(item, dict):
                        parsed.append({"mac": str(item.get("mac","")).upper(), "note": str(item.get("note",""))})
                    elif isinstance(item, str):  # 구버전 마이그레이션
                        parsed.append({"mac": item.upper(), "note": ""})
                if parsed:
                    self._mac_entries = parsed
        elif wl := self._prefs.get("mac_whitelist"):  # 구버전 키 마이그레이션
            if isinstance(wl, list) and wl:
                self._mac_entries = [{"mac": str(m).upper(), "note": ""} for m in wl]
        self._normalize_option_arrays()
        self._rebuild_selector()
        self._update_kw2_state()
        self.after(100, self._update_topic_state)

    def _normalize_option_arrays(self):
        n = max(1, len(self._prompts))
        def _fit(arr, default):
            arr.extend([default] * max(0, n - len(arr)))
            del arr[n:]
        _fit(self._prompts, "")
        _fit(self._prompts2, "")
        _fit(self._kw2_enabled, False)
        _fit(self._option_enabled, True)
        _fit(self._topic_enabled, False)
        _fit(self._collect_enabled, False)
        _fit(self._guest_prompt_enabled, False)
        while len(self._prompt_names) < n:
            self._prompt_names.append(f"옵션 {len(self._prompt_names)+1}")
        del self._prompt_names[n:]
        _fit(self._kw_per_option, "")
        _fit(self._kw2_per_option, "")
        _fit(self._collect_kw_per_option, "")
        _fit(self._img_source_per_option, "AI")
        self._selected_prompt_idx = max(0, min(n - 1, self._selected_prompt_idx))

    def _fetch_mac_from_gist(self):
        """시작 시 Gist에서 최신 mac_entries를 동기적으로 가져옵니다."""
        url = re.sub(r'/raw/[0-9a-f]{40}/', '/raw/', self._remote_url.strip())
        if not url:
            return
        try:
            import urllib.request as _ur
            gist_m = re.search(
                r'gist\.githubusercontent\.com/([^/]+)/([0-9a-f]+)/raw/([^?]+)', url)
            if gist_m:
                gist_id = gist_m.group(2)
                api_url = f"https://api.github.com/gists/{gist_id}"
                req = _ur.Request(api_url, headers={
                    "User-Agent": "BAMHOBAKBot/1.0",
                    "Accept":     "application/vnd.github+json",
                })
                with _urlopen_ssl(req, timeout=10) as resp:
                    api_json = json.loads(resp.read().decode("utf-8"))
                files = api_json.get("files", {})
                for _, fdata in files.items():
                    if fdata.get("filename", "").endswith(".json"):
                        data = json.loads(fdata.get("content", "{}"))
                        if me := data.get("mac_entries"):
                            if isinstance(me, list) and me:
                                self._mac_entries = [
                                    {"mac": str(e.get("mac","")).upper(),
                                     "note": str(e.get("note","")),
                                     "guest": bool(e.get("guest", False))}
                                    for e in me if isinstance(e, dict)
                                ]
                                if gpe := data.get("guest_prompt_enabled"):
                                    if isinstance(gpe, list):
                                        for i, v in enumerate(gpe[:15]):
                                            self._guest_prompt_enabled[i] = bool(v)
                                break
        except Exception:
            pass  # 실패 시 로컬 prefs 목록 사용

    def _check_mac_allowed(self) -> bool:
        import tkinter.messagebox as _mb
        if not self._mac_entries:
            _mb.showerror(
                "실행 불가",
                "허용 MAC 목록을 불러올 수 없습니다.\n인터넷 연결을 확인하고 다시 실행해 주세요."
            )
            import sys; sys.exit(0)
        current = _get_mac_address().upper()
        for e in self._mac_entries:
            if e["mac"].upper() == current:
                self._is_guest = bool(e.get("guest", False))
                return True
        self._show_access_denied(current)
        self.after(0, self._safe_exit)
        return False

    def _safe_exit(self):
        try:
            self.quit()
        except Exception:
            pass
        import sys
        sys.exit(0)

    def _apply_guest_mode(self):
        for attr in ("btn_img", "btn_all", "row2", "img_prog_frame", "img_hdr"):
            try:
                getattr(self, attr).pack_forget()
            except Exception:
                pass
        try:
            self._auto_btn.pack_forget()
        except Exception:
            pass
        self._rebuild_selector()

    def _show_access_denied(self, mac: str):
        import tkinter as _tk
        dlg = _tk.Toplevel(self)
        dlg.title("접근 거부")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"360x200+{(sw-360)//2}+{(sh-200)//2}")
        dlg.configure(bg="#F4F6FB")

        _tk.Label(dlg, text="이 컴퓨터는 허용되지 않은 기기입니다.",
                  bg="#F4F6FB", fg="#1A2340",
                  font=("Malgun Gothic", 12, "bold")).pack(pady=(24, 8))

        mac_row = _tk.Frame(dlg, bg="#F4F6FB")
        mac_row.pack()
        _tk.Label(mac_row, text="이 PC MAC:", bg="#F4F6FB",
                  fg="#6B7899", font=("Malgun Gothic", 11)).pack(side="left", padx=(0,6))
        mac_lbl = _tk.Label(mac_row, text=mac, bg="#F4F6FB",
                            fg="#4F6FE8", font=("Malgun Gothic", 12, "bold"),
                            cursor="hand2")
        mac_lbl.pack(side="left")

        copied_lbl = _tk.Label(dlg, text="", bg="#F4F6FB",
                               fg="#2A9D6F", font=("Malgun Gothic", 10))
        copied_lbl.pack(pady=2)

        def _copy():
            dlg.clipboard_clear()
            dlg.clipboard_append(mac)
            copied_lbl.config(text="✅ 클립보드에 복사됨")

        mac_lbl.bind("<Button-1>", lambda e: _copy())

        _tk.Label(dlg, text="관리자에게 문의하세요.",
                  bg="#F4F6FB", fg="#6B7899",
                  font=("Malgun Gothic", 10)).pack(pady=(4, 0))

        btn_frame = _tk.Frame(dlg, bg="#F4F6FB")
        btn_frame.pack(pady=(12, 0))

        _tk.Button(btn_frame, text="📋 복사", command=_copy,
                   bg="#4F6FE8", fg="white",
                   font=("Malgun Gothic", 10, "bold"),
                   relief="flat", padx=16, pady=6,
                   cursor="hand2").pack(side="left", padx=(0, 8))

        _tk.Button(btn_frame, text="확인", command=dlg.destroy,
                   bg="#D0D7E8", fg="#1A2340",
                   font=("Malgun Gothic", 10),
                   relief="flat", padx=16, pady=6).pack(side="left")

        dlg.wait_window()

    def _on_close(self):
        self._save_prefs()
        gemini_scraper.stop()
        self.destroy()

    def _set_browser_ui(self, state: str, msg: str = ""):
        configs = {
            "on":      ("●", "#2ECC71", "글 생성 준비됨"),
            "off":     ("●", "#E74C3C", "글 생성 종료됨"),
            "loading": ("●", "#F39C12", "글 생성 준비 중"),
            "error":   ("●", "#E74C3C", f"오류"),
        }
        dot, color, text = configs.get(state, configs["off"])
        self.browser_dot.configure(text=dot, text_color=color)
        self.browser_status_lbl.configure(text=text, text_color=color)

    def _set_hf_ui(self, state: str, msg: str = ""):
        configs = {
            "on":      ("#2ECC71", "이미지 생성 준비됨"),
            "off":     ("#95A5A6", "이미지 토큰 없음"),
            "loading": ("#F39C12", "이미지 준비 중"),
            "error":   ("#E74C3C", f"이미지 오류"),
        }
        color, text = configs.get(state, configs["off"])
        self.hf_dot.configure(text_color=color)
        self.hf_status_lbl.configure(text=text, text_color=color)

    def _set_sync_ui(self, state: str, msg: str = ""):
        configs = {
            "idle":    ("#95A5A6", "", ""),
            "loading": ("#F39C12", "●", "동기화 중..."),
            "ok":      ("#2ECC71", "●", "동기화 완료"),
            "error":   ("#E74C3C", "●", f"동기화 실패"),
        }
        color, dot, text = configs.get(state, configs["idle"])
        # 헤더 동기화 상태
        try:
            self.sync_hdr_dot.configure(text=dot, text_color=color)
            self.sync_hdr_lbl.configure(text=text, text_color=color)
        except Exception:
            pass
        # 다이얼로그 안의 레이블 (열려있을 때만)
        try:
            self.sync_status_lbl.configure(text=text, text_color=color)
        except Exception:
            pass

    def _sync_remote_prompts(self, _retry: int = 0):
        url = re.sub(r'/raw/[0-9a-f]{40}/', '/raw/', self._remote_url.strip())
        if not url:
            return
        self._remote_url = url
        self.after(0, lambda: self._set_sync_ui("loading"))
        try:
            import urllib.request as _ur

            gist_m = re.search(
                r'gist\.githubusercontent\.com/([^/]+)/([0-9a-f]+)/raw/([^?]+)', url)
            if gist_m:
                gist_id = gist_m.group(2)
                filename = gist_m.group(3).rsplit('/', 1)[-1]
                api_url = f"https://api.github.com/gists/{gist_id}"
                _sync_headers = {
                    "User-Agent": "BAMHOBAKBot/1.0",
                    "Accept":     "application/vnd.github+json",
                }
                _tok = getattr(config, "GITHUB_TOKEN", "").strip()
                if _tok:
                    _sync_headers["Authorization"] = f"token {_tok}"
                api_req = _ur.Request(api_url, headers=_sync_headers)
                with _urlopen_ssl(api_req, timeout=20) as resp:
                    api_json = json.loads(resp.read().decode("utf-8"))
                files = api_json.get("files", {})
                raw_content = None
                for fname, fdata in files.items():
                    if fname == filename or fname.endswith(".json"):
                        raw_content = fdata.get("content", "")
                        break
                if raw_content is None:
                    raise ValueError("Gist에서 JSON 파일을 찾을 수 없습니다.")
                data = json.loads(raw_content)
            else:
                sep = "&" if "?" in url else "?"
                req = _ur.Request(f"{url}{sep}_t={int(time.time())}", headers={
                    "User-Agent": "BAMHOBAKBot/1.0"})
                with _urlopen_ssl(req, timeout=20) as resp:
                    raw = resp.read().decode("utf-8")
                data = json.loads(raw)

            self.after(0, lambda: self._apply_remote_data(data))
            self.after(0, lambda: self._set_sync_ui("ok"))
            self.after(200, self._save_prefs)
        except Exception as e:
            if _retry < 3:
                # 실패 시 3초 대기 후 재시도 (최대 3회)
                time.sleep(3)
                self._sync_remote_prompts(_retry + 1)
            else:
                self.after(0, lambda err=str(e): self._set_sync_ui("error", err))

    def _apply_remote_data(self, data: dict):
        if p := data.get("prompts"):
            if isinstance(p, list) and p:
                self._prompts = [str(v) if v else "" for v in p]
        if p2 := data.get("prompts2"):
            if isinstance(p2, list):
                self._prompts2 = [str(v) if v else "" for v in p2]
        if kw2 := data.get("kw2_enabled"):
            if isinstance(kw2, list):
                self._kw2_enabled = [bool(v) for v in kw2]
        if oe := data.get("option_enabled"):
            if isinstance(oe, list):
                self._option_enabled = [bool(v) for v in oe]
        if te := data.get("topic_enabled"):
            if isinstance(te, list):
                self._topic_enabled = [bool(v) for v in te]
        if ce := data.get("collect_enabled"):
            if isinstance(ce, list):
                self._collect_enabled = [bool(v) for v in ce]
        if cc := data.get("collect_count"):
            try: self._collect_count = int(cc)
            except Exception: pass
        if cs := data.get("collect_skip"):
            try: self._collect_skip = int(cs)
            except Exception: pass
        if ck := data.get("collect_chunk"):
            self._collect_chunk = str(ck)
        if cm := data.get("collect_maxchars"):
            try: self._collect_maxchars = int(cm)
            except Exception: pass
        if ch := data.get("collect_header"):
            self._collect_header = str(ch)
        if tl := data.get("topic_lists"):
            if isinstance(tl, dict):
                for k, v in tl.items():
                    if isinstance(v, list):
                        self._topic_lists[str(k)] = [str(t) for t in v if t]
        if tr := data.get("topic_rows"):
            if isinstance(tr, list):
                self._topic_rows = [
                    [str(k) for k in row if k]
                    for row in tr if isinstance(row, list)
                ]
        if names := data.get("prompt_names"):
            if isinstance(names, list):
                self._prompt_names = [str(n) if n else f"옵션 {i+1}" for i, n in enumerate(names)]
        if vs := data.get("var_settings"):
            if isinstance(vs, dict):
                for k in self._var_settings:
                    if k in vs:
                        self._var_settings[k] = float(vs[k])
        if vsp := data.get("var_settings_picsum"):
            if isinstance(vsp, dict):
                for k in self._var_settings_picsum:
                    if k in vsp:
                        self._var_settings_picsum[k] = float(vsp[k])
        if vsf := data.get("var_settings_flickr"):
            if isinstance(vsf, dict):
                for k in self._var_settings_flickr:
                    if k in vsf:
                        self._var_settings_flickr[k] = float(vsf[k])
        if mw := data.get("max_width"):
            try:
                self._max_width = int(mw)
            except Exception:
                pass
        if me := data.get("mac_entries"):
            if isinstance(me, list) and me:
                parsed = []
                for item in me:
                    if isinstance(item, dict):
                        parsed.append({
                            "mac": str(item.get("mac","")).upper(),
                            "note": str(item.get("note","")),
                            "guest": bool(item.get("guest", False)),
                        })
                    elif isinstance(item, str):
                        parsed.append({"mac": item.upper(), "note": "", "guest": False})
                if parsed:
                    self._mac_entries = parsed
        if gpe := data.get("guest_prompt_enabled"):
            if isinstance(gpe, list):
                self._guest_prompt_enabled = [bool(v) for v in gpe]
        if ac := data.get("auto_config"):
            if isinstance(ac, dict):
                try:
                    import yaml as _yaml_rd
                    _auto_p = _BASE_DIR / "auto" / "config.yaml"
                    _auto_p.parent.mkdir(parents=True, exist_ok=True)
                    with open(_auto_p, "w", encoding="utf-8") as _f:
                        _yaml_rd.dump(ac, _f, allow_unicode=True,
                                      default_flow_style=False, sort_keys=False)
                except Exception:
                    pass
        self._normalize_option_arrays()
        self._rebuild_selector()
        self._update_kw2_state()

    def _auto_warmup_hf(self):
        if not config.CF_ACCOUNT_ID or not config.CF_API_TOKEN:
            self.after(0, lambda: self._set_hf_ui("off"))
            return
        try:
            image_generator.warmup()
            self.after(0, lambda: self._set_hf_ui("on"))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self._set_hf_ui("error", msg))

    def _auto_start_browser(self):
        try:
            gemini_scraper.start()
            self.after(0, lambda: self._set_browser_ui("on"))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self._set_browser_ui("error", msg))

    # ── 전체 레이아웃 ────────────────────────────────────
    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color=C["accent"], height=54, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        _lbl(hdr, "",
             font=("Malgun Gothic", 16, "bold"), color="white").pack(side="left", padx=22, pady=12)

        ctrl = ctk.CTkFrame(hdr, fg_color="transparent")
        ctrl.pack(side="right", padx=10, pady=8)

        _HDR_DOT  = ("Malgun Gothic", 10, "bold")
        _HDR_LBL  = ("Malgun Gothic", 9, "bold")
        _HDR_SEP  = ("Malgun Gothic", 10)

        def _sep():
            ctk.CTkLabel(ctrl, text="|", width=6,
                         font=_HDR_SEP, text_color="#8899CC").pack(side="left", padx=2)

        # 프롬프트 동기화 상태 (헤더)
        self.sync_hdr_dot = ctk.CTkLabel(
            ctrl, text="", width=10,
            font=_HDR_DOT, text_color="#95A5A6")
        self.sync_hdr_dot.pack(side="left", padx=(0, 1))

        self.sync_hdr_lbl = ctk.CTkLabel(
            ctrl, text="", width=72,
            font=_HDR_LBL, text_color="#95A5A6", anchor="w")
        self.sync_hdr_lbl.pack(side="left")

        _sep()

        self.hf_dot = ctk.CTkLabel(
            ctrl, text="●", width=10,
            font=_HDR_DOT, text_color="#F39C12", cursor="hand2")
        self.hf_dot.pack(side="left", padx=(0, 1))
        self.hf_dot.bind("<Button-1>", lambda e: self._save_settings())

        self.hf_status_lbl = ctk.CTkLabel(
            ctrl, text="이미지 생성 준비 중...", width=90,
            font=_HDR_LBL, text_color="#F39C12", anchor="w", cursor="hand2")
        self.hf_status_lbl.pack(side="left")
        self.hf_status_lbl.bind("<Button-1>", lambda e: self._save_settings())

        _sep()

        self.browser_dot = ctk.CTkLabel(
            ctrl, text="●", width=10,
            font=_HDR_DOT, text_color="#F39C12")
        self.browser_dot.pack(side="left", padx=(0, 1))

        self.browser_status_lbl = ctk.CTkLabel(
            ctrl, text="글 생성 준비 중...", width=82,
            font=_HDR_LBL, text_color="#F39C12", anchor="w")
        self.browser_status_lbl.pack(side="left")

        _sep()

        self._update_btn = ctk.CTkButton(
            ctrl, text="업데이트",
            command=self._show_update_dialog,
            height=22, width=90, font=("Malgun Gothic", 9, "bold"),
            fg_color=C["ok"], hover_color="#1E8259",
            text_color="white", corner_radius=6,
        )
        # pack 하지 않음 — 업데이트 발견 시 표시

        self._btn_secret = ctk.CTkButton(
            ctrl, text="★",
            command=self._check_password,
            width=26, height=26,
            font=("Malgun Gothic", 13),
            fg_color="transparent",
            hover_color="#5566AA",
            text_color="#CCDDF8",
            corner_radius=6, border_width=0,
        )
        self._btn_secret.pack(side="left", padx=(0, 2))

        # 헤더 탭 버튼
        tab_btn_area = ctk.CTkFrame(hdr, fg_color="transparent")
        tab_btn_area.pack(side="left", padx=(4, 0), pady=8)

        tab1_frame = ctk.CTkFrame(self, fg_color=C["card"],
                                  border_color=C["border"], border_width=1, corner_radius=14)
        tab2_frame = ctk.CTkFrame(self, fg_color=C["card"],
                                  border_color=C["border"], border_width=1, corner_radius=14)

        _TAB_PAD = dict(padx=16, pady=(8, 16))

        def _show_tab1():
            tab2_frame.pack_forget()
            tab1_frame.pack(fill="both", expand=True, **_TAB_PAD)
            btn_tab1.configure(fg_color="white", text_color=C["accent"], hover_color="#E8EAF6")
            btn_tab2.configure(fg_color="transparent", text_color="white", hover_color="#6478EB")

        def _show_tab2():
            tab1_frame.pack_forget()
            tab2_frame.pack(fill="both", expand=True, **_TAB_PAD)
            btn_tab2.configure(fg_color="white", text_color=C["accent"], hover_color="#E8EAF6")
            btn_tab1.configure(fg_color="transparent", text_color="white", hover_color="#6478EB")

        self._auto_btn = ctk.CTkButton(
            tab_btn_area, text="🤖  오토봇", command=self._launch_naver_auto,
            height=28, font=("Malgun Gothic", 12, "bold"),
            fg_color="#2A9D6F", hover_color="#1E8259",
            text_color="white", corner_radius=8,
        )
        if not self._is_guest:
            self._auto_btn.pack(side="left", padx=(0, 5))
        self._auto_proc = None

        ctk.CTkLabel(tab_btn_area, text="|", width=10,
                     font=("Malgun Gothic", 12), text_color="#8899CC").pack(side="left", padx=4)

        btn_tab1 = ctk.CTkButton(
            tab_btn_area, text="✨  생성하기", command=_show_tab1,
            height=28, font=("Malgun Gothic", 12, "bold"),
            fg_color="white", hover_color="#E8EAF6",
            text_color=C["accent"], corner_radius=8,
        )
        btn_tab1.pack(side="left", padx=(0, 5))

        btn_tab2 = ctk.CTkButton(
            tab_btn_area, text="⚙️  설정 및 가이드", command=_show_tab2,
            height=28, font=("Malgun Gothic", 12, "bold"),
            fg_color="transparent", hover_color="#6478EB",
            text_color="white", corner_radius=8,
        )
        btn_tab2.pack(side="left")

        self._build_generate_tab(tab1_frame)
        self._build_settings_tab(tab2_frame)
        _show_tab1()

    # ── 네이버 자동화 실행 ────────────────────────────────
    def _launch_naver_auto(self):
        if self._auto_proc and self._auto_proc.is_alive():
            return

        import tkinter.messagebox as mb
        import multiprocessing

        if getattr(sys, "frozen", False):
            naver_dir = str(Path(sys._MEIPASS) / "auto")
        else:
            naver_dir = str(Path(__file__).parent / "auto")

        if not Path(naver_dir, "main.py").exists():
            mb.showerror("자동화 로그인", f"auto 파일을 찾을 수 없습니다.\n{naver_dir}")
            return

        import os as _os
        _os.environ["AUTO_CONFIG_PATH"] = str(_BASE_DIR / "auto" / "config.yaml")
        p = multiprocessing.Process(target=_naver_auto_worker, args=(naver_dir,), daemon=True)
        p.start()
        self._auto_proc = p
        self._auto_btn.configure(fg_color="#C0392B", hover_color="#A93226")
        self._poll_auto_proc()

    def _poll_auto_proc(self):
        if self._auto_proc and self._auto_proc.is_alive():
            self.after(1000, self._poll_auto_proc)
        else:
            self._auto_proc = None
            self._auto_btn.configure(fg_color="#2A9D6F", hover_color="#1E8259")

    def _chrome_launch_watcher(self):
        """Chrome이 새로 켜지면 오토봇 자동 시작"""
        import subprocess, time

        def chrome_running():
            try:
                r = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return "chrome.exe" in r.stdout.lower()
            except Exception:
                return False

        was_running = chrome_running()
        while True:
            time.sleep(2)
            now_running = chrome_running()
            if not was_running and now_running:
                proc = getattr(self, "_auto_proc", None)
                if not (proc and proc.is_alive()):
                    self.after(0, self._launch_naver_auto)
            was_running = now_running

    # ── 생성하기 탭 ──────────────────────────────────────
    def _build_generate_tab(self, parent):
        parent.configure(fg_color=C["card"])

        top = _card(parent)
        top.pack(fill="x", padx=10, pady=(8, 6))
        ti = ctk.CTkFrame(top, fg_color="transparent")
        ti.pack(fill="x", padx=14, pady=12)

        row1 = ctk.CTkFrame(ti, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))

        self.prompt_selector = ctk.CTkOptionMenu(
            row1,
            values=self._prompt_names,
            command=self._on_prompt_select,
            width=170, height=38,
            dynamic_resizing=False,
            font=F_SMB,
            fg_color=C["accent_bg"],
            button_color=C["accent"],
            button_hover_color=C["accent_h"],
            text_color=C["text"],
            dropdown_fg_color=C["card"],
            dropdown_text_color=C["text"],
            dropdown_font=F_SMB,
            dropdown_hover_color=C["accent_bg"],
            corner_radius=8,
        )
        self.prompt_selector.set(self._prompt_names[0])
        self.prompt_selector.pack(side="left", padx=(0, 6))

        self.kw_row1_lbl = ctk.CTkLabel(
            row1, text="키워드",
            font=F_B, text_color=C["subtext"],
        )
        # 인기글 수집 모드에서만 표시

        self._kw_frame = ctk.CTkFrame(row1, fg_color="transparent")
        self._kw_frame.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.keyword_entry = _UndoEntry(
            self._kw_frame,
            placeholder_text="키워드 입력",
            height=38, font=F,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], placeholder_text_color=C["subtext"],
            corner_radius=8,
        )
        self.keyword_entry.pack(fill="x", expand=True)
        self.keyword_entry.bind("<Return>", lambda e: self._start_all())

        self.keyword_textbox = tk.Text(
            self._kw_frame,
            height=4, font=F,
            bg=C["input_bg"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", bd=0, padx=6, pady=4, wrap="word",
            highlightthickness=1, highlightbackground=C["border"],
        )
        # 초기 숨김 (시크릿 모드일 때만 표시)

        self.topic_dropdown = _TopicPicker(
            self._kw_frame,
            values=["(저장된 목록 없음)"],
            font=F,
            fg_color=C["accent_bg"], button_color=C["accent"],
            button_hover_color=C["accent_h"],
            text_color=C["text"],
            corner_radius=8,
        )
        # 초기 숨김

        self.kw2_lbl = ctk.CTkCheckBox(
            row1, text="주제",
            variable=self.kw2_var,
            command=self._on_kw2_toggle,
            font=F_B,
            fg_color=C["accent"], hover_color=C["accent_h"],
            checkmark_color="white",
            text_color=C["subtext"],
            width=20, height=20,
        )
        self.kw2_lbl.pack(side="left", padx=(0, 6))

        self.kw2_topic_lbl = ctk.CTkLabel(
            row1, text="주제",
            font=F_B, text_color=C["subtext"],
        )
        # 주제 사용 ON (비수집) 시에만 표시

        self.kw2_entry = _UndoEntry(
            row1,
            placeholder_text="주제 입력",
            width=120, height=38, font=F,
            fg_color="#B8C0D0", border_color="#9AA5BB",
            text_color="#70788A", placeholder_text_color="#70788A",
            corner_radius=8, state="disabled",
        )
        self.kw2_entry.pack(side="left", padx=(0, 6))

        _BTN_W, _BTN_H = 72, 34
        _BTN_F = ("Malgun Gothic", 11, "bold")

        self.btn_text = ctk.CTkButton(
            row1, text="글만", command=self._start_text_only,
            width=_BTN_W, height=_BTN_H, font=_BTN_F,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="white", corner_radius=8)
        self.btn_text.pack(side="left", padx=(0, 3))

        self.btn_img = ctk.CTkButton(
            row1, text="이미지만", command=self._start_image_only,
            width=_BTN_W, height=_BTN_H, font=_BTN_F,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="white", corner_radius=8)
        self.btn_img.pack(side="left", padx=(0, 3))

        self.btn_all = ctk.CTkButton(
            row1, text="전체 생성", command=self._start_all,
            width=_BTN_W, height=_BTN_H, font=_BTN_F,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="white", corner_radius=8)
        self.btn_all.pack(side="left", padx=(0, 3))

        self.btn_stop = ctk.CTkButton(
            row1, text="중단", command=self._stop_generation,
            width=52, height=34, font=("Malgun Gothic", 11, "bold"),
            fg_color=C["disabled"], hover_color="#888FA0",
            text_color="white", corner_radius=8, state="disabled")
        self.btn_stop.pack(side="left")

        # 인기글 수집 모드 전용 두 번째 줄 (원제목 입력)
        self.collect_row2 = ctk.CTkFrame(ti, fg_color="transparent")
        # 초기 숨김 — collect ON 시에만 pack
        self.collect_kw_lbl = ctk.CTkLabel(
            self.collect_row2, text="원제목",
            font=F_B, text_color=C["subtext"],
        )
        self.collect_kw_lbl.pack(side="left", padx=(176, 4))
        self.collect_kw_entry = _UndoEntry(
            self.collect_row2,
            placeholder_text="기본 제목 입력",
            height=38, font=F,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], placeholder_text_color=C["subtext"],
            corner_radius=8,
        )
        self.collect_kw_entry.pack(side="left", fill="x", expand=True, padx=(0, 283))

        self.row2 = row2 = ctk.CTkFrame(ti, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))

        # 로컬 이미지 변형 (AI 생성과 독립 실행)
        self.local_img_btn = ctk.CTkButton(
            row2, text="📁 이미지 선택", command=self._pick_local_img_folder,
            width=100, height=28, font=F_SM,
            fg_color=C["accent_bg"], hover_color=C["border"],
            text_color=C["accent"], corner_radius=7,
        )
        self.local_img_btn.pack(side="left", padx=(0, 4))

        self.local_var_btn = ctk.CTkButton(
            row2, text="▶ 변환 실행", command=self._run_local_variation,
            width=90, height=28, font=F_SM,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="white", corner_radius=7,
            state="normal" if self._local_img_folder else "disabled",
        )
        self.local_var_btn.pack(side="left", padx=(0, 6))

        self.local_img_lbl = _lbl(
            row2,
            self._local_img_folder if self._local_img_folder else "이미지 폴더 미선택",
            font=F_SM, color=C["ok"] if self._local_img_folder else C["subtext"],
        )
        self.local_img_lbl.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row2, text="|", width=8,
                     font=("Malgun Gothic", 12), text_color=C["border"]).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            row2, text="📂 저장 위치", command=self._pick_variation_output_dir,
            width=90, height=28, font=F_SM,
            fg_color=C["accent_bg"], hover_color=C["border"],
            text_color=C["accent"], corner_radius=7,
        ).pack(side="left", padx=(0, 4))

        self.var_out_lbl = _lbl(
            row2,
            self._variation_output_dir if self._variation_output_dir else "기본: 바탕화면",
            font=F_SM,
            color=C["ok"] if self._variation_output_dir else C["subtext"],
        )
        self.var_out_lbl.pack(side="left", fill="x", expand=True)

        img_cnt_frame = ctk.CTkFrame(row2, fg_color="transparent")
        img_cnt_frame.pack(side="right")
        self.img_src_menu = ctk.CTkOptionMenu(
            img_cnt_frame, values=["AI", "플리커", "픽숨"],
            command=self._on_img_source_change,
            width=80, height=28, font=F_SMB,
            fg_color=C["accent_bg"], button_color=C["border"],
            button_hover_color=C["accent"], text_color=C["text"],
            dropdown_fg_color=C["input_bg"], dropdown_text_color=C["text"],
            dropdown_font=F_SMB, dropdown_hover_color=C["accent_bg"], corner_radius=8,
        )
        self.img_src_menu.pack(side="left", padx=(0, 8))
        _lbl(img_cnt_frame, "이미지", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 6))
        self.img_count_entry = _UndoEntry(
            img_cnt_frame, width=52, height=28, font=F_SMB,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], justify="center", corner_radius=8,
        )
        self.img_count_entry.pack(side="left")
        _lbl(img_cnt_frame, "장", font=F_SM, color=C["subtext"]).pack(side="left", padx=(4, 0))

        # ② 진행 상태 (1줄)
        prog_area = ctk.CTkFrame(parent, fg_color="transparent")
        prog_area.pack(fill="x", padx=14, pady=(0, 4))

        one_row = ctk.CTkFrame(prog_area, fg_color="transparent")
        one_row.pack(fill="x")

        # 전체 상태 (왼쪽)
        self.status_label = _lbl(one_row, "키워드를 입력하고 생성하기를 눌러주세요.",
                                  font=F_SM, color=C["subtext"])
        self.status_label.pack(side="left", fill="x", expand=True)

        # 📝 글
        ctk.CTkLabel(one_row, text="📝", font=F_SM, width=22,
                     text_color=C["subtext"]).pack(side="left", padx=(8, 0))
        self.text_status_lbl = _lbl(one_row, "대기 중", font=F_SM, color=C["subtext"], width=76, anchor="w")
        self.text_status_lbl.pack(side="left")
        self.text_prog = ctk.CTkProgressBar(one_row, width=100, height=8, corner_radius=4,
            progress_color=C["accent_bg"], fg_color=C["accent_bg"])
        self.text_prog.pack(side="left", padx=(4, 0))
        self.text_prog.set(0)

        # 📷 이미지
        self.img_prog_frame = ctk.CTkFrame(one_row, fg_color="transparent")
        self.img_prog_frame.pack(side="left")
        ctk.CTkLabel(self.img_prog_frame, text="📷", font=F_SM, width=22,
                     text_color=C["subtext"]).pack(side="left", padx=(10, 0))
        self.img_status_lbl = _lbl(self.img_prog_frame, "대기 중", font=F_SM, color=C["subtext"], width=100, anchor="w")
        self.img_status_lbl.pack(side="left")
        self.img_prog = ctk.CTkProgressBar(self.img_prog_frame, width=100, height=8, corner_radius=4,
            progress_color=C["accent_bg"], fg_color=C["accent_bg"])
        self.img_prog.pack(side="left", padx=(4, 0))
        self.img_prog.set(0)

        # 타이머 (오른쪽)
        self.timer_label = ctk.CTkLabel(
            one_row, text="", width=54,
            font=("Malgun Gothic", 12, "bold"), text_color=C["accent"])
        self.timer_label.pack(side="left", padx=(10, 0))

        # ③ 본문
        body_hdr = ctk.CTkFrame(parent, fg_color="transparent")
        body_hdr.pack(fill="x", padx=14, pady=(8, 2))
        _lbl(body_hdr, "생성된 글", font=F_SMB, color=C["subtext"]).pack(side="left")
        self.btn_copy = ctk.CTkButton(
            body_hdr, text="글 복사", command=self._copy_as_html,
            width=130, height=28, font=("Malgun Gothic", 11, "bold"),
            fg_color=C["ok"], hover_color="#1E7A55",
            text_color="white", corner_radius=8,
        )
        self.btn_copy.pack(side="right")
        self.text_count_lbl = ctk.CTkLabel(
            body_hdr, text="", font=("Malgun Gothic", 11),
            text_color=C["ok"],
        )
        self.text_count_lbl.pack(side="right", padx=(0, 8))

        # ⑤ 이미지 영역 — bottom에 먼저 pack해야 콘텐츠 expand에 밀리지 않음
        self.img_hdr = img_hdr = ctk.CTkFrame(parent, fg_color="transparent")
        img_hdr.pack(side="bottom", fill="x", padx=14, pady=(2, 4))
        img_top = ctk.CTkFrame(img_hdr, fg_color="transparent")
        img_top.pack(fill="x", pady=(0, 2))
        _lbl(img_top, "생성된 이미지", font=F_SMB, color=C["subtext"]).pack(side="left")
        _lbl(img_top, "※ 이미지 클릭 시 클립보드에 복사됨", font=("Malgun Gothic", 11),
             color=C["subtext"]).pack(side="left", padx=(8, 0))
        self.btn_download = ctk.CTkButton(
            img_top, text="전체 이미지 저장", command=self._download_all,
            width=140, height=28, font=("Malgun Gothic", 11, "bold"),
            fg_color=C["ok"], hover_color="#1E7A55",
            text_color="white", corner_radius=8)
        self.btn_download.pack(side="right")
        # 가로 슬라이드 이미지 프레임 (마우스 휠 + 스크롤바, 높이 자동)
        img_wrapper = tk.Frame(img_hdr, bg=C["card"])
        img_wrapper.pack(fill="x")

        # 가로 스크롤바
        self._img_hscroll = LoopyScrollbar(img_wrapper)
        self._img_hscroll.pack(side="bottom", fill="x")

        self._img_canvas = tk.Canvas(
            img_wrapper, bg=C["card"],
            highlightthickness=0, bd=0,
            xscrollcommand=self._img_hscroll.set,
        )
        self._img_canvas.pack(side="top", fill="x")
        self._img_hscroll.configure(command=self._img_canvas.xview)

        img_inner = tk.Frame(self._img_canvas, bg=C["card"])
        self._img_canvas_win = self._img_canvas.create_window(
            0, 2, anchor="nw", window=img_inner
        )
        self._img_canvas.configure(height=self._calc_thumb_sz(3) + 26)

        def _update_scrollregion(e=None):
            bb = self._img_canvas.bbox("all")
            if bb:
                # 캔버스 높이를 실제 콘텐츠 높이에 맞게 자동 조정
                self._img_canvas.configure(
                    height=bb[3] + 8,
                    scrollregion=(0, 0, bb[2] + 4, bb[3] + 8),
                )
        img_inner.bind("<Configure>", _update_scrollregion)
        self._img_canvas.bind("<Configure>", _update_scrollregion)

        def _img_scroll(e):
            self._img_canvas.xview_scroll(-1 * (e.delta // 120), "units")
        for w in (self._img_canvas, img_inner, img_wrapper):
            w.bind("<MouseWheel>", _img_scroll)
        self._img_scroll_fn = _img_scroll

        self.img_frame = img_inner
        self._init_image_slots(3)

        # ③ 콘텐츠 박스 — 이미지 영역 이후 남은 공간 차지
        content_frame = tk.Frame(
            parent, bg=C["input_bg"],
            highlightbackground=C["border"], highlightthickness=1,
        )
        content_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        scrollbar = ctk.CTkScrollbar(content_frame, width=14)
        scrollbar.pack(side="right", fill="y", pady=1)
        self.content_box = RichText(content_frame, bg=C["input_bg"], fg=C["text"])
        self.content_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.configure(command=self.content_box.yview)
        self.content_box.pack(side="left", fill="both", expand=True)

    _IMG_COLS  = 10   # 한 줄에 표시할 최대 개수

    def _calc_thumb_sz(self, count):
        return 116  # 정사각형 고정 크기

    def _init_image_slots(self, count):
        for w in self.img_frame.winfo_children():
            w.destroy()
        self._img_refs  = [None] * count
        self._img_pil   = [None] * count
        self.img_labels = []
        sz = self._calc_thumb_sz(count)
        self._thumb_sz  = sz
        from PIL import ImageTk as _ITk
        # 빈 이미지로 픽셀 단위 크기 고정 (tk.Label은 이미지 없으면 문자 단위)
        _blank = _ITk.PhotoImage(Image.new("RGB", (sz, sz), C["card"]))
        for i in range(count):
            lbl = tk.Label(
                self.img_frame,
                image=_blank,
                bg=C["card"],
                cursor="hand2",
                bd=0, padx=0, pady=0,
                highlightthickness=0,
                relief="flat",
            )
            lbl._blank = _blank  # GC 방지
            lbl.pack(side="left", padx=(0, 3))
            lbl.bind("<Button-1>", lambda e, idx=i: self._copy_image_at(idx))
            try:
                lbl.bind("<MouseWheel>", self._img_scroll_fn)
            except Exception:
                pass
            self.img_labels.append(lbl)
        try:
            self.after(80, lambda: self._img_canvas.configure(
                scrollregion=self._img_canvas.bbox("all")))
        except Exception:
            pass

    # ── 설정 & 가이드 탭 ─────────────────────────────────
    def _build_settings_tab(self, parent):
        parent.configure(fg_color=C["card"])
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True)

        _lbl(scroll, "API 키 입력", font=F_LG, color=C["accent"]).pack(anchor="w", padx=28, pady=(20,4))
        _lbl(scroll, "처음 사용하거나 다른 컴퓨터에서 사용할 때 입력 후 저장하세요.",
             font=F_SM, color=C["subtext"]).pack(anchor="w", padx=30, pady=(0,14))

        gc = _card(scroll); gc.pack(fill="x", padx=28, pady=(0,10))
        gi = ctk.CTkFrame(gc, fg_color="transparent"); gi.pack(fill="x", padx=16, pady=14)
        _lbl(gi, "✅  글 생성: Gemini 웹 자동화 방식 사용 중", font=F_B, color=C["ok"]).pack(anchor="w")
        _lbl(gi, "로그인 없이 gemini.google.com을 자동으로 사용합니다. API 키 불필요.",
             font=F_SM, color=C["subtext"]).pack(anchor="w", pady=(4, 0))

        cc = _card(scroll); cc.pack(fill="x", padx=28, pady=(0,14))
        ci = ctk.CTkFrame(cc, fg_color="transparent"); ci.pack(fill="x", padx=16, pady=14)
        ct = ctk.CTkFrame(ci, fg_color="transparent"); ct.pack(fill="x")
        _lbl(ct, "☁️  Cloudflare Workers AI (이미지 생성)", font=F_B).pack(side="left")
        _link(ct, "→ 무료 가입", "https://dash.cloudflare.com/sign-up").pack(side="right")

        _lbl(ci, "Account ID", font=F_SMB, color=C["subtext"]).pack(anchor="w", pady=(10,2))
        self.cf_account_entry = _UndoEntry(ci, height=36, font=F,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], corner_radius=8, placeholder_text="32자리 Account ID")
        self.cf_account_entry.pack(fill="x")
        self.cf_account_entry.insert(0, config.CF_ACCOUNT_ID)

        _lbl(ci, "API Token", font=F_SMB, color=C["subtext"]).pack(anchor="w", pady=(8,2))
        self.cf_token_entry = _UndoEntry(ci, height=36, font=F,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], corner_radius=8, placeholder_text="Workers AI 권한 토큰")
        self.cf_token_entry.pack(fill="x")
        self.cf_token_entry.insert(0, config.CF_API_TOKEN)

        _btn(scroll, "💾  저장하기", self._save_settings, w=180, h=42).pack(pady=(14,6))
        self.save_label = ctk.CTkLabel(scroll, text="", font=F_SM); self.save_label.pack()

        ctk.CTkFrame(scroll, height=1, fg_color=C["border"]).pack(fill="x", padx=28, pady=16)

        self._guide(scroll, "☁️  Cloudflare Workers AI 설정 방법",
                    "https://dash.cloudflare.com/sign-up",
                    "cloudflare.com 가입 바로가기", [
            ("1단계", "Cloudflare 가입\n"
                      "dash.cloudflare.com/sign-up 접속 → 이메일 + 비밀번호 입력 후 가입\n"
                      "가입 직후 화면에서 오른쪽 하단 'Skip' 버튼을 2번 눌러 건너뛰세요.\n"
                      "가입 후 인증 메일이 옵니다. 메일의 'Verify email' 버튼을 클릭해 인증을 완료하세요."),
            ("2단계", "Account ID 찾기\n"
                      "로그인 후 대시보드 주소창을 보면 'dash.cloudflare.com/영문숫자32자리/home' 형태입니다.\n"
                      "주소창에서 dash.cloudflare.com/ 바로 뒤의 영문숫자 32자리가 Account ID입니다.\n"
                      "예) dash.cloudflare.com/  →  2d4085d048b414dfc96f818d4e25ffd2  ← 이 부분\n"
                      "복사 후 앱의 'Account ID'에 붙여넣기"),
            ("3단계", "API Token 생성 시작\n"
                      "오른쪽 위 사람 아이콘 클릭 → 'Profile' 클릭\n"
                      "'API Tokens' 탭 클릭 → 파란 'Create Token' 버튼 클릭"),
            ("4단계", "Workers AI 템플릿 선택\n"
                      "목록에서 'Workers AI' 항목을 찾아 오른쪽 'Use template' 버튼 클릭"),
            ("5단계", "계정 범위 설정 후 생성\n"
                      "'Account Resources' 섹션의 'Select...' 드롭다운 클릭 → 본인 계정 선택\n"
                      "아래 'Continue to summary' 클릭 → 'Create Token' 클릭"),
            ("6단계", "토큰 복사 & 앱에 입력\n"
                      "화면에 표시된 토큰을 즉시 복사하세요 (이 화면을 벗어나면 다시 볼 수 없습니다)\n"
                      "위 'API Token' 칸에 방금 복사한 토큰 입력 → '저장하기' 클릭"),
        ])


    def _guide(self, parent, title, url, link_text, steps):
        card = _card(parent); card.pack(fill="x", padx=28, pady=(0, 14))
        inner = ctk.CTkFrame(card, fg_color="transparent"); inner.pack(fill="x", padx=16, pady=14)
        top = ctk.CTkFrame(inner, fg_color="transparent"); top.pack(fill="x", pady=(0,10))
        _lbl(top, title, font=F_B).pack(side="left")
        _link(top, f"🔗 {link_text}", url).pack(side="right")
        for step_title, step_body in steps:
            row = ctk.CTkFrame(inner, fg_color=C["accent_bg"],
                               corner_radius=8, border_color=C["border"], border_width=1)
            row.pack(fill="x", pady=2)
            ri = ctk.CTkFrame(row, fg_color="transparent"); ri.pack(fill="x", padx=10, pady=7)
            ctk.CTkLabel(ri, text=step_title, width=52, height=20,
                         fg_color=C["accent"], corner_radius=5,
                         font=("Malgun Gothic", 11, "bold"), text_color="white").pack(side="left", padx=(0,10))
            _lbl(ri, step_body, font=F_SM, color=C["text"],
                 anchor="w", justify="left", wraplength=720).pack(side="left", fill="x", expand=True)

    # ── 설정 저장 ────────────────────────────────────────
    def _save_settings(self):
        acc = self.cf_account_entry.get().strip()
        tok = self.cf_token_entry.get().strip()
        if acc == "2424" and tok == "2424":
            acc, tok = _DEFAULT_CF_ACCOUNT_ID, _DEFAULT_CF_API_TOKEN
            self.cf_account_entry.delete(0, "end")
            self.cf_account_entry.insert(0, acc)
            self.cf_token_entry.delete(0, "end")
            self.cf_token_entry.insert(0, tok)
        ENV_PATH.write_text(
            f"CF_ACCOUNT_ID={acc}\nCF_API_TOKEN={tok}\n"
            f"NAVER_BLOG_ID={config.NAVER_BLOG_ID}\nGITHUB_TOKEN={config.GITHUB_TOKEN}\n",
            encoding="utf-8")
        config.CF_ACCOUNT_ID = acc
        config.CF_API_TOKEN  = tok
        self.save_label.configure(text="✅  저장 완료!", text_color=C["ok"])
        if acc and tok:
            self.after(0, lambda: self._set_hf_ui("loading"))
            threading.Thread(target=self._auto_warmup_hf, daemon=True).start()

    # ── GitHub Gist 업로드 ──────────────────────────────
    def _upload_to_gist(self, data: dict, status_lbl, url_entry=None):
        token = config.GITHUB_TOKEN.strip()
        if not token:
            self.after(0, lambda: status_lbl.configure(
                text="⚠️ 설정 탭에서 GitHub 토큰을 먼저 입력하고 저장하세요.",
                text_color=C["err"]))
            return

        import urllib.request as _ur

        payload = {
            "description": "BAMHOBAK 프롬프트 설정",
            "public": False,
            "files": {
                "prompts.json": {
                    "content": json.dumps(data, ensure_ascii=False, indent=2)
                }
            }
        }
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "BAMHOBAKBot/1.0",
        }
        body = json.dumps(payload).encode("utf-8")

        gist_m = re.search(
            r'gist\.githubusercontent\.com/[^/]+/([0-9a-f]+)/raw', self._remote_url)
        if gist_m:
            gist_id = gist_m.group(1)
            api_url = f"https://api.github.com/gists/{gist_id}"
            req = _ur.Request(api_url, data=body, headers=headers, method="PATCH")
            action = "업데이트"
        else:
            api_url = "https://api.github.com/gists"
            req = _ur.Request(api_url, data=body, headers=headers, method="POST")
            action = "생성"

        try:
            with _urlopen_ssl(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            raw_url = result["files"]["prompts.json"]["raw_url"]
            raw_url = re.sub(r'/raw/[0-9a-f]{40}/', '/raw/', raw_url)
            self._remote_url = raw_url
            self._save_prefs()
            self.after(0, lambda: status_lbl.configure(
                text=f"✅ Gist {action} 완료!", text_color=C["ok"]))
            if url_entry:
                self.after(0, lambda u=raw_url: (
                    url_entry.delete(0, "end"),
                    url_entry.insert(0, u),
                ))
        except Exception as e:
            err_msg = str(e)[:50]
            self.after(0, lambda: status_lbl.configure(
                text=f"⚠️ 업로드 실패: {err_msg}", text_color=C["err"]))

    # ── 타이머 ───────────────────────────────────────────
    def _start_timer(self):
        self._timer_running = True
        self._timer_start   = time.time()
        threading.Thread(target=self._run_timer, daemon=True).start()

    def _run_timer(self):
        while self._timer_running:
            elapsed = time.time() - self._timer_start
            m, s = divmod(int(elapsed), 60)
            txt = f"{m:02d}:{s:02d}"
            self.after(0, lambda t=txt: self.timer_label.configure(text=t))
            time.sleep(0.5)

    def _stop_timer(self):
        self._timer_running = False
        elapsed = time.time() - getattr(self, "_timer_start", time.time())
        m, s = divmod(int(elapsed), 60)
        self.after(0, lambda: self.timer_label.configure(
            text=f"✓ {m:02d}:{s:02d}", text_color=C["ok"]))

    def _on_img_source_change(self, new_source: str):
        self._img_count_by_source[self._img_source] = self.img_count_entry.get().strip() or "3"
        self._img_source = new_source
        cnt = self._img_count_by_source.get(new_source, "3")
        self.img_count_entry.delete(0, "end")
        self.img_count_entry.insert(0, cnt)

    # ── 생성 공통 ────────────────────────────────────────
    def _get_img_count(self):
        try:
            n = int(self.img_count_entry.get().strip())
            return max(1, min(n, 100))
        except ValueError:
            return 3

    def _check_ready(self):
        idx = self._selected_prompt_idx
        if self._topic_enabled[idx]:
            kw = self.topic_dropdown.get().strip()
            if not kw or kw == "(저장된 목록 없음)":
                self._set_status("⚠️  주제 목록을 먼저 등록해 주세요.", color=C["err"]); return None
        elif self._is_secret_mode():
            kw = self.keyword_textbox.get("1.0", "end").strip()
            if not kw:
                self._set_status("⚠️  내용을 입력해 주세요.", color=C["err"]); return None
        else:
            kw = self.keyword_entry.get().strip()
            if not kw:
                self._set_status("⚠️  키워드를 입력해 주세요.", color=C["err"]); return None
        return kw

    def _lock_btns(self, locked=True):
        state = "disabled" if locked else "normal"
        col   = C["disabled"] if locked else C["accent"]
        def _do():
            for b in (self.btn_all, self.btn_text, self.btn_img):
                b.configure(state=state, fg_color=col)
            self.btn_stop.configure(
                state="normal" if locked else "disabled",
                fg_color=C["err"] if locked else C["disabled"],
            )
        self.after(0, _do)

    def _stop_generation(self):
        self._stop_event.set()


    # ── 전체 생성 ────────────────────────────────────────
    def _start_all(self):
        kw = self._check_ready()
        if not kw: return
        self._stop_event.clear()
        idx = self._selected_prompt_idx
        kw2 = (self.kw2_entry.get().strip()
               if not self._topic_enabled[idx] and (self._kw2_enabled[idx] or not self._collect_enabled[idx])
               else "")
        collect_kw2 = self.collect_kw_entry.get().strip() if self._collect_enabled[idx] else ""
        count = self._get_img_count()
        self._init_image_slots(count)
        self._reset_outputs()
        self._lock_btns(True)
        self.timer_label.configure(text="", text_color=C["accent"])
        threading.Thread(target=self._gen_all, args=(kw, kw2, collect_kw2, count), daemon=True).start()

    def _check_password(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("")
        dlg.geometry("220x110")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"220x110+{(sw-220)//2}+{(sh-110)//2}")

        _lbl(dlg, "비밀번호", font=F_SM, color=C["subtext"]).pack(pady=(14, 6))
        pw_entry = _UndoEntry(
            dlg, width=150, height=32, show="*", font=F,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], corner_radius=8,
        )
        pw_entry.pack()
        pw_entry.focus()

        def _confirm(event=None):
            if pw_entry.get() == "2424":
                dlg.destroy()
                self._open_prompt_dialog()
            else:
                pw_entry.delete(0, "end")
                pw_entry.configure(border_color=C["err"])

        pw_entry.bind("<Return>", _confirm)
        _btn(dlg, "확인", _confirm, w=80, h=28).pack(pady=(8, 0))

    def _on_prompt_select(self, choice: str):
        if choice == "시크릿":
            prev = self._prompt_names[self._selected_prompt_idx] \
                if self._selected_prompt_idx < len(self._prompt_names) else self._prompt_names[0]
            self.prompt_selector.set(prev)
            self._ask_secret_password(choice)
            return
        old_idx = self._selected_prompt_idx
        try:
            self._kw_per_option[old_idx] = self.keyword_entry.get().strip()
            self._kw2_per_option[old_idx] = (self.kw2_entry._entry.get() if hasattr(self.kw2_entry, '_entry') else self.kw2_entry.get()).strip()
            self._collect_kw_per_option[old_idx] = self.collect_kw_entry.get().strip()
            self._img_count_by_source[self._img_source] = self.img_count_entry.get().strip() or "3"
            self._img_source_per_option[old_idx] = self._img_source
        except Exception:
            pass
        try:
            self._selected_prompt_idx = self._prompt_names.index(choice)
        except ValueError:
            pass
        new_idx = self._selected_prompt_idx
        self.keyword_entry.delete(0, "end")
        self.keyword_entry.insert(0, self._kw_per_option[new_idx])
        try:
            self.kw2_entry.configure(state="normal")
            self.kw2_entry.delete(0, "end")
            self.kw2_entry.insert(0, self._kw2_per_option[new_idx])
        except Exception:
            pass
        try:
            self.collect_kw_entry.delete(0, "end")
            self.collect_kw_entry.insert(0, self._collect_kw_per_option[new_idx])
        except Exception:
            pass
        self._img_source = self._img_source_per_option[new_idx]
        self.img_src_menu.set(self._img_source)
        _cnt = self._img_count_by_source.get(self._img_source, "3")
        self.img_count_entry.delete(0, "end")
        self.img_count_entry.insert(0, _cnt)
        self._update_kw2_state()
        self._update_topic_state()

    def _ask_secret_password(self, target_choice: str):
        dlg = ctk.CTkToplevel(self)
        dlg.title("")
        dlg.geometry("220x110")
        dlg.resizable(False, False)
        dlg.grab_set(); dlg.lift(); dlg.focus_force()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"220x110+{(sw-220)//2}+{(sh-110)//2}")
        _lbl(dlg, "비밀번호", font=F_SM, color=C["subtext"]).pack(pady=(14, 6))
        pw_entry = _UndoEntry(
            dlg, width=150, height=32, show="*", font=F,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], corner_radius=8,
        )
        pw_entry.pack(); pw_entry.focus()
        def _confirm(event=None):
            if pw_entry.get() == "2424":
                dlg.destroy()
                old_idx = self._selected_prompt_idx
                try:
                    self._kw_per_option[old_idx] = self.keyword_entry.get().strip()
                    self._kw2_per_option[old_idx] = (self.kw2_entry._entry.get() if hasattr(self.kw2_entry, '_entry') else self.kw2_entry.get()).strip()
                    self._collect_kw_per_option[old_idx] = self.collect_kw_entry.get().strip()
                    self._img_count_by_source[self._img_source] = self.img_count_entry.get().strip() or "3"
                    self._img_source_per_option[old_idx] = self._img_source
                except Exception:
                    pass
                try:
                    self._selected_prompt_idx = self._prompt_names.index(target_choice)
                except ValueError:
                    pass
                new_idx = self._selected_prompt_idx
                self.keyword_entry.delete(0, "end")
                self.keyword_entry.insert(0, self._kw_per_option[new_idx])
                try:
                    self.kw2_entry.configure(state="normal")
                    self.kw2_entry.delete(0, "end")
                    self.kw2_entry.insert(0, self._kw2_per_option[new_idx])
                except Exception:
                    pass
                try:
                    self.collect_kw_entry.delete(0, "end")
                    self.collect_kw_entry.insert(0, self._collect_kw_per_option[new_idx])
                except Exception:
                    pass
                self._img_source = self._img_source_per_option[new_idx]
                self.img_src_menu.set(self._img_source)
                _cnt2 = self._img_count_by_source.get(self._img_source, "3")
                self.img_count_entry.delete(0, "end")
                self.img_count_entry.insert(0, _cnt2)
                self.prompt_selector.set(target_choice)
                self._update_kw2_state()
                self._update_topic_state()
            else:
                pw_entry.delete(0, "end")
                pw_entry.configure(border_color=C["err"])
        pw_entry.bind("<Return>", _confirm)
        _btn(dlg, "확인", _confirm, w=80, h=28).pack(pady=(8, 0))

    def _pick_variation_output_dir(self):
        folder = filedialog.askdirectory(title="변환 결과 저장 위치 선택")
        if not folder:
            return
        self._variation_output_dir = folder
        self._save_prefs()
        self.var_out_lbl.configure(text=folder, text_color=C["ok"])

    def _pick_local_img_folder(self):
        folder = filedialog.askdirectory(title="이미지 폴더 선택")
        if not folder:
            return
        self._local_img_folder = folder
        self._save_prefs()
        name = Path(folder).name
        self.local_img_lbl.configure(text=f"📂 {name}", text_color=C["ok"])
        self.local_var_btn.configure(state="normal", fg_color=C["accent"])

    def _is_mostly_solid(self, img: Image.Image, threshold: float = 0.60) -> bool:
        """이미지의 60% 이상이 단일 색상 블록이면 True (패딩된 불량 이미지 감지)."""
        try:
            import numpy as np
            small = np.array(img.resize((80, 80)), dtype=np.uint8)
            q = (small // 32).reshape(-1, 3)
            _, counts = np.unique(q, axis=0, return_counts=True)
            return float(counts.max()) / len(q) > threshold
        except Exception:
            return False

    @staticmethod
    def _has_excessive_red(img: Image.Image, threshold: float = 0.10) -> bool:
        """선명한 빨강 픽셀이 10% 초과이면 True (loremflickr 오류 이미지 감지)."""
        try:
            small = img.convert("RGB").resize((80, 80))
            pixels = small.getdata()
            red = sum(1 for r, g, b in pixels if r > 180 and g < 80 and b < 80)
            return red / len(pixels) > threshold
        except Exception:
            return False

    def _apply_variation(self, img: Image.Image, vs=None, wm_text=None) -> Image.Image:
        from PIL import ImageEnhance
        try:
            import numpy as np
        except Exception:
            np = None
        if vs is None:
            vs = self._var_settings
            # 가로 최대 크기 리사이즈는 이미지 선택 모드에서만
            mw = self._max_width
            if mw > 0 and img.width > img.height and img.width > mw:
                new_h = int(img.height * mw / img.width)
                img = img.resize((mw, new_h), Image.LANCZOS)

        def _rand_signed(lo, hi):
            """lo~hi 범위 절댓값, 방향 랜덤"""
            if hi <= 0:
                return 0.0
            lo = min(lo, hi)
            v = random.uniform(lo, hi)
            return v if random.random() < 0.5 else -v

        img = img.copy().convert("RGB")
        w, h = img.size

        # 배너형 이미지 감지 (로컬 모드에서만)
        is_banner = False
        if vs is self._var_settings and np is not None:
            arr_check = np.array(img, dtype=np.uint8)
            ph, pw = arr_check.shape[:2]
            white_mask = (arr_check[..., 0] > 210) & (arr_check[..., 1] > 210) & (arr_check[..., 2] > 210)
            if white_mask.mean() > 0.25:
                is_banner = True
            if not is_banner:
                small = arr_check[::8, ::8].reshape(-1, 3)
                q = (small // 64).astype(np.uint8)
                _, counts = np.unique(q, axis=0, return_counts=True)
                if counts.max() / len(small) > 0.18:
                    is_banner = True
            if not is_banner:
                px_lum = arr_check.astype(np.float32).mean(axis=2)
                bright_frac = float((px_lum > 200).mean())
                dark_frac   = float((px_lum < 60).mean())
                mean_brightness = float(arr_check.astype(np.float32).mean())
                if mean_brightness > 200 or (bright_frac > 0.50 and dark_frac > 0.02):
                    is_banner = True

        c_lo = vs["crop_pct_min"] / 100.0
        c_hi = vs["crop_pct_max"] / 100.0
        if c_hi > 0 and not is_banner:
            cx = int(w * random.uniform(c_lo, c_hi))
            cy = int(h * random.uniform(c_lo, c_hi))
            left   = random.randint(0, max(0, cx))
            top    = random.randint(0, max(0, cy))
            right  = w - random.randint(0, max(0, cx))
            bottom = h - random.randint(0, max(0, cy))
            img = img.crop((left, top, right, bottom)).resize((w, h), Image.LANCZOS)

        # 가로세로 비율 변형 (양수=가로 늘림, 음수=세로 늘림)
        ar = random.uniform(vs["aspect_ratio_min"] / 100.0, vs["aspect_ratio_max"] / 100.0)
        if abs(ar) > 0.0005:
            if ar > 0:
                new_w = max(1, int(w * (1 + ar)))
                img = img.resize((new_w, h), Image.LANCZOS).resize((w, h), Image.LANCZOS)
            else:
                new_h = max(1, int(h * (1 - ar)))
                img = img.resize((w, new_h), Image.LANCZOS).resize((w, h), Image.LANCZOS)

        # 밝기/대비/채도 — 슬라이더 범위가 음수~양수이므로 random.uniform 직접 사용
        br = random.uniform(vs["brightness_pct_min"] / 100.0, vs["brightness_pct_max"] / 100.0)
        if abs(br) > 0.0005 and not is_banner:
            img = ImageEnhance.Brightness(img).enhance(max(0.01, 1 + br))

        cr = random.uniform(vs["contrast_pct_min"] / 100.0, vs["contrast_pct_max"] / 100.0)
        if abs(cr) > 0.0005:
            img = ImageEnhance.Contrast(img).enhance(max(0.01, 1 + cr))

        colr = random.uniform(vs["color_pct_min"] / 100.0, vs["color_pct_max"] / 100.0)
        if abs(colr) > 0.0005:
            img = ImageEnhance.Color(img).enhance(max(0.0, 1 + colr))

        rot = random.uniform(vs["rotation_deg_min"], vs["rotation_deg_max"])
        if random.random() < 0.5:
            rot = -rot
        if abs(rot) > 0.001 and not is_banner:
            ow, oh = img.width, img.height
            img = img.rotate(rot, resample=Image.BILINEAR, expand=False)
            # 검은 모서리 제거: 회전 각도에 비례해 크롭 후 원본 크기로 복원
            pad = int(max(ow, oh) * abs(math.sin(math.radians(rot))) / 2) + 2
            if 0 < pad < min(ow, oh) // 4:
                img = img.crop((pad, pad, ow - pad, oh - pad))
                img = img.resize((ow, oh), Image.LANCZOS)

        nz_lo = int(vs["noise_min"])
        nz_hi = int(vs["noise_max"])
        if nz_hi > 0 and np is not None:
            arr  = np.array(img, dtype=np.int16)
            mag  = np.random.randint(nz_lo, nz_hi + 1, arr.shape).astype(np.int16)
            sign = np.random.choice([-1, 1], arr.shape).astype(np.int16)
            img  = Image.fromarray(np.clip(arr + mag * sign, 0, 255).astype(np.uint8))

        # 색조 이동 — 슬라이더 음수~양수 (음수=반대 방향 회전)
        deg = random.uniform(vs["hue_shift_min"], vs["hue_shift_max"])
        if abs(deg) > 0.001:
            rad = math.radians(deg)
            if np is not None:
                c, s = math.cos(rad), math.sin(rad)
                k, sq = 1.0 / 3.0, math.sqrt(1.0 / 3.0)
                M = np.array([
                    [c+(1-c)*k,    (1-c)*k-sq*s, (1-c)*k+sq*s],
                    [(1-c)*k+sq*s,  c+(1-c)*k,   (1-c)*k-sq*s],
                    [(1-c)*k-sq*s, (1-c)*k+sq*s,  c+(1-c)*k  ],
                ], dtype=np.float32)
                f = np.array(img, dtype=np.float32) / 255.0
                img = Image.fromarray((np.clip(f @ M.T, 0, 1) * 255).astype(np.uint8))

        # 선명도 — 양수=샤픈(UnsharpMask), 음수=블러
        sp = random.uniform(vs["sharpness_min"] / 100.0, vs["sharpness_max"] / 100.0)
        if sp > 0.0005:
            from PIL import ImageFilter
            pct = int(sp * 300)
            img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=pct, threshold=2))
        elif sp < -0.0005:
            img = ImageEnhance.Sharpness(img).enhance(max(0.0, 1.0 + sp))

        # 색온도 — 슬라이더 음수~양수 (양수=따뜻, 음수=차가움) / 배너 이미지 제외
        tmp = random.uniform(vs["temperature_min"], vs["temperature_max"])
        if abs(tmp) > 0.001 and not is_banner and np is not None:
            arr = np.array(img, dtype=np.int16)
            arr[..., 0] = np.clip(arr[..., 0] + tmp, 0, 255)
            arr[..., 2] = np.clip(arr[..., 2] - tmp, 0, 255)
            img = Image.fromarray(arr.astype(np.uint8))

        # 감마 보정 — 슬라이더 음수~양수 (양수=밝아짐, 음수=어두워짐)
        gam = random.uniform(vs["gamma_min"] / 100.0, vs["gamma_max"] / 100.0)
        if abs(gam) > 0.0005 and np is not None:
            gamma = max(0.01, 1.0 - gam)
            lut = (np.arange(256, dtype=np.float32) / 255.0) ** gamma * 255.0
            lut = np.clip(lut, 0, 255).astype(np.uint8)
            img = Image.fromarray(lut[np.array(img, dtype=np.uint8)])

        # JPEG 재압축 — 다른 품질로 재인코딩해 DCT 계수 변화
        jq_lo = vs["jpeg_quality_min"]
        jq_hi = vs["jpeg_quality_max"]
        if jq_hi > 0:
            import io as _io
            reduction = random.uniform(jq_lo, jq_hi)
            quality = max(1, int(100 - reduction))
            buf = _io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=quality)
            buf.seek(0)
            img = Image.open(buf).copy()

        # 미세 이동 (Translation) — 전체 이미지를 ±px 이동 후 리사이즈
        tr_lo = vs["translate_min"]
        tr_hi = vs["translate_max"]
        if tr_hi > 0:
            dx = int(random.uniform(tr_lo, tr_hi)) * (1 if random.random() < 0.5 else -1)
            dy = int(random.uniform(tr_lo, tr_hi)) * (1 if random.random() < 0.5 else -1)
            if dx != 0 or dy != 0:
                left   = max(0, dx);  top    = max(0, dy)
                right  = w - max(0, -dx); bottom = h - max(0, -dy)
                img = img.crop((left, top, right, bottom)).resize((w, h), Image.LANCZOS)

        # RGB 채널 개별 오프셋 — R/G/B 각 채널을 독립적으로 조정 / 배너 이미지 제외
        rgb_lo = vs["rgb_offset_min"]
        rgb_hi = vs["rgb_offset_max"]
        if (rgb_lo != 0.0 or rgb_hi != 0.0) and not is_banner and np is not None:
            arr = np.array(img, dtype=np.int16)
            for ch in range(3):
                offset = random.uniform(rgb_lo, rgb_hi)
                arr[..., ch] = np.clip(arr[..., ch] + offset, 0, 255)
            img = Image.fromarray(arr.astype(np.uint8))

        # 좌우반전 확률
        _hflip_prob = vs.get("hflip_prob", 0.0) / 100.0
        if _hflip_prob > 0.0 and random.random() < _hflip_prob:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)

        # 보이지 않는 반복 워터마크
        wm_lo = vs["watermark_min"] / 100.0
        wm_hi = vs["watermark_max"] / 100.0
        _wm_src = wm_text or (Path(self._local_img_folder).name if self._local_img_folder else "")
        if wm_hi > 0 and _wm_src:
            wm_opacity = random.uniform(wm_lo, wm_hi)
            if wm_opacity > 0:
                img = self._apply_watermark(img, _wm_src, wm_opacity)

        return img

    @staticmethod
    def _apply_watermark(img: Image.Image, text: str, opacity: float) -> Image.Image:
        from PIL import ImageDraw, ImageFont
        w, h = img.size
        diag = int((w ** 2 + h ** 2) ** 0.5) + 2
        overlay = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font_size = max(16, min(w, h) // 20)
        font = ImageFont.load_default()
        for path in ("C:/Windows/Fonts/malgunbd.ttf",
                     "C:/Windows/Fonts/arialbd.ttf",
                     "C:/Windows/Fonts/calibrib.ttf",
                     "C:/Windows/Fonts/malgun.ttf",
                     "C:/Windows/Fonts/arial.ttf"):
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        alpha = max(1, int(opacity * 255))
        step_x, step_y = tw + 200, th + 160
        for y in range(0, diag, step_y):
            for x in range(0, diag, step_x):
                draw.text((x, y), text, fill=(180, 180, 180, alpha), font=font)
        overlay = overlay.rotate(30, expand=False)
        ox, oy = (diag - w) // 2, (diag - h) // 2
        overlay = overlay.crop((ox, oy, ox + w, oy + h))
        base = img.convert("RGBA")
        return Image.alpha_composite(base, overlay).convert("RGB")

    def _run_local_variation(self):
        folder = Path(self._local_img_folder)
        if not folder.exists():
            self._set_status("⚠️ 선택한 폴더가 없습니다. 폴더를 다시 선택해 주세요.", color=C["err"])
            self._local_img_folder = ""
            self.local_img_lbl.configure(text="폴더를 선택하면 원본 이미지를 매번 다르게 변형합니다", text_color=C["subtext"])
            self.local_var_btn.configure(state="disabled", fg_color=C["disabled"])
            return
        exts  = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
        try:
            files = sorted([f for f in folder.rglob("*")
                            if f.is_file() and f.suffix.lower() in exts])
        except Exception as e:
            self._set_status(f"⚠️ 폴더 읽기 실패: {e}", color=C["err"])
            return
        if not files:
            self._set_status("⚠️ 폴더에 이미지가 없습니다.", color=C["err"])
            return
        self._stop_event.clear()
        self._lock_btns(True)
        # 글만 버튼은 변형 중에도 사용 가능
        self.after(0, lambda: self.btn_text.configure(state="normal", fg_color=C["accent"]))
        self.local_var_btn.configure(state="disabled", fg_color=C["disabled"])
        count = len(files)
        self._img_refs = [None] * count
        self._img_pil  = [None] * count
        self.after(0, lambda: self._init_image_slots(count))
        threading.Thread(target=self._do_local_variation, args=(files,), daemon=True).start()

    def _do_local_variation(self, files):
        import time as _time
        import shutil as _shutil
        count = len(files)
        src_root = Path(self._local_img_folder)
        src_name = src_root.name
        folder_name = f"{_time.strftime('%m%d%H%M%S')}_{src_name}"
        # 지정된 출력 폴더 우선, 없으면 Desktop → Documents → exe 순으로 시도
        base_candidates = (
            [Path(self._variation_output_dir)] if self._variation_output_dir
            else [Path.home() / "Desktop",
                  Path.home() / "OneDrive" / "Desktop",
                  Path.home() / "Documents",
                  _BASE_DIR]
        )
        for base_dir in base_candidates:
            try:
                out_dir = base_dir / folder_name
                out_dir.mkdir(parents=True, exist_ok=True)
                break
            except Exception:
                continue
        else:
            self._set_status("⚠️ 출력 폴더를 만들 수 없습니다.", color=C["err"])
            self._lock_btns(False)
            return
        try:
            for i, src in enumerate(files):
                if self._stop_event.is_set():
                    self._set_img_status("중단됨", 0, C["err"])
                    break
                self._set_img_status(f"변형 중... {i+1}/{count}", (i / count))
                # 하위폴더 구조 유지
                rel = src.relative_to(src_root)
                out_path = out_dir / rel
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if src.suffix.lower() == ".gif":
                    # GIF는 변형 없이 그대로 복사
                    _shutil.copy2(src, out_path)
                    try:
                        from PIL import ImageOps as _Iops
                        _raw = Image.open(src)
                        pil_img = _Iops.exif_transpose(_raw).convert("RGB")
                    except Exception:
                        pil_img = image_generator.create_placeholder_image()
                else:
                    try:
                        from PIL import ImageOps as _Iops
                        _raw = Image.open(src)
                        pil_img = self._apply_variation(_Iops.exif_transpose(_raw).convert("RGB"))
                    except Exception as e:
                        import traceback
                        err_txt = traceback.format_exc()
                        try:
                            log_path = Path.home() / "Desktop" / "blogbot_img_error.txt"
                            log_path.write_text(
                                f"파일: {src}\n에러:\n{err_txt}", encoding="utf-8")
                        except Exception:
                            pass
                        self._set_img_status(f"이미지 {i+1} 실패: {str(e)[:60]}", i/count, C["err"])
                        pil_img = image_generator.create_placeholder_image()
                    pil_img.save(out_path)
                self._img_pil[i] = pil_img
                # 표시용 썸네일
                thumb = pil_img.copy()
                sz = getattr(self, "_thumb_sz", 88)
                thumb.thumbnail((sz, sz), Image.LANCZOS)
                from PIL import ImageTk as _ITk
                thumb_r = thumb.resize((sz, sz), Image.LANCZOS)
                tk_img = _ITk.PhotoImage(thumb_r)
                self._img_refs[i] = tk_img
                self.after(0, lambda idx=i, ti=tk_img: self.img_labels[idx].configure(image=ti))
                self._set_img_status(f"변형 완료 {i+1}/{count}", ((i+1) / count))
            if not self._stop_event.is_set():
                self._last_out_dir = out_dir
                self._set_status(f"✅  {count}장 변형 완료! → {out_dir.name}", color=C["ok"])
                self._set_img_status("완료", 1.0, C["ok"])
                self.after(0, lambda: self._img_hscroll.enable(True))
        finally:
            self._lock_btns(False)
            self.after(0, lambda: self.local_var_btn.configure(
                state="normal", fg_color=C["accent"]))

    def _rebuild_selector(self):
        """활성화된 옵션만 드롭다운에 표시. 게스트 모드: 게스트 허용 옵션만, 비게스트: 게스트 전용 옵션 제외."""
        n = len(self._prompts)
        if self._is_guest:
            enabled_names = [self._prompt_names[i] for i in range(n)
                             if self._option_enabled[i] and self._guest_prompt_enabled[i]]
        else:
            enabled_names = [self._prompt_names[i] for i in range(n)
                             if self._option_enabled[i] and not self._guest_prompt_enabled[i]]
        if not enabled_names:
            if not self._is_guest:
                for i in range(n):
                    if not self._guest_prompt_enabled[i]:
                        self._option_enabled[i] = True
                        enabled_names = [self._prompt_names[i]]
                        break
                if not enabled_names and n > 0:
                    self._option_enabled[0] = True
                    enabled_names = [self._prompt_names[0]]
        self.prompt_selector.configure(values=enabled_names if enabled_names else ["—"])
        current = self._prompt_names[self._selected_prompt_idx]
        if current not in enabled_names:
            first = enabled_names[0]
            self._selected_prompt_idx = self._prompt_names.index(first)
            self.prompt_selector.set(first)
        else:
            self.prompt_selector.set(current)

    def _on_kw2_toggle(self):
        idx = self._selected_prompt_idx
        self._kw2_enabled[idx] = self.kw2_var.get()
        self._update_kw2_state()
        self._save_prefs()

    def _update_kw2_state(self):
        idx = self._selected_prompt_idx
        enabled = self._kw2_enabled[idx]
        collect_on = self._collect_enabled[idx]
        topic_on = self._topic_enabled[idx]
        self.kw2_var.set(enabled)

        try:
            saved = self.kw2_entry._entry.get()
        except Exception:
            saved = self.kw2_entry.get()

        if topic_on:
            # 육성 주제 사용 ON: 체크박스·입력칸 모두 숨김
            self.kw_row1_lbl.pack_forget()
            self.kw2_lbl.pack_forget()
            self.kw2_topic_lbl.pack_forget()
            self.kw2_entry.pack_forget()
            self.collect_row2.pack_forget()
            return

        # 입력칸 표시 (위치 고정)
        self.kw2_entry.pack_forget()
        self.kw2_entry.pack(side="left", padx=(0, 6), before=self.btn_text)

        if collect_on:
            # 인기글 수집 ON: row1에 키워드·업체 레이블, 두 번째 줄에 원제목 입력
            self.kw_row1_lbl.pack_forget()
            self.kw_row1_lbl.pack(side="left", padx=(0, 4), before=self._kw_frame)
            self.kw2_lbl.pack_forget()
            self.kw2_lbl.pack(side="left", padx=(0, 6), before=self.kw2_entry)
            self.kw2_lbl.configure(text="업체명")
            # collect_row2 표시 (before=self.row2로 올바른 위치에 삽입)
            self.collect_row2.pack_forget()
            self.collect_row2.pack(fill="x", pady=(2, 0), before=self.row2)
            if enabled:
                self.kw2_entry.configure(
                    state="normal",
                    fg_color=C["input_bg"],
                    border_color=C["border"],
                    text_color=C["text"],
                    placeholder_text="업체명 입력",
                    placeholder_text_color=C["subtext"],
                )
            else:
                self.kw2_entry.configure(
                    state="disabled",
                    fg_color="#B8C0D0",
                    border_color="#9AA5BB",
                    text_color="#70788A",
                    placeholder_text="업체명 입력",
                    placeholder_text_color="#70788A",
                )
        else:
            # 인기글 수집 OFF
            self.collect_row2.pack_forget()
            if enabled:
                # 주제 사용 ON: 키워드·주제 레이블 표시 (체크박스 숨김)
                self.kw_row1_lbl.pack_forget()
                self.kw_row1_lbl.pack(side="left", padx=(0, 4), before=self._kw_frame)
                self.kw2_lbl.pack_forget()
                self.kw2_topic_lbl.pack_forget()
                self.kw2_topic_lbl.pack(side="left", padx=(0, 6), before=self.kw2_entry)
                self.kw2_entry.configure(
                    state="normal",
                    fg_color=C["input_bg"],
                    border_color=C["border"],
                    text_color=C["text"],
                    placeholder_text="주제 입력",
                    placeholder_text_color=C["subtext"],
                )
            else:
                # 주제 사용 OFF: 레이블 숨김
                self.kw_row1_lbl.pack_forget()
                self.kw2_lbl.pack_forget()
                self.kw2_topic_lbl.pack_forget()
                self.kw2_entry.configure(
                    state="disabled",
                    fg_color="#B8C0D0",
                    border_color="#9AA5BB",
                    text_color="#70788A",
                    placeholder_text="주제 입력",
                    placeholder_text_color="#70788A",
                )

        self.kw2_entry.delete(0, "end")
        if saved:
            self.kw2_entry.insert(0, saved)

    def _is_secret_mode(self):
        idx = self._selected_prompt_idx
        if idx < len(self._prompt_names):
            return self._prompt_names[idx] == "시크릿"
        return False

    def _update_topic_state(self):
        idx = self._selected_prompt_idx
        if self._topic_enabled[idx]:
            self.keyword_entry.pack_forget()
            self.keyword_textbox.pack_forget()
            keys = [k for k, v in self._topic_lists.items() if len(v) > 0]
            if not keys:
                keys = ["(저장된 목록 없음)"]
            cur = self.topic_dropdown.get()
            if self._topic_rows:
                valid_set = set(keys)
                groups = [[k for k in row if k in valid_set] for row in self._topic_rows]
            else:
                groups = None
            self.topic_dropdown.configure(values=keys, groups=groups)
            if cur not in keys:
                self.topic_dropdown.set(keys[0])
            self.topic_dropdown.pack(fill="x", expand=True)
        elif self._is_secret_mode():
            self.topic_dropdown.pack_forget()
            self.keyword_entry.pack_forget()
            self.keyword_textbox.pack(fill="x", expand=True)
        else:
            self.topic_dropdown.pack_forget()
            self.keyword_textbox.pack_forget()
            self.keyword_entry.pack(fill="x", expand=True)

    # ── 업데이트 ──────────────────────────────────────────
    @staticmethod
    def _parse_ver(v):
        try:
            return tuple(int(x) for x in v.lstrip("v").split("."))
        except Exception:
            return (0, 0, 0)

    def _check_update_log(self):
        import glob, time
        try:
            for log in glob.glob(str(Path(os.environ.get("TEMP", "")) / "bbb_upd_*" / "update.log")):
                p = Path(log)
                if time.time() - p.stat().st_mtime < 300:
                    content = p.read_text(errors="replace")
                    print(f"[UPDATE LOG]\n{content}")
                    try: p.unlink()
                    except Exception: pass
        except Exception:
            pass

    def _check_for_update(self):
        import urllib.request
        try:
            req = urllib.request.Request(
                _DEFAULT_UPDATE_CHECK_URL,
                headers={"User-Agent": "BamhobakBlogBot"},
            )
            with _urlopen_ssl(req, timeout=15) as r:
                gist = json.loads(r.read().decode())
            raw = gist.get("files", {}).get("version.json", {}).get("content", "{}")
            data = json.loads(raw)
            latest = data.get("version", "")
            if latest and self._parse_ver(latest) > self._parse_ver(APP_VERSION):
                url   = data.get("url", "")
                notes = data.get("notes", "")
                self._update_info = {"version": latest, "url": url, "notes": notes}
                self.after(0, self._show_update_notification)
        except Exception:
            pass

    def _show_update_notification(self):
        try:
            self.after(0, self._show_update_dialog)
        except Exception:
            pass

    def _show_update_dialog(self):
        info = getattr(self, "_update_info", {})
        dlg = ctk.CTkToplevel(self)
        dlg.wm_attributes("-alpha", 0)
        dlg.title("업데이트")
        dlg.geometry("340x200")
        dlg.resizable(False, False)
        dlg.grab_set()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"340x200+{(sw-340)//2}+{(sh-200)//2}")

        _lbl(dlg, "업데이트가 있습니다.", font=F_B, color=C["text"]).pack(pady=(30, 6))
        _lbl(dlg, "업데이트를 진행해주세요.", font=F_SM, color=C["subtext"]).pack(pady=(0, 20))

        if not getattr(sys, "frozen", False):
            _lbl(dlg, "⚠️ 개발 환경에서는 업데이트를 지원하지 않습니다.",
                 font=F_SM, color=C["err"]).pack(pady=4)
            _btn(dlg, "확인", dlg.destroy).pack()
            dlg.after(50, lambda: dlg.wm_attributes("-alpha", 1))
            return

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack()

        def _start():
            dlg.destroy()
            self._do_update(info.get("url", ""), info.get("version", ""))

        _btn(btn_row, "지금 업데이트", _start, w=130, h=34).pack(side="left", padx=(0, 10))
        _btn(btn_row, "나중에", dlg.destroy, w=80, h=34).pack(side="left")
        dlg.after(50, lambda: dlg.wm_attributes("-alpha", 1))

    def _do_update(self, url, new_version):
        import tempfile, zipfile, urllib.request

        dlg = ctk.CTkToplevel(self)
        dlg.wm_attributes("-alpha", 0)
        dlg.title("업데이트 중...")
        dlg.geometry("360x140")
        dlg.resizable(False, False)
        dlg.grab_set()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"360x140+{(sw-360)//2}+{(sh-140)//2}")

        status_lbl = _lbl(dlg, "준비 중...", font=F_SM, color=C["subtext"])
        status_lbl.pack(pady=(22, 8))
        prog = ctk.CTkProgressBar(dlg, width=320)
        prog.pack(padx=20)
        prog.set(0)
        dlg.after(50, lambda: dlg.wm_attributes("-alpha", 1))

        def _worker():
            try:
                tmp_dir   = Path(tempfile.mkdtemp(prefix="bbb_upd_"))
                zip_path  = tmp_dir / f"update_{new_version}.zip"
                extract_dir = tmp_dir / "new"
                extract_dir.mkdir()

                self.after(0, lambda: status_lbl.configure(text="다운로드 중..."))

                req = urllib.request.Request(url, headers={"User-Agent": "BamhobakBlogBot"})
                with _urlopen_ssl(req, timeout=120) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    with open(zip_path, "wb") as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                self.after(0, lambda p=min(0.8, downloaded/total): prog.set(p))

                self.after(0, lambda: (status_lbl.configure(text="압축 해제 중..."), prog.set(0.85)))
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)

                self.after(0, lambda: (status_lbl.configure(text="적용 중... 곧 재시작됩니다"), prog.set(1.0)))

                current_dir = _BASE_DIR
                log_path = tmp_dir / "update.log"
                src = str(extract_dir).replace("'", "''")
                dst = str(current_dir).replace("'", "''")
                log = str(log_path).replace("'", "''")
                exe = str(current_dir / "BamhobakBlogBot.exe").replace("'", "''")
                pid = os.getpid()

                ps1 = f"""$appPid = {pid}
try {{ Wait-Process -Id $appPid -Timeout 60 -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Seconds 2
$src = '{src}'
$dst = '{dst}'
$log = '{log}'
'START' | Out-File $log -Encoding UTF8
try {{
    $srcLen = $src.TrimEnd('\\').Length + 1
    Get-ChildItem -LiteralPath $src -Recurse -File | Where-Object {{ $_.Name -ne '.prefs.json' }} | ForEach-Object {{
        $rel    = $_.FullName.Substring($srcLen)
        $target = Join-Path $dst $rel
        $dir    = Split-Path $target -Parent
        if (-not (Test-Path -LiteralPath $dir)) {{ New-Item -ItemType Directory -Path $dir -Force | Out-Null }}
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }}
    'COPY_DONE' | Out-File $log -Append -Encoding UTF8
    if (Test-Path -LiteralPath '{exe}') {{
        'LAUNCH' | Out-File $log -Append -Encoding UTF8
        Start-Process -FilePath '{exe}'
    }} else {{
        'EXE_NOT_FOUND' | Out-File $log -Append -Encoding UTF8
    }}
}} catch {{
    "ERROR: $_" | Out-File $log -Append -Encoding UTF8
}}
Start-Sleep -Seconds 2
Remove-Item -Path (Split-Path $log) -Recurse -Force -ErrorAction SilentlyContinue
"""
                ps1_path = tmp_dir / "update_apply.ps1"
                ps1_path.write_text(ps1, encoding="utf-8-sig")

                self.after(1000, lambda: self._launch_updater(ps1_path, log_path))
            except Exception as e:
                self.after(0, lambda: status_lbl.configure(
                    text=f"오류: {e}", text_color=C["err"]))

        threading.Thread(target=_worker, daemon=True).start()

    def _launch_updater(self, ps1_path, log_path=None):
        import ctypes
        try:
            args = f'-NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps1_path}"'
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "open", "powershell", args, None, 0
            )
            if ret <= 32:
                raise RuntimeError(f"ShellExecute 실패: {ret}")
            self.quit()
            sys.exit(0)
        except Exception as e:
            # 실패 시 업데이트 다이얼로그에 오류 표시
            try:
                for w in self.winfo_children():
                    try:
                        if isinstance(w, ctk.CTkToplevel) and "업데이트" in str(w.title()):
                            for c in w.winfo_children():
                                try: c.configure(text=f"오류: {e}", text_color=C["err"])
                                except Exception: pass
                    except Exception: pass
            except Exception: pass

    def _open_prompt_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.wm_attributes("-alpha", 0)
        dlg.title("관리자 설정")
        dlg.geometry("940x760")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        dlg.geometry(f"940x760+{(sw-940)//2}+{(sh-760)//2}")

        working         = list(self._prompts)
        working2        = list(self._prompts2)
        working_kw2     = list(self._kw2_enabled)
        working_topic   = list(self._topic_enabled)
        working_collect = list(self._collect_enabled)
        working_enabled = list(self._option_enabled)
        working_names   = list(self._prompt_names)
        working_guest   = list(self._guest_prompt_enabled)
        cur_idx         = [self._selected_prompt_idx]
        w_var           = {k: v for k, v in self._var_settings.items()}
        w_var_picsum    = {k: v for k, v in self._var_settings_picsum.items()}
        w_var_flickr    = {k: v for k, v in self._var_settings_flickr.items()}

        # tab2 lazy build 전에도 _save()에서 참조하므로 미리 초기화
        mw_entry = None
        _ps_w_entry = None; _ps_h_entry = None
        _fl_w_entry = None; _fl_h_entry = None; _fl_kw_entry = None

        # tab5 lazy build 전에도 _save()에서 참조하므로 미리 초기화
        c5_opt_count_var      = tk.StringVar(value=str(self._collect_count))
        c5_opt_skip_var       = tk.StringVar(value=str(self._collect_skip))
        c5_opt_chunk_var      = tk.StringVar(value=self._collect_chunk)
        c5_opt_maxch_var      = tk.StringVar(value=str(self._collect_maxchars))
        c5_opt_header_var     = tk.StringVar(value=self._collect_header)
        c5_opt_delimiters_var = tk.StringVar(value=self._collect_delimiters)
        c5_opt_ending_var     = tk.StringVar(value=self._collect_ending)
        c5_opt_bottom_var     = tk.StringVar(value=self._collect_bottom)

        # ── 탭 버튼 행 ────────────────────────────────────
        tab_btn_row = ctk.CTkFrame(dlg, fg_color=C["accent_bg"], corner_radius=0, height=36)
        tab_btn_row.pack(fill="x", padx=0, pady=0)
        tab_btn_row.pack_propagate(False)

        tab1_content = ctk.CTkFrame(dlg, fg_color="transparent")
        tab2_content = ctk.CTkFrame(dlg, fg_color="transparent")
        tab3_content = ctk.CTkFrame(dlg, fg_color="transparent")
        tab4_content = ctk.CTkFrame(dlg, fg_color="transparent")
        tab5_content = ctk.CTkFrame(dlg, fg_color="transparent")
        tab6_content = ctk.CTkFrame(dlg, fg_color="transparent")
        active_tab = [1]
        tab1_btn_ref = [None]; tab2_btn_ref = [None]; tab3_btn_ref = [None]
        tab4_btn_ref = [None]; tab5_btn_ref = [None]; tab6_btn_ref = [None]
        btn_row_ref   = [None]
        _clear_btn_ref = [None]
        _all_tabs    = [tab1_content, tab2_content, tab3_content, tab4_content, tab5_content, tab6_content]

        def _show_tab(n):
            if n == 2 and not _t2_built[0]:   _build_tab2(); _t2_built[0] = True
            elif n == 3 and not _t3_built[0]: _build_tab3(); _t3_built[0] = True
            elif n == 4 and not _t4_built[0]: _build_tab4(); _t4_built[0] = True
            elif n == 5 and not _t5_built[0]: _build_tab5(); _t5_built[0] = True
            elif n == 6 and not _t6_built[0]: _build_t6_widgets(); _t6_built[0] = True
            active_tab[0] = n
            for tf in _all_tabs:
                tf.pack_forget()
            for tb, idx in [
                (tab1_btn_ref[0],1),(tab2_btn_ref[0],4),(tab3_btn_ref[0],2),
                (tab4_btn_ref[0],5),(tab6_btn_ref[0],6),(tab5_btn_ref[0],3),
            ]:
                if tb:
                    tb.configure(fg_color=C["accent"] if idx==n else "transparent",
                                 text_color="white" if idx==n else C["subtext"])
            _all_tabs[n-1].pack(fill="both", expand=True, padx=12, pady=(8, 0))
            if btn_row_ref[0]:
                btn_row_ref[0].pack(fill="x", padx=12, pady=(4, 4), side="bottom")
            if _clear_btn_ref[0]:
                if n == 2:
                    _clear_btn_ref[0].pack(side="right", padx=(6, 0))
                else:
                    _clear_btn_ref[0].pack_forget()

        tab1_btn = ctk.CTkButton(
            tab_btn_row, text="프롬프트 옵션",
            command=lambda: _show_tab(1),
            width=140, height=32, font=F_SMB,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="white", corner_radius=6,
        )
        tab1_btn.pack(side="left", padx=(8, 4), pady=2)
        tab1_btn_ref[0] = tab1_btn

        tab2_btn = ctk.CTkButton(
            tab_btn_row, text="주제 목록",
            command=lambda: _show_tab(4),
            width=120, height=32, font=F_SMB,
            fg_color="transparent", hover_color=C["border"],
            text_color=C["subtext"], corner_radius=6,
        )
        tab2_btn.pack(side="left", padx=(0, 4), pady=2)
        tab2_btn_ref[0] = tab2_btn

        tab3_btn = ctk.CTkButton(
            tab_btn_row, text="이미지 변형",
            command=lambda: _show_tab(2),
            width=120, height=32, font=F_SMB,
            fg_color="transparent", hover_color=C["border"],
            text_color=C["subtext"], corner_radius=6,
        )
        tab3_btn.pack(side="left", padx=(0, 4), pady=2)
        tab3_btn_ref[0] = tab3_btn

        tab4_btn = ctk.CTkButton(
            tab_btn_row, text="인기글 수집",
            command=lambda: _show_tab(5),
            width=120, height=32, font=F_SMB,
            fg_color="transparent", hover_color=C["border"],
            text_color=C["subtext"], corner_radius=6,
        )
        tab4_btn.pack(side="left", padx=(0, 4), pady=2)
        tab4_btn_ref[0] = tab4_btn

        tab6_btn = ctk.CTkButton(
            tab_btn_row, text="오토봇",
            command=lambda: _show_tab(6),
            width=100, height=32, font=F_SMB,
            fg_color="transparent", hover_color=C["border"],
            text_color=C["subtext"], corner_radius=6,
        )
        tab6_btn.pack(side="left", padx=(0, 4), pady=2)
        tab6_btn_ref[0] = tab6_btn

        tab5_btn = ctk.CTkButton(
            tab_btn_row, text="허용 MAC",
            command=lambda: _show_tab(3),
            width=100, height=32, font=F_SMB,
            fg_color="transparent", hover_color=C["border"],
            text_color=C["subtext"], corner_radius=6,
        )
        tab5_btn.pack(side="left", padx=(0, 4), pady=2)
        tab5_btn_ref[0] = tab5_btn

        # ── 하단 고정 영역 먼저 side="bottom"으로 팩 ──────
        sync_area = ctk.CTkFrame(dlg, fg_color="transparent")
        sync_area.pack(fill="x", padx=12, pady=(4, 8), side="bottom")

        ctk.CTkFrame(dlg, height=1, fg_color=C["border"]).pack(
            fill="x", padx=0, pady=0, side="bottom")

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(4, 4), side="bottom")
        btn_row_ref[0] = btn_row

        # ── 탭1 내용: 프롬프트 옵션 ──────────────────────
        left = ctk.CTkScrollableFrame(
            tab1_content, width=195, fg_color=C["accent_bg"], corner_radius=8,
            scrollbar_button_color=C["border"],
        )
        left.pack(side="left", fill="y", padx=(0, 10))

        right = ctk.CTkFrame(tab1_content, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        name_row = ctk.CTkFrame(right, fg_color="transparent")
        name_row.pack(fill="x", pady=(0, 8))
        _lbl(name_row, "이름", font=F_SMB, color=C["subtext"]).pack(side="left", padx=(0, 8))
        name_entry = _UndoEntry(
            name_row, height=30, font=F,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], corner_radius=7,
        )
        name_entry.pack(side="left", fill="x", expand=True, padx=(0, 12))
        name_entry.insert(0, working_names[cur_idx[0]])

        enabled_var = ctk.BooleanVar(value=working_enabled[cur_idx[0]])
        ctk.CTkCheckBox(
            name_row, text="사용",
            variable=enabled_var,
            command=lambda: _refresh_enabled(),
            font=F_SMB, text_color=C["text"],
            fg_color=C["ok"], hover_color="#1E7A55",
            checkmark_color="white",
            width=20, height=20,
        ).pack(side="left")

        guest_var = ctk.BooleanVar(value=working_guest[cur_idx[0]])
        ctk.CTkCheckBox(
            name_row, text="게스트",
            variable=guest_var,
            command=lambda: _refresh_guest(),
            font=F_SMB, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_h"],
            checkmark_color="white",
            width=20, height=20,
        ).pack(side="left", padx=(10, 0))

        _lbl(right, "프롬프트 1  —  키워드 아래에 추가됩니다.",
             font=F_SMB, color=C["text"]).pack(anchor="w", pady=(0, 3))
        txt1 = tk.Text(
            right, height=8, font=F,
            bg=C["input_bg"], fg=C["text"],
            insertbackground=C["text"],
            relief="flat", bd=0, padx=6, pady=4, wrap="word",
            highlightthickness=1, highlightbackground=C["border"],
        )
        txt1.pack(fill="x", pady=(0, 8))

        topic_var   = ctk.BooleanVar(value=working_topic[cur_idx[0]])
        collect_var = ctk.BooleanVar(value=working_collect[cur_idx[0]])
        kw2_var     = ctk.BooleanVar(value=working_kw2[cur_idx[0]] if not working_collect[cur_idx[0]] else False)

        def _on_topic():
            if topic_var.get():
                collect_var.set(False); kw2_var.set(False); _refresh_txt2()
        def _on_collect():
            if collect_var.get():
                topic_var.set(False); kw2_var.set(False); _refresh_txt2()
        def _on_kw2():
            if kw2_var.get():
                topic_var.set(False); collect_var.set(False)
            _refresh_txt2()

        topic_row = ctk.CTkFrame(right, fg_color="transparent")
        topic_row.pack(fill="x", pady=(0, 6))
        ctk.CTkCheckBox(
            topic_row, text="육성 주제 사용",
            variable=topic_var, command=_on_topic,
            font=F_SMB, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_h"],
            checkmark_color="white",
            width=20, height=20,
        ).pack(side="left")
        _lbl(topic_row, "  —  키워드별 저장된 주제 목록에서 랜덤 선택.", font=F_SM, color=C["subtext"]).pack(side="left")

        collect_row = ctk.CTkFrame(right, fg_color="transparent")
        collect_row.pack(fill="x", pady=(0, 6))
        ctk.CTkCheckBox(
            collect_row, text="인기글 수집 사용",
            variable=collect_var, command=_on_collect,
            font=F_SMB, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_h"],
            checkmark_color="white",
            width=20, height=20,
        ).pack(side="left")
        _lbl(collect_row, "  —  인기글 상위글 수집 후 참조.", font=F_SM, color=C["subtext"]).pack(side="left")

        cb_row = ctk.CTkFrame(right, fg_color="transparent")
        cb_row.pack(fill="x", pady=(0, 3))
        ctk.CTkCheckBox(
            cb_row, text="주제 사용",
            variable=kw2_var, command=_on_kw2,
            font=F_SMB, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_h"],
            checkmark_color="white",
            width=20, height=20,
        ).pack(side="left")
        p2_lbl = _lbl(cb_row, "  —  주제 아래에 추가됩니다.", font=F_SM, color=C["subtext"])
        p2_lbl.pack(side="left")

        txt2 = tk.Text(
            right, height=8, font=F,
            bg=C["accent_bg"], fg=C["disabled"],
            insertbackground=C["text"],
            relief="flat", bd=0, padx=6, pady=4, wrap="word",
            highlightthickness=1, highlightbackground=C["border"],
            state="disabled",
        )
        txt2.pack(fill="x")

        def _refresh_txt2():
            if kw2_var.get():
                txt2.configure(state="normal", bg=C["input_bg"], fg=C["text"])
                p2_lbl.configure(text_color=C["subtext"])
            else:
                txt2.configure(state="disabled", bg=C["accent_bg"], fg=C["disabled"])
                p2_lbl.configure(text_color=C["disabled"])

        def _refresh_enabled():
            val = enabled_var.get()
            working_enabled[cur_idx[0]] = val
            self._option_enabled[cur_idx[0]] = val
            self._rebuild_selector()
            _update_btn_style(cur_idx[0], selected=True)
            self._save_prefs()

        def _refresh_guest():
            working_guest[cur_idx[0]] = guest_var.get()

        def _btn_label(i):
            return working_names[i]

        def _update_btn_style(i, selected=False):
            is_on = working_enabled[i]
            if selected:
                fc = C["accent"] if is_on else "#909090"
                tc = "white"
            else:
                has = working[i] or working2[i]
                fc = "transparent"
                if not is_on:
                    tc = "#AAAAAA"
                elif working_guest[i]:
                    tc = "#6FCF97"
                else:
                    tc = C["accent"] if has else C["subtext"]
            opt_btns[i].configure(text=_btn_label(i), fg_color=fc, text_color=tc)

        def _switch_to(idx, save=True):
            if save:
                working_names[cur_idx[0]]   = name_entry.get().strip() or f"옵션 {cur_idx[0]+1}"
                working[cur_idx[0]]         = txt1.get("1.0", "end").strip()
                working2[cur_idx[0]]        = txt2.get("1.0", "end").strip()
                if not working_collect[cur_idx[0]]:
                    working_kw2[cur_idx[0]] = kw2_var.get()
                working_topic[cur_idx[0]]   = topic_var.get()
                working_collect[cur_idx[0]] = collect_var.get()
                working_enabled[cur_idx[0]] = enabled_var.get()
                working_guest[cur_idx[0]]   = guest_var.get()
            _update_btn_style(cur_idx[0], selected=False)
            cur_idx[0] = idx
            _update_btn_style(idx, selected=True)
            name_entry.delete(0, "end")
            name_entry.insert(0, working_names[idx])
            enabled_var.set(working_enabled[idx])
            guest_var.set(working_guest[idx])
            kw2_var.set(working_kw2[idx] if not working_collect[idx] else False)
            topic_var.set(working_topic[idx])
            collect_var.set(working_collect[idx])
            _refresh_txt2()
            txt1.delete("1.0", "end")
            if working[idx]:
                txt1.insert("1.0", working[idx])
            txt2.configure(state="normal")
            txt2.delete("1.0", "end")
            if working2[idx]:
                txt2.insert("1.0", working2[idx])
            _refresh_txt2()

        opt_btns = []
        opt_rows = []
        opt_drag = {"idx": None, "start_y": 0}
        _add_row_ref = [None]

        def _get_opt_drop_idx(y_root):
            for i, row_w in enumerate(opt_rows):
                try:
                    if y_root < row_w.winfo_rooty() + row_w.winfo_height() // 2:
                        return i
                except Exception:
                    pass
            return len(opt_rows)

        def _on_opt_drag_start(event, idx):
            opt_drag["idx"] = idx
            opt_drag["start_y"] = event.y_root

        def _on_opt_drag_motion(event):
            if opt_drag["idx"] is None:
                return
            dst = min(_get_opt_drop_idx(event.y_root), len(opt_rows) - 1)
            for i, row_w in enumerate(opt_rows):
                try:
                    row_w.configure(fg_color=C["accent_bg"] if i == dst else "transparent")
                except Exception:
                    pass

        def _on_opt_drag_end(event):
            if opt_drag["idx"] is None:
                return
            for row_w in opt_rows:
                try:
                    row_w.configure(fg_color="transparent")
                except Exception:
                    pass
            moved = abs(event.y_root - opt_drag["start_y"]) > 5
            src_idx = opt_drag["idx"]
            opt_drag["idx"] = None
            if not moved:
                return
            dst_idx = _get_opt_drop_idx(event.y_root)
            if dst_idx > src_idx:
                dst_idx -= 1
            if src_idx == dst_idx:
                return
            ci = cur_idx[0]
            working_names[ci]   = name_entry.get().strip() or f"옵션 {ci+1}"
            working[ci]         = txt1.get("1.0", "end").strip()
            working2[ci]        = txt2.get("1.0", "end").strip()
            working_kw2[ci]     = kw2_var.get()
            working_topic[ci]   = topic_var.get()
            working_collect[ci] = collect_var.get()
            working_enabled[ci] = enabled_var.get()
            for arr in [working, working2, working_names, working_enabled, working_kw2, working_topic, working_collect, working_guest]:
                arr.insert(dst_idx, arr.pop(src_idx))
            for arr in [self._kw_per_option, self._kw2_per_option, self._img_source_per_option]:
                if src_idx < len(arr):
                    arr.insert(min(dst_idx, len(arr)), arr.pop(src_idx))
            if ci == src_idx:
                cur_idx[0] = dst_idx
            elif src_idx < ci <= dst_idx:
                cur_idx[0] = ci - 1
            elif dst_idx <= ci < src_idx:
                cur_idx[0] = ci + 1
            _rebuild_opt_list()
            idx = cur_idx[0]
            name_entry.delete(0, "end")
            name_entry.insert(0, working_names[idx])
            enabled_var.set(working_enabled[idx])
            kw2_var.set(working_kw2[idx] if not working_collect[idx] else False)
            topic_var.set(working_topic[idx])
            collect_var.set(working_collect[idx])
            txt1.delete("1.0", "end")
            if working[idx]:
                txt1.insert("1.0", working[idx])
            txt2.configure(state="normal")
            txt2.delete("1.0", "end")
            if working2[idx]:
                txt2.insert("1.0", working2[idx])
            _refresh_txt2()

        def _save_current_fields():
            ci = cur_idx[0]
            if 0 <= ci < len(working):
                working_names[ci]   = name_entry.get().strip() or f"옵션 {ci+1}"
                working[ci]         = txt1.get("1.0", "end").strip()
                working2[ci]        = txt2.get("1.0", "end").strip()
                working_kw2[ci]     = kw2_var.get()
                working_topic[ci]   = topic_var.get()
                working_collect[ci] = collect_var.get()
                working_enabled[ci] = enabled_var.get()
                working_guest[ci]   = guest_var.get()

        def _add_opt():
            _save_current_fields()
            n = len(working)
            working.append(""); working2.append("")
            working_names.append(f"옵션 {n+1}")
            working_enabled.append(True); working_kw2.append(False)
            working_topic.append(False); working_collect.append(False)
            working_guest.append(False)
            self._kw_per_option.append(""); self._kw2_per_option.append("")
            self._img_source_per_option.append("AI")
            _rebuild_opt_list()
            _switch_to(n)

        def _delete_opt(del_i):
            if len(working) <= 1:
                return
            _save_current_fields()
            for arr in [working, working2, working_names, working_enabled,
                        working_kw2, working_topic, working_collect, working_guest]:
                arr.pop(del_i)
            for arr in [self._kw_per_option, self._kw2_per_option, self._img_source_per_option]:
                if del_i < len(arr):
                    arr.pop(del_i)
            new_idx = cur_idx[0]
            if new_idx >= len(working):
                new_idx = len(working) - 1
            elif new_idx > del_i:
                new_idx -= 1
            cur_idx[0] = new_idx
            _rebuild_opt_list()
            _switch_to(cur_idx[0], save=False)

        def _rebuild_opt_list():
            for r in opt_rows:
                r.destroy()
            opt_rows.clear()
            opt_btns.clear()
            for i in range(len(working)):
                is_on = working_enabled[i]
                has   = working[i] or working2[i]
                row = ctk.CTkFrame(left, fg_color="transparent", corner_radius=6)
                row.pack(padx=2, pady=2, fill="x")
                handle = tk.Label(
                    row, text="⠿",
                    bg=C["accent_bg"], fg=C["subtext"],
                    font=("Malgun Gothic", 11),
                    cursor="fleur", padx=2,
                )
                handle.pack(side="left")
                handle.bind("<Button-1>",        lambda e, n=i: _on_opt_drag_start(e, n))
                handle.bind("<B1-Motion>",       _on_opt_drag_motion)
                handle.bind("<ButtonRelease-1>", _on_opt_drag_end)
                if i == cur_idx[0]:
                    _tc = "white"
                elif not is_on:
                    _tc = "#AAAAAA"
                elif working_guest[i]:
                    _tc = "#6FCF97"
                else:
                    _tc = C["accent"] if has else C["subtext"]
                b = ctk.CTkButton(
                    row,
                    text=_btn_label(i),
                    command=lambda n=i: _switch_to(n),
                    height=30,
                    font=F_SM,
                    fg_color=C["accent"] if i == cur_idx[0] else "transparent",
                    hover_color="#D4DCF5",
                    text_color=_tc,
                    corner_radius=6,
                    anchor="w",
                )
                del_btn = ctk.CTkButton(
                    row, text="✕", command=lambda n=i: _delete_opt(n),
                    width=22, height=22, font=("Malgun Gothic", 10, "bold"),
                    fg_color="transparent", hover_color=C["err"],
                    text_color=C["subtext"], corner_radius=4,
                )
                del_btn.pack(side="right", padx=(1, 2))
                b.pack(side="left", fill="x", expand=True)
                opt_btns.append(b)
                opt_rows.append(row)
            # + 추가 버튼 (매번 파괴 후 재생성)
            if _add_row_ref[0]:
                try: _add_row_ref[0].destroy()
                except Exception: pass
            add_row = ctk.CTkFrame(left, fg_color="transparent")
            add_row.pack(padx=2, pady=(4, 2), fill="x")
            ctk.CTkButton(
                add_row, text="+ 옵션 추가", command=_add_opt,
                height=26, font=F_SM,
                fg_color="transparent", hover_color=C["accent_bg"],
                text_color=C["accent"], corner_radius=6, border_width=1,
                border_color=C["accent"],
            ).pack(fill="x")
            _add_row_ref[0] = add_row

        _rebuild_opt_list()

        _refresh_txt2()
        if working[cur_idx[0]]:
            txt1.insert("1.0", working[cur_idx[0]])
        txt2.configure(state="normal")
        if working2[cur_idx[0]]:
            txt2.insert("1.0", working2[cur_idx[0]])
        _refresh_txt2()

        # ── 탭2~5 lazy build 공유 상태 ──────────────────────────────
        _VAR_DEFAULTS = {
            "crop_pct_min": 0.5,         "crop_pct_max": 3.5,
            "brightness_pct_min": -6.0,  "brightness_pct_max": 6.0,
            "contrast_pct_min": -6.0,    "contrast_pct_max": 6.0,
            "color_pct_min": -6.0,       "color_pct_max": 6.0,
            "rotation_deg_min": 0.2,     "rotation_deg_max": 1.5,
            "noise_min": 1.0,            "noise_max": 4.0,
            "hue_shift_min": -8.0,       "hue_shift_max": 8.0,
            "sharpness_min": -25.0,      "sharpness_max": 40.0,
            "temperature_min": -6.0,     "temperature_max": 6.0,
            "gamma_min": -6.0,           "gamma_max": 6.0,
            "aspect_ratio_min": -5.0,    "aspect_ratio_max": 5.0,
            "jpeg_quality_min": 1.0,     "jpeg_quality_max": 15.0,
            "translate_min": 1.0,        "translate_max": 7.0,
            "rgb_offset_min": -6.0,      "rgb_offset_max": 6.0,
            "watermark_min": 0.1,        "watermark_max": 1.5,
            "hflip_prob": 0.0,
        }
        slider_refs        = []
        slider_refs_picsum = []
        slider_refs_flickr = []
        var_mode = ["img_select"]
        _t2_built = [False]
        _t3_save = [None]; _t3_built = [False]
        _t4_save = [None]; _t4_built = [False]
        _t5_save = [None]; _t5_built = [False]

        def _build_tab2():
            nonlocal mw_entry, _ps_w_entry, _ps_h_entry, _fl_w_entry, _fl_h_entry, _fl_kw_entry
            # ── 탭2 내용: 이미지 변형 설정 ──────────────────────────
            _VAR_PARAMS = [
                ("랜덤 크롭 범위",        "crop_pct",         0,  15,  0.5,  "{:.1f}%"),
                ("밝기 조절",             "brightness_pct",  -30,  30,  0.5,  "{:.1f}%"),
                ("대비 조절",             "contrast_pct",    -30,  30,  0.5,  "{:.1f}%"),
                ("채도 조절",             "color_pct",       -30,  30,  0.5,  "{:.1f}%"),
                ("회전 각도",             "rotation_deg",      0,  15,  0.1,  "{:.1f}°"),
                ("픽셀 노이즈",           "noise",             0,  50,  1.0,  "{:.0f}"),
                ("색조 이동",             "hue_shift",       -30,  30,  0.5,  "{:.1f}°"),
                ("선명도(+샤픈/-블러)",   "sharpness",       -50,  50,  0.5,  "{:.1f}%"),
                ("색온도(+따뜻/-차가)",   "temperature",     -20,  20,  0.5,  "{:.1f}"),
                ("감마(+밝음/-어둠)",     "gamma",           -20,  20,  0.5,  "{:.1f}%"),
                ("비율(+가로/-세로늘림)", "aspect_ratio",    -15,  15,  0.5,  "{:.1f}%"),
                ("JPEG 재압축(품질감소)", "jpeg_quality",      0,  30,  0.5,  "{:.1f}%"),
                ("미세 이동",             "translate",          0,  15,  0.5,  "{:.1f}px"),
                ("RGB 채널 오프셋",       "rgb_offset",       -30,  30,  0.5,  "{:.1f}"),
                ("워터마크 투명도(0=없음)","watermark",          0,  30,  0.1,  "{:.1f}%"),
            ]

            # 모드 선택 행
            _t2_mode_row = ctk.CTkFrame(tab2_content, fg_color="transparent")
            _t2_mode_row.pack(fill="x", pady=(0, 6))
            _t2_img_panel    = ctk.CTkFrame(tab2_content, fg_color="transparent")
            _t2_picsum_panel = ctk.CTkFrame(tab2_content, fg_color="transparent")
            _t2_flickr_panel = ctk.CTkFrame(tab2_content, fg_color="transparent")
            _t2_all_panels   = [_t2_img_panel, _t2_picsum_panel, _t2_flickr_panel]
            _t2_all_btns     = []  # filled after button creation

            def _switch_var_mode(mode):
                var_mode[0] = mode
                panel_map = {"img_select": _t2_img_panel, "picsum": _t2_picsum_panel, "flickr": _t2_flickr_panel}
                for p in _t2_all_panels:
                    p.pack_forget()
                panel_map[mode].pack(fill="both", expand=True)
                active_fg = C["accent"]; active_tc = "white"
                inactive_fg = C["accent_bg"]; inactive_tc = C["subtext"]
                mode_order = ["img_select", "flickr", "picsum"]
                for btn, m in zip(_t2_all_btns, mode_order):
                    if m == mode:
                        btn.configure(fg_color=active_fg, text_color=active_tc)
                    else:
                        btn.configure(fg_color=inactive_fg, text_color=inactive_tc)

            _t2_img_btn = ctk.CTkButton(
                _t2_mode_row, text="이미지 선택", width=120, height=28,
                fg_color=C["accent"], text_color="white", font=F_SMB,
                hover_color=C["accent_h"], corner_radius=6,
                command=lambda: _switch_var_mode("img_select"),
            )
            _t2_img_btn.pack(side="left", padx=(0, 4))
            _t2_flk_btn = ctk.CTkButton(
                _t2_mode_row, text="플리커", width=100, height=28,
                fg_color=C["accent_bg"], text_color=C["subtext"], font=F_SMB,
                hover_color=C["border"], corner_radius=6,
                command=lambda: _switch_var_mode("flickr"),
            )
            _t2_flk_btn.pack(side="left", padx=(0, 4))
            _t2_pcs_btn = ctk.CTkButton(
                _t2_mode_row, text="픽숨", width=100, height=28,
                fg_color=C["accent_bg"], text_color=C["subtext"], font=F_SMB,
                hover_color=C["border"], corner_radius=6,
                command=lambda: _switch_var_mode("picsum"),
            )
            _t2_pcs_btn.pack(side="left")
            _t2_all_btns.extend([_t2_img_btn, _t2_flk_btn, _t2_pcs_btn])

            def _make_slider(parent, from_, to, step, init_val):
                n_steps = round((to - from_) / step)
                sl = ctk.CTkSlider(
                    parent, from_=from_, to=to, number_of_steps=n_steps,
                    fg_color=C["border"], progress_color=C["accent"],
                    button_color=C["accent"], button_hover_color=C["accent_h"],
                    height=12,
                )
                sl.set(init_val)
                return sl

            def _make_flip_row(parent, wd):
                row = ctk.CTkFrame(parent, fg_color=C["accent_bg"], corner_radius=8)
                row.pack(fill="x", pady=(0, 5))
                hdr = ctk.CTkFrame(row, fg_color="transparent")
                hdr.pack(fill="x", padx=8, pady=(5, 1))
                _lbl(hdr, "좌우반전 확률", font=F_SMB, color=C["text"]).pack(side="left")
                val_lbl = _lbl(hdr, f"{wd['hflip_prob']:.0f}%", font=("Malgun Gothic", 11, "bold"), color=C["accent"])
                val_lbl.pack(side="right")
                sl_row = ctk.CTkFrame(row, fg_color="transparent")
                sl_row.pack(fill="x", padx=8, pady=(0, 6))
                _lbl(sl_row, "확률", font=("Malgun Gothic", 11), color=C["subtext"], width=24).pack(side="left")
                sl = _make_slider(sl_row, 0, 100, 1, wd["hflip_prob"])
                sl.pack(side="left", fill="x", expand=True, padx=(3, 0))

                def _on_flip(v, _d=wd, _vl=val_lbl):
                    rv = round(float(v))
                    _d["hflip_prob"] = float(rv)
                    _vl.configure(text=f"{rv}%")

                sl.configure(command=_on_flip)

            def _make_param_row(parent, lbl_text, base, from_, to, step, fmt, wd, sl_list):
                k_min = f"{base}_min"
                k_max = f"{base}_max"
                row = ctk.CTkFrame(parent, fg_color=C["accent_bg"], corner_radius=8)
                row.pack(fill="x", pady=(0, 5))
                hdr = ctk.CTkFrame(row, fg_color="transparent")
                hdr.pack(fill="x", padx=8, pady=(5, 1))
                _lbl(hdr, lbl_text, font=F_SMB, color=C["text"]).pack(side="left")
                range_lbl = _lbl(
                    hdr,
                    f"{fmt.format(wd[k_min])} ~ {fmt.format(wd[k_max])}",
                    font=("Malgun Gothic", 11, "bold"), color=C["accent"],
                )
                range_lbl.pack(side="right")
                min_row = ctk.CTkFrame(row, fg_color="transparent")
                min_row.pack(fill="x", padx=8, pady=(0, 1))
                _lbl(min_row, "최소", font=("Malgun Gothic", 11), color=C["subtext"], width=24).pack(side="left")
                sl_min = _make_slider(min_row, from_, to, step, wd[k_min])
                sl_min.pack(side="left", fill="x", expand=True, padx=(3, 0))
                max_row = ctk.CTkFrame(row, fg_color="transparent")
                max_row.pack(fill="x", padx=8, pady=(0, 6))
                _lbl(max_row, "최대", font=("Malgun Gothic", 11), color=C["subtext"], width=24).pack(side="left")
                sl_max = _make_slider(max_row, from_, to, step, wd[k_max])
                sl_max.pack(side="left", fill="x", expand=True, padx=(3, 0))
                sl_list.append((sl_min, sl_max, k_min, k_max, range_lbl, fmt, step))

                def _on_min(v, km=k_min, kx=k_max, sm=sl_min, f=fmt, s=step, rl=range_lbl, _d=wd):
                    rv = round(float(v) / s) * s
                    if rv > _d[kx]: rv = _d[kx]; sm.set(rv)
                    _d[km] = rv
                    rl.configure(text=f"{f.format(_d[km])} ~ {f.format(_d[kx])}")

                def _on_max(v, km=k_min, kx=k_max, sx=sl_max, f=fmt, s=step, rl=range_lbl, _d=wd):
                    rv = round(float(v) / s) * s
                    if rv < _d[km]: rv = _d[km]; sx.set(rv)
                    _d[kx] = rv
                    rl.configure(text=f"{f.format(_d[km])} ~ {f.format(_d[kx])}")

                sl_min.configure(command=_on_min)
                sl_max.configure(command=_on_max)

            # ── 이미지 선택 패널 ──────────────────────────────────
            mw_row = ctk.CTkFrame(_t2_img_panel, fg_color=C["accent_bg"], corner_radius=8)
            mw_row.pack(fill="x", pady=(4, 0), side="bottom")
            mw_inner = ctk.CTkFrame(mw_row, fg_color="transparent")
            mw_inner.pack(fill="x", padx=8, pady=6)
            _lbl(mw_inner, "가로 최대 크기 (px, 가로 이미지만 / 0=사용 안 함)",
                 font=F_SMB, color=C["text"]).pack(side="left")
            mw_entry = _UndoEntry(
                mw_inner, width=80, height=28, font=F,
                fg_color=C["input_bg"], border_color=C["border"],
                text_color=C["text"], corner_radius=6,
            )
            mw_entry.pack(side="right")
            mw_entry.insert(0, str(self._max_width) if self._max_width else "0")

            _t2_col_scroll = ctk.CTkScrollableFrame(
                _t2_img_panel, fg_color="transparent",
                scrollbar_button_color=C["border"],
            )
            _t2_col_scroll.pack(fill="both", expand=True)
            _t2_col_wrap = ctk.CTkFrame(_t2_col_scroll, fg_color="transparent")
            _t2_col_wrap.pack(fill="both", expand=True)
            _t2_col_wrap.columnconfigure(0, weight=1)
            _t2_col_wrap.columnconfigure(1, weight=1)
            _t2_col_wrap.columnconfigure(2, weight=1)
            _t2_col_L = ctk.CTkFrame(_t2_col_wrap, fg_color="transparent")
            _t2_col_L.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
            _t2_col_M = ctk.CTkFrame(_t2_col_wrap, fg_color="transparent")
            _t2_col_M.grid(row=0, column=1, sticky="nsew", padx=(3, 3))
            _t2_col_R = ctk.CTkFrame(_t2_col_wrap, fg_color="transparent")
            _t2_col_R.grid(row=0, column=2, sticky="nsew", padx=(3, 0))

            n = len(_VAR_PARAMS)
            third = (n + 2) // 3
            for i, (lbl_text, base, from_, to, step, fmt) in enumerate(_VAR_PARAMS):
                col = _t2_col_L if i < third else (_t2_col_M if i < third * 2 else _t2_col_R)
                _make_param_row(col, lbl_text, base, from_, to, step, fmt, w_var, slider_refs)
            _make_flip_row(_t2_col_L, w_var)

            # ── PICSUM 패널 ────────────────────────────────────────
            _ps_size_row = ctk.CTkFrame(_t2_picsum_panel, fg_color=C["accent_bg"], corner_radius=8)
            _ps_size_row.pack(fill="x", pady=(4, 0), side="bottom")
            _ps_size_inner = ctk.CTkFrame(_ps_size_row, fg_color="transparent")
            _ps_size_inner.pack(fill="x", padx=8, pady=6)
            _lbl(_ps_size_inner, "이미지 크기 (가로 × 세로 px)",
                 font=F_SMB, color=C["text"]).pack(side="left")
            _ps_h_entry = _UndoEntry(
                _ps_size_inner, width=70, height=28, font=F,
                fg_color=C["input_bg"], border_color=C["border"],
                text_color=C["text"], corner_radius=6,
            )
            _ps_h_entry.pack(side="right")
            _ps_h_entry.insert(0, str(self._picsum_height))
            _lbl(_ps_size_inner, "×", font=F_SMB, color=C["subtext"]).pack(side="right", padx=(4, 4))
            _ps_w_entry = _UndoEntry(
                _ps_size_inner, width=70, height=28, font=F,
                fg_color=C["input_bg"], border_color=C["border"],
                text_color=C["text"], corner_radius=6,
            )
            _ps_w_entry.pack(side="right", padx=(0, 0))
            _ps_w_entry.insert(0, str(self._picsum_width))

            _t2p_col_scroll = ctk.CTkScrollableFrame(
                _t2_picsum_panel, fg_color="transparent",
                scrollbar_button_color=C["border"],
            )
            _t2p_col_scroll.pack(fill="both", expand=True)
            _t2p_col_wrap = ctk.CTkFrame(_t2p_col_scroll, fg_color="transparent")
            _t2p_col_wrap.pack(fill="both", expand=True)
            _t2p_col_wrap.columnconfigure(0, weight=1)
            _t2p_col_wrap.columnconfigure(1, weight=1)
            _t2p_col_wrap.columnconfigure(2, weight=1)
            _t2p_col_L = ctk.CTkFrame(_t2p_col_wrap, fg_color="transparent")
            _t2p_col_L.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
            _t2p_col_M = ctk.CTkFrame(_t2p_col_wrap, fg_color="transparent")
            _t2p_col_M.grid(row=0, column=1, sticky="nsew", padx=(3, 3))
            _t2p_col_R = ctk.CTkFrame(_t2p_col_wrap, fg_color="transparent")
            _t2p_col_R.grid(row=0, column=2, sticky="nsew", padx=(3, 0))

            for i, (lbl_text, base, from_, to, step, fmt) in enumerate(_VAR_PARAMS):
                col = _t2p_col_L if i < third else (_t2p_col_M if i < third * 2 else _t2p_col_R)
                _make_param_row(col, lbl_text, base, from_, to, step, fmt, w_var_picsum, slider_refs_picsum)
            _make_flip_row(_t2p_col_L, w_var_picsum)

            # ── FLICKR 패널 ────────────────────────────────────────
            # 키워드 입력 (가장 아래)
            _fl_kw_row = ctk.CTkFrame(_t2_flickr_panel, fg_color=C["accent_bg"], corner_radius=8)
            _fl_kw_row.pack(fill="x", pady=(2, 0), side="bottom")
            _fl_kw_inner = ctk.CTkFrame(_fl_kw_row, fg_color="transparent")
            _fl_kw_inner.pack(fill="x", padx=8, pady=6)
            _lbl(_fl_kw_inner, "검색 키워드 (비우면 랜덤 자동 선택)",
                 font=F_SMB, color=C["text"]).pack(side="left")
            _fl_kw_entry = _UndoEntry(
                _fl_kw_inner, width=160, height=28, font=F,
                fg_color=C["input_bg"], border_color=C["border"],
                text_color=C["text"], corner_radius=6,
                placeholder_text="nature, city, food ...",
            )
            _fl_kw_entry.pack(side="right")
            if self._flickr_keyword:
                _fl_kw_entry.insert(0, self._flickr_keyword)

            # 이미지 크기 (키워드 위)
            _fl_size_row = ctk.CTkFrame(_t2_flickr_panel, fg_color=C["accent_bg"], corner_radius=8)
            _fl_size_row.pack(fill="x", pady=(4, 2), side="bottom")
            _fl_size_inner = ctk.CTkFrame(_fl_size_row, fg_color="transparent")
            _fl_size_inner.pack(fill="x", padx=8, pady=6)
            _lbl(_fl_size_inner, "이미지 크기 (가로 × 세로 px)",
                 font=F_SMB, color=C["text"]).pack(side="left")
            _fl_h_entry = _UndoEntry(
                _fl_size_inner, width=70, height=28, font=F,
                fg_color=C["input_bg"], border_color=C["border"],
                text_color=C["text"], corner_radius=6,
            )
            _fl_h_entry.pack(side="right")
            _fl_h_entry.insert(0, str(self._flickr_height))
            _lbl(_fl_size_inner, "×", font=F_SMB, color=C["subtext"]).pack(side="right", padx=(4, 4))
            _fl_w_entry = _UndoEntry(
                _fl_size_inner, width=70, height=28, font=F,
                fg_color=C["input_bg"], border_color=C["border"],
                text_color=C["text"], corner_radius=6,
            )
            _fl_w_entry.pack(side="right", padx=(0, 0))
            _fl_w_entry.insert(0, str(self._flickr_width))

            _t2f_col_scroll = ctk.CTkScrollableFrame(
                _t2_flickr_panel, fg_color="transparent",
                scrollbar_button_color=C["border"],
            )
            _t2f_col_scroll.pack(fill="both", expand=True)
            _t2f_col_wrap = ctk.CTkFrame(_t2f_col_scroll, fg_color="transparent")
            _t2f_col_wrap.pack(fill="both", expand=True)
            _t2f_col_wrap.columnconfigure(0, weight=1)
            _t2f_col_wrap.columnconfigure(1, weight=1)
            _t2f_col_wrap.columnconfigure(2, weight=1)
            _t2f_col_L = ctk.CTkFrame(_t2f_col_wrap, fg_color="transparent")
            _t2f_col_L.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
            _t2f_col_M = ctk.CTkFrame(_t2f_col_wrap, fg_color="transparent")
            _t2f_col_M.grid(row=0, column=1, sticky="nsew", padx=(3, 3))
            _t2f_col_R = ctk.CTkFrame(_t2f_col_wrap, fg_color="transparent")
            _t2f_col_R.grid(row=0, column=2, sticky="nsew", padx=(3, 0))

            for i, (lbl_text, base, from_, to, step, fmt) in enumerate(_VAR_PARAMS):
                col = _t2f_col_L if i < third else (_t2f_col_M if i < third * 2 else _t2f_col_R)
                _make_param_row(col, lbl_text, base, from_, to, step, fmt, w_var_flickr, slider_refs_flickr)
            _make_flip_row(_t2f_col_L, w_var_flickr)

            # 초기 모드: 이미지 선택
            _t2_img_panel.pack(fill="both", expand=True)


        def _build_tab3():
            # ── 탭3: 허용 MAC 관리 ───────────────────────────
            mac_entries_work = [dict(e) for e in self._mac_entries]
            current_mac = _get_mac_address().upper()

            _lbl(tab3_content, "🔒 허용 MAC 주소 관리", font=F_B).pack(anchor="w", pady=(8, 2))
            _lbl(tab3_content, "등록된 MAC만 실행 가능. 비어있으면 모든 PC 허용. 저장 후 Gist 업로드하면 자동 동기화.",
                 font=F_SM, color=C["subtext"]).pack(anchor="w", pady=(0, 6))

            # 현재 PC MAC 표시
            cur_frame = ctk.CTkFrame(tab3_content, fg_color=C["accent_bg"], corner_radius=8)
            cur_frame.pack(fill="x", pady=(0, 8))
            _lbl(cur_frame, "이 PC MAC:", font=F_SMB, color=C["subtext"]).pack(side="left", padx=(12,6), pady=8)
            cur_mac_lbl = _UndoEntry(cur_frame, height=26, font=F_B, fg_color="transparent",
                                       border_width=0, text_color=C["accent"], width=170)
            cur_mac_lbl.insert(0, current_mac)
            cur_mac_lbl.configure(state="readonly")
            cur_mac_lbl.pack(side="left", pady=8)


            # 수동 입력 행
            add_row = ctk.CTkFrame(tab3_content, fg_color="transparent")
            add_row.pack(fill="x", pady=(0, 6))
            mac_entry = _UndoEntry(add_row, height=30, font=F_SM,
                                     fg_color=C["input_bg"], border_color=C["border"],
                                     text_color=C["text"], corner_radius=7, width=170,
                                     placeholder_text="XX:XX:XX:XX:XX:XX 또는 XX-XX-...")
            mac_entry.pack(side="left", padx=(0, 6))
            note_entry = _UndoEntry(add_row, height=30, font=F_SM,
                                      fg_color=C["input_bg"], border_color=C["border"],
                                      text_color=C["text"], corner_radius=7,
                                      placeholder_text="비고 (이름/장소)")
            note_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

            def _add_manual():
                raw = mac_entry.get().strip().upper().replace("-", ":")
                if len(raw) == 17 and raw.count(":") == 5:
                    macs = [e["mac"] for e in mac_entries_work]
                    if raw not in macs:
                        mac_entries_work.append({"mac": raw, "note": note_entry.get().strip()})
                        _refresh_list()
                    mac_entry.delete(0, "end")
                    note_entry.delete(0, "end")
                else:
                    mac_entry.configure(border_color=C["err"])
                    dlg.after(1000, lambda: mac_entry.configure(border_color=C["border"]))

            ctk.CTkButton(add_row, text="추가", command=_add_manual,
                          width=60, height=30, font=F_SMB,
                          fg_color=C["accent"], hover_color=C["accent_h"],
                          text_color="white", corner_radius=7).pack(side="left")

            # MAC 목록
            list_frame = ctk.CTkScrollableFrame(tab3_content, fg_color=C["card"],
                                                 border_color=C["border"], border_width=1,
                                                 corner_radius=8)
            list_frame.pack(fill="both", expand=True, pady=(0, 6))

            def _refresh_list():
                for w in list_frame.winfo_children():
                    w.destroy()
                if not mac_entries_work:
                    _lbl(list_frame, "등록된 MAC 없음 (모든 PC 허용 상태)",
                         font=F_SM, color=C["subtext"]).pack(pady=20)
                    return
                for entry in list(mac_entries_work):
                    m, note = entry["mac"], entry.get("note", "")
                    row = ctk.CTkFrame(list_frame, fg_color="transparent")
                    row.pack(fill="x", pady=1)
                    is_cur = (m == current_mac)
                    color = C["ok"] if is_cur else C["text"]
                    prefix = "✅ " if is_cur else "   "
                    _lbl(row, f"{prefix}{m}", font=F_SM, color=color).pack(side="left", padx=(8,4))

                    note_var_entry = _UndoEntry(row, height=24, font=F_SM, width=140,
                                                  fg_color=C["input_bg"], border_color=C["border"],
                                                  text_color=C["subtext"], corner_radius=5)
                    note_var_entry.insert(0, note)
                    note_var_entry.pack(side="left", padx=(0,4))

                    def _update_note(e, entry=entry, nve=note_var_entry):
                        entry["note"] = nve.get().strip()

                    note_var_entry.bind("<FocusOut>", _update_note)
                    note_var_entry.bind("<Return>",   _update_note)

                    guest_val = ctk.BooleanVar(value=bool(entry.get("guest", False)))
                    def _toggle_guest(entry=entry, gv=guest_val):
                        entry["guest"] = gv.get()
                    ctk.CTkCheckBox(row, text="게스트",
                        variable=guest_val,
                        command=lambda entry=entry, gv=guest_val: _toggle_guest(entry, gv),
                        font=F_SM, text_color=C["text"],
                        fg_color=C["accent"], hover_color=C["accent_h"],
                        checkmark_color="white", width=16, height=16,
                    ).pack(side="left", padx=(6, 4))

                    def _del(entry=entry):
                        if entry in mac_entries_work:
                            mac_entries_work.remove(entry)
                        _refresh_list()
                    ctk.CTkButton(row, text="삭제", command=_del,
                                  width=46, height=24, font=F_SM,
                                  fg_color=C["err"], hover_color="#A03030",
                                  text_color="white", corner_radius=5).pack(side="left", padx=(0, 4))

            _refresh_list()

            def _save_mac():
                self._mac_entries = [dict(e) for e in mac_entries_work]
                self._save_prefs()
                _save_btn.configure(text="✅ 저장됨", fg_color=C["ok"])
                dlg.after(2000, lambda: _save_btn.configure(text="저장", fg_color=C["accent"]))

            _t3_save[0] = _save_mac

        def _build_tab4():
            # ── 탭4 내용: 주제 목록 관리 ─────────────────────
            working_topics = {k: list(v) for k, v in self._topic_lists.items()}

            # 행 그룹 초기화 – 저장된 그룹이 없으면 전체를 1행으로
            working_rows: list = []
            if self._topic_rows:
                for _r in self._topic_rows:
                    _valid = [k for k in _r if k in working_topics]
                    if _valid:
                        working_rows.append(_valid)
                _all_g = {k for _r in working_rows for k in _r}
                _ung = [k for k in working_topics if k not in _all_g]
                if _ung:
                    if working_rows:
                        working_rows[-1].extend(_ung)
                    else:
                        working_rows.append(_ung)
            if not working_rows:
                working_rows.append(list(working_topics.keys()))
            # 항상 정확히 3개 행 유지
            while len(working_rows) < 3:
                working_rows.append([])
            while len(working_rows) > 3:
                working_rows[2].extend(working_rows.pop(3))

            sel_kw = [None]
            sel_kw_row = [None]

            tl_left = ctk.CTkFrame(tab4_content, width=440, fg_color=C["accent_bg"], corner_radius=8)
            tl_left.pack(side="left", fill="y", padx=(0, 10))
            tl_left.pack_propagate(False)

            tl_right = ctk.CTkFrame(tab4_content, fg_color="transparent")
            tl_right.pack(side="left", fill="both", expand=True)

            kw_scroll = ctk.CTkScrollableFrame(tl_left, fg_color="transparent",
                                                scrollbar_button_color=C["border"])
            kw_scroll.pack(fill="both", expand=True, padx=4, pady=(4, 0))

            tl_top = ctk.CTkFrame(tl_right, fg_color="transparent")
            tl_top.pack(fill="x", pady=(0, 6))
            sel_kw_lbl = _lbl(tl_top, "키워드를 선택하세요", font=F_B, color=C["text"])
            sel_kw_lbl.pack(side="left")
            topic_count_lbl = _lbl(tl_top, "", font=F_SM, color=C["subtext"])
            topic_count_lbl.pack(side="left", padx=(8, 0))

            tl_txt = tk.Text(
                tl_right, font=F_SM,
                bg=C["input_bg"], fg=C["text"],
                insertbackground=C["text"],
                relief="flat", bd=0, padx=6, pady=4, wrap="word",
                highlightthickness=1, highlightbackground=C["border"],
            )
            tl_txt.pack(fill="both", expand=True)

            tl_btn_row = ctk.CTkFrame(tl_right, fg_color="transparent")
            tl_btn_row.pack(fill="x", pady=(6, 0))

            kw_btns = []

            def _parse_topics(text: str) -> list:
                items = [t.strip() for t in text.replace('\n', ';').split(';') if t.strip()]
                return items

            chip_drag = {
                "item": None, "group_idx": None,
                "target_item": None, "target_group": None,
                "chip_map": {},
                "sx": 0, "sy": 0,
            }

            def _chip_est_w(text):
                cw = sum(14 if ord(c) > 127 else 8 for c in text)
                return max(50, cw + 24)

            def _chip_drag_start(event, item, g_idx):
                chip_drag["item"] = item
                chip_drag["group_idx"] = g_idx
                chip_drag["target_item"] = None
                chip_drag["target_group"] = None
                chip_drag["sx"] = event.x_root
                chip_drag["sy"] = event.y_root

            def _chip_find_nearest(x_root, y_root):
                best_item, best_group, best_dist = None, None, float("inf")
                for name, (chip, gidx) in chip_drag["chip_map"].items():
                    if name == chip_drag["item"]:
                        continue
                    try:
                        cx = chip.winfo_rootx() + chip.winfo_width() // 2
                        cy = chip.winfo_rooty() + chip.winfo_height() // 2
                        dist = abs(cx - x_root) + abs(cy - y_root) * 1.5
                        if dist < best_dist:
                            best_dist, best_item, best_group = dist, name, gidx
                    except Exception:
                        pass
                return best_item, best_group

            def _chip_drag_motion(event):
                target_item, target_group = _chip_find_nearest(event.x_root, event.y_root)
                old_item = chip_drag["target_item"]
                if target_item != old_item:
                    if old_item and old_item in chip_drag["chip_map"]:
                        chip_drag["chip_map"][old_item][0].configure(
                            fg_color=C["accent"] if old_item == sel_kw[0] else C["accent_bg"])
                    if target_item and target_item in chip_drag["chip_map"]:
                        chip_drag["chip_map"][target_item][0].configure(fg_color="#E8923A")
                    chip_drag["target_item"] = target_item
                    chip_drag["target_group"] = target_group

            def _chip_drag_end(event, src_item, src_gidx):
                target_item = chip_drag["target_item"]
                target_group = chip_drag["target_group"]
                if target_item and target_item in chip_drag["chip_map"]:
                    chip_drag["chip_map"][target_item][0].configure(
                        fg_color=C["accent"] if target_item == sel_kw[0] else C["accent_bg"])
                moved = (abs(event.x_root - chip_drag["sx"]) > 6 or
                         abs(event.y_root - chip_drag["sy"]) > 6)
                chip_drag["item"] = None
                chip_drag["target_item"] = None
                chip_drag["target_group"] = None
                if moved and target_item and target_item != src_item:
                    if target_group == src_gidx:
                        row = working_rows[src_gidx]
                        row.insert(row.index(target_item), row.pop(row.index(src_item)))
                    elif target_group is not None and 0 <= target_group < len(working_rows):
                        working_rows[src_gidx].remove(src_item)
                        dst = working_rows[target_group]
                        dst.insert(dst.index(target_item), src_item)
                    dlg.after(1, _refresh_kw_list)
                elif not moved:
                    _select_kw(src_item, src_gidx)

            def _refresh_kw_list():
                for b in kw_btns:
                    b.destroy()
                kw_btns.clear()
                chip_drag["chip_map"].clear()
                kw_scroll.update_idletasks()

                for g_idx, row_names in enumerate(working_rows):
                    # 그룹 컨테이너
                    grp = ctk.CTkFrame(kw_scroll, fg_color=C["bg"], corner_radius=7,
                                       border_width=1, border_color=C["border"])
                    grp.pack(fill="x", pady=(0, 6), padx=2)
                    kw_btns.append(grp)

                    # 헤더: 행N (개수) | + 주제 | ↑ | ↓ | 행 삭제
                    hdr = ctk.CTkFrame(grp, fg_color="transparent")
                    hdr.pack(fill="x", padx=6, pady=(4, 2))
                    _lbl(hdr, f"행 {g_idx+1}  ({len(row_names)}개)",
                         font=F_SM, color=C["subtext"]).pack(side="left")

                    if g_idx < len(working_rows) - 1:
                        def _mv_down(gi=g_idx):
                            working_rows[gi], working_rows[gi + 1] = (
                                working_rows[gi + 1], working_rows[gi])
                            dlg.after(1, _refresh_kw_list)
                        ctk.CTkButton(hdr, text="행↓", width=34, height=20, font=F_SM,
                                      fg_color=C["accent_bg"], hover_color=C["accent_h"],
                                      text_color=C["text"], corner_radius=4,
                                      command=_mv_down).pack(side="right", padx=2)
                    if g_idx > 0:
                        def _mv_up(gi=g_idx):
                            working_rows[gi], working_rows[gi - 1] = (
                                working_rows[gi - 1], working_rows[gi])
                            dlg.after(1, _refresh_kw_list)
                        ctk.CTkButton(hdr, text="행↑", width=34, height=20, font=F_SM,
                                      fg_color=C["accent_bg"], hover_color=C["accent_h"],
                                      text_color=C["text"], corner_radius=4,
                                      command=_mv_up).pack(side="right", padx=2)

                    def _add_to_row(gi=g_idx):
                        _add_kw(gi)
                    ctk.CTkButton(hdr, text="+ 주제", width=54, height=20, font=F_SM,
                                  fg_color=C["accent"], hover_color=C["accent_h"],
                                  text_color="white", corner_radius=4,
                                  command=_add_to_row).pack(side="right", padx=(0, 4))

                    # 칩 영역: 가용 너비에 따라 흐름 배치, 중앙 정렬
                    chips_area = ctk.CTkFrame(grp, fg_color="transparent")
                    chips_area.pack(fill="x", padx=4, pady=(0, 4))

                    # tl_left(440) - kw_scroll padx(8) - 스크롤바(14) - grp padx(4) - chips padx(8) - 여유(16)
                    avail = 390
                    has_nav = len(working_rows) > 1
                    nav_w = 22 if has_nav else 0
                    rows_items: list = []
                    cur_row: list = []
                    cur_w = 0
                    for _item in row_names:
                        cw = _chip_est_w(_item) + nav_w + 6
                        if cur_row and cur_w + cw > avail:
                            rows_items.append(cur_row)
                            cur_row, cur_w = [], 0
                        cur_row.append(_item)
                        cur_w += cw
                    if cur_row:
                        rows_items.append(cur_row)

                    for batch in rows_items:
                        row_f = ctk.CTkFrame(chips_area, fg_color="transparent")
                        row_f.pack(anchor="center", pady=1)
                        for item in batch:
                            is_sel = item == sel_kw[0]
                            # 칩 + 이동 버튼 래퍼
                            cw = ctk.CTkFrame(row_f, fg_color="transparent")
                            cw.pack(side="left", padx=3, pady=2)
                            chip = ctk.CTkLabel(
                                cw, text=item,
                                height=28, font=F_SM,
                                fg_color=C["accent"] if is_sel else C["accent_bg"],
                                text_color="white" if is_sel else C["text"],
                                corner_radius=14, cursor="hand2",
                            )
                            chip.pack(side="left")
                            # 개별 행 이동 버튼 (행이 2개 이상일 때만)
                            if len(working_rows) > 1:
                                nav = ctk.CTkFrame(cw, fg_color="transparent")
                                nav.pack(side="left", padx=(1, 0))
                                if g_idx > 0:
                                    def _chip_up(k=item, gi=g_idx):
                                        working_rows[gi].remove(k)
                                        working_rows[gi - 1].append(k)
                                        dlg.after(1, _refresh_kw_list)
                                    ctk.CTkButton(nav, text="↑", width=18, height=13,
                                                  font=("Malgun Gothic", 8),
                                                  fg_color="transparent",
                                                  hover_color=C["border"],
                                                  text_color=C["subtext"],
                                                  corner_radius=2,
                                                  command=_chip_up).pack()
                                if g_idx < len(working_rows) - 1:
                                    def _chip_dn(k=item, gi=g_idx):
                                        working_rows[gi].remove(k)
                                        working_rows[gi + 1].append(k)
                                        dlg.after(1, _refresh_kw_list)
                                    ctk.CTkButton(nav, text="↓", width=18, height=13,
                                                  font=("Malgun Gothic", 8),
                                                  fg_color="transparent",
                                                  hover_color=C["border"],
                                                  text_color=C["subtext"],
                                                  corner_radius=2,
                                                  command=_chip_dn).pack()
                            chip_drag["chip_map"][item] = (chip, g_idx)
                            chip.bind("<ButtonPress-1>",  lambda e, k=item, gi=g_idx: _chip_drag_start(e, k, gi))
                            chip.bind("<B1-Motion>",       lambda e: _chip_drag_motion(e))
                            chip.bind("<ButtonRelease-1>", lambda e, k=item, gi=g_idx: _chip_drag_end(e, k, gi))
                            chip.bind("<Double-Button-1>", lambda e, k=item: _rename_kw(k))

            def _select_kw(kw_item: str, g_idx: int = None):
                if sel_kw[0] and sel_kw[0] in working_topics:
                    topics_text = tl_txt.get("1.0", "end").strip()
                    working_topics[sel_kw[0]] = _parse_topics(topics_text)
                old_sel = sel_kw[0]
                sel_kw[0] = kw_item
                sel_kw_row[0] = g_idx
                sel_kw_lbl.configure(text=kw_item)
                tl_txt.delete("1.0", "end")
                topics = working_topics.get(kw_item, [])
                topic_count_lbl.configure(text=f"({len(topics)}개)")
                tl_txt.insert("1.0", ";".join(topics))
                if old_sel and old_sel in chip_drag["chip_map"]:
                    try:
                        chip_drag["chip_map"][old_sel][0].configure(
                            fg_color=C["accent_bg"], text_color=C["text"])
                    except Exception:
                        pass
                if kw_item in chip_drag["chip_map"]:
                    try:
                        chip_drag["chip_map"][kw_item][0].configure(
                            fg_color=C["accent"], text_color="white")
                    except Exception:
                        pass

            def _add_kw(target_group=None):
                add_dlg = ctk.CTkToplevel(dlg)
                add_dlg.title("주제 추가")
                add_dlg.geometry("260x100")
                add_dlg.resizable(False, False)
                add_dlg.grab_set(); add_dlg.lift()
                sw2, sh2 = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
                add_dlg.geometry(f"260x100+{(sw2-260)//2}+{(sh2-100)//2}")
                _lbl(add_dlg, "주제명", font=F_SM, color=C["subtext"]).pack(pady=(10, 4))
                e = _UndoEntry(add_dlg, width=200, height=30, font=F,
                                 fg_color=C["input_bg"], border_color=C["border"],
                                 text_color=C["text"], corner_radius=7)
                e.pack(); e.focus()
                def _confirm(event=None):
                    kw_new = e.get().strip()
                    if kw_new and kw_new not in working_topics:
                        working_topics[kw_new] = []
                        gi = target_group if target_group is not None else (
                            sel_kw_row[0] if sel_kw_row[0] is not None else len(working_rows) - 1)
                        gi = max(0, min(gi, len(working_rows) - 1))
                        working_rows[gi].append(kw_new)
                        _refresh_kw_list()
                        _select_kw(kw_new, gi)
                    add_dlg.destroy()
                e.bind("<Return>", _confirm)
                _btn(add_dlg, "추가", _confirm, w=80, h=28).pack(pady=(6, 0))

            def _rename_kw(kw_item: str):
                ren_dlg = ctk.CTkToplevel(dlg)
                ren_dlg.title("주제명 수정")
                ren_dlg.geometry("260x100")
                ren_dlg.resizable(False, False)
                ren_dlg.grab_set(); ren_dlg.lift()
                sw2, sh2 = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
                ren_dlg.geometry(f"260x100+{(sw2-260)//2}+{(sh2-100)//2}")
                _lbl(ren_dlg, "주제명", font=F_SM, color=C["subtext"]).pack(pady=(10, 4))
                e = _UndoEntry(ren_dlg, width=200, height=30, font=F,
                                 fg_color=C["input_bg"], border_color=C["border"],
                                 text_color=C["text"], corner_radius=7)
                e.pack(); e.insert(0, kw_item); e.focus()
                def _confirm(event=None):
                    new_name = e.get().strip()
                    if new_name and new_name != kw_item and new_name not in working_topics:
                        new_dict = {}
                        for k, v in working_topics.items():
                            new_dict[new_name if k == kw_item else k] = v
                        working_topics.clear()
                        working_topics.update(new_dict)
                        for row in working_rows:
                            if kw_item in row:
                                row[row.index(kw_item)] = new_name
                        if sel_kw[0] == kw_item:
                            sel_kw[0] = new_name
                            sel_kw_lbl.configure(text=new_name)
                        _refresh_kw_list()
                    ren_dlg.destroy()
                e.bind("<Return>", _confirm)
                _btn(ren_dlg, "저장", _confirm, w=80, h=28).pack(pady=(6, 0))

            def _del_kw():
                if sel_kw[0] and sel_kw[0] in working_topics:
                    item = sel_kw[0]
                    del working_topics[item]
                    for row in working_rows:
                        if item in row:
                            row.remove(item)
                    sel_kw[0] = None
                    sel_kw_row[0] = None
                    sel_kw_lbl.configure(text="키워드를 선택하세요")
                    topic_count_lbl.configure(text="")
                    tl_txt.delete("1.0", "end")
                    _refresh_kw_list()

            def _save_topics():
                if sel_kw[0] and sel_kw[0] in working_topics:
                    topics_text = tl_txt.get("1.0", "end").strip()
                    working_topics[sel_kw[0]] = _parse_topics(topics_text)
                    topic_count_lbl.configure(text=f"({len(working_topics[sel_kw[0]])}개)")
                    _refresh_kw_list()
                self._topic_lists = {k: list(v) for k, v in working_topics.items()}
                self._topic_rows = [list(r) for r in working_rows]
                self._save_prefs()
                self._update_topic_state()
                _save_btn.configure(text="✅ 저장됨", fg_color=C["ok"])
                dlg.after(2000, lambda: _save_btn.configure(text="저장", fg_color=C["accent"]))

            _btn(tl_btn_row, "+ 주제 추가", _add_kw, w=100, h=30).pack(side="left")
            _btn(tl_btn_row, "🗑 삭제", _del_kw, w=80, h=30,
                 color=C["err"], hover="#A03030").pack(side="left", padx=(6, 0))

            _refresh_kw_list()
            if working_topics:
                first_item = next(
                    (k for r in working_rows for k in r if k in working_topics), None)
                if first_item:
                    gi = next((i for i, r in enumerate(working_rows) if first_item in r), 0)
                    _select_kw(first_item, gi)

            _t4_save[0] = _save_topics

        def _build_tab5():
            # ── 탭5 내용: 인기글 수집 ────────────────────────
            import threading as _threading
            import naver_collector as _nc

            def _c5_save_opts():
                try: self._collect_count    = int(c5_opt_count_var.get())
                except Exception: pass
                try: self._collect_skip     = int(c5_opt_skip_var.get())
                except Exception: pass
                self._collect_chunk         = c5_opt_chunk_var.get().strip() or "0"
                try: self._collect_maxchars = int(c5_opt_maxch_var.get())
                except Exception: pass
                self._collect_header        = c5_opt_header_var.get().strip() or "[인기글 참조]"
                c5_opt_header_var.set(self._collect_header)
                self._collect_delimiters    = c5_opt_delimiters_var.get().strip()
                self._collect_ending        = c5_opt_ending_var.get().strip()
                self._collect_bottom        = c5_opt_bottom_var.get().strip()
                self._save_prefs()
                _save_btn.configure(text="✅ 저장됨", fg_color=C["ok"])
                dlg.after(2000, lambda: _save_btn.configure(text="저장", fg_color=C["accent"]))

            # ── 옵션 영역 (side="bottom") ─────────────────────
            c5_opt_frame = ctk.CTkFrame(tab5_content, fg_color=C["input_bg"],
                                        corner_radius=8, border_width=0)
            c5_opt_frame.pack(side="bottom", fill="x", pady=(8, 4))

            def _opt_entry(parent, var, w=60):
                _UndoEntry(parent, textvariable=var, width=w, height=28, font=F_SM,
                             fg_color=C["bg"], border_color=C["border"],
                             text_color=C["text"], corner_radius=6, justify="center",
                ).pack(side="left", padx=(0, 6))

            def _div(parent):
                ctk.CTkFrame(parent, fg_color=C["border"], width=1, height=20).pack(side="left", padx=14)

            # 구분 기준 버튼 행
            def _open_delimiters_dlg():
                d = ctk.CTkToplevel(dlg)
                d.title("구분 기준 설정")
                d.geometry("440x150")
                d.resizable(False, False)
                d.grab_set(); d.lift()
                sw2, sh2 = d.winfo_screenwidth(), d.winfo_screenheight()
                d.geometry(f"440x150+{(sw2-440)//2}+{(sh2-150)//2}")
                _lbl(d, "구분 단어 ( ; 로 구분, 예: 어요;에요;예요;니다 )",
                     font=F_SM, color=C["subtext"]).pack(pady=(14, 6), padx=16, anchor="w")
                entry = _UndoEntry(d, width=410, height=32, font=F,
                                     fg_color=C["input_bg"], border_color=C["border"],
                                     text_color=C["text"], corner_radius=7)
                entry.pack(padx=16)
                entry.insert(0, c5_opt_delimiters_var.get())
                def _ok():
                    c5_opt_delimiters_var.set(entry.get().strip())
                    d.destroy()
                br = ctk.CTkFrame(d, fg_color="transparent")
                br.pack(pady=8)
                _btn(br, "확인", _ok, w=80, h=30, small=True).pack(side="left", padx=4)
                _btn(br, "취소", d.destroy, w=80, h=30, small=True,
                     color=C["subtext"]).pack(side="left", padx=4)

            opt_row0 = ctk.CTkFrame(c5_opt_frame, fg_color="transparent")
            opt_row0.pack(fill="x", padx=14, pady=(10, 4))
            _btn(opt_row0, "구분 기준", _open_delimiters_dlg, w=90, h=28, small=True).pack(side="left", padx=(0, 8))
            _lbl(opt_row0, "미설정 시 . ! ? 기준 / 설정 시 해당 단어 기준",
                 font=F_SM, color=C["subtext"]).pack(side="left")

            # 1행: 1.포스팅 수집수 | 2.앞뒤 문단 빼기 | 3.단락 구분
            opt_row1 = ctk.CTkFrame(c5_opt_frame, fg_color="transparent")
            opt_row1.pack(fill="x", padx=14, pady=(10, 6))
            _lbl(opt_row1, "1. 수집수", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 6))
            _opt_entry(opt_row1, c5_opt_count_var, w=52)
            _lbl(opt_row1, "개", font=F_SM, color=C["subtext"]).pack(side="left")
            _div(opt_row1)
            _lbl(opt_row1, "2. 앞뒤 문단 빼기", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 6))
            _opt_entry(opt_row1, c5_opt_skip_var, w=52)
            _lbl(opt_row1, "개 ( 0=끄기 )", font=F_SM, color=C["subtext"]).pack(side="left")
            _div(opt_row1)
            _lbl(opt_row1, "3. 단락 구분", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 6))
            _opt_entry(opt_row1, c5_opt_chunk_var, w=68)
            _lbl(opt_row1, "( 예: 2~4 / 0=끄기 )", font=F_SM, color=C["subtext"]).pack(side="left")

            # 2행: 4.글자수 제한 | 5.참조 헤더 | 6.참조 바텀
            opt_row2 = ctk.CTkFrame(c5_opt_frame, fg_color="transparent")
            opt_row2.pack(fill="x", padx=14, pady=(0, 4))
            _lbl(opt_row2, "4. 글자수 제한", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 6))
            _opt_entry(opt_row2, c5_opt_maxch_var, w=72)
            _lbl(opt_row2, "자 ( 0=끄기 )", font=F_SM, color=C["subtext"]).pack(side="left")
            _div(opt_row2)
            _lbl(opt_row2, "5. 참조 헤더", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 6))
            _opt_entry(opt_row2, c5_opt_header_var, w=120)
            _div(opt_row2)
            _lbl(opt_row2, "6. 참조 바텀", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 6))
            _opt_entry(opt_row2, c5_opt_bottom_var, w=160)

            # 3행: 7.맨끝 문구
            opt_row4 = ctk.CTkFrame(c5_opt_frame, fg_color="transparent")
            opt_row4.pack(fill="x", padx=14, pady=(0, 12))
            _lbl(opt_row4, "7. 맨끝 문구(업체 입력시)", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 6))
            _opt_entry(opt_row4, c5_opt_ending_var, w=300)

            # ── 테스트 영역 (상단) ────────────────────────────
            c5_top = ctk.CTkFrame(tab5_content, fg_color="transparent")
            c5_top.pack(fill="x", pady=(0, 6))
            _lbl(c5_top, "키워드", font=F_SMB, color=C["subtext"]).pack(side="left", padx=(0, 8))
            c5_kw_entry = _UndoEntry(
                c5_top, height=32, font=F,
                fg_color=C["input_bg"], border_color=C["border"],
                text_color=C["text"], corner_radius=7,
            )
            c5_kw_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            c5_status = _lbl(c5_top, "", font=F_SM, color=C["subtext"])
            c5_status.pack(side="left", padx=(0, 8))

            c5_result = tk.Text(
                tab5_content, font=F_SM,
                bg=C["input_bg"], fg=C["text"],
                insertbackground=C["text"],
                relief="flat", bd=0, padx=6, pady=4, wrap="word",
                highlightthickness=1, highlightbackground=C["border"],
                state="disabled",
            )
            c5_result.pack(fill="both", expand=True)

            def _c5_collect():
                kw = c5_kw_entry.get().strip()
                if not kw:
                    c5_status.configure(text="키워드를 입력하세요.", text_color=C["err"])
                    return
                try:
                    cnt  = int(c5_opt_count_var.get())
                    skip = int(c5_opt_skip_var.get())
                except ValueError:
                    cnt, skip = 5, 0
                c5_status.configure(text="🔄 수집 중...", text_color=C["accent"])
                c5_result.configure(state="normal")
                c5_result.delete("1.0", "end")
                c5_result.insert("1.0", "수집 중...\n")
                c5_result.configure(state="disabled")
                c5_collect_btn.configure(state="disabled")

                def _run():
                    try:
                        def _prog(done, total):
                            dlg.after(0, lambda d=done, t=total:
                                c5_status.configure(text=f"🔄 {d}/{t} 수집 중...", text_color=C["accent"]))
                        chunk = c5_opt_chunk_var.get().strip() or "0"
                        try: maxch = int(c5_opt_maxch_var.get())
                        except Exception: maxch = 0
                        dlims = [x.strip() for x in c5_opt_delimiters_var.get().split(';') if x.strip()] or None
                        results = _nc.collect(kw, cnt, skip=skip, chunk_range=chunk,
                                              maxchars=maxch, delimiters=dlims, progress_cb=_prog)
                        lines = [c5_opt_header_var.get().strip() or "[인기글 참조]"]
                        for _title, text, _url in results:
                            lines.append(f"\n{text}")
                        if bottom := c5_opt_bottom_var.get().strip():
                            lines.append(f"\n{bottom}")
                        output = "\n".join(lines) if results else "결과 없음"

                        def _done():
                            c5_result.configure(state="normal")
                            c5_result.delete("1.0", "end")
                            c5_result.insert("1.0", output)
                            c5_result.configure(state="disabled")
                            c5_status.configure(text=f"✅ {len(results)}개 수집 완료", text_color=C["ok"])
                            c5_collect_btn.configure(state="normal")
                        dlg.after(0, _done)
                    except Exception as e:
                        def _err(msg=str(e)):
                            c5_result.configure(state="normal")
                            c5_result.delete("1.0", "end")
                            c5_result.insert("1.0", f"오류: {msg}")
                            c5_result.configure(state="disabled")
                            c5_status.configure(text="❌ 오류", text_color=C["err"])
                            c5_collect_btn.configure(state="normal")
                        dlg.after(0, _err)

                _threading.Thread(target=_run, daemon=True).start()

            c5_collect_btn = _btn(c5_top, "수집", _c5_collect, w=70, h=32)
            c5_collect_btn.pack(side="left")

            _t5_save[0] = _c5_save_opts

        # ── 탭6 내용: 자동봇 설정 ────────────────────────
        import yaml as _yaml_t6
        _auto_cfg_path = _BASE_DIR / "auto" / "config.yaml"
        try:
            with open(_auto_cfg_path, encoding="utf-8") as _f6:
                _auto_cfg = _yaml_t6.safe_load(_f6) or {}
        except Exception:
            _auto_cfg = {}
        _a6sc  = _auto_cfg.get("scenario", {})
        _a6act = _auto_cfg.get("actions", {})
        _a6br  = _auto_cfg.get("browser", {})

        _t6_headless   = ctk.BooleanVar(value=_a6br.get("headless", True))
        _t6_act_keys   = ["home","search","news","blog","mail","kin","shopping","weather","finance"]
        _t6_act_lbls   = ["홈 탐색","키워드 검색","뉴스 읽기","블로그 검색","메일 확인","지식iN","쇼핑 탐색","날씨 확인","증권 확인"]
        _t6_act_vars   = {k: ctk.BooleanVar(value=_a6act.get(k, True)) for k in _t6_act_keys}
        _t6_c = {}       # entry widget refs — populated by _build_t6_widgets
        _t6_built = [False]

        def _build_t6_widgets():
            t6_sf = ctk.CTkFrame(tab6_content, fg_color="transparent")
            t6_sf.pack(fill="both", expand=True, padx=0, pady=0)

            _lbl(t6_sf, "브라우저", font=F_B).pack(anchor="w", pady=(8, 4))
            _t6_br_card = ctk.CTkFrame(t6_sf, fg_color=C["accent_bg"], corner_radius=8)
            _t6_br_card.pack(fill="x", pady=(0, 10))
            ctk.CTkCheckBox(_t6_br_card, text="백그라운드 실행 (headless — 브라우저 창 숨김)",
                            variable=_t6_headless, font=F,
                            text_color=C["text"], fg_color=C["accent"],
                            hover_color=C["accent_h"], checkmark_color="white",
                            ).pack(anchor="w", padx=12, pady=8)

            _lbl(t6_sf, "액션 사용", font=F_B).pack(anchor="w", pady=(0, 4))
            _t6_act_card = ctk.CTkFrame(t6_sf, fg_color=C["accent_bg"], corner_radius=8)
            _t6_act_card.pack(fill="x", pady=(0, 10))
            for _i6, (_k6, _l6) in enumerate(zip(_t6_act_keys, _t6_act_lbls)):
                _r6, _c6 = divmod(_i6, 5)
                ctk.CTkCheckBox(_t6_act_card, text=_l6, variable=_t6_act_vars[_k6],
                                font=F, text_color=C["text"],
                                fg_color=C["accent"], hover_color=C["accent_h"],
                                checkmark_color="white",
                                ).grid(row=_r6, column=_c6, sticky="w",
                                       padx=(12 if _c6 == 0 else 0, 16), pady=5)

            _lbl(t6_sf, "수치 설정", font=F_B).pack(anchor="w", pady=(0, 4))
            _t6_num_card = ctk.CTkFrame(t6_sf, fg_color=C["accent_bg"], corner_radius=8)
            _t6_num_card.pack(fill="x", pady=(0, 8))

            def _t6e(parent, row, col, w=58):
                e = _UndoEntry(parent, height=28, width=w, font=F_SM,
                               fg_color=C["input_bg"], border_color=C["border"],
                               text_color=C["text"], corner_radius=7)
                e.grid(row=row, column=col, sticky="w", padx=(0, 4), pady=3)
                return e

            def _sc_rng(key, def_min, def_max):
                v = _a6sc.get(key, {})
                if isinstance(v, dict):
                    return v.get("min", def_min), v.get("max", def_max)
                return (v, v) if v else (def_min, def_max)

            # 수치 grid — 좌우 2항목씩 4행
            # cols: 0=좌라벨, 1=min, 2=~, 3=max, 4=간격, 5=우라벨, 6=min, 7=~, 8=max
            _rg = ctk.CTkFrame(_t6_num_card, fg_color="transparent")
            _rg.pack(fill="x", pady=(4, 4))
            _rg.columnconfigure(4, minsize=10)

            def _gl(text, row, col, lx=(12, 8), py=3):
                _lbl(_rg, text, font=F_SM, color=C["subtext"]).grid(
                    row=row, column=col, sticky="w", padx=lx, pady=py)

            def _gt(row, col):
                _lbl(_rg, "~", font=F_SM, color=C["subtext"]).grid(
                    row=row, column=col, padx=2, pady=3)

            # row 0: 검색 클릭 수 | 뉴스 기사 수
            _srch_min, _srch_max = _sc_rng("search_click_count", 2, 4)
            _news_min, _news_max = _sc_rng("news_article_count", 2, 5)
            _gl("검색 클릭 수", 0, 0)
            _t6_srch_min_e = _t6e(_rg, 0, 1); _t6_srch_min_e.insert(0, str(_srch_min))
            _gt(0, 2)
            _t6_srch_max_e = _t6e(_rg, 0, 3); _t6_srch_max_e.insert(0, str(_srch_max))
            _gl("뉴스 기사 수", 0, 5, lx=(16, 8))
            _t6_news_min_e = _t6e(_rg, 0, 6); _t6_news_min_e.insert(0, str(_news_min))
            _gt(0, 7)
            _t6_news_max_e = _t6e(_rg, 0, 8); _t6_news_max_e.insert(0, str(_news_max))

            # row 1: 메일 읽기 수 | 실행당 키워드 수
            _mail_min, _mail_max = _sc_rng("mail_read_count", 1, 3)
            _gl("메일 읽기 수", 1, 0)
            _t6_mail_min_e = _t6e(_rg, 1, 1); _t6_mail_min_e.insert(0, str(_mail_min))
            _gt(1, 2)
            _t6_mail_max_e = _t6e(_rg, 1, 3); _t6_mail_max_e.insert(0, str(_mail_max))
            _gl("실행당 키워드 수", 1, 5, lx=(16, 8))
            _t6_kwcnt_e = _t6e(_rg, 1, 6); _t6_kwcnt_e.insert(0, str(_a6sc.get("keyword_count", 20)))

            # row 2: 액션 사이 대기 | 라운드 사이 휴식
            _gl("액션 사이 대기 (초)", 2, 0)
            _t6_dmin_e = _t6e(_rg, 2, 1); _t6_dmin_e.insert(0, str(_a6sc.get("between_action_delay", {}).get("min", 5)))
            _gt(2, 2)
            _t6_dmax_e = _t6e(_rg, 2, 3); _t6_dmax_e.insert(0, str(_a6sc.get("between_action_delay", {}).get("max", 15)))
            _gl("라운드 사이 휴식 (초)", 2, 5, lx=(16, 8))
            _t6_rmin_e = _t6e(_rg, 2, 6); _t6_rmin_e.insert(0, str(_a6sc.get("round_rest", {}).get("min", 30)))
            _gt(2, 7)
            _t6_rmax_e = _t6e(_rg, 2, 8); _t6_rmax_e.insert(0, str(_a6sc.get("round_rest", {}).get("max", 90)))

            # row 3: 페이지 체류 시간
            _gl("페이지 체류 시간 (초)", 3, 0, py=(3, 8))
            _t6_dwell_min_e = _t6e(_rg, 3, 1); _t6_dwell_min_e.insert(0, str(_a6sc.get("page_dwell", {}).get("min", 4)))
            _gt(3, 2)
            _t6_dwell_max_e = _t6e(_rg, 3, 3); _t6_dwell_max_e.insert(0, str(_a6sc.get("page_dwell", {}).get("max", 12)))

            _lbl(t6_sf, "키워드 풀 (;로 구분)", font=F_B).pack(anchor="w", pady=(0, 4))
            _kw_outer = ctk.CTkFrame(t6_sf, fg_color=C["input_bg"],
                                     border_color=C["border"], border_width=1,
                                     corner_radius=6)
            _kw_outer.pack(fill="x", pady=(0, 8))
            _kw_outer.pack_propagate(True)
            _t6_kw_sb = tk.Scrollbar(_kw_outer)
            _t6_kw_sb.pack(side="right", fill="y", pady=2)
            _t6_kw_box = tk.Text(_kw_outer, height=5, font=F_SM,
                                  bg=C["input_bg"], fg=C["text"],
                                  insertbackground=C["text"],
                                  relief="flat", bd=0, padx=6, pady=4,
                                  wrap="char", highlightthickness=0,
                                  yscrollcommand=_t6_kw_sb.set)
            _t6_kw_box.pack(side="left", fill="both", expand=True)
            _t6_kw_sb.config(command=_t6_kw_box.yview)
            kw_text = ";".join(_auto_cfg.get("keywords", []))
            if kw_text:
                _t6_kw_box.insert("1.0", kw_text)
            _t6_c.update({
                "srch_min": _t6_srch_min_e, "srch_max": _t6_srch_max_e,
                "news_min": _t6_news_min_e, "news_max": _t6_news_max_e,
                "mail_min": _t6_mail_min_e, "mail_max": _t6_mail_max_e,
                "kwcnt": _t6_kwcnt_e, "dmin": _t6_dmin_e, "dmax": _t6_dmax_e,
                "rmin": _t6_rmin_e, "rmax": _t6_rmax_e,
                "dwell_min": _t6_dwell_min_e, "dwell_max": _t6_dwell_max_e,
                "kw": _t6_kw_box,
            })

        def _save_auto():
            import yaml as _yaml_sv
            try:
                with open(_auto_cfg_path, encoding="utf-8") as _f:
                    _c = _yaml_sv.safe_load(_f) or {}
            except Exception:
                _c = {}
            _c.setdefault("browser", {})["headless"] = _t6_headless.get()
            _c["actions"] = {k: v.get() for k, v in _t6_act_vars.items()}
            _sc2 = _c.setdefault("scenario", {})
            def _iv(e, d):
                if e is None: return d
                try: return int(e.get().strip())
                except Exception: return d
            _sc2["search_click_count"] = {"min": _iv(_t6_c.get("srch_min"), 2), "max": _iv(_t6_c.get("srch_max"), 4)}
            _sc2["news_article_count"] = {"min": _iv(_t6_c.get("news_min"), 2), "max": _iv(_t6_c.get("news_max"), 5)}
            _sc2["mail_read_count"]    = {"min": _iv(_t6_c.get("mail_min"), 1), "max": _iv(_t6_c.get("mail_max"), 3)}
            _sc2["keyword_count"]               = _iv(_t6_c.get("kwcnt"), 20)
            _sc2.setdefault("between_action_delay", {})
            _sc2["between_action_delay"]["min"] = _iv(_t6_c.get("dmin"), 5)
            _sc2["between_action_delay"]["max"] = _iv(_t6_c.get("dmax"), 15)
            _sc2.setdefault("round_rest", {})
            _sc2["round_rest"]["min"]           = _iv(_t6_c.get("rmin"), 30)
            _sc2["round_rest"]["max"]           = _iv(_t6_c.get("rmax"), 90)
            _sc2.setdefault("page_dwell", {})
            _sc2["page_dwell"]["min"]           = _iv(_t6_c.get("dwell_min"), 4)
            _sc2["page_dwell"]["max"]           = _iv(_t6_c.get("dwell_max"), 12)
            _kw_box = _t6_c.get("kw")
            _kw_raw = _kw_box.get("1.0", "end").strip() if _kw_box else ""
            _c["keywords"] = [k.strip() for k in _kw_raw.split(";") if k.strip()]
            try:
                with open(_auto_cfg_path, "w", encoding="utf-8") as _f:
                    _yaml_sv.dump(_c, _f, allow_unicode=True,
                                  default_flow_style=False, sort_keys=False)
            except Exception as _e:
                import tkinter.messagebox as _mb2
                _mb2.showerror("자동봇 설정 저장 실패", str(_e), parent=dlg)
                return
            _save_btn.configure(text="✅ 저장됨", fg_color=C["ok"])
            dlg.after(2000, lambda: _save_btn.configure(text="저장", fg_color=C["accent"]))

        # ── 탭1을 기본으로 표시 ───────────────────────────
        def _do_save():
            n = active_tab[0]
            if n in (1, 2):              _save()
            elif n == 3 and _t3_save[0]: _t3_save[0]()
            elif n == 4 and _t4_save[0]: _t4_save[0]()
            elif n == 5 and _t5_save[0]: _t5_save[0]()
            elif n == 6:                 _save_auto()

        # ── 하단 버튼 내용 채우기 ─────────────────────────
        save_notify = None  # 미사용 (저장 버튼 텍스트로 대체)

        def _save():
            working_names[cur_idx[0]]   = name_entry.get().strip() or f"옵션 {cur_idx[0]+1}"
            working[cur_idx[0]]         = txt1.get("1.0", "end").strip()
            working2[cur_idx[0]]        = txt2.get("1.0", "end").strip()
            if not working_collect[cur_idx[0]]:
                working_kw2[cur_idx[0]] = kw2_var.get()
            working_topic[cur_idx[0]]   = topic_var.get()
            working_collect[cur_idx[0]] = collect_var.get()
            working_enabled[cur_idx[0]] = enabled_var.get()
            working_guest[cur_idx[0]]   = guest_var.get()
            self._prompts             = list(working)
            self._prompts2            = list(working2)
            self._kw2_enabled         = list(working_kw2)
            self._topic_enabled       = list(working_topic)
            self._collect_enabled     = list(working_collect)
            self._option_enabled      = list(working_enabled)
            self._prompt_names        = list(working_names)
            self._guest_prompt_enabled = list(working_guest)
            try: self._collect_count    = int(c5_opt_count_var.get())
            except Exception: pass
            try: self._collect_skip     = int(c5_opt_skip_var.get())
            except Exception: pass
            self._collect_chunk         = c5_opt_chunk_var.get().strip() or "0"
            try: self._collect_maxchars = int(c5_opt_maxch_var.get())
            except Exception: pass
            self._collect_header        = c5_opt_header_var.get().strip() or "[인기글 참조]"
            self._collect_delimiters    = c5_opt_delimiters_var.get().strip()
            self._collect_ending        = c5_opt_ending_var.get().strip()
            self._collect_bottom        = c5_opt_bottom_var.get().strip()
            self._selected_prompt_idx = cur_idx[0]
            self._var_settings        = {k: v for k, v in w_var.items()}
            self._var_settings_picsum = {k: v for k, v in w_var_picsum.items()}
            self._var_settings_flickr = {k: v for k, v in w_var_flickr.items()}
            try:
                self._max_width = max(0, int(mw_entry.get().strip() or "0"))
            except (ValueError, AttributeError):
                self._max_width = 0
            try:
                self._picsum_width  = max(100, int(_ps_w_entry.get().strip() or "900"))
            except (ValueError, AttributeError):
                self._picsum_width = 900
            try:
                self._picsum_height = max(100, int(_ps_h_entry.get().strip() or "700"))
            except (ValueError, AttributeError):
                self._picsum_height = 700
            try:
                self._flickr_width  = max(100, int(_fl_w_entry.get().strip() or "1000"))
            except (ValueError, AttributeError):
                self._flickr_width = 1000
            try:
                self._flickr_height = max(100, int(_fl_h_entry.get().strip() or "1000"))
            except (ValueError, AttributeError):
                self._flickr_height = 1000
            try:
                self._flickr_keyword = _fl_kw_entry.get().strip()
            except AttributeError:
                pass
            self._rebuild_selector()
            self._update_kw2_state()
            self._update_topic_state()
            self._save_prefs()
            gh_tok = gh_token_entry.get().strip()
            if gh_tok != config.GITHUB_TOKEN:
                config.GITHUB_TOKEN = gh_tok
                try:
                    existing = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
                    lines = [l for l in existing.splitlines()
                             if not l.startswith("GITHUB_TOKEN=")]
                    lines.append(f"GITHUB_TOKEN={gh_tok}")
                    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
                except Exception:
                    pass
            _save_btn.configure(text="✅ 저장됨", fg_color=C["ok"])
            dlg.after(2000, lambda: _save_btn.configure(text="저장", fg_color=C["accent"]))

        def _clear():
            if active_tab[0] == 2:
                _clear_map = {
                    "picsum":     (slider_refs_picsum, w_var_picsum),
                    "flickr":     (slider_refs_flickr, w_var_flickr),
                    "img_select": (slider_refs, w_var),
                }
                sl_list, wd = _clear_map.get(var_mode[0], (slider_refs, w_var))
                for sl_n, sl_x, km, kx, rl, f, s in sl_list:
                    dn, dx = _VAR_DEFAULTS[km], _VAR_DEFAULTS[kx]
                    wd[km] = dn; wd[kx] = dx
                    sl_n.set(dn); sl_x.set(dx)
                    rl.configure(text=f"{f.format(dn)} ~ {f.format(dx)}")
            else:
                txt1.delete("1.0", "end")
                txt2.configure(state="normal")
                txt2.delete("1.0", "end")
                _refresh_txt2()

        _save_btn = _btn(btn_row, "저장", _do_save, w=100, h=34)
        _save_btn.pack(side="right", padx=(6, 0))
        _clear_btn_ref[0] = _btn(btn_row, "초기화", _clear, w=80, h=34,
                                 color=C["subtext"], hover=C["text"])
        _show_tab(1)

        # ── 원격 프롬프트 동기화 내용 채우기 ──────────────
        sync_top = ctk.CTkFrame(sync_area, fg_color="transparent")
        sync_top.pack(fill="x", pady=(0, 4))
        _lbl(sync_top, "원격 프롬프트 동기화", font=F_SMB, color=C["subtext"]).pack(side="left")
        self.sync_status_lbl = ctk.CTkLabel(sync_top, text="", font=F_SM, text_color=C["subtext"])
        self.sync_status_lbl.pack(side="right")

        token_row = ctk.CTkFrame(sync_area, fg_color="transparent")
        token_row.pack(fill="x", pady=(0, 4))
        _lbl(token_row, "🐙 GitHub 토큰", font=F_SM, color=C["subtext"]).pack(side="left", padx=(0, 8))
        gh_token_entry = _UndoEntry(
            token_row, height=28, font=F_SM,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], corner_radius=7,
            placeholder_text="ghp_xxxxxxxxxxxx")
        gh_token_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if config.GITHUB_TOKEN:
            gh_token_entry.insert(0, config.GITHUB_TOKEN)
        _link(token_row, "→ 발급", "https://github.com/settings/tokens/new?scopes=gist").pack(side="left")

        sync_row = ctk.CTkFrame(sync_area, fg_color="transparent")
        sync_row.pack(fill="x")
        sync_url_entry = _UndoEntry(
            sync_row, height=32, font=F_SM,
            fg_color=C["input_bg"], border_color=C["border"],
            text_color=C["text"], corner_radius=7,
            placeholder_text="https://gist.githubusercontent.com/.../prompts.json")
        sync_url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if self._remote_url:
            sync_url_entry.insert(0, self._remote_url)

        def _do_sync():
            raw = sync_url_entry.get().strip()
            raw = re.sub(r'/raw/[0-9a-f]{40}/', '/raw/', raw)
            sync_url_entry.delete(0, "end")
            sync_url_entry.insert(0, raw)
            self._remote_url = raw
            self._save_prefs()
            threading.Thread(target=self._sync_remote_prompts, daemon=True).start()

        ctk.CTkButton(
            sync_row, text="동기화", command=_do_sync,
            width=72, height=32, font=F_SM,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="white", corner_radius=7,
        ).pack(side="left", padx=(0, 6))

        def _do_upload_gist():
            data = {
                "prompt_names":   list(self._prompt_names),
                "prompts":        list(self._prompts),
                "prompts2":       list(self._prompts2),
                "kw2_enabled":    list(self._kw2_enabled),
                "option_enabled":   list(self._option_enabled),
                "topic_enabled":    list(self._topic_enabled),
                "collect_enabled":  list(self._collect_enabled),
                "collect_count":    self._collect_count,
                "collect_skip":     self._collect_skip,
                "collect_chunk":    self._collect_chunk,
                "collect_maxchars": self._collect_maxchars,
                "collect_header":   self._collect_header,
                "topic_lists":      dict(self._topic_lists),
                "topic_rows":       [list(r) for r in self._topic_rows],
                "var_settings":        {k: v for k, v in self._var_settings.items()},
                "var_settings_picsum": {k: v for k, v in self._var_settings_picsum.items()},
                "var_settings_flickr": {k: v for k, v in self._var_settings_flickr.items()},
                "max_width":      self._max_width,
                "mac_entries":    list(self._mac_entries),
                "guest_prompt_enabled": list(self._guest_prompt_enabled),
            }
            try:
                import yaml as _yaml_up
                _auto_p = _BASE_DIR / "auto" / "config.yaml"
                with open(_auto_p, encoding="utf-8") as _f:
                    data["auto_config"] = _yaml_up.safe_load(_f) or {}
            except Exception:
                pass
            self.sync_status_lbl.configure(
                text="🔄 Gist 업로드 중...", text_color=C["accent"])
            threading.Thread(
                target=self._upload_to_gist,
                args=(data, self.sync_status_lbl, sync_url_entry),
                daemon=True,
            ).start()

        ctk.CTkButton(
            sync_row, text="Gist 업로드", command=_do_upload_gist,
            width=90, height=32, font=F_SM,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="white", corner_radius=7,
        ).pack(side="left", padx=(6, 0))

        dlg.after(50, lambda: dlg.wm_attributes("-alpha", 1))

    def _collect_reference(self, kw: str) -> str:
        """인기글 수집 후 참조 블록 반환. 실패 시 빈 문자열."""
        import naver_collector as _nc
        try:
            dlims = [x.strip() for x in self._collect_delimiters.split(';') if x.strip()] or None
            results = _nc.collect(kw, self._collect_count, self._collect_skip,
                                  chunk_range=self._collect_chunk,
                                  maxchars=self._collect_maxchars,
                                  delimiters=dlims)
            if not results:
                return ""
            lines = [self._collect_header]
            for _title, text, _url in results:
                lines.append(f"\n{text}")
            if self._collect_bottom:
                lines.append(f"\n{self._collect_bottom}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _gen_all(self, kw, kw2, collect_kw2, count):
        self._start_timer()
        try:
            err_box = []
            idx = self._selected_prompt_idx

            self._set_text_status("생성 중...", 0.1)
            self._set_img_status("이미지 생성 중...", 0.05)

            img_done = threading.Event()

            # 주제 모드면 랜덤 항목 사전 추출 — 이미지·글 모두 동일 항목 사용
            _topic_item = None
            if self._topic_enabled[idx]:
                _stored = self._topic_lists.get(kw, [])
                if _stored:
                    _topic_item = random.choice(_stored)
            _img_kw = _topic_item if _topic_item else kw

            # 이미지 생성 — 글 생성과 동시 실행 (브라우저 대기 없이 바로 시작)
            def image_worker():
                try:
                    img_prompt = content_generator.get_image_prompt(_img_kw)
                    self._gen_images(img_prompt, count, kw=_img_kw)
                except Exception as e:
                    err_box.append(f"이미지 오류: {e}")
                    self._set_img_status("오류", 0, C["err"])
                finally:
                    img_done.set()

            threading.Thread(target=image_worker, daemon=True).start()

            self._ensure_browser()

            # Gemini 글 생성 — 이미지 생성과 동시 실행
            try:
                effective_kw = kw
                if _topic_item:
                    effective_kw = f"{kw} 전문 블로거가 쓸는 {_topic_item}"
                parts = []
                if self._collect_enabled[idx]:
                    self._set_text_status("자료 수집 중...", 0.05)
                    ref = self._collect_reference(kw)
                    self._set_text_status("수집 완료", 0.15)
                    parts.append(effective_kw)
                    parts.append("키워드로 블로그 포스팅을 작성.")
                    parts.append("참고 제목은 아래와 같아")
                    if collect_kw2:
                        parts.append(collect_kw2)
                    if ref:
                        parts.append(ref)
                    if self._prompts[idx]:
                        parts.append(self._prompts[idx])
                    if kw2:
                        parts.append(kw2)
                        if self._collect_ending:
                            parts.append(self._collect_ending)
                else:
                    parts.append(effective_kw)
                    if self._prompts[idx]:
                        parts.append(self._prompts[idx])
                    # 일반 주제 모드
                    if kw2:
                        parts.append(kw2)
                    if self._kw2_enabled[idx] and self._prompts2[idx]:
                        parts.append(self._prompts2[idx])
                self._set_text_status("생성 중...", 0.2)
                for _attempt in range(2):
                    try:
                        result = content_generator.generate("\n".join(parts), "", cancel_event=self._stop_event)
                        break
                    except RuntimeError as e:
                        if _attempt == 0 and "시간 초과" in str(e) and not self._stop_event.is_set():
                            self._set_text_status("응답 없음, 재시도 중...", 0.3)
                            continue
                        raise
                self._last_body = result["content"]
                self._set_content(self._last_body)
                self._set_text_status("완료!", 1.0, C["ok"])
            except Exception as e:
                if self._stop_event.is_set():
                    self._set_text_status("중단됨", 0, C["err"])
                else:
                    _emsg = "제미나이 1076 오류입니다. 다시 시도해주세요." if "gemini_server_error" in str(e) else f"글 오류: {e}"
                    err_box.append(_emsg)
                    self._set_text_status("오류", 0, C["err"])

            img_done.wait()

            if self._stop_event.is_set():
                self._set_status("⏹  중단됨", color=C["err"])
            elif err_box:
                self._set_status(f"❌  {err_box[0]}", color=C["err"])
            else:
                self._set_status("✅  완료!", color=C["ok"])
        except Exception as e:
            self._set_status(f"❌  오류: {e}", color=C["err"])
        finally:
            self._stop_timer()
            self._lock_btns(False)

    # ── 글만 생성 ────────────────────────────────────────
    def _start_text_only(self):
        kw = self._check_ready()
        if not kw: return
        self._stop_event.clear()
        idx = self._selected_prompt_idx
        kw2 = (self.kw2_entry.get().strip()
               if not self._topic_enabled[idx] and (self._kw2_enabled[idx] or not self._collect_enabled[idx])
               else "")
        collect_kw2 = self.collect_kw_entry.get().strip() if self._collect_enabled[idx] else ""
        self._reset_outputs(reset_images=False)
        self._lock_btns(True)
        self.timer_label.configure(text="", text_color=C["accent"])
        threading.Thread(target=self._gen_text_only, args=(kw, kw2, collect_kw2), daemon=True).start()

    def _gen_text_only(self, kw, kw2, collect_kw2=""):
        self._ensure_browser()
        self._start_timer()
        idx = self._selected_prompt_idx
        try:
            self._set_text_status("생성 중...", 0.1)
            effective_kw = kw
            if self._topic_enabled[idx]:
                stored = self._topic_lists.get(kw, [])
                if stored:
                    effective_kw = f"{kw} 전문 블로거가 쓸는 {random.choice(stored)}"
            parts = []
            if self._collect_enabled[idx]:
                self._set_text_status("자료 수집 중...", 0.05)
                self._set_status("🔄  자료 수집 중...", color=C["accent"])
                ref = self._collect_reference(kw)
                self._set_text_status("수집 완료", 0.15)
                parts.append(effective_kw)
                parts.append("키워드로 블로그 포스팅을 작성.")
                parts.append("참고 제목은 아래와 같아")
                if collect_kw2:
                    parts.append(collect_kw2)
                if ref:
                    parts.append(ref)
                if self._prompts[idx]:
                    parts.append(self._prompts[idx])
                if kw2:
                    parts.append(kw2)
                    if self._collect_ending:
                        parts.append(self._collect_ending)
            else:
                parts.append(effective_kw)
                if self._prompts[idx]:
                    parts.append(self._prompts[idx])
                # 일반 주제 모드
                if kw2:
                    parts.append(kw2)
                if self._kw2_enabled[idx] and self._prompts2[idx]:
                    parts.append(self._prompts2[idx])
            self._set_text_status("생성 중...", 0.2)
            for _attempt in range(2):
                try:
                    result = content_generator.generate("\n".join(parts), "", cancel_event=self._stop_event)
                    break
                except RuntimeError as e:
                    if _attempt == 0 and "시간 초과" in str(e) and not self._stop_event.is_set():
                        self._set_text_status("응답 없음, 재시도 중...", 0.3)
                        continue
                    raise
            self._last_body = result["content"]
            self._set_content(self._last_body)
            self._set_text_status("완료!", 1.0, C["ok"])
            self._set_status("✅  글 생성 완료!", color=C["ok"])
        except Exception as e:
            if self._stop_event.is_set():
                self._set_text_status("중단됨", 0, C["err"])
                self._set_status("⏹  중단됨", color=C["err"])
            else:
                _emsg = "제미나이 1076 오류입니다. 다시 시도해주세요." if "gemini_server_error" in str(e) else f"오류: {e}"
                self._set_text_status("오류", 0, C["err"])
                self._set_status(f"❌  {_emsg}", color=C["err"])
        finally:
            self._stop_timer()
            self._lock_btns(False)

    # ── 이미지만 생성 ────────────────────────────────────
    def _start_image_only(self):
        src = getattr(self, "_img_source", "AI")
        if src in ("픽숨", "플리커"):
            kw = self.keyword_entry.get().strip() if not self._is_secret_mode() else ""
        else:
            kw = self._check_ready()
            if not kw: return
        if src not in ("픽숨", "플리커") and (not config.CF_ACCOUNT_ID or not config.CF_API_TOKEN):
            self._set_status("⚠️  설정 탭에서 Cloudflare 자격증명을 먼저 입력해 주세요.", color=C["err"]); return
        self._stop_event.clear()
        count = self._get_img_count()
        self._init_image_slots(count)
        self._lock_btns(True)
        self.timer_label.configure(text="", text_color=C["accent"])
        threading.Thread(target=self._gen_img_only, args=(kw, count), daemon=True).start()

    def _gen_img_only(self, kw, count):
        self._ensure_browser()
        self._start_timer()
        idx = self._selected_prompt_idx
        try:
            self._set_img_status("프롬프트 준비 중...", 0)
            _img_kw = kw
            if self._topic_enabled[idx]:
                _stored = self._topic_lists.get(kw, [])
                if _stored:
                    _img_kw = random.choice(_stored)
            try:
                prompt = content_generator.get_image_prompt(_img_kw)
            except Exception:
                prompt = f"{_img_kw} related scene, highly detailed, realistic"
            self._gen_images(prompt, count, kw=_img_kw)
            self._set_status("✅  이미지 생성 완료!", color=C["ok"])
        except Exception as e:
            self._set_img_status("오류", 0, C["err"])
            self._set_status(f"❌  오류: {e}", color=C["err"])
        finally:
            self._stop_timer()
            self._lock_btns(False)

    def _ensure_browser(self):
        if not gemini_scraper.is_connected():
            self._set_status("🌐  글 생성 준비 중... 잠시 기다려 주세요.")
            for _ in range(60):
                time.sleep(0.5)
                if gemini_scraper.is_connected():
                    break

    # ── 공통 이미지 생성 루프 ─────────────────────────────
    _IMG_SUBJECTS = [
        "macro close-up of raw materials and natural textures",
        "abstract flat lay arrangement of objects on plain surface",
        "overhead top-down view of items on wooden table",
        "blurred bokeh background with single object in focus",
        "clean studio still life composition on white background",
        "natural materials and organic textures close-up",
        "minimalist object arrangement on neutral background",
        "detailed surface texture and pattern close-up",
    ]
    _IMG_STYLES = [
        "photorealistic professional photography, sharp focus, 4K ultra detailed",
        "cinematic film shot, dramatic lighting, high contrast, rich colors",
        "editorial magazine style, clean minimal composition, studio quality",
        "documentary photography, authentic candid atmosphere, natural tones",
        "commercial advertising photo, vibrant colors, polished finish",
        "moody artistic photography, deep shadows, selective lighting",
    ]
    _IMG_MOODS = [
        "bright clean modern aesthetic, crisp white tones",
        "warm golden cozy atmosphere, soft amber light",
        "cool professional premium feel, blue-tinted natural light",
        "vibrant colorful lively, saturated vivid tones",
        "dramatic bold contrast, dark background with spot lighting",
        "soft pastel natural, airy and fresh lighting",
        "rich deep tones, luxurious and polished look",
        "minimalist spacious, negative space, elegant simplicity",
    ]

    def _gen_images_picsum(self, count, kw=""):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import urllib.request as _ur, io as _io
        pw = max(100, self._picsum_width)
        ph = max(100, self._picsum_height)
        url = f"https://picsum.photos/{pw}/{ph}"

        def _fetch(idx):
            if self._stop_event.is_set():
                return idx, None
            try:
                with _ur.urlopen(url, timeout=8) as r:
                    return idx, Image.open(_io.BytesIO(r.read())).convert("RGB")
            except Exception:
                return idx, None

        self._set_img_status(f"이미지 {count}장 다운로드 중...", 0.05)
        results = [None] * count
        done_dl = 0
        with ThreadPoolExecutor(max_workers=min(count, 30)) as pool:
            futs = {pool.submit(_fetch, i): i for i in range(count)}
            for fut in as_completed(futs):
                idx, img = fut.result()
                results[idx] = img
                done_dl += 1
                self._set_img_status(f"다운로드 {done_dl}/{count}...", done_dl / count * 0.6)

        for i, pil_img in enumerate(results):
            if self._stop_event.is_set():
                self._set_img_status("중단됨", 0, C["err"])
                break
            if pil_img is None:
                pil_img = image_generator.create_placeholder_image()
            _wm = datetime.now().strftime("%m%d%H%M%S")
            pil_img = self._apply_variation(pil_img, vs=self._var_settings_picsum, wm_text=_wm)
            self._show_image(i, pil_img)
            self._set_img_status(f"이미지 {i + 1}/{count} 완료", (i + 1) / count)
        if not self._stop_event.is_set():
            def _enable_scroll_picsum():
                bb = self._img_canvas.bbox("all")
                if bb:
                    self._img_canvas.configure(scrollregion=(0, 0, bb[2] + 4, bb[3] + 8))
                self._img_hscroll.enable(True)
            self.after(100, _enable_scroll_picsum)
            self._auto_save_source_images(count, "픽숨", kw=kw)

    _FLICKR_KW = [
        # 자연/풍경
        "nature", "landscape", "ocean", "mountain", "forest", "sky", "sunset", "flower",
        "river", "lake", "waterfall", "cliff", "valley", "desert", "jungle", "field",
        "horizon", "clouds", "fog", "sunrise", "meadow", "coast", "reef", "glacier",
        # 도시/건축
        "city", "architecture", "street", "building", "bridge", "rooftop", "alley",
        "skyline", "downtown", "subway", "tunnel", "staircase", "window", "facade",
        "plaza", "tower", "cathedral", "ruins", "construction", "pathway",
        # 음식/카페
        "food", "coffee", "cafe", "bakery", "restaurant", "cooking", "dessert",
        "bread", "pasta", "sushi", "salad", "pizza", "tea", "cocktail", "fruit",
        "vegetables", "cheese", "chocolate", "brunch", "streetfood", "grill",
        # 라이프스타일/사람
        "lifestyle", "fashion", "portrait", "people", "family", "friends",
        "reading", "music", "dance", "yoga", "meditation", "work", "study",
        "shopping", "walking", "laughing", "couple", "children", "elderly",
        # 동물
        "cat", "dog", "bird", "wildlife", "animals",
        "horse", "rabbit", "fox", "deer", "butterfly", "fish", "turtle", "owl",
        # 여행/문화
        "travel", "market", "festival", "museum", "art", "culture",
        "temple", "lantern", "carnival", "street-art", "vintage", "craft",
        "ceremony", "tradition", "souvenir", "landmark", "passport", "luggage",
        # 스포츠/활동
        "sport", "cycling", "running", "beach", "surfing", "climbing",
        "swimming", "tennis", "basketball", "football", "hiking", "skateboard",
        "rowing", "skiing", "martial-arts", "gym", "workout",
        # 인테리어/공간
        "interior", "library", "workspace", "garden", "park",
        "bedroom", "kitchen", "studio", "loft", "greenhouse", "patio",
        "bookshelf", "sofa", "lamp", "decoration", "minimalist", "cozy",
        # 계절/날씨
        "autumn", "winter", "spring", "rain", "snow",
        "golden-hour", "storm", "thunder", "ice", "frost", "rainbow", "haze",
        # 야경/야외
        "night", "lights", "neon", "fireworks",
        "stars", "milkyway", "campfire", "lanterns", "streetlight", "reflection",
        # 추상/텍스처
        "texture", "pattern", "abstract", "color", "bokeh", "shadow", "smoke",
        "graffiti", "rust", "wood", "stone", "fabric", "glass", "metal",
    ]

    def _gen_images_flickr(self, count, kw=""):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import urllib.request as _ur, io as _io
        fw = max(100, self._flickr_width)
        fh = max(100, self._flickr_height)
        _search_kw = self._flickr_keyword.strip() if self._flickr_keyword.strip() else None
        collected = 0
        attempt = 0
        max_attempts = count * 6

        def _fetch(idx):
            if self._stop_event.is_set():
                return None
            try:
                _t = int(time.time() * 1000) + idx
                _kw = _search_kw or random.choice(self._FLICKR_KW)
                _req = _ur.Request(
                    f"https://loremflickr.com/{fw}/{fh}/{_kw}?t={_t}",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                             "Cache-Control": "no-cache, no-store",
                             "Pragma": "no-cache"},
                )
                with _ur.urlopen(_req, timeout=8) as r:
                    return Image.open(_io.BytesIO(r.read())).convert("RGB")
            except Exception:
                return None

        while collected < count and attempt < max_attempts:
            if self._stop_event.is_set():
                self._set_img_status("중단됨", 0, C["err"])
                break
            need = count - collected
            batch = min(need + 2, max_attempts - attempt, 30)
            self._set_img_status(f"이미지 {collected + 1}/{count} 가져오는 중...", collected / count)
            with ThreadPoolExecutor(max_workers=batch) as pool:
                futs = [pool.submit(_fetch, attempt + i) for i in range(batch)]
                attempt += batch
                for fut in as_completed(futs):
                    if self._stop_event.is_set() or collected >= count:
                        break
                    pil_img = fut.result()
                    if pil_img is None:
                        continue
                    if self._is_mostly_solid(pil_img) or self._has_excessive_red(pil_img):
                        continue
                    _wm = datetime.now().strftime("%m%d%H%M%S")
                    pil_img = self._apply_variation(pil_img, vs=self._var_settings_flickr, wm_text=_wm)
                    self._show_image(collected, pil_img)
                    collected += 1
                    self._set_img_status(f"이미지 {collected}/{count} 완료", collected / count)
        if not self._stop_event.is_set():
            def _enable_scroll_flickr():
                bb = self._img_canvas.bbox("all")
                if bb:
                    self._img_canvas.configure(scrollregion=(0, 0, bb[2] + 4, bb[3] + 8))
                self._img_hscroll.enable(True)
            self.after(100, _enable_scroll_flickr)
            self._auto_save_source_images(count, "플리커", kw=kw)

    def _gen_images(self, prompt, count, start_prog=0, kw=""):
        src = getattr(self, "_img_source", "AI")
        if src == "픽숨":
            self._gen_images_picsum(count, kw=kw)
            return
        if src == "플리커":
            self._gen_images_flickr(count, kw=kw)
            return
        if not config.CF_ACCOUNT_ID or not config.CF_API_TOKEN:
            self._set_img_status("⚠️ Cloudflare 미연동 — 설정 탭에서 API 키를 입력하세요.", 0, C["err"])
            return
        # 번역된 프롬프트에서 고유명사(상호명·지역명) 제거 후 업종/카테고리만 추출
        # 패턴: 대문자로 시작하는 연속 단어(고유명사)를 제거하고 소문자 단어만 유지
        import re as _re_img
        _raw_base = prompt.split(",")[0].strip()
        # 고유명사 제거: 대문자 시작 단어들 중 일반명사(Clinic, Dental, Cafe 등 업종어)만 남김
        _GENERIC = {
            "clinic","dental","hospital","cafe","coffee","restaurant","shop","store",
            "academy","school","center","centre","salon","spa","gym","fitness",
            "bakery","pharmacy","hotel","market","studio","office","food","beauty",
            "health","medical","care","service","korea","korean","south",
        }
        _words = _raw_base.split()
        _kept = [w for w in _words if w.lower() in _GENERIC or not w[0].isupper()]
        base = " ".join(_kept).strip() or _raw_base
        subjects = random.sample(self._IMG_SUBJECTS, len(self._IMG_SUBJECTS))
        styles   = random.sample(self._IMG_STYLES,   len(self._IMG_STYLES))
        moods    = random.sample(self._IMG_MOODS,    len(self._IMG_MOODS))
        for i in range(1, count + 1):
            if self._stop_event.is_set():
                self._set_img_status("중단됨", 0, C["err"])
                break
            prog = (i - 1) / count
            self._set_img_status(f"이미지 {i}/{count} 생성 중...", prog)
            subject = subjects[(i - 1) % len(subjects)]
            style   = styles[(i - 1) % len(styles)]
            mood    = moods[(i - 1) % len(moods)]
            varied_prompt = (
                f"no text, no signs, no writing, no letters, no words, "
                f"{style}, {subject} of {base}, {mood}, "
                f"clean plain walls, solid neutral background, soft natural lighting, "
                f"blurred background, objects and scenery only, purely visual composition, "
                f"no neon lights, no logos, no billboards, no store signs, no banners, "
                f"no watermark, no typography, completely text-free image"
            )
            seed = random.randint(0, 2**31)
            if i > 1:
                for _ in range(30):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.1)
            if self._stop_event.is_set():
                self._set_img_status("중단됨", 0, C["err"])
                break
            pil_img = None
            for _attempt in range(3):
                try:
                    _img = image_generator.generate_to_memory(varied_prompt, seed=seed + _attempt)
                    if self._is_solid_color_image(_img):
                        self._set_img_status(f"이미지 {i} 단색 감지, 재시도 {_attempt+1}/3...", prog)
                        continue
                    pil_img = _img
                    break
                except Exception as e:
                    self._set_img_status(f"이미지 {i} 실패: {str(e)[:40]}", prog, C["err"])
                    break
            if pil_img is None:
                self._set_img_status(f"이미지 {i} 생성 실패 (단색)", prog, C["err"])
                continue
            self._show_image(i - 1, pil_img)
            prog = i / count
            self._set_img_status(f"이미지 {i}/{count} 완료", prog)
            if i == count:
                self.after(0, lambda: self._img_hscroll.enable(True))

    @staticmethod
    def _is_solid_color_image(pil_img, threshold=12):
        import numpy as np
        arr = np.array(pil_img.convert("RGB"))
        return float(arr.std()) < threshold

    def _reset_outputs(self, reset_images=True):
        self.content_box.set_markdown("")
        try: self.text_count_lbl.configure(text="")
        except Exception: pass
        self._img_pil   = [None] * len(getattr(self, "img_labels", []))
        self._last_body = ""
        for lbl in getattr(self, "img_labels", []):
            blank = getattr(lbl, "_blank", "")
            lbl.configure(image=blank, text="", compound="none")
        try: self._img_hscroll.enable(False)
        except Exception: pass
        try: self.text_prog.stop()
        except Exception: pass
        self.text_prog.configure(mode="determinate", progress_color=C["accent_bg"])
        self.text_prog.set(0)
        self.img_prog.configure(progress_color=C["accent_bg"])
        self.img_prog.set(0)
        self.text_status_lbl.configure(text="대기 중", text_color=C["subtext"])
        self.img_status_lbl.configure(text="대기 중", text_color=C["subtext"])
        self.status_label.configure(text="", text_color=C["subtext"])
        self.btn_copy.configure(fg_color=C["ok"], hover_color="#1E7A55")

    def _set_status(self, msg, prog=None, color=None):
        self.after(0, lambda: self.status_label.configure(text=msg, text_color=color or C["subtext"]))

    def _set_text_status(self, msg, prog, color=None):
        self.after(0, lambda: self.text_status_lbl.configure(text=msg, text_color=color or C["subtext"]))
        if 0 < prog < 1.0:
            def _indet():
                try: self.text_prog.stop()
                except Exception: pass
                self.text_prog.configure(mode="indeterminate", progress_color=C["accent"])
                self.text_prog.start()
            self.after(0, _indet)
        else:
            def _det(p=prog, c=color):
                try: self.text_prog.stop()
                except Exception: pass
                pc = c or (C["accent"] if p > 0 else C["accent_bg"])
                self.text_prog.configure(mode="determinate", progress_color=pc)
                self.text_prog.set(p)
            self.after(0, _det)

    def _set_img_status(self, msg, prog, color=None):
        self.after(0, lambda: self.img_status_lbl.configure(text=msg, text_color=color or C["subtext"]))
        self.after(0, lambda: self.img_prog.set(prog))
        pc = C["ok"] if prog > 0 else C["accent_bg"]
        self.after(0, lambda c=pc: self.img_prog.configure(progress_color=c))

    def _set_content(self, text):
        count = len(text.replace("\n", "").replace(" ", ""))
        self.after(0, lambda: self.content_box.set_markdown(text))
        self.after(0, lambda: self.text_count_lbl.configure(
            text=f"{count:,}자" if text.strip() else "",
        ))

    @staticmethod
    def _markdown_to_html(md: str) -> str:
        lines = md.splitlines()
        html_lines = []
        in_ul = False

        def _emit(tag: str):
            html_lines.append(tag)
            html_lines.append('<p>&nbsp;</p>')

        def _close_ul():
            nonlocal in_ul
            if in_ul:
                html_lines.append('</ul>')
                html_lines.append('<p>&nbsp;</p>')
                in_ul = False

        for line in lines:
            stripped = line.strip()
            # 구분선
            if re.match(r'^---+$', stripped) or re.match(r'^===+$', stripped):
                _close_ul()
                html_lines.append('<hr>')
                html_lines.append('<p></p>')
            # h1
            elif line.startswith('# ') and not line.startswith('## '):
                _close_ul()
                _emit(f'<h1>{_inline(line[2:].strip())}</h1>')
            # h2
            elif line.startswith('## ') and not line.startswith('### '):
                _close_ul()
                _emit(f'<h2>{_inline(line[3:].strip())}</h2>')
            # h3
            elif line.startswith('### '):
                _close_ul()
                _emit(f'<h3>{_inline(line[4:].strip())}</h3>')
            # 인용구
            elif line.startswith('> '):
                _close_ul()
                _emit(f'<blockquote><p>{_inline(line[2:].strip())}</p></blockquote>')
            # 불릿 목록
            elif re.match(r'^[\*\-\•] ', line):
                if not in_ul:
                    html_lines.append('<ul>')
                    in_ul = True
                html_lines.append(f'<li>{_inline(line[2:].strip())}</li>')
            # 번호 목록
            elif re.match(r'^\d+\. ', line):
                _close_ul()
                _om = re.match(r'^(\d+)\. (.*)', line)
                if _om:
                    _emit(f'<p>{_om.group(1)}. {_inline(_om.group(2).strip())}</p>')
                else:
                    _emit(f'<p>{_inline(line)}</p>')
            # 빈 줄 — 콘텐츠 줄이 이미 <p></p> 추가하므로 건너뜀
            elif stripped == '':
                _close_ul()
            # 일반 문단
            else:
                _close_ul()
                _emit(f'<p>{_inline(line)}</p>')

        _close_ul()
        # 끝 빈 단락 제거
        while html_lines and html_lines[-1] == '<p>&nbsp;</p>':
            html_lines.pop()
        # 인용구 앞뒤 줄띄기 제거
        result = []
        for i, item in enumerate(html_lines):
            if item == '<p>&nbsp;</p>':
                next_tag = next((l for l in html_lines[i + 1:] if l.strip()), '')
                prev_tag = next((l for l in reversed(html_lines[:i]) if l.strip()), '')
                if next_tag.startswith('<blockquote') or prev_tag.endswith('</blockquote>'):
                    continue
            result.append(item)
        return '\n'.join(result)

    @staticmethod
    def _set_win_clipboard_html(html_body: str, plain: str):
        k32 = ctypes.windll.kernel32
        u32 = ctypes.windll.user32

        # 64비트 핸들/포인터 타입 명시 (OverflowError 방지)
        HANDLE = ctypes.c_void_p
        k32.GlobalAlloc.argtypes  = [ctypes.c_uint, ctypes.c_size_t]
        k32.GlobalAlloc.restype   = HANDLE
        k32.GlobalLock.argtypes   = [HANDLE]
        k32.GlobalLock.restype    = ctypes.c_void_p
        k32.GlobalUnlock.argtypes = [HANDLE]
        k32.GlobalUnlock.restype  = ctypes.c_bool
        u32.OpenClipboard.argtypes  = [HANDLE]
        u32.OpenClipboard.restype   = ctypes.c_bool
        u32.SetClipboardData.argtypes = [ctypes.c_uint, HANDLE]
        u32.SetClipboardData.restype  = HANDLE

        CF_HTML        = u32.RegisterClipboardFormatW("HTML Format")
        CF_UNICODETEXT = 13

        tmpl = (
            "Version:0.9\r\n"
            "StartHTML:{sh:08d}\r\n"
            "EndHTML:{eh:08d}\r\n"
            "StartFragment:{sf:08d}\r\n"
            "EndFragment:{ef:08d}\r\n"
        )
        wrap_pre  = "<html><body>\r\n<!--StartFragment-->"
        wrap_post = "<!--EndFragment-->\r\n</body></html>"

        dummy_hdr = tmpl.format(sh=0, eh=0, sf=0, ef=0)
        hdr_len   = len(dummy_hdr.encode("utf-8"))
        sf = hdr_len + len(wrap_pre.encode("utf-8"))
        ef = sf + len(html_body.encode("utf-8"))
        eh = ef + len(wrap_post.encode("utf-8"))

        header        = tmpl.format(sh=hdr_len, eh=eh, sf=sf, ef=ef)
        cf_html_bytes = (header + wrap_pre + html_body + wrap_post).encode("utf-8") + b"\x00"
        uc_bytes      = (plain + "\x00").encode("utf-16-le")

        if not u32.OpenClipboard(None):
            raise RuntimeError("클립보드를 열 수 없습니다.")
        try:
            u32.EmptyClipboard()
            for fmt, data in [(CF_HTML, cf_html_bytes), (CF_UNICODETEXT, uc_bytes)]:
                h = k32.GlobalAlloc(0x0002, len(data))
                p = k32.GlobalLock(h)
                ctypes.memmove(p, data, len(data))
                k32.GlobalUnlock(h)
                u32.SetClipboardData(fmt, h)
        finally:
            u32.CloseClipboard()

    def _copy_as_html(self):
        md = self._last_body.strip()
        if not md:
            self._set_status("⚠️  복사할 내용이 없습니다.", color=C["err"])
            return
        html_body = self._markdown_to_html(md)
        # plain text: 모든 콘텐츠 줄 사이에 빈 줄 보장
        _plain_lines = []
        _prev_empty = True
        for _ln in md.splitlines():
            if not _ln.strip():
                if not _prev_empty:
                    _plain_lines.append('')
                _prev_empty = True
            else:
                if not _prev_empty:
                    _plain_lines.append('')
                _plain_lines.append(_ln)
                _prev_empty = False
        plain = '\n'.join(_plain_lines)
        try:
            self._set_win_clipboard_html(html_body, plain)
            self._set_status("✅  서식 복사 완료. 네이버 블로그에 그대로 붙여넣으세요.", color=C["ok"])
            self.btn_copy.configure(fg_color=C["ok"], hover_color="#1E7A55")
        except Exception as e:
            self._set_status(f"⚠️  복사 실패: {e}", color=C["err"])

    def _show_image(self, idx, pil_img):
        from PIL import ImageTk
        self._img_pil[idx] = pil_img
        sz = getattr(self, "_thumb_sz", 116)
        resized = pil_img.resize((sz, sz), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(resized)
        self._img_refs[idx] = tk_img
        self.after(0, lambda: self.img_labels[idx].configure(image=tk_img, text="", compound="none"))

    def _copy_image_at(self, idx):
        pil_img = self._img_pil[idx] if idx < len(self._img_pil) else None
        if pil_img is None:
            return
        try:
            buf = io.BytesIO()
            pil_img.convert("RGB").save(buf, "BMP")
            data = buf.getvalue()[14:]
            buf.close()
            CF_DIB, GHND = 8, 0x0042
            k32 = ctypes.windll.kernel32
            u32 = ctypes.windll.user32
            k32.GlobalAlloc.restype   = ctypes.c_void_p
            k32.GlobalAlloc.argtypes  = [ctypes.c_uint, ctypes.c_size_t]
            k32.GlobalLock.restype    = ctypes.c_void_p
            k32.GlobalLock.argtypes   = [ctypes.c_void_p]
            k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            u32.SetClipboardData.restype  = ctypes.c_void_p
            u32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
            hMem = k32.GlobalAlloc(GHND, len(data))
            pMem = k32.GlobalLock(hMem)
            ctypes.memmove(pMem, data, len(data))
            k32.GlobalUnlock(hMem)
            u32.OpenClipboard(0)
            u32.EmptyClipboard()
            u32.SetClipboardData(CF_DIB, hMem)
            u32.CloseClipboard()
            self._set_status(f"📋  이미지 {idx+1} 클립보드에 복사됨")
            # 복사된 이미지를 50% 투명하게 표시
            sz = getattr(self, "_thumb_sz", 88)
            bg = Image.new("RGB", pil_img.size, (255, 255, 255))
            faded = Image.blend(bg, pil_img.convert("RGB"), alpha=0.5)
            from PIL import ImageTk as _ITk
            faded_r = faded.resize((sz, sz), Image.LANCZOS)
            faded_tk = _ITk.PhotoImage(faded_r)
            self._img_refs[idx] = faded_tk
            self.img_labels[idx].configure(image=faded_tk)
        except Exception as e:
            self._set_status(f"⚠️  클립보드 복사 실패: {e}", color=C["err"])

    def _download_all(self):
        import time as _t, re as _re
        idx = self._selected_prompt_idx
        if self._topic_enabled[idx]:
            kw = self.topic_dropdown.get().strip()
        elif self._is_secret_mode():
            kw = self.keyword_textbox.get("1.0", "end").strip().split('\n')[0][:20]
        else:
            kw = self.keyword_entry.get().strip()
        kw = _re.sub(r'[\\/:*?"<>|\s]+', '_', kw)[:30] or "images"
        folder_name = f"{_t.strftime('%m%d%H%M%S')}_{kw}"
        if self._last_out_dir and self._last_out_dir.parent.exists():
            base = self._last_out_dir.parent
        elif self._variation_output_dir:
            base = Path(self._variation_output_dir)
        else:
            base = Path.home() / "Desktop"
        images_to_save = [p for p in self._img_pil if p is not None]
        if not images_to_save:
            self._set_status("생성된 이미지가 없습니다.", color=C["err"])
            return
        dest = base / folder_name
        dest.mkdir(parents=True, exist_ok=True)
        date_tag = _t.strftime('%m%d%H%M')
        saved = 0
        _src_is_photo = self._img_source in ("픽숨", "플리커")
        for i, pil_img in enumerate(self._img_pil):
            if pil_img is not None:
                if _src_is_photo:
                    fname = f"{date_tag}_{saved + 1}.png"
                else:
                    fname = f"{kw}_{date_tag}_{saved + 1}.png"
                pil_img.save(dest / fname)
                saved += 1
        self._set_status(f"✅  {saved}개 파일을 {dest.name}에 저장했습니다.", color=C["ok"])

    def _auto_save_source_images(self, count: int, src: str, kw: str = ""):
        """PICSUM/FLICKR 이미지 생성 후 count >= 10이면 자동 저장."""
        if count < 10:
            return
        import time as _t
        folder_name = _t.strftime('%m%d%H%M%S')
        if self._variation_output_dir:
            base = Path(self._variation_output_dir)
        else:
            base = Path.home() / "Desktop"
        dest = base / folder_name
        dest.mkdir(parents=True, exist_ok=True)
        date_tag = _t.strftime('%m%d%H%M')
        saved = 0
        for i, pil_img in enumerate(self._img_pil):
            if pil_img is not None:
                fname = f"{date_tag}_{saved + 1}.png"
                pil_img.save(dest / fname)
                saved += 1
        self._last_out_dir = dest
        if saved:
            self.after(0, lambda d=dest.name, n=saved: self._set_img_status(
                f"✅ {n}개 자동 저장 완료 → {d}", 1.0, C["ok"]))


def _naver_auto_worker(naver_dir: str):
    """별도 프로세스에서 naver-auto를 실행하는 엔트리포인트."""
    import sys, os, io, runpy

    # windowed 앱에서 stdout/stderr가 None → multiprocessing spawn 오류 방지
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

    sys.frozen = False  # get_base_dir()가 __file__ 기준으로 동작하도록
    sys.path.insert(0, naver_dir)
    os.chdir(naver_dir)
    runpy.run_path(os.path.join(naver_dir, "main.py"), run_name="__main__")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    app = App()
    app.mainloop()
