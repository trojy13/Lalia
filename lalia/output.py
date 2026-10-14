"""Putting the text into the target window.

Paste (default): the clipboard is saved, the text is put on it, the paste keys
are sent, and the old clipboard comes back unless something else changed it in
the meantime. The text is marked so Windows clipboard history (Win+V) and cloud
clipboard skip it.

Type: every character goes as a KEYEVENTF_UNICODE key event, which, unlike
typing by virtual key, does not depend on the keyboard layout, so Greek arrives
as Greek whatever layout is active.
"""
from __future__ import annotations

import ctypes
import logging
import os
import time
from dataclasses import dataclass

from . import win32 as w

log = logging.getLogger(__name__)

# Top-level windows that are part of the shell, not something to dictate into.
SHELL_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland",
    "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow",
}

PASTE_COMBOS = {
    "ctrl_v": (w.VK_CONTROL, w.VK_V),
    "shift_insert": (w.VK_SHIFT, w.VK_INSERT),
    "ctrl_shift_v": (w.VK_CONTROL, w.VK_SHIFT, w.VK_V),
}

MODIFIERS = (w.VK_SHIFT, w.VK_CONTROL, w.VK_MENU, w.VK_LWIN, w.VK_RWIN)


@dataclass
class Target:
    """Where the user was when the recording stopped."""
    mode: str
    foreground: int
    cursor: tuple[int, int]


@dataclass
class Delivery:
    ok: bool
    message: str = ""
    in_clipboard: bool = False
    notice: bool = False  # nothing went wrong, there was just nothing to type


def capture_target(mode: str) -> Target:
    fg = w.GetForegroundWindow()
    return Target(mode=mode, foreground=int(fg or 0), cursor=w.cursor_pos())


# --- target window ------------------------------------------------------------
def _is_ours_floating(hwnd) -> bool:
    """The overlay or the floating mic button: never a dictation target."""
    if w.window_pid(hwnd) != os.getpid():
        return False
    return bool(w.GetWindowLongPtrW(hwnd, w.GWL_EXSTYLE) & w.WS_EX_NOACTIVATE)


def window_under(point: tuple[int, int]):
    h = w.WindowFromPoint(w.wintypes.POINT(*point))
    if not h:
        return None
    root = w.GetAncestor(h, w.GA_ROOT)
    if not root or w.class_name(root) in SHELL_CLASSES or _is_ours_floating(root):
        return None
    return root


def resolve_window(target: Target):
    """The window to type into, or None."""
    if target.mode in ("under_mouse", "click_at_mouse"):
        under = window_under(target.cursor)
        if under:
            return under
    fg = w.GetForegroundWindow() or target.foreground
    if not fg or w.class_name(fg) in SHELL_CLASSES:  # e.g. the taskbar after a tray click
        return None
    return fg


def _same(a, b) -> bool:
    return int(a or 0) == int(b or 0)


