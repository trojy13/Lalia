"""ctypes bindings for the Win32 calls Lalia makes.

Every function gets explicit argtypes/restype: handles are 64-bit, and ctypes'
default int return would silently truncate an HWND.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:  # pragma: no cover - dwmapi ships with every supported Windows
    dwmapi = None

ULONG_PTR = ctypes.c_size_t
LONG_PTR = ctypes.c_ssize_t

# --- messages and hotkeys -------------------------------------------------
WM_QUIT = 0x0012
WM_USER = 0x0400
WM_APP = 0x8000
WM_HOTKEY = 0x0312
PM_NOREMOVE = 0x0000

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

ERROR_ACCESS_DENIED = 5
ERROR_ALREADY_EXISTS = 183
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

# --- virtual keys ---------------------------------------------------------
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_INSERT = 0x2D
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_V = 0x56

# Keys on the navigation cluster need KEYEVENTF_EXTENDEDKEY, otherwise Windows
# reads them as their numeric-keypad twins (Insert would become Numpad 0).
EXTENDED_KEYS = {
    0x21, 0x22, 0x23, 0x24,  # PageUp, PageDown, End, Home
    0x25, 0x26, 0x27, 0x28,  # arrows
    0x2D, 0x2E,  # Insert, Delete
    0x5B, 0x5C, 0x5D,  # LWin, RWin, Apps
    0x6F,  # Numpad divide
    0x90,  # NumLock
    0xA3, 0xA5,  # RControl, RMenu
}

# --- SendInput ------------------------------------------------------------
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MAPVK_VK_TO_VSC = 0
SM_SWAPBUTTON = 23

# Marks input Lalia injected, should anything ever need to tell it apart.
LALIA_EXTRA_INFO = 0x4C414C49  # "LALI"


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


# --- windows --------------------------------------------------------------
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_APPWINDOW = 0x00040000

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9

HWND_TOPMOST = wintypes.HWND(-1)
HWND_MESSAGE = wintypes.HWND(-3)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

# --- clipboard ------------------------------------------------------------
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# Formats whose handle is not an HGLOBAL (GDI objects, metafiles, owner-display):
# they cannot be copied byte-for-byte, so a clipboard snapshot leaves them out.
CF_NON_HGLOBAL = {2, 3, 9, 14, 0x0080, 0x0082, 0x0083, 0x008E}

# --- processes ------------------------------------------------------------
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TokenElevation = 20
WAIT_OBJECT_0 = 0
INFINITE = 0xFFFFFFFF
EVENT_MODIFY_STATE = 0x0002


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("lPrivate", wintypes.DWORD),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _fn(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype = restype
    f.argtypes = argtypes
    return f


H = wintypes.HANDLE
HWND = wintypes.HWND
BOOL = wintypes.BOOL
UINT = wintypes.UINT
DWORD = wintypes.DWORD
INT = ctypes.c_int

RegisterHotKey = _fn(user32, "RegisterHotKey", BOOL, HWND, INT, UINT, UINT)
UnregisterHotKey = _fn(user32, "UnregisterHotKey", BOOL, HWND, INT)
GetMessageW = _fn(user32, "GetMessageW", BOOL, ctypes.POINTER(MSG), HWND, UINT, UINT)
PeekMessageW = _fn(user32, "PeekMessageW", BOOL, ctypes.POINTER(MSG), HWND, UINT, UINT, UINT)
PostThreadMessageW = _fn(user32, "PostThreadMessageW", BOOL, DWORD, UINT, wintypes.WPARAM, wintypes.LPARAM)
GetAsyncKeyState = _fn(user32, "GetAsyncKeyState", ctypes.c_short, INT)
MapVirtualKeyW = _fn(user32, "MapVirtualKeyW", UINT, UINT, UINT)
SendInput = _fn(user32, "SendInput", UINT, UINT, ctypes.POINTER(INPUT), INT)
GetSystemMetrics = _fn(user32, "GetSystemMetrics", INT, INT)

GetForegroundWindow = _fn(user32, "GetForegroundWindow", HWND)
SetForegroundWindow = _fn(user32, "SetForegroundWindow", BOOL, HWND)
BringWindowToTop = _fn(user32, "BringWindowToTop", BOOL, HWND)
WindowFromPoint = _fn(user32, "WindowFromPoint", HWND, wintypes.POINT)
GetAncestor = _fn(user32, "GetAncestor", HWND, HWND, UINT)
GetParent = _fn(user32, "GetParent", HWND, HWND)
GetCursorPos = _fn(user32, "GetCursorPos", BOOL, ctypes.POINTER(wintypes.POINT))
SetCursorPos = _fn(user32, "SetCursorPos", BOOL, INT, INT)
GetWindowThreadProcessId = _fn(user32, "GetWindowThreadProcessId", DWORD, HWND, ctypes.POINTER(DWORD))
AttachThreadInput = _fn(user32, "AttachThreadInput", BOOL, DWORD, DWORD, BOOL)
IsIconic = _fn(user32, "IsIconic", BOOL, HWND)
IsWindow = _fn(user32, "IsWindow", BOOL, HWND)
ShowWindow = _fn(user32, "ShowWindow", BOOL, HWND, INT)
SetWindowPos = _fn(user32, "SetWindowPos", BOOL, HWND, HWND, INT, INT, INT, INT, UINT)
GetWindowLongPtrW = _fn(user32, "GetWindowLongPtrW", LONG_PTR, HWND, INT)
SetWindowLongPtrW = _fn(user32, "SetWindowLongPtrW", LONG_PTR, HWND, INT, LONG_PTR)
GetWindowTextW = _fn(user32, "GetWindowTextW", INT, HWND, wintypes.LPWSTR, INT)
GetClassNameW = _fn(user32, "GetClassNameW", INT, HWND, wintypes.LPWSTR, INT)
MonitorFromPoint = _fn(user32, "MonitorFromPoint", H, wintypes.POINT, DWORD)
GetMonitorInfoW = _fn(user32, "GetMonitorInfoW", BOOL, H, ctypes.POINTER(MONITORINFO))
CreateWindowExW = _fn(
    user32, "CreateWindowExW", HWND,
    DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, DWORD, INT, INT, INT, INT, HWND, H, H, wintypes.LPVOID,
)

OpenClipboard = _fn(user32, "OpenClipboard", BOOL, HWND)
CloseClipboard = _fn(user32, "CloseClipboard", BOOL)
EmptyClipboard = _fn(user32, "EmptyClipboard", BOOL)
GetClipboardData = _fn(user32, "GetClipboardData", H, UINT)
SetClipboardData = _fn(user32, "SetClipboardData", H, UINT, H)
EnumClipboardFormats = _fn(user32, "EnumClipboardFormats", UINT, UINT)
RegisterClipboardFormatW = _fn(user32, "RegisterClipboardFormatW", UINT, wintypes.LPCWSTR)
GetClipboardSequenceNumber = _fn(user32, "GetClipboardSequenceNumber", DWORD)

GetCurrentThreadId = _fn(kernel32, "GetCurrentThreadId", DWORD)
GetCurrentProcessId = _fn(kernel32, "GetCurrentProcessId", DWORD)
GetCurrentProcess = _fn(kernel32, "GetCurrentProcess", H)
GlobalAlloc = _fn(kernel32, "GlobalAlloc", H, UINT, ctypes.c_size_t)
GlobalLock = _fn(kernel32, "GlobalLock", wintypes.LPVOID, H)
GlobalUnlock = _fn(kernel32, "GlobalUnlock", BOOL, H)
GlobalSize = _fn(kernel32, "GlobalSize", ctypes.c_size_t, H)
GlobalFree = _fn(kernel32, "GlobalFree", H, H)
CreateMutexW = _fn(kernel32, "CreateMutexW", H, wintypes.LPVOID, BOOL, wintypes.LPCWSTR)
CreateEventW = _fn(kernel32, "CreateEventW", H, wintypes.LPVOID, BOOL, BOOL, wintypes.LPCWSTR)
OpenEventW = _fn(kernel32, "OpenEventW", H, DWORD, BOOL, wintypes.LPCWSTR)
SetEvent = _fn(kernel32, "SetEvent", BOOL, H)
WaitForSingleObject = _fn(kernel32, "WaitForSingleObject", DWORD, H, DWORD)
CloseHandle = _fn(kernel32, "CloseHandle", BOOL, H)
OpenProcess = _fn(kernel32, "OpenProcess", H, DWORD, BOOL, DWORD)

OpenProcessToken = _fn(advapi32, "OpenProcessToken", BOOL, H, DWORD, ctypes.POINTER(H))
GetTokenInformation = _fn(
    advapi32, "GetTokenInformation", BOOL, H, INT, wintypes.LPVOID, DWORD, ctypes.POINTER(DWORD),
)


# --- small helpers ----------------------------------------------------------
def window_text(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    GetWindowTextW(hwnd, buf, 512)
    return buf.value


def class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_pid(hwnd) -> int:
    pid = DWORD(0)
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def work_area_at(x: int, y: int) -> tuple[int, int, int, int]:
    """Work area (left, top, right, bottom) of the monitor nearest to a point."""
    mon = MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and GetMonitorInfoW(mon, ctypes.byref(info)):
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    return 0, 0, GetSystemMetrics(0), GetSystemMetrics(1)


def key_down(vk: int) -> bool:
    return bool(GetAsyncKeyState(vk) & 0x8000)


def make_floating(hwnd, click_through: bool = False) -> None:
    """Always on top, never takes keyboard focus, no taskbar button.

    The same idea as PCB's notification panel (SetWindowPos HWND_TOPMOST with
    SWP_NOACTIVATE, ShowWindow SW_SHOWNOACTIVATE), plus WS_EX_NOACTIVATE so a
    click on the window leaves the focus in the app being dictated into.
    """
    style = GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
    style &= ~WS_EX_APPWINDOW
    if click_through:
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
    SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3
GWLP_WNDPROC = -4
WNDPROC = ctypes.WINFUNCTYPE(LONG_PTR, HWND, UINT, wintypes.WPARAM, wintypes.LPARAM)
CallWindowProcW = _fn(user32, "CallWindowProcW", LONG_PTR,
                      ctypes.c_void_p, HWND, UINT, wintypes.WPARAM, wintypes.LPARAM)
_wndprocs: dict[int, object] = {}  # keeps the ctypes callbacks alive


def no_activate_on_click(hwnd) -> None:
    """Tk answers WM_MOUSEACTIVATE by activating its toplevel, WS_EX_NOACTIVATE
    or not. Subclass the window so a click is delivered without activation."""
    hwnd = int(hwnd)
    if hwnd in _wndprocs:
        return
    old = GetWindowLongPtrW(hwnd, GWLP_WNDPROC)

    @WNDPROC
    def proc(h, msg, wparam, lparam):
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        return CallWindowProcW(old, h, msg, wparam, lparam)

    _wndprocs[hwnd] = proc
    SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(proc, ctypes.c_void_p).value)


def show_no_activate(hwnd, x: int | None = None, y: int | None = None) -> None:
    flags = SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
    if x is None or y is None:
        flags |= SWP_NOMOVE
        x = y = 0
    SetWindowPos(hwnd, HWND_TOPMOST, x, y, 0, 0, flags)
    ShowWindow(hwnd, SW_SHOWNOACTIVATE)


def hide(hwnd) -> None:
    ShowWindow(hwnd, SW_HIDE)


def round_corners(hwnd) -> None:
    """Windows 11 rounded corners; Windows 10 ignores the attribute."""
    if dwmapi is None:
        return
    pref = ctypes.c_int(DWMWCP_ROUND)
    try:
        dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE,
                                     ctypes.byref(pref), ctypes.sizeof(pref))
    except OSError:
        pass


def set_dpi_awareness() -> None:
    """System-DPI aware: Tk scales with the primary monitor's DPI, and every
    coordinate Lalia reads or sends (cursor, monitors, clicks) shares one space."""
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        try:
            user32.SetProcessDPIAware()
        except (OSError, AttributeError):
            pass


def set_app_user_model_id(app_id: str) -> None:
    """Own taskbar identity and icon instead of being grouped under python.exe."""
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(wintypes.LPCWSTR(app_id))
    except (OSError, AttributeError):
        pass
