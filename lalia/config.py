"""Settings: one JSON file, unknown keys ignored, bad values fall back to defaults."""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

MODES = ("hold", "toggle", "both")
LANGUAGES = ("el_en", "el", "en", "auto")  # el_en = Greek with English words and phrases
SECOND_PASS = ("auto", "on", "off")  # auto = only when recognition runs on the GPU
DEVICES = ("auto", "cuda", "cpu")
PASTE_METHODS = ("ctrl_v", "shift_insert", "ctrl_shift_v", "type", "clipboard")
TARGETS = ("under_mouse", "focused", "click_at_mouse")
OVERLAY_POSITIONS = ("bottom", "top", "none")

# Values restricted to a fixed set of choices.
_CHOICES = {
    "mode": MODES,
    "language": LANGUAGES,
    "second_pass": SECOND_PASS,
    "device": DEVICES,
    "paste_method": PASTE_METHODS,
    "target": TARGETS,
    "overlay_position": OVERLAY_POSITIONS,
}

# Numeric values clamped to a sane range.
_RANGES = {
    "beam_size": (1, 10),
    "history_limit": (0, 5000),
    "max_seconds": (5, 1800),
    "unload_after_minutes": (0, 1440),
    "paste_delay_ms": (0, 2000),
    "restore_delay_ms": (100, 5000),
}


@dataclass
class Settings:
    # Shortcut and recording
    hotkey: str = "Ctrl+Space"
    mode: str = "hold"  # hold = push-to-talk, toggle = press/press, both = hold or tap
    microphone: str = ""  # "" = the Windows default input device
    sounds: bool = True
    max_seconds: int = 300

    # Recognition
    model: str = "large-v3-turbo"
    language: str = "el_en"
    device: str = "auto"
    beam_size: int = 5
    custom_words: list[str] = field(default_factory=list)  # prompt words and correction terms
    medical_vocabulary: bool = True  # built-in pharmacy terms (lalia/data/medical_el.txt)
    second_pass: str = "auto"  # re-read with the sound-alike terms in the prompt
    unload_after_minutes: int = 0  # 0 = keep the model loaded

    # Text
    replacements: list[str] = field(default_factory=list)  # "from => to", one per entry
    spoken_punctuation: bool = False
    trailing_space: bool = True

    # Output
    target: str = "under_mouse"
    paste_method: str = "ctrl_v"
    restore_clipboard: bool = True
    auto_enter: bool = False
    paste_delay_ms: int = 60
    restore_delay_ms: int = 600

    # Windows on screen
    overlay_position: str = "bottom"
    mic_button: bool = False
    mic_button_x: int | None = None
    mic_button_y: int | None = None
    mic_button_only_over: str = ""  # comma-separated window-title patterns, "" = always

    # App
    history_limit: int = 100
    start_with_windows: bool = False
    first_run_done: bool = False

    def copy(self) -> "Settings":
        return dataclasses.replace(
            self,
            custom_words=list(self.custom_words),
            replacements=list(self.replacements),
        )


def _coerce(name: str, value, default):
    """The value if it fits the field, else the default."""
    if name in _CHOICES:
        return value if value in _CHOICES[name] else default
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, int) or name in ("mic_button_x", "mic_button_y"):
        if value is None and default is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        value = int(value)
        if name in _RANGES:
            lo, hi = _RANGES[name]
            value = max(lo, min(hi, value))
        return value
    if isinstance(default, list):
        if not isinstance(value, list):
            return default
        return [str(v) for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
    if isinstance(default, str):
        return value if isinstance(value, str) else default
    return default


def from_dict(data: dict) -> Settings:
    base = Settings()
    values = {}
    for f in dataclasses.fields(Settings):
        default = getattr(base, f.name)
        if f.name in data:
            values[f.name] = _coerce(f.name, data[f.name], default)
    return dataclasses.replace(base, **values)


def load(path: Path | None = None) -> Settings:
    path = path or paths.SETTINGS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as e:
        log.warning("settings unreadable (%s), using defaults", e)
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    return from_dict(data)


def save(settings: Settings, path: Path | None = None) -> None:
    path = path or paths.SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dataclasses.asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
