"""Notification-area icon and menu (pystray, on a thread of its own)."""
from __future__ import annotations

import logging
import os
import threading
import time
import winreg

import pystray

from . import icons, paths

log = logging.getLogger(__name__)


class Tray:
    def __init__(self, app):
        self.app = app
        self._state = "loading"
        self._images = {}
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self.app.status_line(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Ρυθμίσεις…", lambda: app.call_soon(app.show_settings), default=True),
            pystray.MenuItem("Πλωτό κουμπί μικροφώνου", lambda: app.call_soon(app.toggle_mic_button),
                             checked=lambda item: app.settings.mic_button),
            pystray.MenuItem("Ήχοι", lambda: app.call_soon(app.toggle_sounds),
                             checked=lambda item: app.settings.sounds),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Φάκελος δεδομένων", lambda: os.startfile(paths.DATA_DIR)),
            pystray.MenuItem("Έξοδος", lambda: app.call_soon(app.quit)),
        )
        self.icon = pystray.Icon(paths.APP_NAME, icon=self._image("loading"),
                                 title=f"{paths.APP_TITLE} — φόρτωση…", menu=menu)
        self._thread = threading.Thread(target=self._run, name="lalia-tray", daemon=True)

    def _image(self, state: str):
        if state not in self._images:
            self._images[state] = icons.mic_image(state, 64)
        return self._images[state]

    def _run(self) -> None:
        try:
            self.icon.run()
        except Exception:
            log.exception("tray icon stopped")

    def start(self) -> None:
        self._thread.start()

    def set_state(self, state: str, tooltip: str | None = None) -> None:
        try:
            if state != self._state:
                self._state = state
                self.icon.icon = self._image(state)
            if tooltip is not None:
                self.icon.title = tooltip[:127]
            self.icon.update_menu()
        except Exception as e:  # the icon may not be up yet
            log.debug("tray update: %s", e)

    def notify(self, message: str, title: str = paths.APP_TITLE) -> None:
        try:
            self.icon.notify(message, title)
        except Exception as e:
            log.debug("tray notify: %s", e)

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass

    def promote_later(self, delay: float = 6.0) -> None:
        """Windows 11 hides new tray icons behind the ^ overflow. Like PCB's
        companion, set IsPromoted under HKCU\\Control Panel\\NotifyIconSettings,
        but only on entries whose tooltip is Lalia's, since the executable is
        python(w).exe and could host other tray icons too."""
        def work():
            time.sleep(delay)
            root = r"Control Panel\NotifyIconSettings"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root) as k:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(k, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            with winreg.OpenKey(k, sub, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as entry:
                                tip, _ = winreg.QueryValueEx(entry, "InitialTooltip")
                                if isinstance(tip, str) and tip.startswith(paths.APP_TITLE):
                                    winreg.SetValueEx(entry, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        except OSError:
                            continue
            except OSError:
                pass  # Windows 10 has no such key
        threading.Thread(target=work, name="lalia-promote", daemon=True).start()
