"""Speech recognition with faster-whisper (CTranslate2).

NVIDIA GPU: float16 on CUDA, with cuBLAS/cuDNN from the nvidia-* pip wheels.
Anything else: int8 on the CPU. The model loads once and stays loaded.
"""
from __future__ import annotations

import logging
import os
import sysconfig
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import paths

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000

# (name, label, approximate download size in MB)
MODELS = [
    ("large-v3-turbo", "Whisper Large v3 Turbo — συνιστάται", 1620),
    ("large-v3", "Whisper Large v3 — πιο αργό, λίγο πιο ακριβές", 3090),
    ("medium", "Whisper Medium — για αδύναμους υπολογιστές", 1530),
    ("small", "Whisper Small — γρήγορο, λιγότερο ακριβές", 490),
    ("base", "Whisper Base — μόνο για δοκιμές", 150),
]
MODEL_SIZES_MB = {name: mb for name, _label, mb in MODELS}

_cuda_dirs_added = False


def add_cuda_dll_dirs() -> list[str]:
    """Put the bin folders of the nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels on
    the DLL search path. CTranslate2 loads cublas64_12.dll and cudnn64_9.dll by
    name, so both os.add_dll_directory and PATH are set."""
    global _cuda_dirs_added
    found = []
    roots = {Path(sysconfig.get_paths()["purelib"]), Path(sysconfig.get_paths()["platlib"])}
    for root in roots:
        nvidia = root / "nvidia"
        if not nvidia.is_dir():
            continue
        for pkg in sorted(nvidia.iterdir()):
            bin_dir = pkg / "bin"
            if bin_dir.is_dir() and any(bin_dir.glob("*.dll")):
                found.append(str(bin_dir))
    if found and not _cuda_dirs_added:
        for d in found:
            try:
                os.add_dll_directory(d)
            except OSError:
                pass
        os.environ["PATH"] = os.pathsep.join(found + [os.environ.get("PATH", "")])
        _cuda_dirs_added = True
    return found


@dataclass
class Result:
    text: str
    seconds_audio: float
    seconds_taken: float
    language: str


class Transcriber:
    def __init__(self, models_dir: Path | None = None):
        self.models_dir = Path(models_dir or paths.MODELS_DIR)
        self._model = None
        self._key: tuple[str, str] | None = None
        self._lock = threading.Lock()
        self.device_label = ""  # e.g. "GPU (cuda, float16)"
        self.load_seconds = 0.0
        self.last_used = time.monotonic()
        self.last_error = ""

    # -- model files ----------------------------------------------------------
    def is_downloaded(self, name: str) -> bool:
        if Path(name).is_dir():
            return True
        from faster_whisper.utils import download_model

        try:
            download_model(name, cache_dir=str(self.models_dir), local_files_only=True)
            return True
        except Exception:
            return False

    def _model_path(self, name: str) -> str:
        """Local copy first: once downloaded, Lalia never goes online again."""
        if Path(name).is_dir():  # a converted CTranslate2 model folder
            return name
        from faster_whisper.utils import download_model

        try:
            return download_model(name, cache_dir=str(self.models_dir), local_files_only=True)
        except Exception:
            log.info("model %s not on disk, downloading", name)
            return download_model(name, cache_dir=str(self.models_dir))

    def download_size_so_far(self) -> int:
        total = 0
        for f in self.models_dir.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
        return total

    # -- loading -------------------------------------------------------------
    @property
    def loaded(self) -> bool:
        return self._model is not None

    def loaded_key(self) -> tuple[str, str] | None:
        return self._key if self._model is not None else None

    def load(self, name: str, device: str = "auto") -> None:
        """Load (downloading first if needed). Falls back to the CPU when CUDA
        does not work, and checks the device with a short warm-up run, because a
        missing cuDNN only shows when the encoder first runs."""
        with self._lock:
            if self._model is not None and self._key == (name, device):
                return
            self._unload_locked()
            t0 = time.monotonic()
            path = self._model_path(name)

            import ctranslate2
            from faster_whisper import WhisperModel

            candidates = []
            if device in ("auto", "cuda"):
                add_cuda_dll_dirs()
                try:
                    if ctranslate2.get_cuda_device_count() > 0:
                        candidates.append(("cuda", "float16"))
                except Exception as e:  # pragma: no cover - driver specific
                    log.warning("CUDA query failed: %s", e)
            candidates.append(("cpu", "int8"))

            # Half the logical CPUs, at most 8; LALIA_CPU_THREADS overrides (for tuning).
            threads = int(os.environ.get("LALIA_CPU_THREADS") or 0) or max(1, min(8, (os.cpu_count() or 4) // 2))
            errors = []
            for dev, compute in candidates:
                try:
                    model = WhisperModel(path, device=dev, compute_type=compute, cpu_threads=threads)
                    segments, _ = model.transcribe(
                        np.zeros(SAMPLE_RATE, dtype=np.float32), language="en", beam_size=1,
                        vad_filter=False, without_timestamps=True,
                    )
                    list(segments)
                except Exception as e:
                    log.warning("loading %s on %s/%s failed: %s", name, dev, compute, e)
                    errors.append(f"{dev}: {e}")
                    continue
                self._model = model
                self._key = (name, device)
                self.device_label = ("GPU" if dev == "cuda" else "CPU") + f" ({dev}, {compute})"
                self.load_seconds = time.monotonic() - t0
                self.last_used = time.monotonic()
                self.last_error = ""
                if device == "cuda" and dev != "cuda":
                    self.last_error = "Η GPU δεν λειτούργησε, χρησιμοποιείται η CPU."
                log.info("model %s loaded on %s in %.1fs", name, self.device_label, self.load_seconds)
                return
            self.last_error = "; ".join(errors)
            raise RuntimeError(f"Δεν φορτώθηκε το μοντέλο {name}: {self.last_error}")

    def unload(self) -> None:
        with self._lock:
            self._unload_locked()

    def _unload_locked(self) -> None:
        if self._model is not None:
            log.info("unloading model %s", self._key)
        self._model = None
        self._key = None
        self.device_label = ""
        import gc

        gc.collect()

    @property
    def on_gpu(self) -> bool:
        return self.device_label.startswith("GPU")

    def count_tokens(self, text: str) -> int:
        """Prompt length in Whisper tokens (an estimate before the model loads)."""
        model = self._model
        if model is None:
            return len(text) // 2
        return len(model.hf_tokenizer.encode(" " + text, add_special_tokens=False).ids)

    # -- recognition -----------------------------------------------------------
    def transcribe(self, audio: np.ndarray, *, language: str, beam_size: int,
                   initial_prompt: str | None) -> Result:
        with self._lock:
            if self._model is None:
                raise RuntimeError("Το μοντέλο δεν έχει φορτωθεί")
            t0 = time.monotonic()
            segments, info = self._model.transcribe(
                audio,
                language=None if language == "auto" else language,
                task="transcribe",
                beam_size=beam_size,
                # A dictation clip is one thought: conditioning on earlier text only
                # adds a way for one bad segment to spoil the next.
                condition_on_previous_text=False,
                initial_prompt=initial_prompt,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 700, "speech_pad_ms": 300},
                without_timestamps=True,
            )
            parts = []
            for seg in segments:
                # Whisper's own no-speech rule, applied per segment.
                if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
                    continue
                parts.append(seg.text)
            self.last_used = time.monotonic()
            return Result(
                text="".join(parts).strip(),
                seconds_audio=len(audio) / SAMPLE_RATE,
                seconds_taken=time.monotonic() - t0,
                language=getattr(info, "language", language) or language,
            )
