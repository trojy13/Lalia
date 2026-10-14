"""The controller: recording state, the recognition worker, and the windows.

Threads: Tk main loop (all state and UI), the hotkey thread, the tray thread,
PortAudio's callback thread, and one worker that loads the model, recognises
and types, one dictation at a time and in order. Other threads reach the main
loop only through call_soon().
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass

import numpy as np
from PIL import ImageTk

from . import autostart, config, icons, paths, sounds, textproc, vocabulary
from .audio import SAMPLE_RATE, Recorder
from .history import History
from .hotkey import HotkeyThread
from .micbutton import MicButton, foreground_title, title_matches
from .output import Deliverer, Delivery, Target, blocked_by_elevation, capture_target
from .overlay import Overlay
from .recognition import recognise
from .transcriber import MODEL_SIZES_MB, Transcriber
from .tray import Tray

log = logging.getLogger(__name__)

HOLD_THRESHOLD = 0.4  # "both" mode: held longer than this = push-to-talk, shorter = toggle
MIN_SECONDS = 0.3


@dataclass
class Job:
    audio: np.ndarray
    target: Target
    settings: config.Settings
    generation: int
    lexicon: vocabulary.Lexicon | None


def preview(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


class App:
    def __init__(self, settings: config.Settings, background: bool = False):
        self.settings = settings
        self.background = background
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(paths.APP_TITLE)
        self._icon_photo = ImageTk.PhotoImage(icons.mic_image("idle", 64))
        self.root.iconphoto(True, self._icon_photo)
        self.root.report_callback_exception = self._tk_error
        self.scale = self.root.winfo_fpixels("1i") / 96.0

        self._calls: queue.SimpleQueue = queue.SimpleQueue()
        self._jobs: queue.Queue = queue.Queue()
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self.lexicon = self._build_lexicon(settings)
        self.history = History()
        self.overlay = Overlay(self.root, self.scale, settings.overlay_position)
        self.micbutton: MicButton | None = None
        self.settings_window = None

        self.state = "idle"  # idle | recording
        self._rec_source = ""
        self._rec_started = 0.0
        self._max_job = None
        self._pending = 0
        self.generation = 0
        self.model_state = "loading"  # loading | downloading | ready | error
        self.model_message = "Φόρτωση μοντέλου…"
        self.hotkey_ok = False
        self.hotkey_message = ""
        self._download_base = 0
        self._quitting = False

        self.hotkeys = HotkeyThread(
            settings.hotkey,
            on_press=lambda: self.call_soon(self.on_hotkey_press),
            on_release=lambda: self.call_soon(self.on_hotkey_release),
            on_cancel=lambda: self.call_soon(self.cancel),
            on_status=lambda ok, msg: self.call_soon(self._hotkey_status, ok, msg),
        )
        self.tray = Tray(self)
        self.worker = threading.Thread(target=self._work_loop, name="lalia-worker", daemon=True)

    # -- plumbing ------------------------------------------------------------------
    def call_soon(self, fn, *args) -> None:
        self._calls.put((fn, args))

    def _pump(self) -> None:
        while True:
            try:
                fn, args = self._calls.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception:
                log.exception("UI call failed")
        if not self._quitting:
            self.root.after(15, self._pump)

    def _tk_error(self, exc, val, tb) -> None:
        log.error("Tk callback failed", exc_info=(exc, val, tb))

    def run(self) -> None:
        sounds.ensure()
        self.hotkeys.start()
        self.tray.start()
        self.worker.start()
        self._jobs.put(("load", None))
        if self.settings.mic_button:
            self._create_mic_button()
        if not self.settings.first_run_done:
            self.tray.promote_later()
            self.settings.first_run_done = True
            config.save(self.settings)
            self.show_settings()
        elif not self.background:
            self.show_settings()
        self.root.after(15, self._pump)
        self.root.after(500, self._watch_foreground)
        self.root.mainloop()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.recorder.abort()
        self.hotkeys.stop()
        self.tray.stop()
        self._jobs.put(("quit", None))
        self.root.after(50, self.root.destroy)

    # -- status text -----------------------------------------------------------------
    def status_line(self) -> str:
        if not self.hotkey_ok and self.hotkey_message:
            return self.hotkey_message
        if self.model_state != "ready":
            return self.model_message
        return f"Έτοιμη · {self.settings.hotkey} · {self.transcriber.device_label}"

    def _refresh_tray(self) -> None:
        if self.state == "recording":
            st = "recording"
        elif self._pending:
            st = "processing"
        elif self.model_state in ("loading", "downloading"):
            st = "loading"
        elif self.model_state == "error" or not self.hotkey_ok:
            st = "error"
        else:
            st = "idle"
        self.tray.set_state(st, f"{paths.APP_TITLE} — {self.status_line()}")
        if self.micbutton:
            self.micbutton.set_state("idle" if st in ("loading", "error") else st)
        if self.settings_window:
            self.settings_window.refresh_status()

    def _hotkey_status(self, ok: bool, message: str) -> None:
        self.hotkey_ok = ok
        self.hotkey_message = "" if ok else message
        if not ok:
            self.tray.notify(message)
        self._refresh_tray()

    # -- recording ----------------------------------------------------------------------
    def on_hotkey_press(self) -> None:
        if self.state == "recording":
            if self.settings.mode in ("toggle", "both"):
                self.stop_recording()
            return
        self.start_recording("hotkey")

    def on_hotkey_release(self) -> None:
        if self.state != "recording" or self._rec_source != "hotkey":
            return
        held = time.monotonic() - self._rec_started
        if self.settings.mode == "hold" or (self.settings.mode == "both" and held >= HOLD_THRESHOLD):
            self.stop_recording()

    def on_mic_click(self) -> None:
        if self.state == "recording":
            self.stop_recording()
        else:
            self.start_recording("button")

    def start_recording(self, source: str) -> None:
        if self.state == "recording":
            return
        try:
            self.recorder.start(self.settings.microphone)
        except Exception as e:
            log.warning("microphone failed: %s", e)
            self._play("error")
            self.overlay.show("error", "Το μικρόφωνο δεν άνοιξε · δείτε τις Ρυθμίσεις", auto_hide_ms=3500)
            return
        self.state = "recording"
        self._rec_source = source
        self._rec_started = time.monotonic()
        self._play("start")
        self.overlay.level_fn = lambda: self.recorder.level
        hint = "Esc: ακύρωση"
        self.overlay.show("recording", "Ακούω…", hint=hint)
        self.hotkeys.set_cancel_enabled(True)
        self._max_job = self.root.after(self.settings.max_seconds * 1000, self._max_reached)
        self._refresh_tray()

    def _max_reached(self) -> None:
        self._max_job = None
        if self.state == "recording":
            self.stop_recording()

    def stop_recording(self) -> None:
        if self.state != "recording":
            return
        if self._max_job:
            self.root.after_cancel(self._max_job)
            self._max_job = None
        audio = self.recorder.stop()
        self.state = "idle"
        self._play("stop")
        target = capture_target(self.settings.target)
        if len(audio) < MIN_SECONDS * SAMPLE_RATE:
            if target.foreground and blocked_by_elevation(target.foreground):
                # Windows hides the key state of administrator windows from normal
                # programs, so push-to-talk cannot see the key being held there.
                self.overlay.show("info", "Παράθυρο διαχειριστή · ξεκινήστε τη Λαλιά ως διαχειριστής "
                                  "ή χρησιμοποιήστε «Πάτημα»", auto_hide_ms=5000)
            else:
                self.overlay.show("info", "Πολύ σύντομο · κρατήστε πατημένη τη συντόμευση όσο μιλάτε",
                                  auto_hide_ms=2200)
            self._after_job_change()
            return
        self._pending += 1
        self._jobs.put(("dictation", Job(audio, target, self.settings.copy(), self.generation, self.lexicon)))
        self._show_processing()
        self._refresh_tray()

    def cancel(self) -> None:
        if self.state == "recording":
            if self._max_job:
                self.root.after_cancel(self._max_job)
                self._max_job = None
            self.recorder.abort()
            self.state = "idle"
        elif not self._pending:
            return
        self.generation += 1  # queued dictations of the old generation are dropped
        self.overlay.show("info", "Ακυρώθηκε", auto_hide_ms=900)
        self._after_job_change()

    def _show_processing(self) -> None:
        if self.model_state == "downloading":
            self.overlay.show("loading", self._download_text())
        elif self.model_state == "loading":
            self.overlay.show("loading", "Φόρτωση μοντέλου…")
        else:
            self.overlay.show("processing", "Μεταγραφή…", hint="Esc: ακύρωση")

    def _after_job_change(self) -> None:
        if self.state != "recording" and not self._pending:
            self.hotkeys.set_cancel_enabled(False)
        self._refresh_tray()

    def _job_finished(self, text: str | None, result: Delivery | None) -> None:
        self._pending = max(0, self._pending - 1)
        if self.state != "recording":
            if self._pending:
                self._show_processing()
            elif result is None:
                pass  # cancelled; the overlay already said so
            elif result.ok and text:
                msg = result.message or preview(text)
                self.overlay.show("done", msg, auto_hide_ms=1600)
            elif result.message:
                quiet = result.in_clipboard or result.notice
                if not quiet:
                    self._play("error")
                self.overlay.show("info" if quiet else "error", result.message,
                                  auto_hide_ms=2200 if result.notice else 3800)
            else:
                self.overlay.hide()
        self._after_job_change()

    def _play(self, name: str) -> None:
        if self.settings.sounds:
            sounds.play(name)

    # -- the worker ---------------------------------------------------------------------
    def _work_loop(self) -> None:
        deliverer = Deliverer()
        while True:
            try:
                kind, payload = self._jobs.get(timeout=30)
            except queue.Empty:
                self._maybe_unload()
                continue
            if kind == "quit":
                break
            try:
                if kind == "load":
                    self._ensure_model(self.settings)
                elif kind == "dictation":
                    self._process(payload, deliverer)
            except Exception:
                log.exception("worker job %s failed", kind)
                if kind == "dictation":
                    self.call_soon(self._job_finished, "", Delivery(False, "Σφάλμα · δείτε το αρχείο καταγραφής"))

    def _ensure_model(self, s: config.Settings) -> bool:
        key = (s.model, s.device)
        if self.transcriber.loaded_key() == key:
            return True
        downloading = not self.transcriber.is_downloaded(s.model)
        self.call_soon(self._model_loading, downloading)
        try:
            self.transcriber.load(s.model, s.device)
        except Exception as e:
            log.exception("model load failed")
            self.call_soon(self._model_failed, str(e))
            return False
        self.call_soon(self._model_ready)
        return True

    def _process(self, job: Job, deliverer: Deliverer) -> None:
        s = job.settings
        if job.generation != self.generation:
            self.call_soon(self._job_finished, None, None)
            return
        if not self._ensure_model(s):
            self.call_soon(self._job_finished, "", Delivery(False, "Το μοντέλο δεν φορτώθηκε · δείτε τις Ρυθμίσεις"))
            return
        result = recognise(self.transcriber, job.audio, s, job.lexicon)
        text = textproc.finalize(result.text, replacements=s.replacements,
                                 spoken_punctuation=s.spoken_punctuation, trailing_space=s.trailing_space)
        log.info("dictation: %.1fs audio, recognised in %.2fs%s, %d characters",
                 result.seconds_audio, result.seconds_taken,
                 f" (second reading, {result.candidates} terms)" if result.second_reading else "", len(text))
        if job.generation != self.generation:
            self.call_soon(self._job_finished, None, None)
            return
        if not text:
            self.call_soon(self._job_finished, "", Delivery(False, "Δεν ακούστηκε ομιλία", notice=True))
            return
        delivery = deliverer.deliver(
            text, job.target, method=s.paste_method, restore_clipboard=s.restore_clipboard,
            auto_enter=s.auto_enter, paste_delay_ms=s.paste_delay_ms, restore_delay_ms=s.restore_delay_ms)
        self.history.add(text, s.history_limit, seconds=round(result.seconds_audio, 1),
                         took=round(result.seconds_taken, 2))
        self.call_soon(self._job_finished, text, delivery)
        if self.settings_window:
            self.call_soon(self.settings_window.refresh_history)

    def _maybe_unload(self) -> None:
        minutes = self.settings.unload_after_minutes
        if (minutes > 0 and self.transcriber.loaded and self.state == "idle" and not self._pending
                and time.monotonic() - self.transcriber.last_used > minutes * 60):
            self.transcriber.unload()
            self.call_soon(self._model_unloaded)

    # -- model state (main thread) --------------------------------------------------------
    def _download_text(self) -> str:
        got = max(0, self.transcriber.download_size_so_far() - self._download_base) / 1e6
        total = MODEL_SIZES_MB.get(self.settings.model)
        return f"Λήψη μοντέλου… {got:,.0f}" + (f" / {total:,} MB" if total else " MB")

    def _model_loading(self, downloading: bool) -> None:
        self.model_state = "downloading" if downloading else "loading"
        if downloading:
            self._download_base = self.transcriber.download_size_so_far()
            self.model_message = "Λήψη μοντέλου (μία φορά)…"
            self.tray.notify(f"Λήψη του μοντέλου {self.settings.model}. Γίνεται μόνο την πρώτη φορά.")
            self.overlay.show("loading", self._download_text())
            self.root.after(1000, self._download_progress)
        else:
            self.model_message = "Φόρτωση μοντέλου…"
        self._refresh_tray()

    def _download_progress(self) -> None:
        if self.model_state != "downloading":
            return
        text = self._download_text()
        self.model_message = text
        if self.overlay.kind == "loading":
            self.overlay.show("loading", text)
        if self.settings_window:
            self.settings_window.refresh_status()
        self.root.after(1000, self._download_progress)

    def _model_ready(self) -> None:
        was_downloading = self.model_state == "downloading"
        self.model_state = "ready"
        self.model_message = f"{self.settings.model} · {self.transcriber.device_label}"
        if self.transcriber.last_error:
            self.tray.notify(self.transcriber.last_error)
        if self.overlay.kind == "loading":
            if self._pending:
                self._show_processing()
            else:
                self.overlay.show("done", f"Έτοιμη · {self.settings.hotkey} για υπαγόρευση",
                                  auto_hide_ms=2500 if was_downloading else 1200)
        self._refresh_tray()

    def _model_failed(self, message: str) -> None:
        self.model_state = "error"
        self.model_message = "Το μοντέλο δεν φορτώθηκε"
        self.tray.notify(message[:250])
        if self.overlay.kind == "loading":
            self.overlay.show("error", self.model_message, auto_hide_ms=4000)
        self._refresh_tray()

    def _model_unloaded(self) -> None:
        self.model_state = "ready"  # it reloads on the next dictation
        self.model_message = f"{self.settings.model} · εκτός μνήμης μέχρι την επόμενη υπαγόρευση"
        self._refresh_tray()

    # -- floating button ---------------------------------------------------------------------
    def _create_mic_button(self) -> None:
        if self.micbutton:
            return
        s = self.settings
        self.micbutton = MicButton(self.root, self.scale, x=s.mic_button_x, y=s.mic_button_y,
                                   on_click=self.on_mic_click, on_right_click=self.show_settings,
                                   on_moved=self._mic_moved)
        self._refresh_tray()

    def _destroy_mic_button(self) -> None:
        if self.micbutton:
            self.micbutton.destroy()
            self.micbutton = None

    def _mic_moved(self, x: int, y: int) -> None:
        self.settings.mic_button_x, self.settings.mic_button_y = x, y
        config.save(self.settings)

    def toggle_mic_button(self) -> None:
        new = self.settings.copy()
        new.mic_button = not new.mic_button
        self.apply_settings(new)

    def toggle_sounds(self) -> None:
        new = self.settings.copy()
        new.sounds = not new.sounds
        self.apply_settings(new)

    def _watch_foreground(self) -> None:
        """PCB's 'only over the ERP' rule, for the floating button."""
        if self._quitting:
            return
        if self.micbutton:
            patterns = self.settings.mic_button_only_over
            if not patterns.strip() or self.state == "recording":
                self.micbutton.set_visible(True)
            else:
                title, ours = foreground_title()
                if not ours:  # our own windows leave the button as it was
                    self.micbutton.set_visible(title_matches(title, patterns))
        self.root.after(500, self._watch_foreground)

    # -- settings ---------------------------------------------------------------------------
    def show_settings(self) -> None:
        from .settings_ui import SettingsWindow

        if self.settings_window and self.settings_window.alive:
            self.settings_window.focus()
            return
        self.settings_window = SettingsWindow(self)

    def settings_closed(self) -> None:
        self.settings_window = None

    @staticmethod
    def _build_lexicon(s: config.Settings) -> vocabulary.Lexicon | None:
        if not s.medical_vocabulary and not s.custom_words:
            return None
        return vocabulary.build_lexicon(s.custom_words, s.medical_vocabulary)

    def apply_settings(self, new: config.Settings) -> None:
        old = self.settings
        self.settings = new
        config.save(new)
        if (new.custom_words, new.medical_vocabulary) != (old.custom_words, old.medical_vocabulary):
            self.lexicon = self._build_lexicon(new)
        if new.hotkey != old.hotkey:
            self.hotkeys.set_combo(new.hotkey)
        if (new.model, new.device) != (old.model, old.device):
            self.model_state = "loading"
            self.model_message = "Φόρτωση μοντέλου…"
            self._jobs.put(("load", None))
        if new.mic_button and not self.micbutton:
            self._create_mic_button()
        elif not new.mic_button and self.micbutton:
            self._destroy_mic_button()
        self.overlay.position = new.overlay_position
        if new.overlay_position == "none":
            self.overlay.hide()
        if new.start_with_windows != autostart.is_enabled():
            autostart.set_enabled(new.start_with_windows)
        self._refresh_tray()
