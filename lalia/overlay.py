"""The status pill near the bottom (or top) of the screen.

It never takes the keyboard focus and lets clicks through, so the window being
dictated into keeps the caret. Shown and hidden with ShowWindow/SetWindowPos
(SW_SHOWNOACTIVATE, SWP_NOACTIVATE) rather than Tk's deiconify, which would
activate it; the same approach PCB uses to keep its notification panel on top.
"""
from __future__ import annotations

import collections
import math
import time
import tkinter as tk
import tkinter.font as tkfont

from . import win32 as w

BG = "#1f2328"
FG = "#f0f3f6"
DIM = "#8b949e"
RED = "#e5484d"
AMBER = "#f5a524"
GREEN = "#30a46c"
GREY = "#8b949e"

ANIMATED = ("recording", "processing", "loading")


def level_to_unit(rms: float) -> float:
    """Microphone RMS to 0..1 on a -55..-15 dBFS scale, which is where speech sits."""
    db = 20 * math.log10(max(rms, 1e-6))
    return max(0.0, min(1.0, (db + 55) / 40))


class Overlay:
    BARS = 11

    def __init__(self, root: tk.Tk, scale: float, position: str = "bottom"):
        self.root = root
        self.s = scale
        self.position = position
        self.kind = ""
        self.text = ""
        self.hint = ""
        self.level_fn = lambda: 0.0
        self._levels = collections.deque([0.0] * self.BARS, maxlen=self.BARS)
        self._visible = False
        self._hide_job = None
        self._tick_job = None
        self._t0 = time.monotonic()

        self.font = tkfont.Font(family="Segoe UI", size=10)
        self.hint_font = tkfont.Font(family="Segoe UI", size=8)
        self.h = int(40 * scale)
        self.w = int(260 * scale)

        prev = w.GetForegroundWindow()
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-alpha", 0.95)
        self.top.configure(bg=BG)
        self.top.geometry(f"{self.w}x{self.h}+-32000+-32000")
        self.canvas = tk.Canvas(self.top, width=self.w, height=self.h, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.top.update_idletasks()
        self.top.update()
        self.hwnd = int(self.top.wm_frame(), 16)
        w.make_floating(self.hwnd, click_through=True)
        w.round_corners(self.hwnd)
        w.hide(self.hwnd)
        if prev:  # creating a Tk window activates it once; hand the focus back
            w.SetForegroundWindow(prev)

    # -- public -------------------------------------------------------------
    def show(self, kind: str, text: str, hint: str = "", auto_hide_ms: int | None = None) -> None:
        if self.position == "none":
            return
        self.kind, self.text, self.hint = kind, text, hint
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        if kind != "recording":
            self._levels.extend([0.0] * self.BARS)
        self._resize_and_place()
        self._draw()
        if not self._visible:
            w.show_no_activate(self.hwnd)
            self._visible = True
        if kind in ANIMATED and self._tick_job is None:
            self._tick_job = self.root.after(50, self._tick)
        if auto_hide_ms:
            self._hide_job = self.root.after(auto_hide_ms, self.hide)

    def hide(self) -> None:
        self._hide_job = None
        if self._visible:
            w.hide(self.hwnd)
            self._visible = False
        self.kind = ""

    # -- layout and drawing -------------------------------------------------------
    def _resize_and_place(self) -> None:
        s = self.s
        left = int((150 if self.kind == "recording" else 44) * s)
        text_w = self.font.measure(self.text)
        hint_w = self.hint_font.measure(self.hint) + int(16 * s) if self.hint else 0
        width = max(int(200 * s), min(int(640 * s), left + text_w + hint_w + int(18 * s)))
        self.w = width
        cx, cy = w.cursor_pos()
        l, t, r, b = w.work_area_at(cx, cy)
        x = l + (r - l - width) // 2
        y = t + int(24 * s) if self.position == "top" else b - self.h - int(28 * s)
        self.top.geometry(f"{width}x{self.h}")
        self.canvas.configure(width=width)
        w.SetWindowPos(self.hwnd, w.HWND_TOPMOST, x, y, width, self.h, w.SWP_NOACTIVATE)

    def _draw(self) -> None:
        c, s = self.canvas, self.s
        c.delete("all")
        mid = self.h / 2
        t = time.monotonic() - self._t0
        if self.kind == "recording":
            r = (5 + 1.5 * math.sin(t * 6)) * s
            c.create_oval(18 * s - r, mid - r, 18 * s + r, mid + r, fill=RED, outline="")
            x0, bar_w, gap = 34 * s, 6 * s, 4 * s
            for i, v in enumerate(self._levels):
                hh = max(3 * s, v * (self.h - 14 * s))
                x = x0 + i * (bar_w + gap)
                c.create_rectangle(x, mid - hh / 2, x + bar_w, mid + hh / 2, fill=FG, outline="")
            text_x = 150 * s
        elif self.kind in ("processing", "loading"):
            color = AMBER if self.kind == "processing" else GREY
            r = 8 * s
            start = (t * 360) % 360
            c.create_arc(18 * s - r, mid - r, 18 * s + r, mid + r, start=-start, extent=270,
                         style="arc", outline=color, width=max(2, int(2.5 * s)))
            text_x = 36 * s
        elif self.kind == "done":
            c.create_line(11 * s, mid, 16 * s, mid + 5 * s, 25 * s, mid - 6 * s,
                          fill=GREEN, width=max(2, int(3 * s)), capstyle="round", joinstyle="round")
            text_x = 36 * s
        else:  # error / info
            color = RED if self.kind == "error" else GREY
            c.create_oval(10 * s, mid - 8 * s, 26 * s, mid + 8 * s, fill=color, outline="")
            c.create_text(18 * s, mid, text="!" if self.kind == "error" else "i", fill="white",
                          font=("Segoe UI", 9, "bold"))
            text_x = 36 * s
        c.create_text(text_x, mid, text=self.text, anchor="w", fill=FG, font=self.font)
        if self.hint:
            c.create_text(self.w - 12 * s, mid, text=self.hint, anchor="e", fill=DIM, font=self.hint_font)

    def _tick(self) -> None:
        self._tick_job = None
        if not self._visible or self.kind not in ANIMATED:
            return
        if self.kind == "recording":
            try:
                self._levels.append(level_to_unit(self.level_fn()))
            except Exception:
                self._levels.append(0.0)
        self._draw()
        self._tick_job = self.root.after(50, self._tick)
