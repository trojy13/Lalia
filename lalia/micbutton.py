"""Floating microphone button, for dictating with the mouse or on a touch screen.

Borrowed from PCB's notification panel: always on top without taking the focus,
remembers where it was dragged, and can show itself only over chosen windows
(PCB's "only over the ERP" title match). A click starts or stops dictation and
the caret stays in the app being dictated into.
"""
from __future__ import annotations

import fnmatch
import os
import tkinter as tk
import unicodedata

from PIL import ImageTk

from . import icons
from . import win32 as w


def _fold(text: str) -> str:
    """Case- and accent-insensitive form: Greek window titles are often in
    capitals, which drop the accents ("ΔΙΟΣΚΟΥΡΙΔΗΣ" vs "Διοσκουρίδης")."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def title_matches(title: str, patterns: str) -> bool:
    """Comma-separated patterns, ignoring case and accents. A pattern without
    wildcards matches anywhere in the title. Empty means 'over every window'."""
    pats = [_fold(p.strip()) for p in patterns.split(",") if p.strip()]
    if not pats:
        return True
    title = _fold(title)
    return any(fnmatch.fnmatchcase(title, p if any(ch in p for ch in "*?[") else f"*{p}*") for p in pats)


class MicButton:
    def __init__(self, root: tk.Tk, scale: float, *, x: int | None, y: int | None,
                 on_click, on_right_click, on_moved):
        self.root = root
        self.s = scale
        self.size = int(48 * scale)
        self.on_click = on_click
        self.on_right_click = on_right_click
        self.on_moved = on_moved
        self.state = "idle"
        self._images: dict[str, ImageTk.PhotoImage] = {}
        self._press = None
        self._dragging = False
        self.visible = False

        if x is None or y is None:
            l, t, r, b = w.work_area_at(*w.cursor_pos())
            x, y = r - self.size - int(24 * scale), b - self.size - int(96 * scale)
        self.x, self.y = int(x), int(y)

        prev = w.GetForegroundWindow()
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.geometry(f"{self.size}x{self.size}+{self.x}+{self.y}")
        self.canvas = tk.Canvas(self.top, width=self.size, height=self.size, highlightthickness=0, bd=0,
                                cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self._image_id = self.canvas.create_image(0, 0, anchor="nw")
        self.set_state("idle")
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonRelease-3>", lambda e: self.on_right_click())
        self.top.update_idletasks()
        self.top.update()
        self.hwnd = int(self.top.wm_frame(), 16)
        w.make_floating(self.hwnd)
        w.round_corners(self.hwnd)
        for h in (self.canvas.winfo_id(), self.top.winfo_id(), self.hwnd):
            w.no_activate_on_click(h)
        self.visible = True
        if prev:
            w.SetForegroundWindow(prev)

    def set_state(self, state: str) -> None:
        self.state = state
        if state not in self._images:
            self._images[state] = ImageTk.PhotoImage(icons.mic_image(state, self.size))
        self.canvas.configure(bg="#%02x%02x%02x" % icons.COLORS.get(state, icons.COLORS["idle"]))
        self.canvas.itemconfigure(self._image_id, image=self._images[state])

    def set_visible(self, visible: bool) -> None:
        if visible == self.visible:
            return
        if visible:
            w.show_no_activate(self.hwnd, self.x, self.y)
        else:
            w.hide(self.hwnd)
        self.visible = visible

    def destroy(self) -> None:
        self.top.destroy()

    # -- mouse ------------------------------------------------------------------
    def _on_press(self, e) -> None:
        self._press = (e.x_root, e.y_root, self.x, self.y)
        self._dragging = False

    def _on_motion(self, e) -> None:
        if not self._press:
            return
        px, py, wx, wy = self._press
        dx, dy = e.x_root - px, e.y_root - py
        if not self._dragging and abs(dx) + abs(dy) < 5 * self.s:
            return
        self._dragging = True
        self.x, self.y = wx + dx, wy + dy
        w.SetWindowPos(self.hwnd, None, self.x, self.y, 0, 0,
                       w.SWP_NOSIZE | w.SWP_NOZORDER | w.SWP_NOACTIVATE)

    def _on_release(self, e) -> None:
        was_drag, self._press = self._dragging, None
        self._dragging = False
        if was_drag:
            self.on_moved(self.x, self.y)
        else:
            self.on_click()


def foreground_title() -> tuple[str, bool]:
    """Title of the foreground window, and whether it belongs to Lalia itself."""
    fg = w.GetForegroundWindow()
    if not fg:
        return "", False
    return w.window_text(fg), w.window_pid(fg) == os.getpid()