def wait_foreground(hwnd, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if _same(w.GetForegroundWindow(), hwnd):
            return True
        time.sleep(0.01)
    return _same(w.GetForegroundWindow(), hwnd)


def activate(hwnd) -> bool:
    """Bring a window to the front. Windows only lets the process the user is
    interacting with do that, so the input queue of the current foreground
    thread is borrowed for the call (AttachThreadInput)."""
    if _same(w.GetForegroundWindow(), hwnd):
        return True
    if w.IsIconic(hwnd):
        w.ShowWindow(hwnd, w.SW_RESTORE)
    me = w.GetCurrentThreadId()
    fg = w.GetForegroundWindow()
    fg_thread = w.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(fg_thread and fg_thread != me and w.AttachThreadInput(me, fg_thread, True))
    try:
        w.BringWindowToTop(hwnd)
        w.SetForegroundWindow(hwnd)
    finally:
        if attached:
            w.AttachThreadInput(me, fg_thread, False)
    if wait_foreground(hwnd, 0.3):
        return True
    # Last resort: a synthetic Alt press releases the foreground lock.
    _send([_key(w.VK_MENU), _key(w.VK_MENU, up=True)])
    w.SetForegroundWindow(hwnd)
    return wait_foreground(hwnd, 0.3)


# --- elevation (UIPI) ------------------------------------------------------------
class _TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", w.DWORD)]


def _process_elevated(process_handle) -> bool | None:
    token = w.H()
    if not w.OpenProcessToken(process_handle, w.TOKEN_QUERY, ctypes.byref(token)):
        return True if ctypes.get_last_error() == w.ERROR_ACCESS_DENIED else None
    try:
        elev = _TOKEN_ELEVATION()
        size = w.DWORD(0)
        if not w.GetTokenInformation(token, w.TokenElevation, ctypes.byref(elev),
                                     ctypes.sizeof(elev), ctypes.byref(size)):
            return None
        return bool(elev.TokenIsElevated)
    finally:
        w.CloseHandle(token)


def _self_elevated() -> bool:
    return bool(_process_elevated(w.GetCurrentProcess()))


def blocked_by_elevation(hwnd) -> bool:
    """Windows silently drops input sent to an administrator window from a
    normal process (UIPI). Detect it so the text can stay on the clipboard."""
    pid = w.window_pid(hwnd)
    if not pid or pid == os.getpid() or _self_elevated():
        return False
    handle = w.OpenProcess(w.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        return _process_elevated(handle) is True
    finally:
        w.CloseHandle(handle)


# --- keyboard and mouse ---------------------------------------------------------
def _key(vk: int, up: bool = False) -> w.INPUT:
    inp = w.INPUT(type=w.INPUT_KEYBOARD)
    flags = w.KEYEVENTF_KEYUP if up else 0
    if vk in w.EXTENDED_KEYS:
        flags |= w.KEYEVENTF_EXTENDEDKEY
    inp.ki = w.KEYBDINPUT(wVk=vk, wScan=w.MapVirtualKeyW(vk, w.MAPVK_VK_TO_VSC) & 0xFF,
                          dwFlags=flags, time=0, dwExtraInfo=w.LALIA_EXTRA_INFO)
    return inp


def _unicode(unit: int, up: bool = False) -> w.INPUT:
    inp = w.INPUT(type=w.INPUT_KEYBOARD)
    inp.ki = w.KEYBDINPUT(wVk=0, wScan=unit,
                          dwFlags=w.KEYEVENTF_UNICODE | (w.KEYEVENTF_KEYUP if up else 0),
                          time=0, dwExtraInfo=w.LALIA_EXTRA_INFO)
    return inp


def _send(inputs: list[w.INPUT]) -> int:
    if not inputs:
        return 0
    arr = (w.INPUT * len(inputs))(*inputs)
    return w.SendInput(len(inputs), arr, ctypes.sizeof(w.INPUT))


def text_key_events(text: str) -> list[tuple[str, int]]:
    """('vk', code) or ('unit', utf16_code_unit) per key, in order. Pure, for tests."""
    events = []
    for ch in text:
        if ch == "\r":
            continue
        if ch == "\n":
            events.append(("vk", w.VK_RETURN))
        elif ch == "\t":
            events.append(("vk", w.VK_TAB))
        else:
            data = ch.encode("utf-16-le")
            for i in range(0, len(data), 2):
                events.append(("unit", int.from_bytes(data[i:i + 2], "little")))
    return events


def type_text(text: str, chunk: int = 32) -> None:
    batch: list[w.INPUT] = []
    for kind, code in text_key_events(text):
        if kind == "vk":
            batch += [_key(code), _key(code, up=True)]
        else:
            batch += [_unicode(code), _unicode(code, up=True)]
        if len(batch) >= chunk * 2:
            _send(batch)
            batch = []
            time.sleep(0.004)
    _send(batch)


def press_combo(vks) -> None:
    _send([_key(vk) for vk in vks] + [_key(vk, up=True) for vk in reversed(vks)])


def click_at(point: tuple[int, int]) -> None:
    w.SetCursorPos(*point)
    if w.GetSystemMetrics(w.SM_SWAPBUTTON):
        down, up = w.MOUSEEVENTF_RIGHTDOWN, w.MOUSEEVENTF_RIGHTUP
    else:
        down, up = w.MOUSEEVENTF_LEFTDOWN, w.MOUSEEVENTF_LEFTUP
    inputs = []
    for flag in (down, up):
        inp = w.INPUT(type=w.INPUT_MOUSE)
        inp.mi = w.MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flag, time=0, dwExtraInfo=w.LALIA_EXTRA_INFO)
        inputs.append(inp)
    _send(inputs)


def wait_modifiers_released(timeout: float, allow=()) -> None:
    """A Shift or Alt still held from the shortcut would turn Ctrl+V into
    something else, so wait until the user lets go."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not any(w.key_down(vk) for vk in MODIFIERS if vk not in allow):
            return
        time.sleep(0.015)


# --- clipboard --------------------------------------------------------------------
class Clipboard:
    """Used from one thread only (the delivery worker). Owns a message-only
    window, because SetClipboardData fails after EmptyClipboard when the
    clipboard was opened without an owner window."""

    _exclusion_formats: list[tuple[int, bytes]] | None = None

    def __init__(self):
        self._hwnd = w.CreateWindowExW(0, "STATIC", "Lalia clipboard", 0, 0, 0, 0, 0,
                                       w.HWND_MESSAGE, None, None, None)

    def _open(self) -> None:
        for _ in range(40):
            if w.OpenClipboard(self._hwnd):
                return
            time.sleep(0.015)
        raise OSError("the clipboard is busy")

    @staticmethod
    def _alloc(data: bytes):
        h = w.GlobalAlloc(w.GMEM_MOVEABLE, max(1, len(data)))
        if not h:
            raise MemoryError("GlobalAlloc failed")
        p = w.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        w.GlobalUnlock(h)
        return h

    def _put(self, fmt: int, data: bytes) -> None:
        h = self._alloc(data)
        if not w.SetClipboardData(fmt, h):
            w.GlobalFree(h)  # ownership passes to the system only on success

    @classmethod
    def _exclusions(cls) -> list[tuple[int, bytes]]:
        if cls._exclusion_formats is None:
            zero = (0).to_bytes(4, "little")
            cls._exclusion_formats = [
                (w.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing"), zero),
                (w.RegisterClipboardFormatW("CanIncludeInClipboardHistory"), zero),
                (w.RegisterClipboardFormatW("CanUploadToCloudClipboard"), zero),
            ]
        return cls._exclusion_formats

    def snapshot(self) -> list[tuple[int, bytes]]:
        items = []
        self._open()
        try:
            fmt = 0
            while True:
                fmt = w.EnumClipboardFormats(fmt)
                if not fmt:
                    break
                if fmt in w.CF_NON_HGLOBAL or 0x0200 <= fmt <= 0x03FF:  # private / GDI ranges
                    continue
                h = w.GetClipboardData(fmt)
                if not h:
                    continue
                size = w.GlobalSize(h)
                if not size or size > 64 * 1024 * 1024:
                    continue
                p = w.GlobalLock(h)
                if not p:
                    continue
                try:
                    items.append((fmt, ctypes.string_at(p, size)))
                finally:
                    w.GlobalUnlock(h)
        finally:
            w.CloseClipboard()
        return items

    def set_text(self, text: str, private: bool = True) -> int:
        """Put text on the clipboard; returns the clipboard sequence number after."""
        self._open()
        try:
            w.EmptyClipboard()
            self._put(w.CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))
            if private:
                for fmt, data in self._exclusions():
                    self._put(fmt, data)
        finally:
            w.CloseClipboard()
        return w.GetClipboardSequenceNumber()

    def restore(self, items: list[tuple[int, bytes]]) -> None:
        self._open()
        try:
            w.EmptyClipboard()
            present = {fmt for fmt, _ in items}
            for fmt, data in items:
                self._put(fmt, data)
            # The old content is already in clipboard history once; keep the
            # restore from adding it a second time.
            for fmt, data in self._exclusions():
                if fmt not in present:
                    self._put(fmt, data)
        finally:
            w.CloseClipboard()

    def get_text(self) -> str | None:
        self._open()
        try:
            h = w.GetClipboardData(w.CF_UNICODETEXT)
            if not h:
                return None
            p = w.GlobalLock(h)
            try:
                return ctypes.wstring_at(p)
            finally:
                w.GlobalUnlock(h)
        finally:
            w.CloseClipboard()


# --- the whole delivery ---------------------------------------------------------------
class Deliverer:
    def __init__(self):
        self._clipboard: Clipboard | None = None

    @property
    def clipboard(self) -> Clipboard:
        if self._clipboard is None:  # created on the thread that uses it
            self._clipboard = Clipboard()
        return self._clipboard

    def _leave_in_clipboard(self, text: str, message: str) -> Delivery:
        try:
            self.clipboard.set_text(text, private=False)
        except OSError as e:
            return Delivery(False, f"{message} (και το πρόχειρο απέτυχε: {e})")
        return Delivery(False, message, in_clipboard=True)

    def deliver(self, text: str, target: Target, *, method: str, restore_clipboard: bool,
                auto_enter: bool, paste_delay_ms: int, restore_delay_ms: int) -> Delivery:
        if method == "clipboard":
            self.clipboard.set_text(text, private=False)
            return Delivery(True, "Στο πρόχειρο · Ctrl+V για επικόλληση", in_clipboard=True)

        hwnd = resolve_window(target)
        if not hwnd:
            return self._leave_in_clipboard(text, "Δεν βρέθηκε παράθυρο · το κείμενο είναι στο πρόχειρο")
        if not activate(hwnd):
            return self._leave_in_clipboard(text, "Δεν άνοιξε το παράθυρο · Ctrl+V για επικόλληση")
        if blocked_by_elevation(hwnd):
            return self._leave_in_clipboard(
                text, "Το παράθυρο τρέχει ως διαχειριστής · Ctrl+V για επικόλληση")
        if target.mode == "click_at_mouse" and window_under(target.cursor):
            click_at(target.cursor)
            time.sleep(0.06)

        if method == "type":
            wait_modifiers_released(3.0)
            type_text(text)
        else:
            combo = PASTE_COMBOS.get(method, PASTE_COMBOS["ctrl_v"])
            # A held Ctrl does not change Ctrl+V; any other held modifier would.
            wait_modifiers_released(3.0, allow=(w.VK_CONTROL,) if method == "ctrl_v" else ())
            saved = None
            if restore_clipboard:
                try:
                    saved = self.clipboard.snapshot()
                except OSError as e:
                    log.warning("clipboard snapshot failed: %s", e)
            seq = self.clipboard.set_text(text, private=True)
            time.sleep(paste_delay_ms / 1000)
            press_combo(combo)
            if saved is not None:
                # The target reads the clipboard some time after the keystroke;
                # restoring too early would paste the old content.
                time.sleep(restore_delay_ms / 1000)
                if w.GetClipboardSequenceNumber() == seq:
                    try:
                        self.clipboard.restore(saved)
                    except OSError as e:
                        log.warning("clipboard restore failed: %s", e)
        if auto_enter:
            time.sleep(0.05)
            press_combo((w.VK_RETURN,))
        return Delivery(True)
