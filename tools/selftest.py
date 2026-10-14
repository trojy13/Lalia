"""End-to-end check of the Windows side, without a microphone.

Opens two small test windows, then for about five seconds moves the focus and
the mouse between them. It checks that:
  1. the global shortcut fires on press and on release;
  2. the overlay and the floating button never take the focus, even when clicked;
  3. paste (Ctrl+V) and character typing deliver Greek text, and the clipboard
     comes back as it was;
  4. "under the mouse" mode types into the window under the pointer.
Keys are sent only after a check that one of the test windows has the focus.

    .venv\\Scripts\\python tools\\selftest.py
"""
from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lalia import win32 as w  # noqa: E402
from lalia.hotkey import HotkeyThread  # noqa: E402
from lalia.micbutton import MicButton  # noqa: E402
from lalia.output import Clipboard, Deliverer, Target, _key, _send, activate  # noqa: E402
from lalia.overlay import Overlay  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    sys.stdout.buffer.write(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}\n".encode("utf-8"))
    sys.stdout.flush()


class UI:
    """Run Tk calls on the main thread from the test thread."""

    def __init__(self, root):
        self.root = root
        self.q: queue.SimpleQueue = queue.SimpleQueue()
        root.after(10, self._pump)

    def _pump(self):
        while True:
            try:
                fn, box, done = self.q.get_nowait()
            except queue.Empty:
                break
            try:
                box.append(fn())
            except Exception as e:  # noqa: BLE001
                box.append(e)
            done.set()
        self.root.after(10, self._pump)

    def __call__(self, fn):
        box, done = [], threading.Event()
        self.q.put((fn, box, done))
        done.wait(5)
        return box[0] if box else None


