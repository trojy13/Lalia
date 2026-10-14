"""Microphone capture: 16 kHz mono float32, opened only while dictating."""
from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000


def resample(audio: np.ndarray, src_rate: int, dst_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Linear-interpolation resampling; plenty for speech going into Whisper."""
    if src_rate == dst_rate or len(audio) == 0:
        return audio.astype(np.float32, copy=False)
    n_out = int(round(len(audio) * dst_rate / src_rate))
    x_old = np.arange(len(audio), dtype=np.float64) / src_rate
    x_new = np.arange(n_out, dtype=np.float64) / dst_rate
    return np.interp(x_new, x_old, audio).astype(np.float32)


def input_devices() -> list[str]:
    """Input device names on the host API of the default input device
    (MME on a stock Windows), so each microphone is listed once."""
    import sounddevice as sd

    try:
        default_in = sd.default.device[0]
        hostapi = sd.query_devices(default_in)["hostapi"] if default_in is not None and default_in >= 0 else 0
    except Exception:
        hostapi = 0
    names = []
    for dev in sd.query_devices():
        if dev["max_input_channels"] > 0 and dev["hostapi"] == hostapi and dev["name"] not in names:
            names.append(dev["name"])
    return names


def refresh_devices() -> None:
    """PortAudio lists devices once at start-up; re-initialise to see new ones."""
    import sounddevice as sd

    try:
        sd._terminate()
        sd._initialize()
    except Exception as e:  # pragma: no cover
        log.warning("device refresh failed: %s", e)


def _resolve(name: str):
    if not name:
        return None
    import sounddevice as sd

    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and dev["name"] == name:
            return i
    log.warning("microphone %r not found, using the default", name)
    return None


class Recorder:
    def __init__(self):
        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._rate = SAMPLE_RATE
        self._frames = 0
        self.level = 0.0  # RMS of the latest block, read by the overlay

    @property
    def active(self) -> bool:
        return self._stream is not None

    @property
    def seconds(self) -> float:
        return self._frames / self._rate if self._rate else 0.0

    def start(self, device_name: str = "") -> None:
        import sounddevice as sd

        if self._stream is not None:
            return
        self._chunks = []
        self._frames = 0
        self.level = 0.0
        device = _resolve(device_name)
        try:
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                    device=device, callback=self._callback)
            self._rate = SAMPLE_RATE
        except Exception as first:
            # Some drivers refuse 16 kHz; record at the device rate and resample.
            try:
                rate = int(sd.query_devices(device, "input")["default_samplerate"])
                stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                        device=device, callback=self._callback)
                self._rate = rate
            except Exception:
                raise first
        stream.start()
        self._stream = stream

    def _callback(self, indata, frames, time_info, status) -> None:
        mono = indata[:, 0].copy()
        with self._lock:
            self._chunks.append(mono)
            self._frames += frames
        if len(mono):
            self.level = float(np.sqrt(np.mean(mono * mono)))

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:  # pragma: no cover
                log.warning("closing the microphone: %s", e)
        self.level = 0.0

    def stop(self) -> np.ndarray:
        self._close()
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return resample(np.concatenate(chunks), self._rate, SAMPLE_RATE)

    def abort(self) -> None:
        self._close()
        with self._lock:
            self._chunks = []
