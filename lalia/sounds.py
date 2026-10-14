"""Short start/stop/error tones, generated once into the data folder.

winsound cannot play from memory asynchronously, so the tones are WAV files.
"""
from __future__ import annotations

import io
import logging
import wave
import winsound

import numpy as np

from . import paths

log = logging.getLogger(__name__)

RATE = 22050
VOLUME = 0.18


def _tone(freqs: list[float], each: float = 0.06) -> bytes:
    parts = []
    for f in freqs:
        t = np.arange(int(RATE * each)) / RATE
        env = np.minimum(1.0, np.minimum(t, each - t) / 0.008)  # 8 ms fade in/out, no clicks
        parts.append(np.sin(2 * np.pi * f * t) * env)
    pcm = (np.concatenate(parts) * VOLUME * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm.tobytes())
    return buf.getvalue()


TONES = {
    "start": [660.0, 990.0],
    "stop": [990.0, 660.0],
    "error": [330.0, 247.0],
}


def ensure() -> None:
    paths.SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    for name, freqs in TONES.items():
        f = paths.SOUNDS_DIR / f"{name}.wav"
        if not f.exists():
            f.write_bytes(_tone(freqs))


def play(name: str) -> None:
    f = paths.SOUNDS_DIR / f"{name}.wav"
    try:
        winsound.PlaySound(str(f), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except RuntimeError as e:
        log.debug("sound %s: %s", name, e)
