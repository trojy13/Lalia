"""Start Lalia: `pythonw -m lalia` (add --background to start in the tray only)."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
import threading

from . import __version__, config, paths
from . import win32 as w

MUTEX_NAME = "Local\\Lalia.SingleInstance"
SHOW_EVENT_NAME = "Local\\Lalia.ShowSettings"


def _setup_logging(debug: bool) -> None:
    paths.ensure_dirs()
    handler = logging.handlers.RotatingFileHandler(paths.LOG_DIR / "lalia.log", maxBytes=1_000_000,
                                                   backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    if sys.stderr is not None:  # python.exe, not pythonw.exe
        root.addHandler(logging.StreamHandler())
    for noisy in ("faster_whisper", "httpx", "httpx2", "httpcore", "huggingface_hub", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def excepthook(exc_type, exc, tb):
        logging.getLogger("lalia").critical("uncaught", exc_info=(exc_type, exc, tb))

    sys.excepthook = excepthook
    threading.excepthook = lambda a: excepthook(a.exc_type, a.exc_value, a.exc_traceback)


def _already_running() -> bool:
    """One Lalia per user session. A second start asks the first to show its
    settings window and exits."""
    global _mutex
    _mutex = w.CreateMutexW(None, False, MUTEX_NAME)
    if w.ctypes.get_last_error() != w.ERROR_ALREADY_EXISTS:
        return False
    ev = w.OpenEventW(w.EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
    if ev:
        # This process was just started by the user, so it may hand the right
        # to come to the front over to the running copy.
        w.user32.AllowSetForegroundWindow(w.wintypes.DWORD(0xFFFFFFFF))  # ASFW_ANY
        w.SetEvent(ev)
        w.CloseHandle(ev)
    return True


_mutex = None


def _listen_for_second_start(app) -> None:
    ev = w.CreateEventW(None, False, False, SHOW_EVENT_NAME)

    def wait():
        while True:
            if w.WaitForSingleObject(ev, w.INFINITE) == w.WAIT_OBJECT_0:
                app.call_soon(app.show_settings)

    threading.Thread(target=wait, name="lalia-second-start", daemon=True).start()


def main() -> None:
    ap = argparse.ArgumentParser(prog="lalia", description="Λαλιά: υπαγόρευση για Windows")
    ap.add_argument("--background", action="store_true", help="start in the tray, no settings window")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if _already_running():
        return
    _setup_logging(args.debug)
    log = logging.getLogger("lalia")
    log.info("Lalia %s starting (Python %s)", __version__, sys.version.split()[0])

    w.set_dpi_awareness()
    w.set_app_user_model_id(paths.APP_ID)
    from . import icons

    if not paths.ICON_FILE.exists():
        try:
            icons.write_ico(paths.ICON_FILE)
        except OSError:
            pass

    from .app import App

    app = App(config.load(), background=args.background)
    _listen_for_second_start(app)
    app.run()
    log.info("Lalia stopped")


if __name__ == "__main__":
    main()
