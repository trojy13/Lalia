"""Transcribe a WAV file the way Lalia does, and print the timings.

    .venv\\Scripts\\python tools\\bench.py samples\\el.wav [--device cpu] [--model small]
"""
from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lalia import textproc  # noqa: E402
from lalia.audio import resample  # noqa: E402
from lalia.transcriber import SAMPLE_RATE, Transcriber  # noqa: E402


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise SystemExit(f"need 16-bit PCM, got {width * 8}-bit")
    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return resample(audio, rate, SAMPLE_RATE)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--language", default="el")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--threads", type=int, default=0, help="CPU threads (0 = Lalia's default)")
    args = ap.parse_args()
    if args.threads:
        import os

        os.environ["LALIA_CPU_THREADS"] = str(args.threads)

    audio = read_wav(args.wav)
    t = Transcriber()
    t0 = time.monotonic()
    t.load(args.model, args.device)
    print(f"load: {time.monotonic() - t0:.1f}s on {t.device_label}")
    for i in range(args.runs):
        r = t.transcribe(audio, language=args.language, beam_size=args.beam, initial_prompt=None)
        print(f"run {i + 1}: {r.seconds_audio:.1f}s audio in {r.seconds_taken:.2f}s")
    text = textproc.finalize(r.text, replacements=[], spoken_punctuation=False, trailing_space=False)
    sys.stdout.buffer.write(("text: " + text + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
