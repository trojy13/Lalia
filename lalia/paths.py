"""Where Lalia keeps its files: %LOCALAPPDATA%\\Lalia (settings, history, models, logs)."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Lalia"
APP_TITLE = "Λαλιά"
APP_ID = "Lalia.Dictation"

DATA_DIR = Path(os.environ.get("LALIA_HOME") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME)
SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.jsonl"
MODELS_DIR = DATA_DIR / "models"
LOG_DIR = DATA_DIR / "logs"
SOUNDS_DIR = DATA_DIR / "sounds"
ICON_FILE = DATA_DIR / "lalia.ico"


def ensure_dirs() -> None:
    for d in (DATA_DIR, MODELS_DIR, LOG_DIR, SOUNDS_DIR):
        d.mkdir(parents=True, exist_ok=True)