def main() -> None:
    w.set_dpi_awareness()
    original_fg = w.GetForegroundWindow()
    original_cursor = w.cursor_pos()

    root = tk.Tk()
    root.title("Lalia self-test A")
    root.geometry("420x90+120+120")
    entry_a = tk.Entry(root, font=("Segoe UI", 12))
    entry_a.pack(fill="x", padx=10, pady=20)
    win_b = tk.Toplevel(root)
    win_b.title("Lalia self-test B")
    win_b.geometry("420x90+620+120")
    entry_b = tk.Entry(win_b, font=("Segoe UI", 12))
    entry_b.pack(fill="x", padx=10, pady=20)
    root.update()
    hwnd_a = int(root.wm_frame(), 16)
    hwnd_b = int(win_b.wm_frame(), 16)
    scale = root.winfo_fpixels("1i") / 96
    ui = UI(root)

    def fg_is(h):
        return int(w.GetForegroundWindow() or 0) == h

    def focus_entry(win_hwnd, entry):
        ok = activate(win_hwnd)
        ui(lambda: entry.focus_force())
        time.sleep(0.15)
        return ok and fg_is(win_hwnd)

    def steps():
        try:
            run_steps()
        finally:
            ui(root.quit)

    def run_steps():
        # 1. hotkey ---------------------------------------------------------
        events = []
        hk = HotkeyThread("Ctrl+Shift+F23", on_press=lambda: events.append("press"),
                          on_release=lambda: events.append("release"), on_cancel=lambda: None,
                          on_status=lambda ok, msg: events.append(("status", ok)))
        hk.start()
        hk.wait_ready()
        time.sleep(0.2)
        if not focus_entry(hwnd_a, entry_a):
            check("focus test window", False, "could not activate the test window; stopping")
            return
        _send([_key(w.VK_CONTROL), _key(w.VK_SHIFT), _key(0x86)])  # F23 down
        time.sleep(0.25)
        pressed_while_held = "press" in events and "release" not in events
        _send([_key(0x86, up=True), _key(w.VK_SHIFT, up=True), _key(w.VK_CONTROL, up=True)])
        time.sleep(0.25)
        check("hotkey registered", ("status", True) in events)
        check("hotkey press while held, then release", pressed_while_held and events[-1] == "release",
              str([e for e in events if isinstance(e, str)]))
        check("hotkey keystroke swallowed", ui(entry_a.get) == "", repr(ui(entry_a.get)))
        hk.stop()

        # 2. overlay and floating button keep the focus where it is ------------------
        ov = ui(lambda: Overlay(root, scale))
        focus_entry(hwnd_a, entry_a)
        ui(lambda: ov.show("recording", "Ακούω…", hint="Esc: ακύρωση"))
        time.sleep(0.3)
        check("overlay shown without taking focus", fg_is(hwnd_a))
        ui(ov.hide)

        clicks = []
        mb = ui(lambda: MicButton(root, scale, x=300, y=400, on_click=lambda: clicks.append(1),
                                  on_right_click=lambda: None, on_moved=lambda x, y: None))
        focus_entry(hwnd_a, entry_a)
        cx, cy = mb.x + mb.size // 2, mb.y + mb.size // 2
        w.SetCursorPos(cx, cy)
        time.sleep(0.1)
        _send_click()
        time.sleep(0.3)
        check("floating button click registered", clicks == [1])
        check("floating button click leaves the focus", fg_is(hwnd_a))
        ui(mb.destroy)

        # 3. paste and typing -------------------------------------------------------
        cb = Clipboard()
        before = cb.snapshot()
        before_text = cb.get_text()
        d = Deliverer()
        opts = dict(restore_clipboard=True, auto_enter=False, paste_delay_ms=60, restore_delay_ms=600)
        text = "Καλημέρα σας, η συνταγή είναι έτοιμη. "
        if focus_entry(hwnd_a, entry_a):
            r = d.deliver(text, Target("focused", hwnd_a, w.cursor_pos()), method="ctrl_v", **opts)
            time.sleep(0.2)
            check("paste with Ctrl+V", r.ok and ui(entry_a.get) == text, repr(ui(entry_a.get)))
            check("clipboard restored", cb.get_text() == before_text,
                  f"{len(before)} formats saved")
        ui(lambda: entry_a.delete(0, "end"))
        text2 = "Γειά σου, κόσμε; Ελέγξτε τη διαθεσιμότητα."
        if focus_entry(hwnd_a, entry_a):
            r = d.deliver(text2, Target("focused", hwnd_a, w.cursor_pos()), method="type", **opts)
            time.sleep(0.3)
            check("character typing (Unicode)", r.ok and ui(entry_a.get) == text2, repr(ui(entry_a.get)))

        # 4. under the mouse ------------------------------------------------------------
        ui(lambda: entry_b.delete(0, "end"))
        if focus_entry(hwnd_a, entry_a):
            ui(lambda: entry_b.focus_set())  # B's own focus is its entry once it is activated
            bx = ui(lambda: win_b.winfo_rootx() + 40)
            by = ui(lambda: win_b.winfo_rooty() + 20)
            target = Target("under_mouse", hwnd_a, (bx, by))
            r = d.deliver("Στο παράθυρο Β. ", target, method="ctrl_v", **opts)
            time.sleep(0.3)
            check("under-mouse mode activates the window under the pointer", fg_is(hwnd_b))
            check("under-mouse mode types there", ui(entry_b.get) == "Στο παράθυρο Β. ",
                  repr(ui(entry_b.get)))

    def _send_click():
        down, up = (w.MOUSEEVENTF_LEFTDOWN, w.MOUSEEVENTF_LEFTUP)
        ins = []
        for flag in (down, up):
            i = w.INPUT(type=w.INPUT_MOUSE)
            i.mi = w.MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=0)
            ins.append(i)
        _send(ins)

    threading.Thread(target=steps, daemon=True).start()
    root.mainloop()
    root.destroy()
    w.SetCursorPos(*original_cursor)
    if original_fg:
        activate(original_fg)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
