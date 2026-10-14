"""Run the whole app once with a WAV file in place of the microphone.

Starts Lalia (tray, overlay, worker, model) with its data in a temporary folder
and the shortcut moved to Ctrl+Shift+F23 so the real one stays free, "dictates"
the WAV, then opens and closes the settings window. By default the typing step
is replaced by a recorder, so the test leaves the focus alone; --real-window
types into a test window instead (it then needs the focus for ~12 s).

    .venv\\Scripts\\python tools\\apptest.py samples\\el.wav [--real-window]
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path

REAL_MODELS = Path(os.environ.get("LOCALAPPDATA", "")) / "Lalia" / "models"
os.environ["LALIA_HOME"] = tempfile.mkdtemp(prefix="lalia-apptest-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import read_wav  # noqa: E402

from lalia import config, paths  # noqa: E402
from lalia import win32 as w  # noqa: E402
from lalia.app import App  # noqa: E402
from lalia.output import activate  # noqa: E402


class FakeRecorder:
    """Plays a WAV into the app at real-time pace, so the level meter moves."""

    def __init__(self, audio):
        self.audio = audio
        self.level = 0.0
        self.active = False
        self._pos = 0

    def start(self, device_name=""):
        self.active = True
        self._pos = 0
        threading.Thread(target=self._feed, daemon=True).start()

    def _feed(self):
        block = 1600
        while self.active and self._pos < len(self.audio):
            chunk = self.audio[self._pos:self._pos + block]
            self.level = float((chunk ** 2).mean() ** 0.5) if len(chunk) else 0.0
            self._pos += block
            time.sleep(0.1)

    def stop(self):
        self.active = False
        return self.audio[: max(self._pos, len(self.audio))]

    def abort(self):
        self.active = False


class RecordingDeliverer:
    """Stands in for the typing step, so the test does not need the focus."""
    texts: list[str] = []

    def deliver(self, text, target, **_kw):
        from lalia.output import Delivery

        RecordingDeliverer.texts.append(text)
        return Delivery(True)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    real_window = "--real-window" in sys.argv
    wav = args[0] if args else "samples/el.wav"
    audio = read_wav(wav)
    if not real_window:
        import lalia.app

        lalia.app.Deliverer = RecordingDeliverer
    w.set_dpi_awareness()
    paths.ensure_dirs()
    original_fg = w.GetForegroundWindow()
    settings = config.Settings(hotkey="Ctrl+Shift+F23", sounds=False, target="focused",
                               first_run_done=True, custom_words=["αμοξικιλλίνη"])
    app = App(settings, background=True)
    app.transcriber.models_dir = REAL_MODELS
    app.recorder = FakeRecorder(audio)

    win = tk.Toplevel(app.root)
    win.title("Lalia app test")
    win.geometry("640x160+160+160")
    box = tk.Text(win, font=("Segoe UI", 11), wrap="word")
    box.pack(fill="both", expand=True)
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        sys.stdout.buffer.write(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}\n".encode("utf-8"))
        sys.stdout.flush()

    def ui_get():
        out = []
        ev = threading.Event()
        app.call_soon(lambda: (out.append(box.get("1.0", "end-1c")), ev.set()))
        ev.wait(3)
        return out[0] if out else None

    def driver():
        try:
            t0 = time.monotonic()
            while app.model_state != "ready" and time.monotonic() - t0 < 120:
                time.sleep(0.2)
            check("model loaded", app.model_state == "ready", app.model_message)
            hwnd = int(win.wm_frame(), 16)
            if real_window:
                app.call_soon(box.focus_force)
                if not activate(hwnd):
                    check("focus test window", False)
                    return
                time.sleep(0.2)
            app.call_soon(app.start_recording, "hotkey")
            time.sleep(len(audio) / 16000 + 0.2)
            fg = w.GetForegroundWindow()
            if real_window and int(fg or 0) != hwnd:
                check("test window kept the focus while recording", False,
                      f"focus went to {w.class_name(fg)!r} {w.window_text(fg)!r} pid {w.window_pid(fg)} "
                      f"(ours {os.getpid()})")
                app.call_soon(app.cancel)
                return
            t1 = time.monotonic()
            app.call_soon(app.stop_recording)
            text = ""
            while time.monotonic() - t1 < 20:
                text = (ui_get() if real_window else "".join(RecordingDeliverer.texts)) or ""
                if text.strip():
                    break
                time.sleep(0.1)
            took = time.monotonic() - t1
            where = "typed into the focused window" if real_window else "recognised and handed to the typing step"
            check(f"dictation {where}", "αποθήκη" in text, f"{took:.2f}s after stop")
            sys.stdout.buffer.write(f"      text: {text}\n".encode("utf-8"))
            check("custom word spelled as given", "αμοξικιλλίνη" in text)
            time.sleep(0.8)
            check("history has the dictation", len(app.history.entries()) == 1)
            app.call_soon(app.show_settings)
            time.sleep(1.5)
            sw = app.settings_window
            check("settings window opens", bool(sw and sw.alive))
            check("history listed in settings", bool(sw and sw.hist.size() == 1))
            if sw:
                app.call_soon(sw.close)
            time.sleep(0.3)
        finally:
            app.call_soon(app.quit)

    threading.Thread(target=driver, daemon=True).start()
    app.run()
    if original_fg:
        activate(original_fg)
    print(f"\n{sum(results)}/{len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
