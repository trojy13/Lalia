"""Global shortcut.

RegisterHotKey, not a keyboard hook: Windows delivers WM_HOTKEY to this thread
and swallows the keystroke, so nothing leaks into the app being dictated into,
and a busy Python process cannot slow the user's typing (a low-level hook would
sit in front of every key press). RegisterHotKey reports only the press; the
release, needed for push-to-talk, is found by polling GetAsyncKeyState.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time

from . import win32 as w

log = logging.getLogger(__name__)

MODIFIER_NAMES = {"ctrl": w.MOD_CONTROL, "alt": w.MOD_ALT, "shift": w.MOD_SHIFT, "win": w.MOD_WIN}
MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")

KEYS: dict[str, int] = {"Space": 0x20, "Insert": 0x2D, "Pause": 0x13, "ScrollLock": 0x91,
                        "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
                        "Apps": 0x5D, "`": 0xC0, "Enter": 0x0D, "Tab": 0x09}
KEYS.update({f"F{i}": 0x6F + i for i in range(1, 25)})
KEYS.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
KEYS.update({str(d): 0x30 + d for d in range(10)})
KEYS.update({f"Num{d}": 0x60 + d for d in range(10)})

# Keys that make sense on their own, without a modifier.
STANDALONE_OK = {f"F{i}" for i in range(1, 25)} | {"Pause", "ScrollLock", "Apps", "Insert"}


class HotkeyError(ValueError):
    pass


def parse(text: str) -> tuple[int, int, str]:
    """'Ctrl+Shift+Space' -> (modifiers, vk, normalised text)."""
    parts = [p.strip() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise HotkeyError("κενή συντόμευση")
    mods = 0
    mod_names = []
    for p in parts[:-1]:
        bit = MODIFIER_NAMES.get(p.lower())
        if bit is None:
            raise HotkeyError(f"άγνωστο πλήκτρο τροποποίησης: {p}")
        mods |= bit
        mod_names.append(p.capitalize())
    key = parts[-1]
    match = next((k for k in KEYS if k.lower() == key.lower()), None)
    if match is None:
        raise HotkeyError(f"άγνωστο πλήκτρο: {key}")
    if not mods and match not in STANDALONE_OK:
        raise HotkeyError(f"το {match} χρειάζεται Ctrl, Alt, Shift ή Win")
    ordered = [m for m in MODIFIER_ORDER if m in mod_names]
    return mods, KEYS[match], "+".join(ordered + [match])


def describe_error(code: int, combo: str) -> str:
    if code == w.ERROR_HOTKEY_ALREADY_REGISTERED:
        return f"Η συντόμευση {combo} χρησιμοποιείται ήδη από άλλη εφαρμογή"
    return f"Η συντόμευση {combo} δεν καταχωρήθηκε (σφάλμα {code})"


class HotkeyThread(threading.Thread):
    MAIN_ID = 1
    CANCEL_ID = 2
    _WM_REREGISTER = w.WM_APP + 1
    _WM_CANCEL_KEY = w.WM_APP + 2

    def __init__(self, combo: str, on_press, on_release, on_cancel, on_status):
        super().__init__(name="lalia-hotkey", daemon=True)
        self._combo = combo
        self._vk = 0
        self._on_press = on_press
        self._on_release = on_release
        self._on_cancel = on_cancel
        self._on_status = on_status  # (ok: bool, message: str)
        self._thread_id = 0
        self._ready = threading.Event()
        self._held = False
        self._cancel_registered = False
        self.registered = False

    # -- called from other threads ------------------------------------------
    def wait_ready(self, timeout: float = 2.0) -> None:
        self._ready.wait(timeout)

    def set_combo(self, combo: str) -> None:
        self._combo = combo
        self._post(self._WM_REREGISTER, 0)

    def set_cancel_enabled(self, enabled: bool) -> None:
        self._post(self._WM_CANCEL_KEY, 1 if enabled else 0)

    def stop(self) -> None:
        self._post(w.WM_QUIT, 0)

    def _post(self, msg: int, wparam: int) -> None:
        if self._thread_id:
            w.PostThreadMessageW(self._thread_id, msg, wparam, 0)

    # -- the thread ------------------------------------------------------------
    def run(self) -> None:
        self._thread_id = w.GetCurrentThreadId()
        msg = w.MSG()
        w.PeekMessageW(ctypes.byref(msg), None, w.WM_USER, w.WM_USER, w.PM_NOREMOVE)  # creates the queue
        self._ready.set()
        self._register()
        while True:
            r = w.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            if msg.message == w.WM_HOTKEY:
                if msg.wParam == self.MAIN_ID:
                    self._main_pressed()
                elif msg.wParam == self.CANCEL_ID:
                    self._safe(self._on_cancel)
            elif msg.message == self._WM_REREGISTER:
                self._register()
            elif msg.message == self._WM_CANCEL_KEY:
                self._set_cancel(bool(msg.wParam))
        w.UnregisterHotKey(None, self.MAIN_ID)
        w.UnregisterHotKey(None, self.CANCEL_ID)

    def _register(self) -> None:
        w.UnregisterHotKey(None, self.MAIN_ID)
        self.registered = False
        try:
            mods, vk, text = parse(self._combo)
        except HotkeyError as e:
            self._safe(self._on_status, False, f"Μη έγκυρη συντόμευση: {e}")
            return
        # No MOD_NOREPEAT: auto-repeat must keep arriving as WM_HOTKEY (and stay
        # swallowed) rather than leak into the focused app as key presses.
        if w.RegisterHotKey(None, self.MAIN_ID, mods, vk):
            self._vk = vk
            self.registered = True
            log.info("hotkey %s registered", text)
            self._safe(self._on_status, True, text)
        else:
            code = ctypes.get_last_error()
            log.warning("hotkey %s not registered: %s", text, code)
            self._safe(self._on_status, False, describe_error(code, text))

    def _set_cancel(self, enabled: bool) -> None:
        if enabled and not self._cancel_registered:
            self._cancel_registered = bool(w.RegisterHotKey(None, self.CANCEL_ID, 0, w.VK_ESCAPE))
        elif not enabled and self._cancel_registered:
            w.UnregisterHotKey(None, self.CANCEL_ID)
            self._cancel_registered = False

    def _main_pressed(self) -> None:
        if self._held:  # auto-repeat while the key is held
            return
        self._held = True
        self._safe(self._on_press)
        threading.Thread(target=self._wait_release, args=(self._vk,), name="lalia-release",
                         daemon=True).start()

    def _wait_release(self, vk: int) -> None:
        while w.key_down(vk):
            time.sleep(0.012)
        self._held = False
        self._safe(self._on_release)

    @staticmethod
    def _safe(fn, *args) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("hotkey callback failed")
